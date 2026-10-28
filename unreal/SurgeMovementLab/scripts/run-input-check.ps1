param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [ValidateRange(30, 300)][int]$TimeoutSeconds = 300,
    [switch]$InputProbe
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$engineFull = [IO.Path]::GetFullPath($EngineRoot).TrimEnd('\')
$attempt = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = [IO.Path]::GetFullPath((Join-Path $projectRoot ('Saved\Verification\input-check-' + $attempt)))
if (-not $runDirectory.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Verification output must remain inside this project.'
}
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$projectFile = Join-Path $projectRoot 'SurgeMovementLab.uproject'
$editor = Join-Path $engineFull 'Engine\Binaries\Win64\UnrealEditor.exe'
$module = Join-Path $projectRoot 'Binaries\Win64\UnrealEditor-SurgeMovementLab.dll'
$captureDirectory = Join-Path $projectRoot 'Saved\Telemetry'
$captureSnapshots = Join-Path $runDirectory 'captures'
$engineLog = Join-Path $runDirectory 'Unreal.log'
$invocationPath = Join-Path $runDirectory 'invocation.json'
$arguments = @($projectFile, '/Engine/Maps/Entry?game=/Script/SurgeMovementLab.LabGameMode', '-game',
    '-windowed', '-ResX=1280', '-ResY=720', '-unattended', '-UnattendedInput', '-nosound', '-nosplash',
    '-NoEpicPortal', '-nop4', '-NoLiveCoding', '-nocrashreports', '-stdout', '-FullStdOutLogOutput',
    '-ExecCmds=t.MaxFPS 60', ('-abslog=' + $engineLog))
if ($InputProbe) { $arguments += '-SurviveInputProbe' }
# -UnattendedInput is a process-only UE5.8 flag (Core/Private/Misc/App.cpp)
# permitting real window input while -unattended suppresses blocking dialogs.
# No smoke driver, fixed time step, NullRHI, or disabled shader compilation.
$sourceKind = if ($InputProbe) { 'unreal-window-and-engine-input-probe' } else { 'unreal-cua-input-check' }
$scope = if ($InputProbe) {
    'Rendered Survive with CUA window input and an opt-in Unreal input-functional probe. Engine-injected held keys are not physical mouse holding or human play. Separate raw-data and input review required.'
} else {
    'Rendered standalone Survive receiving externally operated window mouse/key input. No smoke driver or human-player claim. Captures require separate raw-data and visual/input review.'
}
$result = [ordered]@{
    status = 'starting'; started = (Get-Date).ToString('o'); finished = $null
    process_id = $null; exit_code = $null; timed_out = $false
    process_outcome = 'not_started'; error = $null; captures = @()
    existing_captures_unchanged = $null; inputs_unchanged = $null
    warnings = @(); evidence_errors = @(); scope = $scope
}
$invocation = [ordered]@{
    started = $result.started; project = $projectFile; engine = $engineFull
    executable = $editor; arguments = $arguments; working_directory = $projectRoot
    process_id = $null; process_timeout_seconds = $TimeoutSeconds
    shutdown_grace_seconds = 5; output_drain_grace_seconds = 5
    runner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    executable_sha256 = $null; module_sha256 = $null; engine_version = $null
    source_kind = $sourceKind; external_action_log_expected = $true
    engine_input_probe_enabled = [bool]$InputProbe
    requested_window_pixels = @(1280, 720); frame_cap_fps = 60; fixed_time_step = $false
    smoke_driver = $false; null_rhi = $false; shader_compilation_disabled = $false
    expected_shutdown = 'Operator closes this owned game window, normally with Alt+F4; timeout only terminates its owned process tree.'
    scope = $scope
}
$invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $invocationPath -Encoding utf8

function Get-CaptureInventory {
    if (-not (Test-Path -LiteralPath $captureDirectory)) { return @() }
    $files = @(Get-ChildItem -LiteralPath $captureDirectory -File -Filter '*.jsonl' | Select-Object -First 257)
    if ($files.Count -gt 256) { throw 'More than 256 capture files; this runner will not inspect an unbounded capture directory.' }
    return @($files | Sort-Object Name | ForEach-Object {
        if ($_.Length -gt 4194304) { throw ('Capture exceeds the 4 MiB inspection bound: ' + $_.Name) }
        [ordered]@{
            name = $_.Name; path = $_.FullName; bytes = $_.Length
            last_write_ticks = $_.LastWriteTimeUtc.Ticks
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    })
}

function Get-InputManifest {
    $paths = @($projectFile, $module) + @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'Source'), (Join-Path $projectRoot 'Config') -File -Recurse | ForEach-Object FullName)
    return @($paths | Sort-Object -Unique | ForEach-Object {
        [ordered]@{ path = [IO.Path]::GetRelativePath($projectRoot, $_); sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash }
    })
}

