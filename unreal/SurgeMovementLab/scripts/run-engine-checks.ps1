param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [ValidateSet('Smoke', 'SpeedProbe', 'Automation')][string]$Mode = 'Smoke',
    [ValidateRange(5, 120)][int]$TimeoutSeconds = 110,
    [int]$Seed = 1337,
    [switch]$ReferenceCooldowns
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$engineFull = [IO.Path]::GetFullPath($EngineRoot).TrimEnd('\')
$attempt = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = [IO.Path]::GetFullPath((Join-Path $projectRoot ('Saved\Verification\engine-' + $Mode.ToLowerInvariant() + '-' + $attempt)))
if (-not $runDirectory.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Verification output must remain inside this project.'
}
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$projectFile = Join-Path $projectRoot 'SurgeMovementLab.uproject'
$editor = Join-Path $engineFull 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$module = Join-Path $projectRoot 'Binaries\Win64\UnrealEditor-SurgeMovementLab.dll'
$captureDirectory = Join-Path $projectRoot 'Saved\Telemetry'
$engineLog = Join-Path $runDirectory 'Unreal.log'
$reportDirectory = Join-Path $runDirectory 'AutomationReport'
$expectedProfile = if ($ReferenceCooldowns) { 'survive-lucian-reference-v1' } else { 'survive-lucian-practice-v1' }
$invocationPath = Join-Path $runDirectory 'invocation.json'
$result = [ordered]@{
    status = 'starting'; started = (Get-Date).ToString('o'); finished = $null
    exit_code = $null; timed_out = $false; error = $null
    mode = $Mode; capture = $null; automation = $null
}
$arguments = @($projectFile, '/Engine/Maps/Entry', '-unattended', '-NullRHI', '-nosound', '-nosplash',
    '-nop4', '-NoEpicPortal', '-NoShaderCompile', '-NoLiveCoding', '-nocrashreports', '-stdout', '-FullStdOutLogOutput', ('-abslog=' + $engineLog))
if ($ReferenceCooldowns) { $arguments += '-SurviveReferenceCooldowns' }
if ($Mode -eq 'Automation') {
    # This is the installed Gauntlet editor-automation command shape. Quit is
    # queued by Automation after RunTest; it is not a separate immediate Quit.
    # The tests are world-independent and support ClientContext. Standalone game
    # context avoids this installed editor's NullRHI first-tick crash.
    $arguments[1] = '/Engine/Maps/Entry?game=/Script/Engine.GameModeBase'
    $arguments += @('-game', '-ExecCmds=t.MaxFPS 60,Automation RunTest Survive.;Quit;', ('-ReportExportPath=' + $reportDirectory))
}
else {
    $arguments[1] = '/Engine/Maps/Entry?game=/Script/SurgeMovementLab.LabGameMode'
    $arguments += @('-game', '-SurviveSmoke', ('-SurviveSeed=' + $Seed), '-ExecCmds=t.MaxFPS 60')
    if ($Mode -eq 'SpeedProbe') { $arguments += '-SurviveSpeedProbe' }
}
$invocation = [ordered]@{
    started = $result.started; project = $projectFile; engine = $engineFull
    executable = $editor; arguments = $arguments; working_directory = $projectRoot
    mode = $Mode; process_id = $null; process_timeout_seconds = $TimeoutSeconds
    expected_profile_id = $expectedProfile
    shutdown_and_output_grace_seconds = 10
    runner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    executable_sha256 = $null; module_sha256 = $null; engine_version = $null
    source_kind = if ($Mode -eq 'Automation') { 'unreal-native-automation' } else { 'unreal-smoke-driver' }
    scope = if ($Mode -eq 'Automation') {
        'Four native Survive automation tests in standalone game context using the editor binary. No visual or human-input validation.'
    } else {
        'Actual Unreal simulation driven through game command/ability handlers. Automated actions, not human RMB input, rendered gameplay, or League equivalence.'
    }
}
$invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $invocationPath -Encoding utf8

function Get-CaptureInventory {
    if (-not (Test-Path -LiteralPath $captureDirectory)) { return @() }
    $files = @(Get-ChildItem -LiteralPath $captureDirectory -File -Filter '*.jsonl' | Select-Object -First 257)
    if ($files.Count -gt 256) { throw 'More than 256 existing captures: identify/archive them separately before running this bounded check.' }
    return @($files | Sort-Object Name | ForEach-Object {
        [ordered]@{ name = $_.Name; path = $_.FullName; bytes = $_.Length; last_write_ticks = $_.LastWriteTimeUtc.Ticks }
    })
}

function Get-InputManifest {
    $paths = @($projectFile, $module) + @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'Source'), (Join-Path $projectRoot 'Config') -File -Recurse | ForEach-Object FullName)
    return @($paths | Sort-Object -Unique | ForEach-Object {
        [ordered]@{ path = [IO.Path]::GetRelativePath($projectRoot, $_); sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash }
    })
}

