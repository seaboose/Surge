#include "SurviveAttackDirector.h"
#include "LabCharacter.h"
#include "SurviveThreat.h"
#include "Engine/World.h"
#include "SurviveProfile.h"

ASurviveAttackDirector::ASurviveAttackDirector()
{
    PrimaryActorTick.bCanEverTick = true;
}
void ASurviveAttackDirector::Initialize(ALabCharacter* InUnit, int32 InSeed)
{
    check(HasAuthority());
    Unit = InUnit;
    AddTickPrerequisiteActor(Unit);
    StartSeconds = GetWorld()->GetTimeSeconds();
    Schedule = BuildSchedule(InSeed, SurviveProfile::ProjectileFraction, AimedFraction);
}
TArray<FSurviveAttackDescriptor> ASurviveAttackDirector::BuildSchedule(int32 InSeed, float ProjectileFraction, float TargetedFraction)
{
    TArray<FSurviveAttackDescriptor> Result;
    FRandomStream TypeRandom(InSeed ^ 47), AimRandom(InSeed ^ 31), GeometryRandom(InSeed ^ 17);
    for (double Time = 1.; Time < SurviveProfile::RoundSeconds - SurviveProfile::CircleWarning; Time += SpawnInterval)
    {
        FSurviveAttackDescriptor Attack;
        Attack.ScheduledSeconds = Time;
        Attack.bCircle = TypeRandom.FRand() >= ProjectileFraction;
        Attack.bAimed = AimRandom.FRand() < TargetedFraction;
        const float Angle = GeometryRandom.RandRange(0, 7) * PI / 4.f;
        Attack.Source = FVector(FMath::Cos(Angle) * 900.f, FMath::Sin(Angle) * 900.f, 90.f);
        Attack.RandomTarget = FVector(GeometryRandom.FRandRange(-1050.f, 1050.f), GeometryRandom.FRandRange(-1050.f, 1050.f), 90.f);
        Result.Add(Attack);
    }
    return Result;
}
void ASurviveAttackDirector::CancelThreats()
{
    for (auto& Threat : ActiveThreats) if (Threat.IsValid()) Threat->Cancel();
    ActiveThreats.Reset();
}
void ASurviveAttackDirector::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!HasAuthority() || !Unit) return;
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - StartSeconds >= 60. || !Unit->IsRoundActive())
    {
        CancelThreats();
        Destroy();
        return;
    }
    ActiveThreats.RemoveAll([](const auto& Threat) { return !Threat.IsValid(); });
    if (Schedule.IsValidIndex(ThreatSequence) && Now - StartSeconds >= Schedule[ThreatSequence].ScheduledSeconds)
    {
        // One descriptor per tick. Hitches delay real execution; timestamps
        // describe that delay rather than fabricating earlier events.
        if (ActiveThreats.Num() < 32) SpawnThreat(Schedule[ThreatSequence]);
        ++ThreatSequence;
    }
}
void ASurviveAttackDirector::SpawnThreat(const FSurviveAttackDescriptor& Attack)
{
    // Aimed attacks freeze the player's position at warning time. Random attacks
    // choose an arena coordinate independently of the player. Both use the seed.
    const FVector Target = Attack.bAimed ? Unit->GetActorLocation() : Attack.RandomTarget;
    const FVector Source = Attack.Source;
    FActorSpawnParameters Params;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Threat = GetWorld()->SpawnActor<ASurviveThreat>(Attack.bCircle ? Target : Source, FRotator::ZeroRotator, Params);
    if (!Threat) return;
    Threat->Initialize(Unit, ThreatSequence + 1, Source, Target, Attack.bCircle, Attack.bAimed);
    ActiveThreats.Add(Threat);
}
