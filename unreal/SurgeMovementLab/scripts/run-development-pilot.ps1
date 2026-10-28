param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8'
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Use PowerShell 7 or newer for this bounded development pilot.' }
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$engineFull = [IO.Path]::GetFullPath($EngineRoot).TrimEnd('\')

function Assert-ProjectPath {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -ne $projectRoot -and -not $full.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw ('A pilot evidence/input path left the project: ' + $full)
    }
    # Reject junction/symlink redirection in any existing project ancestor.
    $check = $full
    while ($check -and $check.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase)) {
        if ((Test-Path -LiteralPath $check) -and ((Get-Item -LiteralPath $check -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw ('Reparse-point input/output paths are not supported by this pilot: ' + $check)
        }
        if ($check -eq $projectRoot) { break }
        $check = [IO.Path]::GetDirectoryName($check)
    }
    return $full
}

function Get-ProjectPath {
    param([string]$Relative)
    return Assert-ProjectPath (Join-Path $projectRoot $Relative)
}

$verificationRoot = Get-ProjectPath 'Saved\Verification'
$engineRunner = Get-ProjectPath 'scripts\run-engine-checks.ps1'
$projectFile = Get-ProjectPath 'SurgeMovementLab.uproject'
$module = Get-ProjectPath 'Binaries\Win64\UnrealEditor-SurgeMovementLab.dll'
$profileFile = Get-ProjectPath 'profiles\survive-lucian-practice-v1.json'
$attempt = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$pilotDirectory = Get-ProjectPath ('Saved\Verification\development-pilot-' + $attempt)
New-Item -ItemType Directory -Path $pilotDirectory | Out-Null
$journalPath = Join-Path $pilotDirectory 'journal.jsonl'
$summaryPath = Join-Path $pilotDirectory 'summary.json'
$frozenPath = Join-Path $pilotDirectory 'frozen-inputs.json'
$seeds = @(1337, 2027, 4242)
$stages = @(
    [ordered]@{ condition = 'nominal_baseline'; mode = 'Smoke' },
    [ordered]@{ condition = 'controlled_speed_change'; mode = 'SpeedProbe' },
    [ordered]@{ condition = 'restoration_baseline'; mode = 'Smoke' }
)
$cases = @()
foreach ($seed in $seeds) {
    for ($stage = 0; $stage -lt 3; ++$stage) {
        $cases += [ordered]@{
            ordinal = $cases.Count + 1; seed = $seed; stage = $stage + 1
            condition = $stages[$stage].condition; mode = $stages[$stage].mode
            phase = 'development'; source_kind = 'unreal-smoke-driver'
            profile_id = 'survive-lucian-practice-v1'; fresh_process = $true
            initial_walk_speed_cm_s = 335; timeout_seconds = 120
            restoration_semantics = if ($stage -eq 2) {
                'Fresh Smoke process initializes the compiled 335 cm/s baseline; this does not test carryover or persisted restoration from the preceding process.'
            } else { $null }
        }
    }
}
$plan = [ordered]@{
    schema = 'survive-development-pilot-v1'; created = (Get-Date).ToString('o')
    project = $projectRoot; engine = $engineFull; phase = 'development'
    source_kind = 'unreal-smoke-driver'; case_count = 9; cases = $cases
    condition_labels_are_external = $true; detector_input_labels = $false
    freeze_scope = @('Source/**', 'Config/**', 'SurgeMovementLab.uproject',
        'Binaries/Win64/UnrealEditor-SurgeMovementLab.dll', 'profiles/**/*.json',
        'telemetry/**/*.py,*.html,*.json excluding local/cache directories',
        'scripts/run-engine-checks.ps1', 'scripts/run-development-pilot.ps1')
    scope = 'Sequential owned Unreal development captures only. No human-player claim, held-out evaluation, detector verdict, analysis bundle, or case export is produced here.'
}
$plan | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $pilotDirectory 'plan.json') -Encoding utf8
$summary = [ordered]@{
    schema = $plan.schema; started = (Get-Date).ToString('o'); finished = $null
    status = 'initializing'; planned_cases = 9; completed_cases = 0; running_case = $null
    current_engine_directory = $null; error = $null; phase = 'development'
    frozen_manifest_sha256 = $null; receipts = @(); validation = 'Capture handoff only; analysis and data-quality review remain pending.'
}

