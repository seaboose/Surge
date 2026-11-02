#include "LabPlayerController.h"
#include "LabCharacter.h"
#include "AIController.h"
#include "NavigationSystem.h"
#include "Net/UnrealNetwork.h"
#include "Components/InputComponent.h"
#include "InputCoreTypes.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Navigation/PathFollowingComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Slate/SceneViewport.h"
#include "HAL/PlatformTime.h"
#include "LabGameMode.h"
#include "Framework/Application/SlateApplication.h"
#if !UE_BUILD_SHIPPING
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "InputKeyEventArgs.h"
#include "GenericPlatform/GenericPlatformInputDeviceMapper.h"
#endif

void ALabPlayerController::LabSetSpeed(float SpeedCmS)
{
#if !UE_BUILD_SHIPPING
    if (HasAuthority() && IsLocalController() && Unit &&
        (SpeedCmS == ALabCharacter::PolicySpeed || SpeedCmS == 1200.f))
    {
        Unit->GetCharacterMovement()->MaxWalkSpeed = SpeedCmS;
        Unit->SetControlledWalkSpeed(SpeedCmS);
        UE_LOG(LogTemp, Display, TEXT("Local development movement cap changed to %.0f cm/s"), SpeedCmS);
    }
#endif
}

ALabPlayerController::ALabPlayerController()
{
    bShowMouseCursor = true;
    bEnableClickEvents = true; // HUD recording control; left-click never moves the character.
    bAutoManageActiveCameraTarget = false;
}
void ALabPlayerController::BeginPlay()
{
    Super::BeginPlay();
    BindApplicationActivation();
}
void ALabPlayerController::BindApplicationActivation()
{
    if (!IsLocalController() || ApplicationActivationHandle.IsValid() || !FSlateApplication::IsInitialized()) return;
    ApplicationActivationHandle = FSlateApplication::Get().OnApplicationActivationStateChanged().AddUObject(
        this, &ALabPlayerController::HandleApplicationActivationChanged);
    if (!FSlateApplication::Get().IsActive()) ReleaseMove();
}
void ALabPlayerController::HandleApplicationActivationChanged(bool bIsActive)
{
    if (!IsLocalController()) return;
#if !UE_BUILD_SHIPPING
    const bool bWasMoveHeld = bMoveHeld;
#endif
    // A viewport may retain its internal keyboard focus while the desktop app
    // is inactive. Clear the latch at the event, even if background ticks pause.
    // Activation deliberately does not restore a held movement command.
    if (!bIsActive) ReleaseMove();
#if !UE_BUILD_SHIPPING
    if (bInputProbeRunning)
    {
        const UGameViewportClient* ViewportClient = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
        UE_LOG(LogTemp, Display, TEXT("Survive input probe activation: id=%s session=%s mode=%s elapsed=%.6f active_event=%d slate_active=%d viewport_focus=%d move_held_before=%d move_held_after=%d rmb_down=%d"),
            *InputProbeId, *InputProbeSession, bInputProbeFocusMode ? TEXT("focus") : TEXT("contract"),
            FPlatformTime::Seconds() - InputProbeStartSeconds, bIsActive,
            FSlateApplication::IsInitialized() && FSlateApplication::Get().IsActive(),
            ViewportClient && ViewportClient->Viewport && ViewportClient->Viewport->HasFocus(),
            bWasMoveHeld, bMoveHeld, IsInputKeyDown(EKeys::RightMouseButton));
        LogInputProbeState(TEXT("application_activation_callback"));
        if (!bIsActive && !bInputProbeFocusMode) EndInputProbe(TEXT("contract_application_deactivated"));
    }
#endif
}
void ALabPlayerController::SetupInputComponent()
{
    Super::SetupInputComponent();
    BindApplicationActivation();
    InputComponent->BindKey(EKeys::RightMouseButton, IE_Pressed, this, &ALabPlayerController::ClickMove);
    InputComponent->BindKey(EKeys::RightMouseButton, IE_Released, this, &ALabPlayerController::ReleaseMove);
    InputComponent->BindKey(EKeys::S, IE_Pressed, this, &ALabPlayerController::Stop);
    InputComponent->BindKey(EKeys::Q, IE_Pressed, this, &ALabPlayerController::Dash);
    InputComponent->BindKey(EKeys::E, IE_Pressed, this, &ALabPlayerController::Blink);
    InputComponent->BindKey(EKeys::R, IE_Pressed, this, &ALabPlayerController::RestartRound);
    InputComponent->BindKey(EKeys::F10, IE_Pressed, this, &ALabPlayerController::StopSurgeRecording);
#if !UE_BUILD_SHIPPING
    bInputProbeEnabled = FParse::Param(FCommandLine::Get(), TEXT("SurviveInputProbe"));
    if (bInputProbeEnabled)
    {
        InputComponent->BindKey(EKeys::F8, IE_Pressed, this, &ALabPlayerController::StartInputContractProbe);
        InputComponent->BindKey(EKeys::F9, IE_Pressed, this, &ALabPlayerController::StartInputFocusProbe);
    }
#endif
}
void ALabPlayerController::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME_CONDITION(ALabPlayerController, Unit, COND_OwnerOnly);
}
void ALabPlayerController::AssignUnit(ALabCharacter* InUnit)
{
    if (!HasAuthority()) return;
#if !UE_BUILD_SHIPPING
    if (bInputProbeRunning && Unit != InUnit) EndInputProbe(TEXT("unit_reassigned"));
#endif
    Unit = InUnit;
    OnRep_Unit();
}
void ALabPlayerController::OnRep_Unit()
{
    if (Unit && IsLocalController()) SetViewTarget(Unit);
}
void ALabPlayerController::ClickMove()
{
    if (!HasMovementInputFocus()) return;
    bMoveHeld = true;
    bHasLastCursorGoal = false;
    SendCursorMove(true);
    NextHeldUpdateSeconds = FPlatformTime::Seconds() + HeldMoveIntervalSeconds;
}
void ALabPlayerController::ReleaseMove()
{
    bMoveHeld = false;
    bHasLastCursorGoal = false;
}
bool ALabPlayerController::HasMovementInputFocus() const
{
    const UGameViewportClient* ViewportClient = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
    return !bStudyAutomation && IsLocalController() && FSlateApplication::IsInitialized() && FSlateApplication::Get().IsActive() &&
        ViewportClient && ViewportClient->Viewport && ViewportClient->Viewport->HasFocus();
}
void ALabPlayerController::PlayerTick(float DeltaTime)
{
    Super::PlayerTick(DeltaTime);
#if !UE_BUILD_SHIPPING
    TickInputProbe();
#endif
    // Losing focus/releasing the physical key cancels the latch. Regaining focus
    // or keeping RMB down after S/Q/E cannot restart updates without a new press.
    if (bMoveHeld)
    {
        if (!HasMovementInputFocus() || !IsInputKeyDown(EKeys::RightMouseButton)) ReleaseMove();
        else
        {
            const double Now = FPlatformTime::Seconds();
            if (Now >= NextHeldUpdateSeconds)
            {
                NextHeldUpdateSeconds = Now + HeldMoveIntervalSeconds;
                SendCursorMove(false); // No catch-up commands after a stalled frame.
            }
        }
    }
#if !UE_BUILD_SHIPPING
    ObserveInputProbe();
#endif
}
void ALabPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (ApplicationActivationHandle.IsValid())
    {
        if (FSlateApplication::IsInitialized())
            FSlateApplication::Get().OnApplicationActivationStateChanged().Remove(ApplicationActivationHandle);
        ApplicationActivationHandle.Reset();
    }
