#include "SurviveRecorderStatus.h"
#include "SurvivePaths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"

namespace
{
bool Id(const FString& Value)
{
    FGuid Parsed;
    return FGuid::ParseExact(Value, EGuidFormats::Digits, Parsed) && Value == Value.ToLower();
}
bool LocalPath(const FString& File)
{
    auto& Platform = FPlatformFileManager::Get().GetPlatformFile();
    FString Current = FPaths::ConvertRelativePathToFull(File);
    for (int32 Depth = 0; !Current.IsEmpty() && Depth < 64; ++Depth)
    {
        if (Platform.IsSymlink(*Current) != ESymlinkResult::NonSymlink) return false;
        const FString Parent = FPaths::GetPath(Current);
        if (Parent == Current) break;
        Current = Parent;
    }
    return true;
}
FString TrialFile(const FString& Trial, const TCHAR* Name)
{
    return SurvivePaths::SavedDirectory() / TEXT("StudyTrials") / Trial / Name;
}
bool BoundedNumber(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, double Maximum, double& Out)
{
    return Object->TryGetNumberField(Key, Out) && FMath::IsFinite(Out) && Out >= 0. && Out <= Maximum;
}
}

bool FSurviveRecorderStatus::Parse(const FString& Json, const FString& Trial, const FString& Session, FSurviveRecorderStatus& Out)
{
    if (Json.Len() > 4096 || !Id(Trial)) return false;
    TSharedPtr<FJsonObject> Object;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Object) || !Object.IsValid()) return false;
    FString Schema, ActualTrial, ActualSession, Analysis, Error;
    FSurviveRecorderStatus Candidate;
    if (!Object->TryGetStringField(TEXT("schema"), Schema) || Schema != TEXT("survive-recorder-status-v1") ||
        !Object->TryGetStringField(TEXT("trial_id"), ActualTrial) || ActualTrial != Trial ||
        !Object->TryGetStringField(TEXT("recording_id"), Candidate.RecordingId) || !Id(Candidate.RecordingId) ||
        !Object->TryGetStringField(TEXT("state"), Candidate.State) ||
        !(Candidate.State == TEXT("waiting") || Candidate.State == TEXT("recording") || Candidate.State == TEXT("stopped") ||
          Candidate.State == TEXT("complete") || Candidate.State == TEXT("failed")) ||
        !Object->TryGetStringField(TEXT("analysis_state"), Analysis) ||
        !(Analysis == TEXT("pending") || Analysis == TEXT("complete") || Analysis == TEXT("unavailable")) ||
        !Object->TryGetBoolField(TEXT("stop_requested"), Candidate.bStopRequested)) return false;
    const auto SessionValue = Object->TryGetField(TEXT("session_id"));
    if (!SessionValue.IsValid()) return false;
    if (SessionValue->Type != EJson::Null &&
        (!SessionValue->TryGetString(ActualSession) || !ActualSession.Equals(Session, ESearchCase::IgnoreCase))) return false;
    if (Candidate.State == TEXT("recording") && ActualSession.IsEmpty()) return false;
    double Beat, Count, Gaps, Errors, Pending;
    if (!BoundedNumber(Object, TEXT("heartbeat"), 10000, Beat) || Beat != FMath::FloorToDouble(Beat) ||
        !BoundedNumber(Object, TEXT("records"), 10000, Count) || Count != FMath::FloorToDouble(Count) ||
        !BoundedNumber(Object, TEXT("elapsed_s"), 610, Candidate.Elapsed) ||
        !BoundedNumber(Object, TEXT("stale_s"), 610, Candidate.StaleSeconds) ||
        !BoundedNumber(Object, TEXT("sequence_gaps"), 10000, Gaps) ||
        !BoundedNumber(Object, TEXT("parse_errors"), 10000, Errors) ||
        !BoundedNumber(Object, TEXT("pending_bytes"), 4096, Pending)) return false;
    const auto SourceTime = Object->TryGetField(TEXT("source_elapsed_s"));
    if (!SourceTime.IsValid() || (SourceTime->Type != EJson::Null &&
        !BoundedNumber(Object, TEXT("source_elapsed_s"), 60.1, Candidate.SourceElapsed))) return false;
    if (Count > 0 && (ActualSession.IsEmpty() || SourceTime->Type == EJson::Null)) return false;
    const auto ErrorValue = Object->TryGetField(TEXT("error"));
    if (!ErrorValue.IsValid() || (ErrorValue->Type != EJson::Null &&
        (!ErrorValue->TryGetString(Error) || Error.Len() > 300))) return false;
    Candidate.Heartbeat = static_cast<int32>(Beat);
    Candidate.Records = static_cast<int32>(Count);
    Candidate.bHealthWarning = Gaps > 0 || Errors > 0 || Pending > 0 || !Error.IsEmpty();
    Out = Candidate;
    return true;
}

