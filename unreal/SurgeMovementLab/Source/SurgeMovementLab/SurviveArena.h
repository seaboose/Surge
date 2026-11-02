#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SurviveSim.h"
#include "SurviveArena.generated.h"

// Fixed original arena: authority pathfinding uses the same rectangle geometry
// as the generated static collision. No installed/editor-authored navmesh needed.
UCLASS()
class SURGEMOVEMENTLAB_API ASurviveArena : public AActor
{
    GENERATED_BODY()
public:
    ASurviveArena();
    static constexpr float HalfExtent = float(SurviveSim::ArenaHalfExtent);
    static bool IsWalkable(const FVector& Point, float PathRadius);
    static bool FindPath(const FVector& From, const FVector& To, float PathRadius, TArray<FVector>& OutPath);
private:
    static bool SegmentClear(const FVector2D& From, const FVector2D& To, float PathRadius);
};
