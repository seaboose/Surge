#include "SurvivePaths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformFileManager.h"

bool SurvivePaths::NormalizeSavedDirectory(const FString& Requested, FString& Out)
{
    if (Requested.IsEmpty() || Requested.Len() > 1024 || FPaths::IsRelative(Requested)) return false;
    FString Candidate = Requested;
    FPaths::NormalizeDirectoryName(Candidate);
    if (Candidate.StartsWith(TEXT("//")) || !FPaths::CollapseRelativeDirectories(Candidate)) return false;
    // Refuse volume roots and linked ancestors. A packaged launcher supplies a
    // dedicated existing user-data directory, never a path from the renderer.
    if (FPaths::GetPath(Candidate).IsEmpty() || Candidate.Len() <= 3) return false;
    auto& Platform = FPlatformFileManager::Get().GetPlatformFile();
    for (FString Current = Candidate; !Current.IsEmpty(); )
    {
        if (Platform.IsSymlink(*Current) != ESymlinkResult::NonSymlink) return false;
        const FString Parent = FPaths::GetPath(Current);
        if (Parent == Current) break;
        Current = Parent;
    }
    Out = Candidate;
    return true;
}

FString SurvivePaths::SavedDirectory()
{
    static const FString Directory = []
    {
        FString Requested;
        if (!FParse::Value(FCommandLine::Get(), TEXT("SurviveSavedDir="), Requested))
            return FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir());
        FString Normalized;
        if (NormalizeSavedDirectory(Requested, Normalized)) return Normalized;
        UE_LOG(LogTemp, Error, TEXT("SurviveSavedDir must be an absolute local data directory without linked ancestors."));
        FPlatformMisc::RequestExitWithStatus(true, 2);
        return FString();
    }();
    return Directory;
}
