#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SurviveProfile.h"
#include "SurviveAttackDirector.generated.h"
class ALabCharacter;
class ASurviveThreat;

struct FSurviveAttackDescriptor
{
    double ScheduledSeconds = 0;
    bool bAimed = false;
    bool bCircle = false;
    FVector Source;
    FVector RandomTarget;
};

// One authority-owned, seedable threat schedule per unit. No hidden tracking.
UCLASS()
class SURGEMOVEMENTLAB_API ASurviveAttackDirector : public AActor
{
    GENERATED_BODY()
public:
    ASurviveAttackDirector();
    void Initialize(ALabCharacter* InUnit, int32 InSeed);
    void CancelThreats();
    static TArray<FSurviveAttackDescriptor> BuildSchedule(int32 Seed, float ProjectileFraction, float AimedFraction);
    virtual void Tick(float DeltaSeconds) override;
    // Frozen initial capture policy; changing it requires updating run metadata.
    static constexpr float AimedFraction = SurviveProfile::AimedFraction;
    static constexpr float SpawnInterval = SurviveProfile::SpawnInterval;
private:
    UPROPERTY() TObjectPtr<ALabCharacter> Unit;
    TArray<FSurviveAttackDescriptor> Schedule;
    double StartSeconds = 0;
    int32 ThreatSequence = 0;
    TArray<TWeakObjectPtr<ASurviveThreat>> ActiveThreats;
    void SpawnThreat(const FSurviveAttackDescriptor& Attack);
};