function Save-Summary {
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding utf8
}

function Write-Journal {
    param([object]$Entry)
    $entryText = (ConvertTo-Json -InputObject $Entry -Depth 8 -Compress) + "`n"
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($entryText)
    $stream = [IO.File]::Open($journalPath, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}

function Get-ScopedFiles {
    param([string]$Directory, [string[]]$Extensions = @(), [switch]$SkipLocalCaches)
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push((Assert-ProjectPath $Directory))
    $excluded = @('local', 'cache', '__pycache__', '.cache', '.pytest_cache', '.mypy_cache', '.ruff_cache')
    while ($pending.Count -gt 0) {
        $next = $pending.Pop()
        foreach ($item in (Get-ChildItem -LiteralPath $next -Force)) {
            if ($SkipLocalCaches -and $item.PSIsContainer -and $item.Name -in $excluded) { continue }
            $path = Assert-ProjectPath $item.FullName
            if ($item.PSIsContainer) { $pending.Push($path) }
            elseif ($Extensions.Count -eq 0 -or $item.Extension.ToLowerInvariant() -in $Extensions) { $path }
        }
    }
}

function Get-FreezeManifest {
    $paths = @($projectFile, $module, $engineRunner, $PSCommandPath)
    $paths += @(Get-ScopedFiles (Get-ProjectPath 'Source'))
    $paths += @(Get-ScopedFiles (Get-ProjectPath 'Config'))
    $paths += @(Get-ScopedFiles (Get-ProjectPath 'profiles') -Extensions @('.json'))
    $paths += @(Get-ScopedFiles (Get-ProjectPath 'telemetry') -Extensions @('.py', '.html', '.json') -SkipLocalCaches)
    return @($paths | Sort-Object -Unique | ForEach-Object {
        $path = Assert-ProjectPath $_
        [ordered]@{ path = [IO.Path]::GetRelativePath($projectRoot, $path); sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
    })
}

function Assert-Frozen {
    param([string]$SnapshotName)
    $current = @(Get-FreezeManifest)
    ConvertTo-Json -InputObject $current -Depth 4 | Set-Content -LiteralPath (Join-Path $pilotDirectory ($SnapshotName + '.json')) -Encoding utf8
    if ((ConvertTo-Json -InputObject $frozen -Depth 4 -Compress) -ne (ConvertTo-Json -InputObject $current -Depth 4 -Compress)) {
        throw ('Frozen source/configuration/module/profile/telemetry/runner files changed: ' + $SnapshotName)
    }
}

function Get-ModeDirectories {
    param([string]$Mode)
    return @(Get-ChildItem -LiteralPath $verificationRoot -Directory -Filter ('engine-' + $Mode.ToLowerInvariant() + '-*') |
        ForEach-Object { Assert-ProjectPath $_.FullName })
}

Save-Summary
Write-Journal ([ordered]@{ event = 'pilot_initialized'; timestamp = (Get-Date).ToString('o'); plan = (Join-Path $pilotDirectory 'plan.json'); planned_cases = 9; phase = 'development' })
try {
    if ($cases.Count -ne 9 -or $seeds.Count -ne 3 -or $stages.Count -ne 3) { throw 'The predetermined pilot must contain exactly three seeds and three ordered stages per seed.' }
    foreach ($required in @($engineRunner, $projectFile, $module, $profileFile)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw ('Required built source/runner/profile missing: ' + $required) }
    }
    $frozen = @(Get-FreezeManifest)
    ConvertTo-Json -InputObject $frozen -Depth 4 | Set-Content -LiteralPath $frozenPath -Encoding utf8
    $summary.frozen_manifest_sha256 = (Get-FileHash -LiteralPath $frozenPath -Algorithm SHA256).Hash
    $frozenModuleHash = (Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash
    $frozenProfileHash = (Get-FileHash -LiteralPath $profileFile -Algorithm SHA256).Hash
    $frozenEngineRunnerHash = (Get-FileHash -LiteralPath $engineRunner -Algorithm SHA256).Hash
    $summary.status = 'running'
    Save-Summary
    foreach ($case in $cases) {
        $index = [int]$case.ordinal - 1
        $expectedStage = $index % 3
        if ($summary.completed_cases -ne $index -or $case.seed -ne $seeds[[int][Math]::Floor($index / 3)] -or
            $case.stage -ne $expectedStage + 1 -or $case.condition -ne $stages[$expectedStage].condition -or
            $case.mode -ne $stages[$expectedStage].mode) { throw 'Pilot stage/order/count differs from the predetermined nine-case plan.' }
        Assert-Frozen ('case-' + $case.ordinal + '-inputs-before')
        $directoriesBefore = @(Get-ModeDirectories $case.mode)
        $summary.running_case = $case
        $summary.current_engine_directory = $null
        Save-Summary
        Write-Journal ([ordered]@{
            event = 'case_running'; timestamp = (Get-Date).ToString('o'); case = $case
            frozen_manifest_sha256 = $summary.frozen_manifest_sha256
        })
        Write-Output ('Development pilot case ' + $case.ordinal + '/9: seed ' + $case.seed + ', ' + $case.condition)
        $childError = $null
        try {
            # Call the reviewed runner synchronously: it creates/bounds only its
            # own editor process tree. No shell, parallelism, retry or cleanup.
            & $engineRunner -EngineRoot $engineFull -Mode $case.mode -Seed $case.seed -TimeoutSeconds 120
        }
        catch { $childError = $_.Exception.Message }
        $newDirectories = @(Get-ModeDirectories $case.mode | Where-Object { $_ -notin $directoriesBefore })
        if ($newDirectories.Count -eq 1) { $summary.current_engine_directory = $newDirectories[0]; Save-Summary }
        Assert-Frozen ('case-' + $case.ordinal + '-inputs-after')
        if ($newDirectories.Count -ne 1) { throw ('Expected exactly one new engine-' + $case.mode.ToLowerInvariant() + ' directory; found ' + $newDirectories.Count + '.') }
        $engineDirectory = Assert-ProjectPath $newDirectories[0]
        $resultPath = Assert-ProjectPath (Join-Path $engineDirectory 'result.json')
        $invocationPath = Assert-ProjectPath (Join-Path $engineDirectory 'invocation.json')
        $childResult = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
        $childInvocation = Get-Content -LiteralPath $invocationPath -Raw | ConvertFrom-Json
        if ($childError) { throw ('Child runner failed: ' + $childError) }
        if ($childResult.status -ne 'passed' -or $childResult.exit_code -ne 0 -or $childResult.timed_out -or
            $childResult.mode -ne $case.mode -or $childInvocation.mode -ne $case.mode -or
            $childInvocation.project -ne $projectFile -or $childInvocation.expected_profile_id -ne $case.profile_id -or
            $childInvocation.runner_sha256 -ne $frozenEngineRunnerHash -or $childInvocation.module_sha256 -ne $frozenModuleHash -or
            ('-SurviveSeed=' + $case.seed) -notin $childInvocation.arguments -or
            ('-SurviveSpeedProbe' -in $childInvocation.arguments) -ne ($case.mode -eq 'SpeedProbe') -or
            '-SurviveReferenceCooldowns' -in $childInvocation.arguments) { throw 'Child result/invocation does not match this frozen practice-profile case.' }
        $capture = $childResult.capture
        if (-not $capture -or $capture.session_id -notmatch '^[0-9a-fA-F]{32}$' -or $capture.bytes -gt 4194304 -or $capture.bytes -le 0) {
            throw 'Child result does not identify a bounded session capture.'
        }
        $rawPath = Assert-ProjectPath ([string]$capture.snapshot)
        $expectedRaw = Join-Path $engineDirectory 'capture.jsonl'
        $originalRaw = Assert-ProjectPath ([string]$capture.original_path)
        if ($rawPath -ne $expectedRaw -or $originalRaw -ne (Join-Path (Get-ProjectPath 'Saved\Telemetry') ($capture.session_id + '.jsonl'))) {
            throw 'Child capture paths do not match its unique engine directory and session.'
        }
        $rawHash = (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash
        if ($rawHash -ne $capture.sha256 -or (Get-FileHash -LiteralPath $originalRaw -Algorithm SHA256).Hash -ne $rawHash -or
            (Get-Item -LiteralPath $rawPath).Length -ne $capture.bytes) { throw 'Saved child capture fingerprint/size differs from its result.' }
        $reader = [IO.File]::OpenText($rawPath)
        try { $firstRow = $reader.ReadLine() | ConvertFrom-Json }
        finally { $reader.Dispose() }
        if ($firstRow.schema -ne 'survive-v3' -or $firstRow.session_id -ne $capture.session_id -or
            $firstRow.profile_id -ne $case.profile_id -or $firstRow.a -ne $case.seed) { throw 'Raw capture session/profile/seed does not match the planned case.' }
        $receipt = [ordered]@{
            ordinal = $case.ordinal; seed = $case.seed; stage = $case.stage; condition = $case.condition
            phase = 'development'; source_kind = 'unreal-smoke-driver'; fresh_process = $true
            engine_directory = $engineDirectory; result_path = $resultPath
            result_sha256 = (Get-FileHash -LiteralPath $resultPath -Algorithm SHA256).Hash
            invocation_path = $invocationPath; invocation_sha256 = (Get-FileHash -LiteralPath $invocationPath -Algorithm SHA256).Hash
            process_id = $childInvocation.process_id; process_started = $childInvocation.started
            session_id = $capture.session_id; raw_path = $rawPath; original_raw_path = $originalRaw
            raw_sha256 = $rawHash; raw_bytes = $capture.bytes; profile_id = $case.profile_id
            profile_path = $profileFile; profile_sha256 = $frozenProfileHash
            module_path = $module; module_sha256 = $frozenModuleHash; runner_sha256 = $frozenEngineRunnerHash
            frozen_manifest_sha256 = $summary.frozen_manifest_sha256
            status = 'capture_handoff_complete'; analysis = 'pending'
        }
        Write-Journal ([ordered]@{ event = 'case_completed'; timestamp = (Get-Date).ToString('o'); receipt = $receipt })
        $summary.receipts += $receipt
        ++$summary.completed_cases
        $summary.running_case = $null
        $summary.current_engine_directory = $null
        Save-Summary
    }
    if ($summary.completed_cases -ne 9 -or $summary.receipts.Count -ne 9) { throw 'Pilot did not complete exactly nine capture handoffs.' }
    foreach ($seed in $seeds) {
        $completed = @($summary.receipts | Where-Object { $_.seed -eq $seed })
        if ($completed.Count -ne 3 -or ($completed.condition -join '|') -ne ($stages.condition -join '|')) {
            throw ('Pilot stage counts/order are incomplete for seed ' + $seed + '.')
        }
    }
    $summary.status = 'completed'
    Write-Journal ([ordered]@{ event = 'pilot_completed'; timestamp = (Get-Date).ToString('o'); completed_cases = 9; analysis = 'pending'; phase = 'development' })
}
catch {
    $summary.status = 'failed'
    $summary.error = $_.Exception.Message
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $pilotDirectory 'runner-error.log') -Encoding utf8
    Write-Journal ([ordered]@{
        event = 'pilot_failed'; timestamp = (Get-Date).ToString('o'); error = $summary.error
        completed_cases = $summary.completed_cases; running_case = $summary.running_case
        engine_directory = $summary.current_engine_directory; phase = 'development'
    })
}
finally {
    $summary.finished = (Get-Date).ToString('o')
    Save-Summary
    Write-Output ('Preserved development pilot: ' + $pilotDirectory)
}
if ($summary.status -ne 'completed') { throw $summary.error }
Write-Output 'Nine development capture handoffs completed. Data-quality review, detector analysis, evidence bundles and case exports remain pending.'
