#include "SurviveThreat.h"
#include "LabCharacter.h"
#include "Components/SceneComponent.h"
#include "Components/CapsuleComponent.h"
#include "SurviveVisuals.h"
#include "Engine/World.h"
#include "Net/UnrealNetwork.h"
#include "SurviveProfile.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"
#include "SurviveSim.h"

ASurviveThreat::ASurviveThreat()
{
    PrimaryActorTick.bCanEverTick = true;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
    bReplicates = true;
    SetReplicateMovement(true);
    SetNetUpdateFrequency(30.f);
    ProjectileVisual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProjectileVisual"));
    CircleVisual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CircleWarningVisual"));
    ProjectileVisual->SetupAttachment(RootComponent);
    CircleVisual->SetupAttachment(RootComponent);
    ProjectileVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    CircleVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    WarningVisual = CreateDefaultSubobject<ULineBatchComponent>(TEXT("WarningVisual"));
    WarningVisual->SetupAttachment(RootComponent);
    WarningVisual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    WarningVisual->PrimaryComponentTick.bCanEverTick = false;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    if (Sphere.Succeeded()) ProjectileVisual->SetStaticMesh(Sphere.Object);
    if (Cylinder.Succeeded()) CircleVisual->SetStaticMesh(Cylinder.Object);
    ApplyStyle();
}
void ASurviveThreat::ApplyStyle()
{
    ProjectileVisual->SetVisibility(!bCircle);
    CircleVisual->SetVisibility(bCircle);
    ProjectileVisual->SetRelativeScale3D(FVector(Radius / 50.f));
    CircleVisual->SetRelativeScale3D(FVector(Radius / 50.f, Radius / 50.f, .02f));
    CircleVisual->SetRelativeLocation(FVector(0, 0, -88.f));
}
void ASurviveThreat::Initialize(ALabCharacter* InUnit, int32 InId, const FVector& Source, const FVector& Target, bool bInCircle, bool bInAimed)
{
    Unit = InUnit;
    ThreatId = InId;
    Goal = Target;
    LaunchSource = bInCircle ? Target : Source;
    bCircle = bInCircle;
    bAimed = bInAimed;
    Radius = bCircle ? SurviveProfile::CircleRadius : SurviveProfile::ProjectileRadius;
    WarningSeconds = bCircle ? SurviveProfile::CircleWarning : SurviveProfile::ProjectileWarning;
    Speed = SurviveProfile::ProjectileSpeed;
    ApplyStyle();
    Direction = (Target - Source).GetSafeNormal2D();
    if (Direction.IsNearlyZero()) Direction = FVector(1, 0, 0);
    CreatedSeconds = GetWorld()->GetTimeSeconds();
    PreviousUnitLocation = Unit->GetActorLocation();
    LastBlinkSerial = Unit->GetBlinkSerial();
    AddTickPrerequisiteActor(Unit);
    const float CombinedRadius = Radius + SurviveProfile::HitRadius;
    if (bCircle) BaselineThreat = FVector::DistSquared2D(Goal, PreviousUnitLocation) <= FMath::Square(CombinedRadius) ? TEXT("yes") : TEXT("no");
    else
    {
        FHitResult Block;
        FCollisionQueryParams Query(SCENE_QUERY_STAT(SurviveBaseline), false, this);
        Query.AddIgnoredActor(Unit);
        const FVector End = Source + Direction * SurviveProfile::ProjectileRange;
        const bool bBlocked = SurviveProfile::ProjectileBlockedByTerrain &&
            GetWorld()->SweepSingleByChannel(Block, Source, End, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(Radius), Query);
        const FVector Closest = FMath::ClosestPointOnSegment(PreviousUnitLocation, Source, bBlocked ? Block.Location : End);
        BaselineThreat = FVector::DistSquared2D(Closest, PreviousUnitLocation) <= FMath::Square(CombinedRadius) ? TEXT("yes") : TEXT("no");
    }
    Record(TEXT("threat_warning"));
}
void ASurviveThreat::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(ASurviveThreat, bCircle);
    DOREPLIFETIME(ASurviveThreat, bAimed);
    DOREPLIFETIME(ASurviveThreat, bFired);
    DOREPLIFETIME(ASurviveThreat, Goal);
    DOREPLIFETIME(ASurviveThreat, Radius);
}
void ASurviveThreat::Record(const FString& Event)
{
    if (Unit) Unit->RecordEvent(Event, FString::Printf(TEXT("%s_%s"), bCircle ? TEXT("circle") : TEXT("projectile"),
        bAimed ? TEXT("aimed") : TEXT("random")), FString::FromInt(ThreatId), Goal.X, Goal.Y, Radius, bCircle ? WarningSeconds : Speed,
        LaunchSource, bCircle ? FVector::ZeroVector : Direction * Speed, GetActorLocation(), NearestClearance, bClearanceValid, BaselineThreat);
}
void ASurviveThreat::Cancel() { Record(TEXT("threat_cancelled")); Destroy(); }
void ASurviveThreat::Hit()
{
    Record(TEXT("threat_hit"));
    if (Unit) Unit->RegisterHit();
    Destroy();
}
void ASurviveThreat::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    const FColor Color = bAimed ? FColor::Orange : FColor::Cyan;
    WarningVisual->Flush();
    if (bCircle) SurviveVisuals::Circle(WarningVisual, GetActorLocation() - FVector(0, 0, 70), Radius, Color, 3.f);
    else
    {
        WarningVisual->DrawSphere(GetActorLocation(), Radius, 12, Color, 0.f, SDPG_World, 2.f);
        if (!bFired) WarningVisual->DrawLine(GetActorLocation(), Goal, Color, SDPG_World, 1.f);
    }
    if (!HasAuthority()) return;
    if (!Unit || !Unit->IsRoundActive()) { Destroy(); return; }
    const double Age = GetWorld()->GetTimeSeconds() - CreatedSeconds;
    if (Age < WarningSeconds)
    {
        PreviousUnitLocation = Unit->GetActorLocation();
        LastBlinkSerial = Unit->GetBlinkSerial();
        return;
    }
    if (!bFired)
    {
        bFired = true;
        Record(TEXT("threat_fire"));
        if (!bCircle)
        {
            PreviousUnitLocation = Unit->GetActorLocation();
            LastBlinkSerial = Unit->GetBlinkSerial();
            return;
        }
    }
    const FVector CurrentUnit = Unit->GetActorLocation();
    const float CombinedRadius = Radius + SurviveProfile::HitRadius;
    if (bCircle)
    {
        NearestClearance = FVector::Dist2D(CurrentUnit, GetActorLocation()) - CombinedRadius;
        bClearanceValid = true;
        if (FVector::DistSquared2D(CurrentUnit, GetActorLocation()) <= FMath::Square(CombinedRadius)) Hit();
        else { Record(TEXT("threat_expired")); Destroy(); }
        return;
    }
    const FVector Before = GetActorLocation();
    const float Step = FMath::Min(Speed * DeltaSeconds, SurviveProfile::ProjectileRange - DistanceTraveled);
    const FVector After = Before + Direction * Step;
    FHitResult WorldHit;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(SurviveProjectile), false, this);
    Query.AddIgnoredActor(Unit);
    const bool bBlocked = SurviveProfile::ProjectileBlockedByTerrain &&
        GetWorld()->SweepSingleByChannel(WorldHit, Before, After, FQuat::Identity,
            ECC_Visibility, FCollisionShape::MakeSphere(Radius), Query);
    const FVector SegmentEnd = bBlocked ? WorldHit.Location : After;
    // Relative swept segment catches crossing motion between simulation samples.
    // A blink is discontinuous: never create a vulnerable swept path through it.
    const FVector UnitBefore = LastBlinkSerial != Unit->GetBlinkSerial() ? CurrentUnit : PreviousUnitLocation;
    LastBlinkSerial = Unit->GetBlinkSerial();
    const float StepFraction = Speed * DeltaSeconds > SMALL_NUMBER ? Step / (Speed * DeltaSeconds) : 0.f;
    const FVector UnitEnd = FMath::Lerp(UnitBefore, CurrentUnit, StepFraction * (bBlocked ? WorldHit.Time : 1.f));
    const double Clearance = SurviveSim::RelativeClearance({Before.X, Before.Y}, {SegmentEnd.X, SegmentEnd.Y},
        {UnitBefore.X, UnitBefore.Y}, {UnitEnd.X, UnitEnd.Y}, CombinedRadius);
    if (!std::isfinite(Clearance))
    {
        bClearanceValid = false;
        BaselineThreat = TEXT("unknown");
        UE_LOG(LogTemp, Error, TEXT("Invalid Survive collision geometry; threat cancelled without a hit verdict."));
        Cancel();
        return;
    }
    NearestClearance = bClearanceValid ? FMath::Min(NearestClearance, Clearance) : Clearance;
    bClearanceValid = true;
    DistanceTraveled += FVector::Dist2D(Before, SegmentEnd);
    SetActorLocation(SegmentEnd);
    if (Clearance <= 0.) { Hit(); return; }
    PreviousUnitLocation = CurrentUnit;
    if (bBlocked) { Record(TEXT("threat_blocked")); Destroy(); }
    else if (DistanceTraveled >= SurviveProfile::ProjectileRange - .01f) { Record(TEXT("threat_expired")); Destroy(); }
}
