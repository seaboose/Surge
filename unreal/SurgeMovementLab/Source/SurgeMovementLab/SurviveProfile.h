#pragma once
#include "CoreMinimal.h"

// Versioned lab calibration, not a verified reproduction of League's engine.
// Distances use a chosen 1 cm / reference-unit scale. Research provenance and
// timing ambiguities are recorded in the project design documentation.
namespace SurviveProfile
{
    inline constexpr TCHAR Id[] = TEXT("survive-lucian-practice-v1");
    inline constexpr float WalkSpeed = 335.f;
    inline constexpr float PathRadius = 41.f;
    inline constexpr float HitRadius = 65.f;
    inline constexpr float VisualRadius = 50.f;
    inline constexpr float DashMinRange = 200.f;
    inline constexpr float DashMaxRange = 425.f;
    inline constexpr float DashSpeed = 1350.f;
    inline constexpr float DashPracticeCooldown = 4.f;
    inline constexpr float DashReferenceCooldown = 16.f;
    inline constexpr float BlinkRange = 400.f;
    inline constexpr float BlinkPracticeCooldown = 12.f;
    inline constexpr float BlinkReferenceCooldown = 300.f;
    inline constexpr float ProjectileSpeed = 1200.f;
    inline constexpr float ProjectileRadius = 70.f;
    inline constexpr float ProjectileWarning = .25f;
    inline constexpr float ProjectileRange = 1300.f;
    inline constexpr bool ProjectileBlockedByTerrain = false;
    inline constexpr float CircleRadius = 250.f;
    inline constexpr float CircleWarning = .75f;
    inline constexpr double RoundSeconds = 60.;
    inline constexpr int32 DefaultSeed = 1337;
    inline constexpr float AimedFraction = .5f;
    inline constexpr float ProjectileFraction = .7f;
    inline constexpr float SpawnInterval = .8f;
}
