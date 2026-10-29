#pragma once
#include "CoreMinimal.h"

// The local launcher chooses the writable data root; gameplay evidence never does.
namespace SurvivePaths
{
bool NormalizeSavedDirectory(const FString& Requested, FString& Out);
FString SavedDirectory();
}
