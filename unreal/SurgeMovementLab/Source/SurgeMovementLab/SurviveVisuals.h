#pragma once
#include "CoreMinimal.h"
#include "Components/LineBatchComponent.h"

// Gameplay cues use ordinary runtime components in every build configuration.
// They have no collision and do not participate in movement or threat timing.
namespace SurviveVisuals
{
inline void Circle(ULineBatchComponent* Lines, const FVector& Center, float Radius, const FColor& Color, float Thickness)
{
    constexpr int32 Segments = 48;
    TArray<FBatchedLine> Vertices;
    Vertices.Reserve(Segments);
    const float Step = 2.f * PI / Segments;
    for (int32 I = 0; I < Segments; ++I)
    {
        const float A = I * Step;
        const float B = (I + 1) * Step;
        Vertices.Emplace(Center + Radius * FVector(FMath::Cos(A), FMath::Sin(A), 0),
            Center + Radius * FVector(FMath::Cos(B), FMath::Sin(B), 0), Color, 0.f, Thickness, SDPG_World);
    }
    Lines->DrawLines(Vertices);
}
}