function Save-CaptureEvidence {
    param([object[]]$Before)
    $after = @(Get-CaptureInventory)
    $after | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'captures-after.json') -Encoding utf8
    # Never claim ownership if an existing session changed or if concurrent
    # activity created multiple sessions. No pre-existing capture is modified.
    foreach ($old in $Before) {
        $current = @($after | Where-Object { $_.name -eq $old.name })
        if ($current.Count -ne 1 -or $current[0].bytes -ne $old.bytes -or $current[0].last_write_ticks -ne $old.last_write_ticks) {
            throw 'An existing capture changed during this run; capture ownership is ambiguous.'
        }
    }
    $namesBefore = @($Before | ForEach-Object { $_.name })
    $candidates = @($after | Where-Object { $_.name -notin $namesBefore })
    if ($candidates.Count -ne 1) { throw ('Expected exactly one new capture; found ' + $candidates.Count + '. See before/after inventories.') }
    $candidate = $candidates[0]
    if ($candidate.name -notmatch '^[0-9a-fA-F]{32}\.jsonl$' -or $candidate.bytes -gt 4194304 -or $candidate.bytes -eq 0) {
        throw 'The new capture has an unexpected filename or size.'
    }
    $snapshot = Join-Path $runDirectory 'capture.jsonl'
    Copy-Item -LiteralPath $candidate.path -Destination $snapshot
    $rawHash = (Get-FileHash -LiteralPath $candidate.path -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $snapshot -Algorithm SHA256).Hash -ne $rawHash) { throw 'Capture changed while taking its evidence snapshot.' }
    $lines = [IO.File]::ReadAllLines($snapshot)
    if ($lines.Count -lt 2 -or $lines.Count -gt 10000) { throw 'Unexpected capture row count.' }
    $rows = @($lines | ForEach-Object { $_ | ConvertFrom-Json })
    $session = [IO.Path]::GetFileNameWithoutExtension($candidate.name)
    for ($index = 0; $index -lt $rows.Count; ++$index) {
        if ($rows[$index].schema -ne 'survive-v3' -or $rows[$index].session_id -ne $session -or $rows[$index].seq -ne $index) {
            throw ('Capture schema/session/sequence mismatch at row ' + $index + '.')
        }
    }
    $counts = [ordered]@{}
    foreach ($group in ($rows | Group-Object event | Sort-Object Name)) { $counts[$group.Name] = $group.Count }
    $info = [ordered]@{
        original_path = $candidate.path; snapshot = $snapshot; sha256 = $rawHash
        bytes = $candidate.bytes; rows = $rows.Count; session_id = $session
        events = $counts; terminal_reason = $rows[-1].detail; elapsed_s = $rows[-1].elapsed_s
        source_kind = 'unreal-smoke-driver'; operator_actions_are_external = $true
        speed_actions = @()
    }
    $result.capture = $info
    if ($Mode -eq 'SpeedProbe' -and (Test-Path -LiteralPath $engineLog)) {
        $pattern = 'Controlled speed action: session=([0-9a-fA-F]{32}) elapsed=([0-9.]+) actual_cm_s=([0-9.]+)'
        $info.speed_actions = @(Select-String -LiteralPath $engineLog -Pattern $pattern | ForEach-Object {
            $match = [regex]::Match($_.Line, $pattern)
            [ordered]@{
                session_id = $match.Groups[1].Value
                elapsed_s = [double]::Parse($match.Groups[2].Value, [Globalization.CultureInfo]::InvariantCulture)
                actual_cm_s = [double]::Parse($match.Groups[3].Value, [Globalization.CultureInfo]::InvariantCulture)
            }
        })
    }
    $info | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runDirectory 'capture-evidence.json') -Encoding utf8
    if ($rows[0].event -ne 'run_start' -or $rows[-1].event -ne 'run_end' -or $rows[-1].detail -ne 'completed' -or
        $rows[-1].elapsed_s -ne 60 -or $counts['run_start'] -ne 1 -or $counts['run_end'] -ne 1) {
        throw 'Capture did not complete exactly one bounded 60-second round.'
    }
    if ($rows[0].profile_id -ne $expectedProfile -or $rows[0].a -ne $Seed) {
        throw 'Capture profile or seed differs from the requested smoke invocation.'
    }
    if ($counts['sample'] -lt 1 -or $counts['command_grant'] -lt 1 -or
        @($rows | Where-Object { $_.event -eq 'ability_start' -and $_.detail -eq 'dash' }).Count -lt 1 -or
        @($rows | Where-Object { $_.event -eq 'ability_start' -and $_.detail -eq 'blink' }).Count -lt 1 -or
        $counts['threat_warning'] -lt 1 -or $counts['threat_fire'] -lt 1) {
        throw 'Capture lacks successful walking, both mobility types, or live threats.'
    }
    if ($Mode -eq 'SpeedProbe' -and ($info.speed_actions.Count -ne 2 -or
        $info.speed_actions[0].session_id -ne $session -or $info.speed_actions[1].session_id -ne $session -or
        $info.speed_actions[0].actual_cm_s -ne 1200 -or $info.speed_actions[1].actual_cm_s -ne 335 -or
        $info.speed_actions[0].elapsed_s -lt 20 -or $info.speed_actions[1].elapsed_s -lt 35)) {
        throw 'The speed probe lacks both session-bound external change/restoration records.'
    }
}

