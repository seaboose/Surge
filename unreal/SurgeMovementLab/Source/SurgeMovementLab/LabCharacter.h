#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "SurviveProfile.h"
#include "LabCharacter.generated.h"

UCLASS()
class SURGEMOVEMENTLAB_API ALabCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    ALabCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    // Trusted game policy; telemetry never learns its speed limit from a client.
    static constexpr float PolicySpeed = SurviveProfile::WalkSpeed;
    bool TryAbility(uint8 Ability, const FVector& Destination);
    bool IsRoundActive() const { return bCaptureStarted && !bRoundEnded; }
    bool IsDashing() const { return bDashing; }
    uint64 GetBlinkSerial() const { return BlinkSerial; }
    bool MoveToGoal(const FVector& Goal);
    void StopWalking();
    void SetControlledWalkSpeed(float Speed) { ActualWalkSpeed = Speed; }
    int32 GetHits() const { return Hits; }
    int32 GetRunSeed() const { return RunSeed; }
    bool UsesPracticeCooldowns() const { return bPracticeCooldowns; }
    const TCHAR* GetCaptureStatus() const
    {
        return bCaptureFailed ? TEXT("Capture failed") : bCaptureLimitReached ? TEXT("Capture limit reached") :
            bRoundEnded ? TEXT("Capture saved") : bCaptureStarted ? TEXT("Recording") : TEXT("Preparing round");
    }
    const FString& GetOperatorSessionId() const { return Session; }
    void FinishForRestart() { FinishRound(TEXT("restart")); }
    double GetRoundElapsed() const;
    float GetDashCooldown() const;
    float GetBlinkCooldown() const;
    void RegisterHit();
    void RecordEvent(const FString& Event, const FString& Detail = TEXT(""), const FString& RelatedId = TEXT(""),
        double A = 0, double B = 0, double C = 0, double D = 0,
        const FVector& Source = FVector::ZeroVector, const FVector& Velocity = FVector::ZeroVector,
        const FVector& ThreatLocation = FVector::ZeroVector, double Clearance = 0., bool bClearanceValid = false,
        const FString& BaselineThreat = TEXT("unknown"));
private:
    FString Session;
    FString CapturePath;
    double StartSeconds = 0;
    double MonotonicStartSeconds = 0;
    uint64 ServerTick = 0;
    float LastDeltaSeconds = 0;
    int32 RunSeed = SurviveProfile::DefaultSeed;
    bool bPracticeCooldowns = true;
    double NextSampleSeconds = 0;
    int32 Sequence = 0;
    int64 WrittenBytes = 0;
    bool bCaptureFailed = false;
    bool bCaptureLimitReached = false;
    bool bCaptureStarted = false;
    bool bRoundEnded = false;
    bool bFinishingRound = false;
    bool bDashing = false;
    bool bBlinking = false;
    uint64 BlinkSerial = 0;
    int32 AbilitySequence = 0;
    int32 Hits = 0;
    double NextDashSeconds = 0;
    double NextBlinkSeconds = 0;
    double DashStartSeconds = 0;
    float DashDistance = 0;
    float ActualWalkSpeed = SurviveProfile::WalkSpeed;
    TArray<FVector> WalkPath;
    int32 WalkPathIndex = 0;
    FVector DashStart = FVector::ZeroVector;
    FVector DashDirection = FVector::ZeroVector;
    FString DashActivation;
    UPROPERTY() TObjectPtr<class ASurviveAttackDirector> Director;
    UPROPERTY() TObjectPtr<class ULineBatchComponent> HitRadiusVisual;
    void StartCapture();
    void Sample();
    void FinishRound(const FString& Reason);
    void EndDash();
    void TickWalking(float DeltaSeconds);
};