#if !UE_BUILD_SHIPPING
    EndInputProbe(TEXT("controller_end_play"));
#endif
    Super::EndPlay(EndPlayReason);
}
void ALabPlayerController::SendCursorMove(bool bForce)
{
    FHitResult Hit;
    if (GetHitResultUnderCursor(ECC_Visibility, false, Hit) && Hit.bBlockingHit)
    {
        const double Now = FPlatformTime::Seconds();
        const bool bSameGoal = bHasLastCursorGoal && FVector::DistSquared(Hit.ImpactPoint, LastCursorGoal) <= FMath::Square(HeldGoalToleranceCm);
        // Occasional unchanged-goal retry permits recovery from a throttled or
        // initially unreachable press without issuing a new path every tick.
        if (!bForce && bSameGoal && Now - LastCursorCommandSeconds < UnchangedGoalRetrySeconds) return;
        ServerCommand(Hit.ImpactPoint, false);
        LastCursorGoal = Hit.ImpactPoint;
        bHasLastCursorGoal = true;
        LastCursorCommandSeconds = Now;
    }
}
void ALabPlayerController::Stop()
{
    if (bStudyAutomation) return;
    ReleaseMove();
    ServerCommand(FVector::ZeroVector, true);
}
void ALabPlayerController::StopSurgeRecording()
{
    // Recording control is separate from movement and remains available during
    // scripted study windows. It cannot stop gameplay or another game process.
    if (!IsLocalController() || !HasAuthority()) return;
    if (auto* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<ALabGameMode>() : nullptr) Mode->StopRecorder();
}
void ALabPlayerController::Dash() { AbilityAtCursor(0); }
void ALabPlayerController::Blink() { AbilityAtCursor(1); }
void ALabPlayerController::RestartRound()
{
#if !UE_BUILD_SHIPPING
    EndInputProbe(TEXT("round_restart"));
#endif
    ReleaseMove();
    ServerRestartRound();
}
void ALabPlayerController::ServerRestartRound_Implementation()
{
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - LastRestartSeconds < 1.) return;
    LastRestartSeconds = Now;
    if (auto* Mode = GetWorld()->GetAuthGameMode<ALabGameMode>()) Mode->RestartSurviveRound(this);
}
void ALabPlayerController::RunSmokeAction(int32 Action)
{
    if (!HasAuthority() || !Unit) return;
    // Opt-in headless smoke driver uses the real command/ability handlers.
    // Its invocation and synthetic provenance belong in the external run log.
    switch (Action)
    {
    case 0: ServerCommand(FVector(-900, 500, 90), false); break;
    case 1: ServerCommand(FVector(900, -500, 90), false); break;
    case 2: ServerAbility(0, FVector(900, 700, 90)); break;
    case 3: ServerAbility(1, FVector(-700, 700, 90)); break;
    case 4: ServerCommand(FVector::ZeroVector, true); break;
    case 5: ServerCommand(FVector(0, 1050, 90), false); break;
    default: break;
    }
}
void ALabPlayerController::SetStudyAutomation(bool bEnabled)
{
    if (!HasAuthority() || !IsLocalController() || bStudyAutomation == bEnabled) return;
    bStudyAutomation = bEnabled;
    ReleaseMove();
    // Clear a previous destination at both ownership boundaries. A dash already
    // in progress is governed by its ordinary game rule and may finish normally.
    ServerCommand(FVector::ZeroVector, true);
}
void ALabPlayerController::RunStudyAction(int32 Action)
{
    if (!bStudyAutomation || !HasAuthority() || !IsLocalController()) return;
    ReleaseMove();
    RunSmokeAction(Action);
}
void ALabPlayerController::AbilityAtCursor(uint8 Ability)
{
    if (bStudyAutomation) return;
    ReleaseMove();
    FHitResult Hit;
    if (GetHitResultUnderCursor(ECC_Visibility, false, Hit) && Hit.bBlockingHit)
        ServerAbility(Ability, Hit.ImpactPoint);
}
void ALabPlayerController::ServerAbility_Implementation(uint8 Ability, FVector_NetQuantize Destination)
{
    if (Unit && Unit->HasAuthority()) Unit->TryAbility(Ability, FVector(Destination));
}
void ALabPlayerController::ServerCommand_Implementation(FVector_NetQuantize Destination, bool bStop)
{
    if (!Unit || !Unit->HasAuthority() || !Unit->IsRoundActive()) return;
    auto* AI = Cast<AAIController>(Unit->GetController());
    if (!AI) return;
    const FVector Goal(Destination);
    const bool bInvalidGoal = !bStop && (Goal.ContainsNaN() || FMath::Abs(Goal.X) > 5000.f ||
        FMath::Abs(Goal.Y) > 5000.f || FMath::Abs(Goal.Z) > 2000.f);
    // A rejected non-finite request must not poison the entire JSONL capture.
    // Stop ignores the destination. Denials preserve why no move was granted.
    Unit->RecordEvent(TEXT("command_request"), bStop ? TEXT("stop") : TEXT("move"), TEXT(""),
        bStop || bInvalidGoal ? 0. : Goal.X, bStop || bInvalidGoal ? 0. : Goal.Y);
    if (bInvalidGoal) { Unit->RecordEvent(TEXT("command_denied"), TEXT("invalid_destination")); return; }
    if (Unit->IsDashing()) { Unit->RecordEvent(TEXT("command_denied"), TEXT("dash_in_progress")); return; }
    // Stops remain available even when movement requests are throttled.
    if (bStop)
    {
        AI->StopMovement();
        Unit->StopWalking();
        Unit->RecordEvent(TEXT("command_stop"), TEXT("stop"));
        return;
    }
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - LastCommandSeconds < .05) { Unit->RecordEvent(TEXT("command_denied"), TEXT("throttled")); return; }
    LastCommandSeconds = Now;
    const bool bAccepted = Unit->MoveToGoal(Goal);
    Unit->RecordEvent(bAccepted ? TEXT("command_grant") : TEXT("command_denied"),
        bAccepted ? TEXT("move") : TEXT("unreachable"), TEXT(""), Goal.X, Goal.Y);
}

