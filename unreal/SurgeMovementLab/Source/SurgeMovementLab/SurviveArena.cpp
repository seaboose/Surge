#include "SurviveArena.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"
#include "Components/DirectionalLightComponent.h"

ASurviveArena::ASurviveArena()
{
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("ArenaRoot")));
    RootComponent->SetMobility(EComponentMobility::Static);
    bReplicates = true;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    auto AddBox = [&](FName Name, FVector Position, FVector Scale)
    {
        auto* Box = CreateDefaultSubobject<UStaticMeshComponent>(Name);
        Box->SetupAttachment(RootComponent);
        if (Cube.Succeeded()) Box->SetStaticMesh(Cube.Object);
        Box->SetRelativeLocation(Position);
        Box->SetRelativeScale3D(Scale);
        Box->SetMobility(EComponentMobility::Static);
        Box->SetCollisionProfileName(TEXT("BlockAll"));
    };
    const double WidthScale = SurviveSim::ArenaHalfExtent * 2. / 100.;
    const double WallCenter = SurviveSim::ArenaHalfExtent + 50.;
    AddBox(TEXT("Floor"), FVector(0, 0, -50), FVector(WidthScale, WidthScale, 1));
    AddBox(TEXT("WestWall"), FVector(-WallCenter, 0, 100), FVector(1, WidthScale + 2., 2));
    AddBox(TEXT("EastWall"), FVector(WallCenter, 0, 100), FVector(1, WidthScale + 2., 2));
    AddBox(TEXT("SouthWall"), FVector(0, -WallCenter, 100), FVector(WidthScale, 1, 2));
    AddBox(TEXT("NorthWall"), FVector(0, WallCenter, 100), FVector(WidthScale, 1, 2));
    // Rendered collision and navigation share these exact rectangles.
    for (std::size_t I = 0; I < SurviveSim::ArenaObstacles.size(); ++I)
    {
        const auto& Box = SurviveSim::ArenaObstacles[I];
        AddBox(FName(*FString::Printf(TEXT("Obstacle%u"), unsigned(I))),
            FVector((Box.MinX + Box.MaxX) * .5, (Box.MinY + Box.MaxY) * .5, 100),
            FVector((Box.MaxX - Box.MinX) / 100., (Box.MaxY - Box.MinY) / 100., 2));
    }
    auto* Light = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("ArenaLight"));
    Light->SetupAttachment(RootComponent);
    Light->SetRelativeRotation(FRotator(-60.f, -35.f, 0));
    Light->SetIntensity(4.f);
}

bool ASurviveArena::IsWalkable(const FVector& Point, float PathRadius)
{
    return !Point.ContainsNaN() && SurviveSim::IsWalkable({Point.X, Point.Y}, PathRadius);
}

bool ASurviveArena::SegmentClear(const FVector2D& From, const FVector2D& To, float PathRadius)
{
    return SurviveSim::SegmentClear({From.X, From.Y}, {To.X, To.Y}, PathRadius);
}

bool ASurviveArena::FindPath(const FVector& From, const FVector& To, float PathRadius, TArray<FVector>& OutPath)
{
    OutPath.Reset();
    if (From.ContainsNaN() || To.ContainsNaN()) return false;
    SurviveSim::Path Result;
    if (!SurviveSim::FindPath({From.X, From.Y}, {To.X, To.Y}, PathRadius, Result)) return false;
    for (std::size_t I = 0; I < Result.Count; ++I)
        OutPath.Add(FVector(Result.Points[I].X, Result.Points[I].Y, From.Z));
    return true;
}