function Save-NewCaptureEvidence {
    param([object[]]$Before)
    $after = @(Get-CaptureInventory)
    ConvertTo-Json -InputObject $after -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'captures-after.json') -Encoding utf8
    $result.existing_captures_unchanged = $true
    foreach ($old in $Before) {
        $current = @($after | Where-Object { $_.name -eq $old.name })
        if ($current.Count -ne 1 -or $current[0].bytes -ne $old.bytes -or
            $current[0].sha256 -ne $old.sha256 -or $current[0].last_write_ticks -ne $old.last_write_ticks) {
            $result.existing_captures_unchanged = $false
            $result.evidence_errors += ('An existing capture changed or disappeared: ' + $old.name)
        }
    }
    $namesBefore = @($Before | ForEach-Object { $_.name })
    $candidates = @($after | Where-Object { $_.name -notin $namesBefore })
    New-Item -ItemType Directory -Path $captureSnapshots | Out-Null
    foreach ($candidate in $candidates) {
        if ($candidate.name -notmatch '^[0-9a-fA-F]{32}\.jsonl$') {
            $result.warnings += ('New non-session JSONL was inventoried but not copied: ' + $candidate.name)
            continue
        }
        $snapshot = Join-Path $captureSnapshots $candidate.name
        Copy-Item -LiteralPath $candidate.path -Destination $snapshot
        $snapshotHash = (Get-FileHash -LiteralPath $snapshot -Algorithm SHA256).Hash
        $originalHashAfterCopy = (Get-FileHash -LiteralPath $candidate.path -Algorithm SHA256).Hash
        $unchanged = $snapshotHash -eq $candidate.sha256 -and $originalHashAfterCopy -eq $candidate.sha256
        $result.captures += [ordered]@{
            original_path = $candidate.path; snapshot = $snapshot
            session_id_from_filename = [IO.Path]::GetFileNameWithoutExtension($candidate.name)
            bytes = $candidate.bytes; sha256 = $snapshotHash; stable_while_copying = $unchanged
            source_kind = $sourceKind; raw_validation = 'pending'
        }
        if (-not $unchanged) { $result.evidence_errors += ('A new capture changed during copying: ' + $candidate.name) }
    }
    if ($result.captures.Count -eq 0) { $result.warnings += 'No new GUID capture was found. This is not proof that input or capture worked.' }
    # Restarts and disconnects are legitimate review cases. Preserve every new
    # session exactly; do not require 60 seconds, a terminal record, one capture,
    # accepted commands, or successful abilities before the operator reviews it.
    ConvertTo-Json -InputObject $result.captures -Depth 5 | Set-Content -LiteralPath (Join-Path $runDirectory 'capture-evidence.json') -Encoding utf8
}