#if !UE_BUILD_SHIPPING
void ALabPlayerController::StartInputContractProbe() { BeginInputProbe(false); }
void ALabPlayerController::StartInputFocusProbe() { BeginInputProbe(true); }

void ALabPlayerController::BeginInputProbe(bool bFocusMode)
{
    if (!bInputProbeEnabled || !HasAuthority() || !IsLocalController()) return;
    if (bInputProbeRunning) { EndInputProbe(TEXT("operator_cancel")); return; }
    // A probe owns only events it introduces. Never release a pre-existing
    // mouse/stop/dash press as a side effect of trying to start one.
    if (!IsValid(Unit) || !Unit->HasAuthority() || !Unit->IsRoundActive() || !PlayerInput ||
        !HasMovementInputFocus() || IsInputKeyDown(EKeys::RightMouseButton) ||
        IsInputKeyDown(EKeys::S) || IsInputKeyDown(EKeys::Q))
    {
        UE_LOG(LogTemp, Display, TEXT("Survive input probe not started: local active unit, viewport focus, and released RMB/S/Q are required."));
        return;
    }
    bInputProbeRunning = true;
    bInputProbeFocusMode = bFocusMode;
    bProbeOwnsRMB = bProbeOwnsStop = bProbeOwnsDash = false;
    InputProbeStage = 0;
    LastProbeObservedState = -1;
    InputProbeStartSeconds = FPlatformTime::Seconds();
    NextInputProbeStageSeconds = InputProbeStartSeconds;
    NextProbeObservationSeconds = InputProbeStartSeconds;
    InputProbeId = FGuid::NewGuid().ToString(EGuidFormats::Digits);
    InputProbeSession = Unit->GetOperatorSessionId();
    LogInputProbeState(TEXT("begin_engine_simulated_input"));
}

