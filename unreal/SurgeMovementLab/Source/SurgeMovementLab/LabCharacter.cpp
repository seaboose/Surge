#include "LabCharacter.h"
#include "Engine/World.h"
#include "AIController.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "UObject/ConstructorHelpers.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "SurviveAttackDirector.h"
#include "NavigationSystem.h"
#include "Engine/Engine.h"
#include "SurviveArena.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "SurviveVisuals.h"
#include "SurviveSim.h"
#include "SurvivePaths.h"

ALabCharacter::ALabCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    bReplicates = true;
    SetReplicateMovement(true);
    AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
    AIControllerClass = AAIController::StaticClass();
    GetCharacterMovement()->MaxWalkSpeed = PolicySpeed;
    GetCapsuleComponent()->SetCapsuleRadius(SurviveProfile::PathRadius);
    GetCharacterMovement()->bOrientRotationToMovement = true;
    bUseControllerRotationYaw = false;
    auto* Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BasicBody"));
    Body->SetupAttachment(GetCapsuleComponent());
    Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    if (Sphere.Succeeded()) Body->SetStaticMesh(Sphere.Object);
    Body->SetRelativeScale3D(FVector(SurviveProfile::VisualRadius / 50.f, SurviveProfile::VisualRadius / 50.f, 1.f));
    Body->SetRelativeLocation(FVector(0, 0, -38.f));
    HitRadiusVisual = CreateDefaultSubobject<ULineBatchComponent>(TEXT("HitRadiusVisual"));
    HitRadiusVisual->SetupAttachment(RootComponent);
    HitRadiusVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    HitRadiusVisual->PrimaryComponentTick.bCanEverTick = false;
    auto* Arm = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraArm"));
    Arm->SetupAttachment(RootComponent);
    Arm->TargetArmLength = 1400.f;
    Arm->SetRelativeRotation(FRotator(-65.f, 0.f, 0.f));
    Arm->bDoCollisionTest = false;
    Arm->SetUsingAbsoluteRotation(true);
    auto* Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("TopDownCamera"));
    Camera->SetupAttachment(Arm);
}

void ALabCharacter::BeginPlay()
{
    Super::BeginPlay();
    if (!HasAuthority()) return;
    Session = FGuid::NewGuid().ToString(EGuidFormats::Digits);
    FParse::Value(FCommandLine::Get(), TEXT("SurviveSeed="), RunSeed);
    bPracticeCooldowns = !FParse::Param(FCommandLine::Get(), TEXT("SurviveReferenceCooldowns"));
    GetCharacterMovement()->SetMovementMode(MOVE_Custom);
}

void ALabCharacter::StartCapture()
{
    // BeginPlay may run before asset discovery and engine initialization finish.
    // The first gameplay tick defines the round; startup is not measured play.
    const FString Directory = FPaths::Combine(SurvivePaths::SavedDirectory(), TEXT("Telemetry"));
    if (!IFileManager::Get().MakeDirectory(*Directory, true))
    {
        bCaptureFailed = true;
        UE_LOG(LogTemp, Error, TEXT("Movement telemetry directory unavailable; capture disabled."));
    }
    CapturePath = FPaths::Combine(Directory, Session + TEXT(".jsonl"));
    StartSeconds = GetWorld()->GetTimeSeconds();
    MonotonicStartSeconds = FPlatformTime::Seconds();
    NextSampleSeconds = StartSeconds + 1. / 30.;
    bCaptureStarted = true;
    RecordEvent(TEXT("run_start"), bPracticeCooldowns ? TEXT("practice") : TEXT("reference"), TEXT(""), RunSeed, SurviveProfile::AimedFraction, SurviveProfile::RoundSeconds, 3.);
    Sample();
    Director = GetWorld()->SpawnActor<ASurviveAttackDirector>();
    if (Director) Director->Initialize(this, RunSeed);
}

void ALabCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!HasAuthority() || bRoundEnded) return;
    if (!bCaptureStarted) { StartCapture(); return; }
    ++ServerTick;
    LastDeltaSeconds = DeltaSeconds;
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - StartSeconds >= 60.) { FinishRound(TEXT("completed")); return; }
    if (bDashing)
    {
        const double Travel = SurviveSim::DashDistanceAt(Now - DashStartSeconds, DashDistance, SurviveProfile::DashSpeed);
        FHitResult Hit;
        SetActorLocation(DashStart + DashDirection * Travel, true, &Hit);
        if (Hit.bBlockingHit || Travel >= DashDistance) EndDash();
    }
    else TickWalking(DeltaSeconds);
    HitRadiusVisual->Flush();
    SurviveVisuals::Circle(HitRadiusVisual, GetActorLocation() - FVector(0, 0, 88.f), SurviveProfile::HitRadius, FColor::White, 1.f);
    if (Now >= NextSampleSeconds)
    {
        NextSampleSeconds = StartSeconds + (FMath::FloorToDouble((Now - StartSeconds) * 30.) + 1.) / 30.;
        Sample(); // One sample per tick: no fabricated catch-up samples after a hitch.
    }
}

void ALabCharacter::Sample()
{
    RecordEvent(TEXT("sample"));
}

double ALabCharacter::GetRoundElapsed() const
{
    return GetWorld() && bCaptureStarted ? FMath::Clamp(double(GetWorld()->GetTimeSeconds() - StartSeconds), 0., SurviveProfile::RoundSeconds) : 0.;
}
float ALabCharacter::GetDashCooldown() const
{
    return GetWorld() ? FMath::Max(0., NextDashSeconds - GetWorld()->GetTimeSeconds()) : 0.f;
}
float ALabCharacter::GetBlinkCooldown() const
{
    return GetWorld() ? FMath::Max(0., NextBlinkSeconds - GetWorld()->GetTimeSeconds()) : 0.f;
}
bool ALabCharacter::MoveToGoal(const FVector& Goal)
{
    if (!HasAuthority() || !IsRoundActive() || bDashing) return false;
    TArray<FVector> NewPath;
    if (!ASurviveArena::FindPath(GetActorLocation(), Goal, SurviveProfile::PathRadius, NewPath)) return false;
    WalkPath = MoveTemp(NewPath);
    WalkPathIndex = 0;
    return true;
}
void ALabCharacter::StopWalking()
{
    WalkPath.Reset();
    WalkPathIndex = 0;
    GetCharacterMovement()->StopMovementImmediately();
}
void ALabCharacter::TickWalking(float DeltaSeconds)
{
    const FVector Before = GetActorLocation();
    float Remaining = ActualWalkSpeed * DeltaSeconds;
    while (Remaining > KINDA_SMALL_NUMBER && WalkPath.IsValidIndex(WalkPathIndex))
    {
        const FVector Delta = WalkPath[WalkPathIndex] - GetActorLocation();
        const float Distance = Delta.Size2D();
        if (Distance < .1f) { ++WalkPathIndex; continue; }
        const float Step = FMath::Min(Remaining, Distance);
        FHitResult Hit;
        SetActorLocation(GetActorLocation() + Delta.GetSafeNormal2D() * Step, true, &Hit);
        SetActorRotation(FRotator(0, Delta.Rotation().Yaw, 0));
        Remaining -= Step;
        if (Hit.bBlockingHit) { StopWalking(); break; }
        if (Step >= Distance) ++WalkPathIndex;
    }
    if (!WalkPath.IsValidIndex(WalkPathIndex)) StopWalking();
    GetCharacterMovement()->Velocity = DeltaSeconds > SMALL_NUMBER ? (GetActorLocation() - Before) / DeltaSeconds : FVector::ZeroVector;
}