$process = $null
$processStarted = $false
$beforeRecorded = $false
$beforeCaptures = @()
$beforeInputs = @()
$stdoutStream = $null
$stderrStream = $null
$stdoutTask = $null
$stderrTask = $null
$outputDrained = $false
try {
    if ($null -eq [Diagnostics.Process].GetMethod('Kill', [type[]]@([bool]))) { throw 'Use PowerShell 7 or newer for bounded process-tree termination.' }
    foreach ($file in @($projectFile, $editor, $module, (Join-Path $engineFull 'Engine\Build\Build.version'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw ('Required built project or installed engine file missing: ' + $file) }
    }
    $invocation.executable_sha256 = (Get-FileHash -LiteralPath $editor -Algorithm SHA256).Hash
    $invocation.module_sha256 = (Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash
    $invocation.engine_version = Get-Content -LiteralPath (Join-Path $engineFull 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
    $beforeInputs = @(Get-InputManifest)
    $beforeInputs | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'inputs-before.json') -Encoding utf8
    $beforeCaptures = @(Get-CaptureInventory)
    ConvertTo-Json -InputObject $beforeCaptures -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'captures-before.json') -Encoding utf8
    $beforeRecorded = $true
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $runDirectory 'run-input-check.ps1.snapshot')
    $stdoutStream = [IO.File]::Open((Join-Path $runDirectory 'editor.stdout.log'), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $stderrStream = [IO.File]::Open((Join-Path $runDirectory 'editor.stderr.log'), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $editor
    foreach ($argument in $arguments) { $startInfo.ArgumentList.Add($argument) }
    $startInfo.WorkingDirectory = $projectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $false # The owned game window is the input/visual test surface.
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'The owned rendered game could not start.' }
    $processStarted = $true
    $invocation.process_id = $process.Id
    $result.process_id = $process.Id
    Write-Output ('Owned Survive input-check PID: ' + $process.Id)
    Write-Output ('Evidence directory: ' + $runDirectory)
    # Stream output directly to bounded-lifetime files instead of retaining
    # arbitrarily long engine/crash output in the runner's memory.
    $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutStream)
    $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderrStream)
    $invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $invocationPath -Encoding utf8
    $result.status = 'running'
    $result.process_outcome = 'running'
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding utf8
    $result.timed_out = -not $process.WaitForExit($TimeoutSeconds * 1000)
    if ($result.timed_out) {
        $result.process_outcome = 'owned_process_timeout'
        # Stop only the process created here and its descendants. No global
        # process search, other game interaction, installation, or cleanup.
        $process.Kill($true)
        if (-not $process.WaitForExit(5000)) { throw 'Owned game did not terminate within its five-second shutdown limit.' }
        $result.warnings += 'The runner terminated its owned process tree at the time limit; captured sessions may be partial.'
    }
    else { $result.process_outcome = 'exited' }
    $result.exit_code = $process.ExitCode
    if ($result.exit_code -ne 0) { $result.warnings += ('Owned game returned nonzero exit code ' + $result.exit_code + '; inspect engine and capture evidence.') }
}
catch {
    $result.status = 'failed'
    $result.error = $_.Exception.Message
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $runDirectory 'runner-error.log') -Encoding utf8
}
finally {
    if ($null -ne $process) {
        try {
            if ($processStarted -and -not $process.HasExited) {
                $process.Kill($true)
                if (-not $process.WaitForExit(5000)) { $result.evidence_errors += 'Owned process remained active after bounded cleanup.' }
            }
            if ($processStarted -and $process.HasExited -and $null -eq $result.exit_code) { $result.exit_code = $process.ExitCode }
        }
        catch { $result.evidence_errors += ('Owned process cleanup error: ' + $_.Exception.Message) }
        finally { $process.Dispose() }
    }
    try {
        if ($null -ne $stdoutTask -and $null -ne $stderrTask) {
            $outputDrained = [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask, $stderrTask), 5000)
            if (-not $outputDrained) { $result.evidence_errors += 'Engine output did not drain within the five-second limit.' }
        }
    }
    catch { $result.evidence_errors += ('Output capture error: ' + $_.Exception.Message) }
    finally {
        if ($null -ne $stdoutStream) { $stdoutStream.Dispose() }
        if ($null -ne $stderrStream) { $stderrStream.Dispose() }
    }
    if ($processStarted -and $beforeRecorded) {
        try { Save-NewCaptureEvidence -Before $beforeCaptures }
        catch { $result.evidence_errors += ('Capture evidence error: ' + $_.Exception.Message) }
        try {
            $afterInputs = @(Get-InputManifest)
            $afterInputs | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'inputs-after.json') -Encoding utf8
            $result.inputs_unchanged = ($beforeInputs | ConvertTo-Json -Depth 4 -Compress) -eq ($afterInputs | ConvertTo-Json -Depth 4 -Compress)
            if (-not $result.inputs_unchanged) { $result.evidence_errors += 'Project source/configuration/module changed during the input check.' }
        }
        catch { $result.evidence_errors += ('Input fingerprint error: ' + $_.Exception.Message) }
    }
    if ($result.error -or $result.evidence_errors.Count -gt 0) { $result.status = 'failed' }
    elseif ($processStarted) { $result.status = 'captured_pending_review' }
    $invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $invocationPath -Encoding utf8
    $result.finished = (Get-Date).ToString('o')
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding utf8
    Write-Output ('Preserved input-check evidence: ' + $runDirectory)
}
if ($result.status -eq 'failed') { throw ('Input-check runner/evidence failure; inspect result.json in ' + $runDirectory) }
Write-Output 'Captured pending review. Raw-data validation and visual/input QA must be recorded separately; this runner does not issue a playtest pass.'
