#include "LabGameMode.h"
#include "LabCharacter.h"
#include "LabPlayerController.h"
#include "GameFramework/PlayerStart.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "AIController.h"
#include "SurviveArena.h"
#include "SurviveHUD.h"
#include "SurvivePaths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/PlatformMisc.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
ALabGameMode::ALabGameMode()
{
    PlayerControllerClass = ALabPlayerController::StaticClass();
    DefaultPawnClass = nullptr; // Player owns commands/camera; AI owns character locomotion.
    bStartPlayersAsSpectators = true;
    HUDClass = ASurviveHUD::StaticClass();
    PrimaryActorTick.bCanEverTick = true;
}
void ALabGameMode::BeginPlay()
{
    Super::BeginPlay();
    GetWorld()->SpawnActor<ASurviveArena>();
#if UE_BUILD_SHIPPING
    // Shipping does not execute -ExecCmds; retain the launcher's 60 FPS cap.
    if (GEngine) GEngine->SetMaxFPS(60.f);
#endif
    bSmokeDriver = FParse::Param(FCommandLine::Get(), TEXT("SurviveSmoke"));
    bSpeedProbe = bSmokeDriver && FParse::Param(FCommandLine::Get(), TEXT("SurviveSpeedProbe"));
    BeginStudy();
}
void ALabGameMode::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    TickStudy();
    if (IsStudyActive()) RecorderDisplay.Tick(StudyTrial, StudySession);
    if (bStudyLogFailed) return;
    if (!bSmokeDriver) return;
    if (!bSmokeClockStarted)
    {
        SmokeStartSeconds = GetWorld()->GetTimeSeconds();
        bSmokeClockStarted = true;
    }
    const double Elapsed = GetWorld()->GetTimeSeconds() - SmokeStartSeconds;
    if (bSpeedProbe && ((SpeedProbeStage == 0 && Elapsed >= 20.) || (SpeedProbeStage == 1 && Elapsed >= 35.)))
    {
        const float NewSpeed = SpeedProbeStage == 0 ? 1200.f : SurviveProfile::WalkSpeed;
        for (const auto& Entry : Units)
        {
            if (!Entry.Value) continue;
            Entry.Value->SetControlledWalkSpeed(NewSpeed);
            if (StudyMode == TEXT("speed_probe")) LogStudy(SpeedProbeStage == 0 ? TEXT("speed_probe_begin") : TEXT("speed_probe_end"));
            UE_LOG(LogTemp, Display, TEXT("Controlled speed action: session=%s elapsed=%.6f actual_cm_s=%.0f"),
                *Entry.Value->GetOperatorSessionId(), Entry.Value->GetRoundElapsed(), NewSpeed);
            if (auto* PC = Cast<ALabPlayerController>(Entry.Key)) PC->RunSmokeAction(5);
        }
        ++SpeedProbeStage;
    }
    if (NextSmokeAction < 20 && Elapsed >= 1. + NextSmokeAction * 2.5)
    {
        if (StudyMode == TEXT("speed_probe")) LogStudy(TEXT("smoke_action_requested"), NextSmokeAction % 5);
        for (const auto& Entry : Units)
            if (auto* PC = Cast<ALabPlayerController>(Entry.Key)) PC->RunSmokeAction(NextSmokeAction % 5);
        ++NextSmokeAction;
    }
    if (Elapsed > 61.) FPlatformMisc::RequestExit(false);
}
void ALabGameMode::BeginStudy()
{
    if (!FParse::Value(FCommandLine::Get(), TEXT("SurviveStudyMode="), StudyMode)) return;
    FGuid TrialGuid;
    const bool bKnownMode = StudyMode == TEXT("human") || StudyMode == TEXT("scripted") ||
        StudyMode == TEXT("mixed") || StudyMode == TEXT("speed_probe");
    if (!bKnownMode || !FParse::Value(FCommandLine::Get(), TEXT("SurviveStudyTrial="), StudyTrial) ||
        !FGuid::ParseExact(StudyTrial, EGuidFormats::Digits, TrialGuid) ||
        (bSmokeDriver != (StudyMode == TEXT("speed_probe"))) ||
        (StudyMode == TEXT("speed_probe") && !bSpeedProbe))
    {
        UE_LOG(LogTemp, Error, TEXT("Survive study arguments are invalid; no study will run."));
        StudyMode.Reset();
        bSmokeDriver = false;
        FPlatformMisc::RequestExit(false);
        return;
    }
    StudyTrial = TrialGuid.ToString(EGuidFormats::Digits).ToLower();
    bStudyExitAfterRound = FParse::Param(FCommandLine::Get(), TEXT("SurviveStudyExitAfterRound"));
    const FString Directory = SurvivePaths::SavedDirectory() / TEXT("StudyActions");
    IFileManager::Get().MakeDirectory(*Directory, true);
    StudyLogPath = Directory / (StudyTrial + TEXT(".jsonl"));
    if (!FFileHelper::SaveStringToFile(TEXT(""), *StudyLogPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
        &IFileManager::Get(), FILEWRITE_NoReplaceExisting))
    {
        bStudyLogFailed = true;
        UE_LOG(LogTemp, Error, TEXT("Survive study could not create its external action journal; automation disabled."));
        FPlatformMisc::RequestExit(false);
    }
}
bool ALabGameMode::LogStudy(const TCHAR* Event, int32 Action)
{
    if (StudyMode.IsEmpty() || bStudyLogFailed || StudyLogPath.IsEmpty()) return false;
    TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
    Row->SetStringField(TEXT("schema"), TEXT("survive-study-actions-v1"));
    Row->SetStringField(TEXT("trial_id"), StudyTrial);
    Row->SetStringField(TEXT("session_id"), StudySession);
    Row->SetStringField(TEXT("mode"), StudyMode);
    Row->SetStringField(TEXT("event"), Event);
    Row->SetNumberField(TEXT("elapsed_s"), StudyElapsed);
    Row->SetNumberField(TEXT("window"), StudyWindow);
    Row->SetNumberField(TEXT("action"), Action);
    Row->SetStringField(TEXT("source_kind"), TEXT("owned-engine-study-driver"));
    FString Line;
    const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
        TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Line);
    FJsonSerializer::Serialize(Row, Writer);
    if (FFileHelper::SaveStringToFile(Line + TEXT("\n"), *StudyLogPath,
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_Append | FILEWRITE_AllowRead)) return true;
    bStudyLogFailed = true;
    UE_LOG(LogTemp, Error, TEXT("Survive study journal write failed; no further automated actions will be dispatched."));
    return false;
}
void ALabGameMode::TickStudy()
{
    if (StudyMode.IsEmpty() || bStudyEnded) return;
    for (const auto& Entry : Units)
    {
        ALabCharacter* Unit = Entry.Value;
        auto* PC = Cast<ALabPlayerController>(Entry.Key);
        if (!Unit || !PC) continue;
        if (bStudyLogFailed)
        {
            PC->SetStudyAutomation(false);
            bStudyEnded = true;
            FPlatformMisc::RequestExit(false);
            return;
        }
        if (!bStudyStarted)
        {
            if (!Unit->IsRoundActive()) return;
            StudySession = Unit->GetOperatorSessionId();
            StudyElapsed = Unit->GetRoundElapsed();
            if (!LogStudy(TEXT("session_start"))) return;
            bStudyStarted = true;
        }
        if (StudySession == Unit->GetOperatorSessionId()) StudyElapsed = Unit->GetRoundElapsed();
        if (StudySession != Unit->GetOperatorSessionId() || !Unit->IsRoundActive())
        {
            if (StudyWindow >= 0) LogStudy(TEXT("window_end"));
            PC->SetStudyAutomation(false);
            LogStudy(StudySession != Unit->GetOperatorSessionId() ? TEXT("session_changed") : TEXT("session_end"));
            bStudyEnded = true;
            if (bStudyExitAfterRound) FPlatformMisc::RequestExit(false);
            return;
        }
        if (StudyMode == TEXT("human") || StudyMode == TEXT("speed_probe")) return;
        const int32 NewWindow = StudyMode == TEXT("scripted") ? 0 :
            StudyElapsed >= 15. && StudyElapsed < 20. ? 0 :
            StudyElapsed >= 35. && StudyElapsed < 40. ? 1 : -1;
        if (NewWindow != StudyWindow)
        {
            if (StudyWindow >= 0)
            {
                if (!LogStudy(TEXT("window_end"))) return;
                PC->SetStudyAutomation(false);
            }
            StudyWindow = NewWindow;
            StudyActionIndex = 0;
            StudyNextAction = StudyElapsed + (StudyMode == TEXT("scripted") ? 1. : .1);
            if (StudyWindow >= 0)
            {
                if (!LogStudy(TEXT("window_start"))) return;
                PC->SetStudyAutomation(true);
            }
        }
        if (StudyWindow >= 0 && StudyElapsed >= StudyNextAction)
        {
            if (!LogStudy(TEXT("action_requested"), StudyActionIndex % 5)) return;
            PC->RunStudyAction(StudyActionIndex % 5);
            ++StudyActionIndex;
            // One command per tick at most; hitches never cause catch-up bursts.
            StudyNextAction = StudyElapsed + (StudyMode == TEXT("scripted") ? 2.5 : 1.25);
        }
    }
}
void ALabGameMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (bStudyStarted && !bStudyEnded) LogStudy(TEXT("process_or_world_end"));
    Super::EndPlay(EndPlayReason);
}
FString ALabGameMode::GetStudyControlText() const
{
    if (StudyMode.IsEmpty()) return TEXT("");
    if (bStudyLogFailed) return TEXT("Study recording failed; automated commands stopped");
    if (bStudyEnded) return TEXT("Study ended; returning to Surge");
    if (StudyMode == TEXT("human")) return TEXT("Human study | your controls");
    if (StudyMode == TEXT("speed_probe")) return TEXT("Speed-change control | automated commands");
    if (StudyMode == TEXT("scripted")) return TEXT("Scripted study | automated commands");
    return StudyWindow >= 0 ? TEXT("Mixed study | SCRIPT CONTROL") :
        TEXT("Mixed study | your controls; fresh RMB press");
}
void ALabGameMode::PostLogin(APlayerController* NewPlayer)
{
    Super::PostLogin(NewPlayer);
    SpawnUnit(NewPlayer);
}
void ALabGameMode::SpawnUnit(APlayerController* NewPlayer)
{
    auto* PC = Cast<ALabPlayerController>(NewPlayer);
    if (!PC || Units.Num() >= 1) return; // First milestone is one-player practice.
    FVector Start(0, -650, 90);
    Start.Y += Units.Num() * 150.f;
    FActorSpawnParameters Params;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButDontSpawnIfColliding;
    if (auto* Unit = GetWorld()->SpawnActor<ALabCharacter>(Start, FRotator::ZeroRotator, Params))
    {
        Units.Add(NewPlayer, Unit);
        PC->AssignUnit(Unit);
    }
}
void ALabGameMode::RestartSurviveRound(APlayerController* Player)
{
    if (!Player) return;
    if (auto* Found = Units.Find(Player))
    {
        if (*Found)
        {
            AController* AI = (*Found)->GetController();
            (*Found)->FinishForRestart();
            (*Found)->Destroy();
            if (AI) AI->Destroy();
        }
        Units.Remove(Player);
    }
    SpawnUnit(Player);
}
void ALabGameMode::Logout(AController* Exiting)
{
    if (auto* Found = Units.Find(Exiting))
    {
        if (*Found)
        {
            AController* AI = (*Found)->GetController();
            (*Found)->Destroy();
            if (AI) AI->Destroy();
        }
    }
    Units.Remove(Exiting);
    Super::Logout(Exiting);
}