void ALabCharacter::RecordEvent(const FString& Event, const FString& Detail, const FString& RelatedId,
    double A, double B, double C, double D, const FVector& Source, const FVector& Velocity,
    const FVector& ThreatLocation, double Clearance, bool bClearanceValid, const FString& BaselineThreat)
{
    if (!HasAuthority() || !bCaptureStarted || bCaptureFailed || (bRoundEnded && Event != TEXT("run_end"))) return;
    const FVector P = GetActorLocation();
    const double Elapsed = GetWorld()->GetTimeSeconds() - StartSeconds;
    const double MonotonicElapsed = FPlatformTime::Seconds() - MonotonicStartSeconds;
    // Preserve a visibly failed prefix rather than append invalid JSON numbers
    // or substitute a fabricated position into measured evidence.
    if (P.ContainsNaN() || Source.ContainsNaN() || Velocity.ContainsNaN() || ThreatLocation.ContainsNaN() ||
        !FMath::IsFinite(A) || !FMath::IsFinite(B) || !FMath::IsFinite(C) || !FMath::IsFinite(D) ||
        !FMath::IsFinite(Clearance) || !FMath::IsFinite(Elapsed) || !FMath::IsFinite(MonotonicElapsed) ||
        !FMath::IsFinite(LastDeltaSeconds) || Elapsed < 0. || MonotonicElapsed < 0. || LastDeltaSeconds < 0.f)
    {
        bCaptureFailed = true;
        UE_LOG(LogTemp, Error, TEXT("Non-finite Survive telemetry value; capture stopped without appending the invalid record."));
        return;
    }
    // Reserve one record and 2 KiB for a terminal event instead of silently
    // presenting a limit-truncated stream as a complete round.
    if (Event != TEXT("run_end") && !SurviveSim::CaptureBudget::CanWrite(false, Sequence, WrittenBytes, 0))
    {
        bCaptureLimitReached = true;
        FinishRound(TEXT("capture_limit"));
        return;
    }
    auto Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("schema"), TEXT("survive-v3"));
    Row->SetStringField(TEXT("session_id"), Session);
    Row->SetNumberField(TEXT("seq"), Sequence);
    Row->SetNumberField(TEXT("elapsed_s"), FMath::Min(SurviveProfile::RoundSeconds, Elapsed));
    Row->SetNumberField(TEXT("x_cm"), P.X);
    Row->SetNumberField(TEXT("y_cm"), P.Y);
    Row->SetNumberField(TEXT("z_cm"), P.Z);
    Row->SetStringField(TEXT("event"), Event);
    Row->SetStringField(TEXT("movement_mode"), bDashing ? TEXT("dash") : bBlinking ? TEXT("blink") :
        bRoundEnded ? TEXT("ended") : TEXT("walking"));
    Row->SetStringField(TEXT("related_id"), RelatedId);
    Row->SetStringField(TEXT("detail"), Detail);
    Row->SetNumberField(TEXT("a"), A);
    Row->SetNumberField(TEXT("b"), B);
    Row->SetNumberField(TEXT("c"), C);
    Row->SetNumberField(TEXT("d"), D);
    Row->SetNumberField(TEXT("source_x_cm"), Source.X);
    Row->SetNumberField(TEXT("source_y_cm"), Source.Y);
    Row->SetNumberField(TEXT("velocity_x_cm_s"), Velocity.X);
    Row->SetNumberField(TEXT("velocity_y_cm_s"), Velocity.Y);
    Row->SetNumberField(TEXT("server_tick"), ServerTick);
    Row->SetNumberField(TEXT("delta_s"), LastDeltaSeconds);
    Row->SetNumberField(TEXT("monotonic_s"), MonotonicElapsed);
    Row->SetStringField(TEXT("profile_id"), bPracticeCooldowns ? SurviveProfile::Id : TEXT("survive-lucian-reference-v1"));
    Row->SetNumberField(TEXT("path_radius_cm"), SurviveProfile::PathRadius);
    Row->SetNumberField(TEXT("hit_radius_cm"), SurviveProfile::HitRadius);
    Row->SetNumberField(TEXT("visual_radius_cm"), SurviveProfile::VisualRadius);
    Row->SetNumberField(TEXT("threat_x_cm"), ThreatLocation.X);
    Row->SetNumberField(TEXT("threat_y_cm"), ThreatLocation.Y);
    Row->SetNumberField(TEXT("nearest_clearance_cm"), Clearance);
    Row->SetBoolField(TEXT("clearance_valid"), bClearanceValid);
    Row->SetStringField(TEXT("baseline_threat"), BaselineThreat);
    FString Line;
    auto Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Line);
    if (!FJsonSerializer::Serialize(Row, Writer)) { bCaptureFailed = true; return; }
    Line += TEXT("\n");
    const int64 Bytes = FTCHARToUTF8(*Line).Length();
    if (Event != TEXT("run_end") && !SurviveSim::CaptureBudget::CanWrite(false, Sequence, WrittenBytes, Bytes))
    {
        bCaptureLimitReached = true;
        FinishRound(TEXT("capture_limit"));
        return;
    }
    if (!SurviveSim::CaptureBudget::CanWrite(Event == TEXT("run_end"), Sequence, WrittenBytes, Bytes))
    { bCaptureFailed = true; return; }
    if (!FFileHelper::SaveStringToFile(Line, *CapturePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
        &IFileManager::Get(), FILEWRITE_Append | FILEWRITE_AllowRead))
    {
        bCaptureFailed = true;
        UE_LOG(LogTemp, Error, TEXT("Movement telemetry write failed; capture stopped."));
        return;
    }
    WrittenBytes += Bytes;
    ++Sequence;
}

void ALabCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    if (HasAuthority() && bCaptureStarted && !bRoundEnded) FinishRound(TEXT("disconnect"));
    if (Director) Director->Destroy();
    if (HasAuthority()) UE_LOG(LogTemp, Display, TEXT("Movement capture ended: rows=%d bytes=%lld failed=%d"), Sequence, WrittenBytes, bCaptureFailed);
    Super::EndPlay(Reason);
}

void ALabCharacter::FinishRound(const FString& Reason)
{
    if (!bCaptureStarted || bRoundEnded || bFinishingRound) return;
    bFinishingRound = true;
    if (bDashing) EndDash();
    if (Director) Director->CancelThreats();
    bRoundEnded = true;
    StopWalking();
    if (auto* AI = Cast<AAIController>(GetController())) AI->StopMovement();
    GetCharacterMovement()->StopMovementImmediately();
    // Cancellation/ability terminal events can consume the remaining budget
    // while finishing. Preserve that truncation even if the timer fired first.
    const FString TerminalReason = bCaptureLimitReached ? TEXT("capture_limit") : Reason;
    RecordEvent(TEXT("run_end"), TerminalReason,
        TEXT(""), Hits, Sequence, WrittenBytes, GetWorld()->GetTimeSeconds() - StartSeconds);
    // The HUD already owns round feedback. Debug toasts overlap its controls and
    // can linger into a fresh round, so retain this detail only in the engine log.
    UE_LOG(LogTemp, Display, TEXT("Survive round ended: session=%s reason=%s hits=%d capture_failed=%d"),
        *Session, *TerminalReason, Hits, bCaptureFailed);
}

void ALabCharacter::RegisterHit()
{
    if (!HasAuthority() || bRoundEnded) return;
    ++Hits;
    UE_LOG(LogTemp, Verbose, TEXT("Survive hit: session=%s count=%d"), *Session, Hits);
}

void ALabCharacter::EndDash()
{
    if (!bDashing) return;
    bDashing = false;
    GetCharacterMovement()->SetMovementMode(MOVE_Custom);
    GetCharacterMovement()->StopMovementImmediately();
    RecordEvent(TEXT("ability_end"), TEXT("dash"), DashActivation, SurviveProfile::DashMaxRange,
        DashDistance / SurviveProfile::DashSpeed, bPracticeCooldowns ? SurviveProfile::DashPracticeCooldown : SurviveProfile::DashReferenceCooldown);
}