void ALabPlayerController::QueueProbeKey(const FKey& Key, EInputEvent Event, const TCHAR* StageName)
{
    if (!bInputProbeEnabled || !bInputProbeRunning || !HasAuthority() || !IsLocalController() || !PlayerInput) return;
    if (Event != IE_Pressed && Event != IE_Released) return;
    if (Key != EKeys::RightMouseButton && Key != EKeys::S && Key != EKeys::Q) return;
    if (Event == IE_Pressed && (!IsValid(Unit) || !Unit->HasAuthority() || !Unit->IsRoundActive() || !HasMovementInputFocus())) return;
    const bool bPressed = Event == IE_Pressed;
    if (Key == EKeys::RightMouseButton) bProbeOwnsRMB = bPressed;
    else if (Key == EKeys::S) bProbeOwnsStop = bPressed;
    else bProbeOwnsDash = bPressed;
    UGameViewportClient* ViewportClient = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
    const FInputKeyEventArgs Args = FInputKeyEventArgs::CreateSimulated(Key, Event, bPressed ? 1.f : 0.f,
        -1, IPlatformInputDeviceMapper::Get().GetDefaultInputDevice(), false, ViewportClient ? ViewportClient->Viewport : nullptr);
    // This queues UPlayerInput events; the normal Super::PlayerTick dispatches
    // InputComponent bindings on a later frame. No gameplay handler is called.
    const bool bHandled = APlayerController::InputKey(Args);
    UE_LOG(LogTemp, Display, TEXT("Survive input probe event: id=%s session=%s stage=%d key=%s edge=%s engine_handled=%d"),
        *InputProbeId, *InputProbeSession, InputProbeStage, *Key.ToString(), bPressed ? TEXT("pressed") : TEXT("released"), bHandled);
    LogInputProbeState(StageName);
}

