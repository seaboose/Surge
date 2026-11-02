@echo off
setlocal
if not defined SURVIVE_ENGINE_ROOT set "SURVIVE_ENGINE_ROOT=%ProgramFiles%\Epic Games\UE_5.8"
set "SURVIVE_COOLDOWN_OPTION="
if /I "%~1"=="reference" set "SURVIVE_COOLDOWN_OPTION=-SurviveReferenceCooldowns"
if not exist "%SURVIVE_ENGINE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe" (
    echo Unreal Engine 5.8 was not found in its default folder.
    echo Set SURVIVE_ENGINE_ROOT to your installed engine folder, then try again.
    pause
    exit /b 1
)
if not exist "%~dp0Binaries\Win64\UnrealEditor-SurgeMovementLab.dll" (
    echo Survive needs a local build first.
    echo Run scripts\build-local.ps1 in PowerShell 7, then try again.
    pause
    exit /b 1
)
start "" "%SURVIVE_ENGINE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe" "%~dp0SurgeMovementLab.uproject" /Engine/Maps/Entry?game=/Script/SurgeMovementLab.LabGameMode -game -windowed -ResX=1280 -ResY=720 -nosplash -NoEpicPortal -NoLiveCoding %SURVIVE_COOLDOWN_OPTION% -ExecCmds="t.MaxFPS 60"
exit /b %errorlevel%