bool ALabCharacter::TryAbility(uint8 Ability, const FVector& Destination)
{
    if (!HasAuthority() || Ability > 1 || !IsRoundActive()) return false;
    const bool bDash = Ability == 0;
    const FString Kind = bDash ? TEXT("dash") : TEXT("blink");
    const FString Id = FString::Printf(TEXT("ability-%d"), ++AbilitySequence);
    const double Range = bDash ? SurviveProfile::DashMaxRange : SurviveProfile::BlinkRange;
    const double Duration = bDash ? SurviveProfile::DashMaxRange / SurviveProfile::DashSpeed : 0.;
    const double Cooldown = bDash ? (bPracticeCooldowns ? SurviveProfile::DashPracticeCooldown : SurviveProfile::DashReferenceCooldown) :
        (bPracticeCooldowns ? SurviveProfile::BlinkPracticeCooldown : SurviveProfile::BlinkReferenceCooldown);
    RecordEvent(TEXT("ability_request"), Kind, Id, Range, Duration, Cooldown);
    if (bRoundEnded) return false;
    const double Now = GetWorld()->GetTimeSeconds();
    const bool bInvalidDestination = Destination.ContainsNaN() || FMath::Abs(Destination.X) > 5000. ||
        FMath::Abs(Destination.Y) > 5000. || FMath::Abs(Destination.Z) > 2000. || GetActorLocation().ContainsNaN();
    const FString Denial = bDashing ? TEXT("busy") :
        Now < (bDash ? NextDashSeconds : NextBlinkSeconds) ? TEXT("cooldown") :
        bInvalidDestination ? TEXT("invalid_destination") : TEXT("");
    if (!Denial.IsEmpty()) { RecordEvent(TEXT("ability_denied"), Kind + TEXT(":") + Denial, Id); return false; }
    FVector Delta = Destination - GetActorLocation();
    Delta.Z = 0;
    if (Delta.IsNearlyZero()) { RecordEvent(TEXT("ability_denied"), Kind + TEXT(":zero_direction"), Id); return false; }
    const float CursorDistance = float(Delta.Size2D());
    const float Distance = bDash ? float(SurviveSim::ClampDashDistance(CursorDistance, SurviveProfile::DashMinRange, Range)) : FMath::Min(float(Range), CursorDistance);
    if (!FMath::IsFinite(Distance) || Distance <= 0.f)
    { RecordEvent(TEXT("ability_denied"), Kind + TEXT(":invalid_destination"), Id); return false; }
    FVector Landing = GetActorLocation() + Delta.GetSafeNormal2D() * Distance;
    if (!bDash)
    {
        const float HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        if (!ASurviveArena::IsWalkable(Landing, SurviveProfile::PathRadius))
        { RecordEvent(TEXT("ability_denied"), Kind + TEXT(":invalid_landing"), Id); return false; }
        // The chosen landing point cannot silently extend the blink range.
        if (FVector::Dist2D(Landing, GetActorLocation()) > Range + 1.f || FMath::Abs(Landing.Z - GetActorLocation().Z) > 30.f)
        { RecordEvent(TEXT("ability_denied"), Kind + TEXT(":invalid_landing"), Id); return false; }
        FCollisionQueryParams Query(SCENE_QUERY_STAT(SurviveBlink), false, this);
        if (GetWorld()->OverlapBlockingTestByChannel(Landing, FQuat::Identity, ECC_Pawn,
            FCollisionShape::MakeCapsule(GetCapsuleComponent()->GetScaledCapsuleRadius(), HalfHeight), Query))
        { RecordEvent(TEXT("ability_denied"), Kind + TEXT(":blocked_landing"), Id); return false; }
    }
    RecordEvent(TEXT("ability_grant"), Kind, Id, Range, Duration, Cooldown);
    if (bRoundEnded) return false;
    if (auto* AI = Cast<AAIController>(GetController())) AI->StopMovement();
    StopWalking();
    GetCharacterMovement()->StopMovementImmediately();
    if (bDash)
    {
        NextDashSeconds = Now + Cooldown;
        DashActivation = Id;
        DashStartSeconds = Now;
        DashStart = GetActorLocation();
        DashDistance = Distance;
        DashDirection = Delta.GetSafeNormal2D();
        bDashing = true;
        GetCharacterMovement()->SetMovementMode(MOVE_Custom);
        RecordEvent(TEXT("ability_start"), Kind, Id, Range, Duration, Cooldown);
    }
    else
    {
        // A granted activation consumes cooldown even if the engine subsequently
        // rejects the teleport. This avoids a second accepted grant inside it.
        NextBlinkSeconds = Now + Cooldown;
        bBlinking = true;
        RecordEvent(TEXT("ability_start"), Kind, Id, Range, Duration, Cooldown);
        if (!TeleportTo(Landing, GetActorRotation(), false, true))
        {
            RecordEvent(TEXT("ability_denied"), Kind + TEXT(":teleport_failed"), Id);
            bBlinking = false;
            RecordEvent(TEXT("ability_end"), Kind, Id, Range, Duration, Cooldown);
            return false;
        }
        ++BlinkSerial;
        RecordEvent(TEXT("ability_end"), Kind, Id, Range, Duration, Cooldown);
        bBlinking = false;
    }
    return true;
}
