#pragma once
#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "Engine/NetSerialization.h"
#include "LabPlayerController.generated.h"
class ALabCharacter;
UCLASS()
class SURGEMOVEMENTLAB_API ALabPlayerController : public APlayerController
{
    GENERATED_BODY()
public:
    ALabPlayerController();
    virtual void BeginPlay() override;
    virtual void SetupInputComponent() override;
    virtual void PlayerTick(float DeltaTime) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    void AssignUnit(ALabCharacter* InUnit);
    ALabCharacter* GetUnit() const { return Unit; }
    void RunSmokeAction(int32 Action);
    // Owned study driver only. No RPC, OS input injection or policy changes.
    void SetStudyAutomation(bool bEnabled);
    void RunStudyAction(int32 Action);
    void StopSurgeRecording();
    // Local authority console only; no RPC exists for changing the speed cap.
    UFUNCTION(Exec) void LabSetSpeed(float SpeedCmS);
protected:
    UPROPERTY(ReplicatedUsing=OnRep_Unit) TObjectPtr<ALabCharacter> Unit;
    UFUNCTION() void OnRep_Unit();
    UFUNCTION(Server, Reliable) void ServerCommand(FVector_NetQuantize Destination, bool bStop);
    UFUNCTION(Server, Reliable) void ServerAbility(uint8 Ability, FVector_NetQuantize Destination);
    UFUNCTION(Server, Reliable) void ServerRestartRound();
private:
    // Lab input cadence; this is not a claim about League's command rate.
    static constexpr double HeldMoveIntervalSeconds = .1;
    static constexpr double UnchangedGoalRetrySeconds = .5;
    static constexpr float HeldGoalToleranceCm = 5.f;
    double LastCommandSeconds = -1.;
    double LastRestartSeconds = -1.;
    double NextHeldUpdateSeconds = 0.;
    double LastCursorCommandSeconds = -1.;
    bool bMoveHeld = false;
    bool bStudyAutomation = false;
    bool bHasLastCursorGoal = false;
    FVector LastCursorGoal = FVector::ZeroVector;
    FDelegateHandle ApplicationActivationHandle;
    void BindApplicationActivation();
    void HandleApplicationActivationChanged(bool bIsActive);
    void ClickMove();
    void ReleaseMove();
    void SendCursorMove(bool bForce);
    bool HasMovementInputFocus() const;
    void Stop();
    void Dash();
    void Blink();
    void AbilityAtCursor(uint8 Ability);
    void RestartRound();
#if !UE_BUILD_SHIPPING
    // Opt-in local functional probe. Events enter Unreal's InputKey pipeline;
    // these flags track ownership for release-only cleanup, not physical input.
    bool bInputProbeEnabled = false;
    bool bInputProbeRunning = false;
    bool bInputProbeFocusMode = false;
    bool bProbeOwnsRMB = false;
    bool bProbeOwnsStop = false;
    bool bProbeOwnsDash = false;
    int32 InputProbeStage = 0;
    int32 LastProbeObservedState = -1;
    double InputProbeStartSeconds = 0.;
    double NextInputProbeStageSeconds = 0.;
    double NextProbeObservationSeconds = 0.;
    FString InputProbeId;
    FString InputProbeSession;
    void StartInputContractProbe();
    void StartInputFocusProbe();
    void BeginInputProbe(bool bFocusMode);
    void TickInputProbe();
    void ObserveInputProbe();
    void EndInputProbe(const TCHAR* Reason);
    void QueueProbeKey(const FKey& Key, EInputEvent Event, const TCHAR* StageName);
    void LogInputProbeState(const TCHAR* Event) const;
#endif
};
