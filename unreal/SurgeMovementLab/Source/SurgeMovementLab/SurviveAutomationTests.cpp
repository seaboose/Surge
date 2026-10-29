#include "SurviveArena.h"
#include "SurviveProfile.h"
#include "SurviveAttackDirector.h"
#include "SurviveRecorderStatus.h"
#include "SurvivePaths.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSurvivePathTest, "Survive.Movement.FixedArenaPaths",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)
bool FSurvivePathTest::RunTest(const FString& Parameters)
{
    TArray<FVector> Path;
    TestTrue(TEXT("Open route"), ASurviveArena::FindPath(FVector(0, -650, 90), FVector(0, 650, 90), SurviveProfile::PathRadius, Path));
    TestEqual(TEXT("Open route is direct"), Path.Num(), 1);
    TestTrue(TEXT("Route around west obstacle"), ASurviveArena::FindPath(FVector(-700, -250, 90), FVector(-100, -250, 90), SurviveProfile::PathRadius, Path));
    TestTrue(TEXT("Obstacle route has corners"), Path.Num() >= 3);
    for (const auto& Point : Path) TestTrue(TEXT("Path corners respect path radius"), ASurviveArena::IsWalkable(Point, SurviveProfile::PathRadius));
    TestFalse(TEXT("Obstacle destination rejected"), ASurviveArena::FindPath(FVector(0, -650, 90), FVector(-400, -250, 90), SurviveProfile::PathRadius, Path));
    TestFalse(TEXT("Outside destination rejected"), ASurviveArena::IsWalkable(FVector(1300, 0, 90), SurviveProfile::PathRadius));
    TestTrue(TEXT("Hit/path radii differ deliberately"), SurviveProfile::HitRadius > SurviveProfile::PathRadius);
    TestTrue(TEXT("Damage radius exceeds visible body radius"), SurviveProfile::HitRadius > SurviveProfile::VisualRadius);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSurviveScheduleTest, "Survive.Attacks.SeedIndependence",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)
bool FSurviveScheduleTest::RunTest(const FString& Parameters)
{
    const auto First = ASurviveAttackDirector::BuildSchedule(1337, .7f, .5f);
    const auto Repeat = ASurviveAttackDirector::BuildSchedule(1337, .7f, .5f);
    const auto MoreCircles = ASurviveAttackDirector::BuildSchedule(1337, .1f, .5f);
    const auto AllTargeted = ASurviveAttackDirector::BuildSchedule(1337, .7f, 1.f);
    const auto OtherSeed = ASurviveAttackDirector::BuildSchedule(42, .7f, .5f);
    TestTrue(TEXT("Finite nonempty schedule"), First.Num() > 0 && First.Num() < 100);
    TestEqual(TEXT("Repeat count"), First.Num(), Repeat.Num());
    bool bDifferentSeedChangesGeometry = false;
    for (int32 I = 0; I < First.Num(); ++I)
    {
        TestTrue(TEXT("Same seed repeats geometry"), First[I].Source.Equals(Repeat[I].Source) && First[I].RandomTarget.Equals(Repeat[I].RandomTarget));
        TestTrue(TEXT("Changing attack kinds preserves geometry"), First[I].Source.Equals(MoreCircles[I].Source) && First[I].RandomTarget.Equals(MoreCircles[I].RandomTarget));
        TestEqual(TEXT("Changing attack kinds preserves target-selection stream"), First[I].bAimed, MoreCircles[I].bAimed);
        TestTrue(TEXT("Changing aim mix preserves geometry"), First[I].Source.Equals(AllTargeted[I].Source) && First[I].RandomTarget.Equals(AllTargeted[I].RandomTarget));
        TestTrue(TEXT("Requested all-targeted mix"), AllTargeted[I].bAimed);
        TestTrue(TEXT("Scheduled warning remains within round"), First[I].ScheduledSeconds >= 0 && First[I].ScheduledSeconds < SurviveProfile::RoundSeconds);
        if (I > 0) TestTrue(TEXT("Strict schedule order"), First[I].ScheduledSeconds > First[I - 1].ScheduledSeconds);
        bDifferentSeedChangesGeometry |= !First[I].RandomTarget.Equals(OtherSeed[I].RandomTarget);
    }
    TestTrue(TEXT("Another seed changes geometry"), bDifferentSeedChangesGeometry);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSurviveRecorderStatusTest, "Survive.Recording.StatusIdentityAndBounds",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)