void FSurviveRecorderDisplay::Tick(const FString& Trial, const FString& Session)
{
    const double Now = FPlatformTime::Seconds();
    if (!Id(Trial) || Now < NextReadSeconds) return;
    NextReadSeconds = Now + .25;
    const FString Path = TrialFile(Trial, TEXT("recorder-status.json"));
    if (!LocalPath(Path)) { bAvailable = false; return; }
    // Status is atomically replaced by the recorder. Permit replacement while
    // retaining this handle's complete old bytes; never observe a partial write.
    auto Opened = FPlatformFileManager::Get().GetPlatformFile().OpenRead(*Path, IPlatformFile::EOpenReadFlags::AllowDelete);
    if (Opened.HasError()) { bAvailable = false; return; }
    TUniquePtr<IFileHandle> Reader = Opened.StealValue();
    if (!Reader || Reader->Size() <= 0 || Reader->Size() > 4096) { bAvailable = false; return; }
    TArray<uint8> Bytes;
    Bytes.SetNumZeroed(static_cast<int32>(Reader->Size()) + 1);
    if (!Reader->Read(Bytes.GetData(), Bytes.Num() - 1)) { bAvailable = false; return; }
    const FString Json = UTF8_TO_TCHAR(reinterpret_cast<const char*>(Bytes.GetData()));
    FSurviveRecorderStatus Value;
    if (!FSurviveRecorderStatus::Parse(Json, Trial, Session, Value)) { bAvailable = false; return; }
    if (Value.RecordingId != Status.RecordingId || Value.Heartbeat != Status.Heartbeat) LastHeartbeatSeconds = Now;
    Status = Value;
    bAvailable = true;
}
bool FSurviveRecorderDisplay::CanStop() const
{
    return bAvailable && FPlatformTime::Seconds() - LastHeartbeatSeconds <= 3. &&
        !bRequested && !Status.bStopRequested && (Status.State == TEXT("waiting") || Status.State == TEXT("recording"));
}
FString FSurviveRecorderDisplay::Text() const
{
    if (!bAvailable || FPlatformTime::Seconds() - LastHeartbeatSeconds > 3.) return TEXT("Surge recorder unavailable - check app");
    if (Status.State == TEXT("stopped")) return FString::Printf(TEXT("Surge stopped: %.1f s saved | partial / Unknown"), Status.SourceElapsed);
    if (Status.State == TEXT("failed")) return TEXT("Surge recording failed - review retained evidence");
    if (Status.State == TEXT("complete")) return TEXT("Surge saved - review session in app");
    if (bRequested || Status.bStopRequested) return TEXT("Stopping Surge recording... gameplay continues");
    if (Status.bHealthWarning) return TEXT("Surge recording needs attention - check app");
    if (Status.State == TEXT("waiting")) return TEXT("Surge armed - waiting for game telemetry");
    if (Status.StaleSeconds > 1.) return FString::Printf(TEXT("Surge receipt delayed %.1f s - check app"), Status.StaleSeconds);
    return FString::Printf(TEXT("Surge recording %.1f s | %d received | receipt %.1f s ago"), Status.Elapsed, Status.Records, Status.StaleSeconds);
}
void FSurviveRecorderDisplay::RequestStop(const FString& Trial)
{
    if (!CanStop() || !Id(Trial)) return;
    const FString Path = TrialFile(Trial, TEXT("recorder-stop.json"));
    if (!LocalPath(Path)) { bAvailable = false; return; }
    const FString Json = FString::Printf(TEXT("{\"schema\":\"survive-recorder-control-v1\",\"trial_id\":\"%s\",\"recording_id\":\"%s\",\"command\":\"stop_recording\"}\n"),
        *Trial, *Status.RecordingId);
    bRequested = FFileHelper::SaveStringToFile(Json, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
        &IFileManager::Get(), FILEWRITE_NoReplaceExisting);
    if (bRequested)
    {
        UE_LOG(LogTemp, Display, TEXT("Surge recorder stop requested for owned trial %s"), *Trial);
    }
    else bAvailable = false;
}