void ALabPlayerController::TickInputProbe()
{
    if (!bInputProbeRunning) return;
    if (!bInputProbeEnabled || !HasAuthority() || !IsLocalController() || !PlayerInput ||
        !IsValid(Unit) || !Unit->HasAuthority() || !Unit->IsRoundActive() || Unit->GetOperatorSessionId() != InputProbeSession)
    { EndInputProbe(TEXT("unit_or_controller_inactive")); return; }
    const double Now = FPlatformTime::Seconds();
    const double Elapsed = Now - InputProbeStartSeconds;
    if (!FMath::IsFinite(Elapsed) || Elapsed < 0.) { EndInputProbe(TEXT("invalid_clock")); return; }
    if (bInputProbeFocusMode)
    {
        if (InputProbeStage == 0)
        {
            if (!HasMovementInputFocus()) { EndInputProbe(TEXT("focus_lost_before_press")); return; }
            QueueProbeKey(EKeys::RightMouseButton, IE_Pressed, TEXT("focus_rmb_press"));
            InputProbeStage = 1;
        }
        else if (InputProbeStage == 1 && Elapsed >= 20.)
        {
            // Focus changes may already have flushed Unreal's key state. Do
            // not synthesize a replacement press or bypass that natural flush.
            QueueProbeKey(EKeys::RightMouseButton, IE_Released, TEXT("focus_rmb_release"));
            InputProbeStage = 2;
            NextInputProbeStageSeconds = Now + .1;
        }
        else if (InputProbeStage == 2 && Now >= NextInputProbeStageSeconds)
            EndInputProbe(TEXT("focus_observation_finished"));
        return;
    }
    if (!HasMovementInputFocus()) { EndInputProbe(TEXT("contract_focus_lost")); return; }
    if (Elapsed >= 8.) { EndInputProbe(TEXT("contract_deadline")); return; }
    if (Now < NextInputProbeStageSeconds) return;
    // Space stages from their actual queue time. A hitch cannot compress the
    // requested holds or produce a burst of fabricated catch-up input.
    switch (InputProbeStage)
    {
    case 0: QueueProbeKey(EKeys::RightMouseButton, IE_Pressed, TEXT("initial_rmb_press")); break;
    case 1: QueueProbeKey(EKeys::S, IE_Pressed, TEXT("stop_press_while_rmb_down")); break;
    case 2: QueueProbeKey(EKeys::S, IE_Released, TEXT("stop_release_keep_rmb_down")); break;
    case 3: QueueProbeKey(EKeys::RightMouseButton, IE_Released, TEXT("rmb_release_before_new_press")); break;
    case 4: QueueProbeKey(EKeys::RightMouseButton, IE_Pressed, TEXT("fresh_rmb_press")); break;
    case 5: QueueProbeKey(EKeys::Q, IE_Pressed, TEXT("dash_press_while_rmb_down")); break;
    case 6: QueueProbeKey(EKeys::Q, IE_Released, TEXT("dash_release_keep_rmb_down")); break;
    case 7: QueueProbeKey(EKeys::RightMouseButton, IE_Released, TEXT("final_rmb_release")); break;
    default: EndInputProbe(TEXT("contract_sequence_finished")); return;
    }
    ++InputProbeStage;
    static constexpr double WaitBeforeNext[] = {1.1, .1, 1.1, .15, 1.1, .1, 1.1, .2};
    NextInputProbeStageSeconds = Now + WaitBeforeNext[InputProbeStage - 1];
}