bool FSurviveRecorderStatusTest::RunTest(const FString& Parameters)
{
    const FString Trial = TEXT("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    const FString Session = TEXT("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB");
    const FString Json = TEXT("{\"schema\":\"survive-recorder-status-v1\",\"trial_id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"recording_id\":\"cccccccccccccccccccccccccccccccc\",\"session_id\":\"BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\",\"state\":\"recording\",\"heartbeat\":1,\"elapsed_s\":5,\"source_elapsed_s\":3,\"records\":90,\"stale_s\":0.1,\"sequence_gaps\":0,\"parse_errors\":0,\"pending_bytes\":0,\"error\":null,\"stop_requested\":false,\"analysis_state\":\"pending\"}");
    FSurviveRecorderStatus Status;
    TestTrue(TEXT("Bound recording status accepted"), FSurviveRecorderStatus::Parse(Json, Trial, Session, Status));
    TestEqual(TEXT("Recorder elapsed stays distinct from game elapsed"), Status.Elapsed, 5.);
    TestEqual(TEXT("Source time remains game clock"), Status.SourceElapsed, 3.);
    TestEqual(TEXT("Received count"), Status.Records, 90);
    TestFalse(TEXT("No invented health warning"), Status.bHealthWarning);
    TestFalse(TEXT("Other trial rejected"), FSurviveRecorderStatus::Parse(Json, TEXT("dddddddddddddddddddddddddddddddd"), Session, Status));
    TestFalse(TEXT("Other game session rejected"), FSurviveRecorderStatus::Parse(Json, Trial, Trial, Status));
    TestFalse(TEXT("Unrecognized state rejected"), FSurviveRecorderStatus::Parse(Json.Replace(TEXT("\"recording\""), TEXT("\"healthy\"")), Trial, Session, Status));
    TestFalse(TEXT("Out of bound counters rejected"), FSurviveRecorderStatus::Parse(Json.Replace(TEXT("\"records\":90"), TEXT("\"records\":10001")), Trial, Session, Status));
    TestFalse(TEXT("Missing required health field rejected"), FSurviveRecorderStatus::Parse(Json.Replace(TEXT("\"stale_s\":0.1,"), TEXT("")), Trial, Session, Status));
    TestTrue(TEXT("Warning stays visible"), FSurviveRecorderStatus::Parse(Json.Replace(TEXT("\"sequence_gaps\":0"), TEXT("\"sequence_gaps\":1")), Trial, Session, Status));
    TestTrue(TEXT("Gap cannot appear healthy"), Status.bHealthWarning);
    TestFalse(TEXT("Oversized status rejected"), FSurviveRecorderStatus::Parse(FString::ChrN(4097, 'x'), Trial, Session, Status));
    TestFalse(TEXT("Received rows require bound session"), FSurviveRecorderStatus::Parse(
        Json.Replace(TEXT("\"session_id\":\"BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\""), TEXT("\"session_id\":null")), Trial, Session, Status));
    // Exercise the same native bounded reader and stop writer called by the HUD
    // and F10, using only this test's new GUID directory and exact filenames.
    const FString FileTrial = FGuid::NewGuid().ToString(EGuidFormats::Digits).ToLower();
    const FString Directory = SurvivePaths::SavedDirectory() / TEXT("StudyTrials") / FileTrial;
    const FString StatusPath = Directory / TEXT("recorder-status.json");
    const FString RequestPath = Directory / TEXT("recorder-stop.json");
    if (!TestFalse(TEXT("Test folder is new"), IFileManager::Get().DirectoryExists(*Directory))) return false;
    IFileManager::Get().MakeDirectory(*Directory, true);
    const FString FileJson = Json.Replace(*Trial, *FileTrial);
    TestTrue(TEXT("Test status writes"), FFileHelper::SaveStringToFile(FileJson, *StatusPath,
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM, &IFileManager::Get(), FILEWRITE_NoReplaceExisting));
    FSurviveRecorderDisplay Display;
    Display.Tick(FileTrial, Session);
    TestTrue(TEXT("Fresh owned recording enables control"), Display.CanStop());
    TestTrue(TEXT("Native HUD reads receipt state"), Display.Text().Contains(TEXT("90 received")));
    Display.RequestStop(FileTrial);
    TestFalse(TEXT("Pending stop prevents repeated submissions"), Display.CanStop());
    FString Request;
    TestTrue(TEXT("Native HUD/F10 handler writes stop request"), FFileHelper::LoadFileToString(Request, *RequestPath));
    TestTrue(TEXT("Request binds exact trial"), Request.Contains(FileTrial));
    TestTrue(TEXT("Request binds exact recording"), Request.Contains(TEXT("cccccccccccccccccccccccccccccccc")));
    TestTrue(TEXT("Request can only stop recorder"), Request.Contains(TEXT("\"command\":\"stop_recording\"")));
    TestTrue(TEXT("Request acknowledged as pending"), Display.Text().Contains(TEXT("gameplay continues")));
    IFileManager::Get().Delete(*StatusPath);
    IFileManager::Get().Delete(*RequestPath);
    IFileManager::Get().DeleteDirectory(*Directory, false, false);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSurviveSavedDirectoryTest, "Survive.Recording.LocalDataRoot",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)
bool FSurviveSavedDirectoryTest::RunTest(const FString& Parameters)
{
    FString Out;
    TestFalse(TEXT("Relative output rejected"), SurvivePaths::NormalizeSavedDirectory(TEXT("Saved/Other"), Out));
    TestFalse(TEXT("Empty output rejected"), SurvivePaths::NormalizeSavedDirectory(TEXT(""), Out));
    TestFalse(TEXT("Network output rejected"), SurvivePaths::NormalizeSavedDirectory(TEXT("//server/share/data"), Out));
    TestFalse(TEXT("Volume root rejected"), SurvivePaths::NormalizeSavedDirectory(TEXT("C:/"), Out));
    TestTrue(TEXT("Local existing project saved directory accepted"), SurvivePaths::NormalizeSavedDirectory(
        FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir()), Out));
    return true;
}
#endif
