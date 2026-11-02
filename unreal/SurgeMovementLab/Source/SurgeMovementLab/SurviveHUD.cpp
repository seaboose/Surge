#include "SurviveHUD.h"
#include "LabPlayerController.h"
#include "LabCharacter.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "SurviveProfile.h"
#include "LabGameMode.h"
#include "Engine/World.h"

void ASurviveHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas || !PlayerOwner || !GEngine) return;
    auto* PC = Cast<ALabPlayerController>(PlayerOwner);
    auto* Unit = PC ? PC->GetUnit() : nullptr;
    auto* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<ALabGameMode>() : nullptr;
    const bool bStudy = Mode && Mode->IsStudyActive();
    DrawRect(FLinearColor(0.f, 0.f, 0.f, .78f), 16, 16, 575, bStudy ? 266 : 164);
    DrawText(TEXT("SURVIVE"), FLinearColor::White, 30, 24, GEngine->GetMediumFont(), 1.2f);
    DrawText(TEXT("RMB move / hold to steer   S stop   Q dash   E blink   R restart"), FLinearColor::White, 30, 64, GEngine->GetSmallFont());
    if (!Unit) { DrawText(TEXT("Waiting for authority-owned character..."), FLinearColor::White, 30, 88); return; }
    DrawText(FString::Printf(TEXT("Time %.1f / 60 s   Hits %d   Seed %d"), Unit->GetRoundElapsed(), Unit->GetHits(), Unit->GetRunSeed()), FLinearColor::White, 30, 88);
    DrawText(FString::Printf(TEXT("Dash %.1f s   Blink %.1f s   %s cooldowns"), Unit->GetDashCooldown(), Unit->GetBlinkCooldown(),
        Unit->UsesPracticeCooldowns() ? TEXT("Practice") : TEXT("Reference")), FLinearColor::White, 30, 110);
    DrawText(Unit->IsRoundActive() ? TEXT("Aimed + random attacks. No invulnerability.") :
        bStudy ? TEXT("Study round ended. Returning to Surge.") : TEXT("Round complete. Press R for a fresh capture."), FLinearColor::White, 30, 132);
    DrawText(FString(TEXT("Game telemetry: ")) + Unit->GetCaptureStatus(), FLinearColor::White, 30, 154);
    if (bStudy)
    {
        DrawText(Mode->GetStudyControlText(), FLinearColor::Yellow, 30, 176);
        DrawText(Mode->GetRecorderText(), FLinearColor(.6f, .95f, 1.f), 30, 198);
        const bool bCanStop = Mode->CanStopRecorder();
        DrawRect(bCanStop ? FLinearColor(.08f, .28f, .34f) : FLinearColor(.13f, .16f, .18f), 30, 222, 230, 26);
        DrawText(TEXT("Stop recording [F10]"), bCanStop ? FLinearColor::White : FLinearColor::Gray, 40, 225);
        if (bCanStop) AddHitBox(FVector2D(30, 222), FVector2D(230, 26), TEXT("StopSurgeRecording"), true);
        DrawText(TEXT("Stops Surge collection only; gameplay continues."), FLinearColor::White, 30, 255, GEngine->GetSmallFont());
    }
}
void ASurviveHUD::NotifyHitBoxClick(FName BoxName)
{
    Super::NotifyHitBoxClick(BoxName);
    if (BoxName == TEXT("StopSurgeRecording"))
        if (auto* PC = Cast<ALabPlayerController>(PlayerOwner)) PC->StopSurgeRecording();
}