$process = $null
$processStarted = $false
$beforeCaptures = @()
try {
    if ($null -eq [Diagnostics.Process].GetMethod('Kill', [type[]]@([bool]))) { throw 'Use PowerShell 7 or newer for bounded process-tree termination.' }
    foreach ($file in @($projectFile, $editor, $module)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw ('Required built project or installed engine file missing: ' + $file) }
    }
    $invocation.executable_sha256 = (Get-FileHash -LiteralPath $editor -Algorithm SHA256).Hash
    $invocation.module_sha256 = (Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash
    $invocation.engine_version = Get-Content -LiteralPath (Join-Path $engineFull 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
    $beforeInputs = @(Get-InputManifest)
    $beforeInputs | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'inputs-before.json') -Encoding utf8
    $beforeCaptures = @(Get-CaptureInventory)
    $beforeCaptures | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'captures-before.json') -Encoding utf8
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $runDirectory 'run-engine-checks.ps1.snapshot')
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $editor
    foreach ($argument in $arguments) { $startInfo.ArgumentList.Add($argument) }
    $startInfo.WorkingDirectory = $projectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'The unattended editor could not start.' }
    $processStarted = $true
    $invocation.process_id = $process.Id
    $invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $invocationPath -Encoding utf8
    $result.status = 'running'
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding utf8
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $result.timed_out = -not $process.WaitForExit($TimeoutSeconds * 1000)
    if ($result.timed_out) {
        # Only the process created above and its descendants are terminated.
        # Never discover, stop, or alter other Unreal, League, or audit processes.
        $process.Kill($true)
        if (-not $process.WaitForExit(5000)) { throw 'Owned editor process did not terminate within the shutdown limit.' }
    }
    if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask, $stderrTask), 5000)) {
        throw 'Owned editor output did not drain within its five-second limit.'
    }
    $stdoutTask.GetAwaiter().GetResult() | Set-Content -LiteralPath (Join-Path $runDirectory 'editor.stdout.log') -Encoding utf8
    $stderrTask.GetAwaiter().GetResult() | Set-Content -LiteralPath (Join-Path $runDirectory 'editor.stderr.log') -Encoding utf8
    $result.exit_code = $process.ExitCode
    if ($Mode -ne 'Automation') { Save-CaptureEvidence -Before $beforeCaptures }
    if ($result.timed_out) { throw ('Owned editor exceeded the bounded ' + $TimeoutSeconds + '-second process limit.') }
    if ($result.exit_code -ne 0) { throw ('Unreal returned exit code ' + $result.exit_code + '.') }
    if ($Mode -eq 'Automation') {
        $reportPath = Join-Path $reportDirectory 'index.json'
        if (-not (Test-Path -LiteralPath $reportPath) -or (Get-Item -LiteralPath $reportPath).Length -gt 4194304) {
            throw 'A bounded native automation JSON report was not produced.'
        }
        $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        $expected = @('Survive.Attacks.SeedIndependence', 'Survive.Movement.FixedArenaPaths', 'Survive.Recording.LocalDataRoot', 'Survive.Recording.StatusIdentityAndBounds')
        $actual = @($report.tests | ForEach-Object { $_.fullTestPath } | Sort-Object)
        $result.automation = [ordered]@{
            report = $reportPath; sha256 = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash
            tests = @($report.tests | ForEach-Object { [ordered]@{ name = $_.fullTestPath; state = $_.state } })
        }
        if (($actual -join '|') -ne ($expected -join '|') -or @($report.tests | Where-Object { $_.state -ne 'Success' }).Count -ne 0) {
            throw 'Expected exactly the four successful native Survive tests; inspect the saved JSON report.'
        }
    }
    $afterInputs = @(Get-InputManifest)
    $afterInputs | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDirectory 'inputs-after.json') -Encoding utf8
    if (($beforeInputs | ConvertTo-Json -Depth 4 -Compress) -ne ($afterInputs | ConvertTo-Json -Depth 4 -Compress)) {
        throw 'Project source/configuration/module changed during verification; saved results cannot establish the current build.'
    }
    $result.status = 'passed'
}
catch {
    $result.status = 'failed'
    $result.error = $_.Exception.Message
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $runDirectory 'runner-error.log') -Encoding utf8
}
finally {
    if ($null -ne $process) {
        try { if ($processStarted -and -not $process.HasExited) { $process.Kill($true) } }
        finally { $process.Dispose() }
    }
    $invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $invocationPath -Encoding utf8
    $result.finished = (Get-Date).ToString('o')
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding utf8
    Write-Output ('Preserved Unreal verification: ' + $runDirectory)
}
if ($result.status -ne 'passed') { throw $result.error }
Write-Output ($Mode + ' passed. ' + $invocation.scope)
