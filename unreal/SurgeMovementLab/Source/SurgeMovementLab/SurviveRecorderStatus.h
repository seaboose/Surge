#pragma once
#include "CoreMinimal.h"

// Display/control channel only; never adds fields to movement telemetry.
struct FSurviveRecorderStatus
{
    FString RecordingId;
    FString State;
    double Elapsed = 0.;
    double SourceElapsed = 0.;
    double StaleSeconds = 0.;
    int32 Records = 0;
    int32 Heartbeat = -1;
    bool bHealthWarning = false;
    bool bStopRequested = false;
    static bool Parse(const FString& Json, const FString& Trial, const FString& Session, FSurviveRecorderStatus& Out);
};

class FSurviveRecorderDisplay
{
public:
    void Tick(const FString& Trial, const FString& Session);
    FString Text() const;
    bool CanStop() const;
    void RequestStop(const FString& Trial);
private:
    FSurviveRecorderStatus Status;
    bool bAvailable = false;
    bool bRequested = false;
    double LastHeartbeatSeconds = -1.;
    double NextReadSeconds = 0.;
};
