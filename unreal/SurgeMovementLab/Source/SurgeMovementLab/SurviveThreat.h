#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SurviveThreat.generated.h"
class ALabCharacter;

UCLASS()
class SURGEMOVEMENTLAB_API ASurviveThreat : public AActor
{
    GENERATED_BODY()
public:
    ASurviveThreat();
    void Initialize(ALabCharacter* InUnit, int32 InId, const FVector& Source, const FVector& Target, bool bInCircle, bool bInAimed);
    virtual void Tick(float DeltaSeconds) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    void Cancel();
protected:
    UPROPERTY(ReplicatedUsing=ApplyStyle) bool bCircle = false;
    UPROPERTY(Replicated) bool bAimed = false;
    UPROPERTY(Replicated) bool bFired = false;
    UPROPERTY(Replicated) FVector Goal = FVector::ZeroVector;
    UPROPERTY(ReplicatedUsing=ApplyStyle) float Radius = 24.f;
    UFUNCTION() void ApplyStyle();
private:
    UPROPERTY() TObjectPtr<class UStaticMeshComponent> ProjectileVisual;
    UPROPERTY() TObjectPtr<class UStaticMeshComponent> CircleVisual;
    UPROPERTY() TObjectPtr<class ULineBatchComponent> WarningVisual;
    UPROPERTY() TObjectPtr<ALabCharacter> Unit;
    int32 ThreatId = 0;
    FVector Direction = FVector::ZeroVector;
    FVector LaunchSource = FVector::ZeroVector;
    FVector PreviousUnitLocation = FVector::ZeroVector;
    uint64 LastBlinkSerial = 0;
    double CreatedSeconds = 0;
    float WarningSeconds = .3f;
    float Speed = 1200.f;
    float DistanceTraveled = 0.f;
    double NearestClearance = 0.;
    bool bClearanceValid = false;
    FString BaselineThreat = TEXT("unknown");
    void Record(const FString& Event);
    void Hit();
};
