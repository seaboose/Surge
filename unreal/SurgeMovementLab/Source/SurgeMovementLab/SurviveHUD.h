#pragma once
#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "SurviveHUD.generated.h"

UCLASS()
class SURGEMOVEMENTLAB_API ASurviveHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
    virtual void NotifyHitBoxClick(FName BoxName) override;
};