void ALabPlayerController::ObserveInputProbe()
{
    if (!bInputProbeRunning) return;
    const double Now = FPlatformTime::Seconds();
    const int32 ObservedState = (HasMovementInputFocus() ? 1 : 0) | (bMoveHeld ? 2 : 0) |
        (IsInputKeyDown(EKeys::RightMouseButton) ? 4 : 0) | (IsInputKeyDown(EKeys::S) ? 8 : 0) |
        (IsInputKeyDown(EKeys::Q) ? 16 : 0);
    if (ObservedState != LastProbeObservedState || Now >= NextProbeObservationSeconds)
    {
        LogInputProbeState(ObservedState != LastProbeObservedState ? TEXT("observed_transition") : TEXT("observed_interval"));
        LastProbeObservedState = ObservedState;
        NextProbeObservationSeconds = Now + .25;
    }
}

void ALabPlayerController::LogInputProbeState(const TCHAR* Event) const
{
    const UGameViewportClient* ViewportClient = GetWorld() ? GetWorld()->GetGameViewport() : nullptr;
    UE_LOG(LogTemp, Display, TEXT("Survive input probe state: id=%s session=%s mode=%s elapsed=%.6f stage=%d event=%s focus=%d move_held=%d rmb_down=%d s_down=%d q_down=%d queued_rmb=%d queued_s=%d queued_q=%d slate_active=%d viewport_focus=%d"),
        *InputProbeId, *InputProbeSession, bInputProbeFocusMode ? TEXT("focus") : TEXT("contract"),
        FPlatformTime::Seconds() - InputProbeStartSeconds, InputProbeStage, Event, HasMovementInputFocus(), bMoveHeld,
        IsInputKeyDown(EKeys::RightMouseButton), IsInputKeyDown(EKeys::S), IsInputKeyDown(EKeys::Q),
        bProbeOwnsRMB, bProbeOwnsStop, bProbeOwnsDash,
        FSlateApplication::IsInitialized() && FSlateApplication::Get().IsActive(),
        ViewportClient && ViewportClient->Viewport && ViewportClient->Viewport->HasFocus());
}

void ALabPlayerController::EndInputProbe(const TCHAR* Reason)
{
    if (!bInputProbeRunning) return;
    // Release only keys introduced by this probe through the same engine input
    // pipeline. Releases remain allowed during focus loss/round shutdown.
    if (bProbeOwnsStop) QueueProbeKey(EKeys::S, IE_Released, TEXT("cleanup_stop_release"));
    if (bProbeOwnsDash) QueueProbeKey(EKeys::Q, IE_Released, TEXT("cleanup_dash_release"));
    if (bProbeOwnsRMB) QueueProbeKey(EKeys::RightMouseButton, IE_Released, TEXT("cleanup_rmb_release"));
    LogInputProbeState(Reason);
    bInputProbeRunning = false;
    bProbeOwnsRMB = bProbeOwnsStop = bProbeOwnsDash = false;
}
#endif
