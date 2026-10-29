#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SurviveRecorderStatus.h"
#include "LabGameMode.generated.h"
UCLASS()
class SURGEMOVEMENTLAB_API ALabGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    ALabGameMode();
    virtual void PostLogin(APlayerController* NewPlayer) override;
    virtual void Logout(AController* Exiting) override;
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    void RestartSurviveRound(APlayerController* Player);
    bool IsStudyActive() const { return !StudyMode.IsEmpty(); }
    FString GetStudyControlText() const;
    FString GetRecorderText() const { return RecorderDisplay.Text(); }
    bool CanStopRecorder() const { return IsStudyActive() && RecorderDisplay.CanStop(); }
    void StopRecorder() { if (IsStudyActive()) RecorderDisplay.RequestStop(StudyTrial); }
private:
    FSurviveRecorderDisplay RecorderDisplay;
    void SpawnUnit(APlayerController* Player);
    bool bSmokeDriver = false;
    bool bSmokeClockStarted = false;
    bool bSpeedProbe = false;
    int32 SpeedProbeStage = 0;
    double SmokeStartSeconds = 0;
    int32 NextSmokeAction = 0;
    FString StudyMode;
    FString StudyTrial;
    FString StudyLogPath;
    FString StudySession;
    double StudyElapsed = 0.;
    double StudyNextAction = 1.;
    int32 StudyActionIndex = 0;
    int32 StudyWindow = -1;
    bool bStudyStarted = false;
    bool bStudyEnded = false;
    bool bStudyLogFailed = false;
    bool bStudyExitAfterRound = false;
    void BeginStudy();
    void TickStudy();
    bool LogStudy(const TCHAR* Event, int32 Action = -1);
    UPROPERTY() TMap<TObjectPtr<AController>, TObjectPtr<class ALabCharacter>> Units;
};
