param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [ValidateSet('Editor', 'Game')][string]$Target = 'Editor',
    [ValidateRange(30, 1200)][int]$TimeoutSeconds = 600,
    [ValidateRange(1, 4)][int]$MaxParallelActions = 4
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$engineFull = [IO.Path]::GetFullPath($EngineRoot).TrimEnd('\')
$attempt = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$logDirectory = Join-Path $projectRoot ('Saved\Verification\build-' + $attempt)
New-Item -ItemType Directory -Path $logDirectory | Out-Null
$targetName = if ($Target -eq 'Editor') { 'SurgeMovementLabEditor' } else { 'SurgeMovementLab' }
$projectFile = Join-Path $projectRoot 'SurgeMovementLab.uproject'
$dotnet = Join-Path $engineFull 'Engine\Binaries\ThirdParty\DotNet\10.0\win-x64\dotnet.exe'
$buildTool = Join-Path $engineFull 'Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.dll'
$headerTool = Join-Path $engineFull 'Engine\Binaries\DotNET\UnrealBuildTool\EpicGames.UHT.dll'
$buildLog = Join-Path $logDirectory 'UnrealBuildTool.log'
# Invoke the already-installed managed tools directly. No launcher, installer,
# SDK download, engine repair, source-engine build or persistent setting change.
$arguments = @($buildTool, $targetName, 'Win64', 'Development', ('-Project=' + $projectFile),
    '-WaitMutex', '-NoHotReloadFromIDE', '-NoLiveCoding', '-NoEngineChanges',
    '-NoUBA', '-NoXGE', '-NoFASTBuild', '-NoSNDBS', ('-MaxParallelActions=' + $MaxParallelActions),
    ('-Log=' + $buildLog))
$invocation = [ordered]@{
    target = $targetName; project = $projectFile; engine = $engineFull
    started = (Get-Date).ToString('o'); executable = $dotnet; arguments = $arguments
    timeout_seconds = $TimeoutSeconds; max_parallel_actions = $MaxParallelActions
    launcher_registration = 'absent'; process_id = $null
    runner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    scope = 'Project-only installed-engine build; no engine installation/repair or gameplay validation.'
}
$result = [ordered]@{ status = 'starting'; exit_code = $null; error = $null; finished = $null }
$process = $null
$processStarted = $false
function Get-SourceManifest {
    $sourceFiles = @($projectFile, $PSCommandPath) + @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'Source'), (Join-Path $projectRoot 'Config') -File -Recurse | ForEach-Object FullName)
    @($sourceFiles | Sort-Object -Unique | ForEach-Object {
        [ordered]@{ path = [IO.Path]::GetRelativePath($projectRoot, $_); sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash }
    })
}
try {
    if ($null -eq [Diagnostics.Process].GetMethod('Kill', [type[]]@([bool]))) { throw 'Use PowerShell 7 or newer for bounded child-process termination.' }
    $required = @($projectFile, $dotnet, $buildTool, $headerTool,
        (Join-Path $engineFull 'Engine\Build\InstalledBuild.txt'),
        (Join-Path $engineFull 'Engine\Build\Build.version'))
    if ($Target -eq 'Editor') { $required += Join-Path $engineFull 'Engine\Intermediate\Build\Win64\x64\UnrealEditor\Development\Engine\UnrealEditor-Engine.lib' }
    foreach ($path in $required) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Required installed file missing: ' + $path) } }
    $registryFile = 'C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat'
    if (Test-Path -LiteralPath $registryFile) {
        $installed = Get-Content -LiteralPath $registryFile -Raw | ConvertFrom-Json
        $engineRecords = @($installed.InstallationList | Where-Object { $_.InstallLocation -and $_.InstallLocation.TrimEnd('\') -eq $engineFull })
        $invocation.launcher_registration = if ($engineRecords.Count -eq 1) { 'registered' } else { 'not registered; structural prerequisites checked' }
    }
    $invocation['engine_version'] = Get-Content -LiteralPath (Join-Path $engineFull 'Engine\Build\Build.version') -Raw | ConvertFrom-Json
    $before = Get-SourceManifest
    $before | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $logDirectory 'sources-before.json') -Encoding utf8
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $logDirectory 'build-local.ps1.snapshot')
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $dotnet
    foreach ($argument in $arguments) { $startInfo.ArgumentList.Add($argument) }
    $startInfo.WorkingDirectory = Join-Path $engineFull 'Engine\Source'
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Environment['DOTNET_ROOT'] = Split-Path -Parent $dotnet
    $startInfo.Environment['DOTNET_MULTILEVEL_LOOKUP'] = '0'
    $startInfo.Environment['DOTNET_ROLL_FORWARD'] = 'LatestMajor'
    $startInfo.Environment['DOTNET_SKIP_FIRST_TIME_EXPERIENCE'] = '1'
    $startInfo.Environment['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    $startInfo.Environment['DOTNET_CLI_HOME'] = $logDirectory
    foreach ($key in @('CL', '_CL_', 'LINK', '_LINK_')) { $startInfo.Environment[$key] = '' }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'UnrealBuildTool could not start.' }
    $processStarted = $true
    $invocation.process_id = $process.Id
    $invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $logDirectory 'invocation.json') -Encoding utf8
    Write-Output ('Bounded build PID ' + $process.Id + '; preserved output: ' + $logDirectory)
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) {
        $process.Kill($true)
        if (-not $process.WaitForExit(5000)) { throw 'Build timeout: owned process tree did not stop within five seconds.' }
    }
    if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask, $stderrTask), 5000)) { throw 'Build output exceeded its five-second drain limit.' }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $stdout | Set-Content -LiteralPath (Join-Path $logDirectory 'console.stdout.log') -Encoding utf8
    $stderr | Set-Content -LiteralPath (Join-Path $logDirectory 'console.stderr.log') -Encoding utf8
    if ($stdout) { Write-Host $stdout.TrimEnd() }
    if ($stderr) { Write-Host $stderr.TrimEnd() }
    $result.exit_code = $process.ExitCode
    if ($timedOut) { throw ('Build exceeded the ' + $TimeoutSeconds + '-second limit.') }
    if ($process.ExitCode -ne 0) { throw ('Unreal build exited with code ' + $process.ExitCode + '.') }
    $after = Get-SourceManifest
    $after | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $logDirectory 'sources-after.json') -Encoding utf8
    if (($before | ConvertTo-Json -Compress) -ne ($after | ConvertTo-Json -Compress)) { throw 'Project sources changed during compilation; verify the new source separately.' }
    $result['source_manifest_sha256'] = (Get-FileHash -LiteralPath (Join-Path $logDirectory 'sources-after.json') -Algorithm SHA256).Hash
    if ($Target -eq 'Editor') {
        $moduleOutput = Join-Path $projectRoot 'Binaries\Win64\UnrealEditor-SurgeMovementLab.dll'
        if (-not (Test-Path -LiteralPath $moduleOutput -PathType Leaf)) { throw 'Build returned success without the expected project module.' }
        $result['module_sha256'] = (Get-FileHash -LiteralPath $moduleOutput -Algorithm SHA256).Hash
        $result['module_bytes'] = (Get-Item -LiteralPath $moduleOutput).Length
    }
    $result.status = 'passed'
}
catch {
    $result.status = 'failed'
    $result.error = $_.Exception.Message
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $logDirectory 'runner-error.log') -Encoding utf8
}
finally {
    if ($process) {
        try { if ($processStarted -and -not $process.HasExited) { $process.Kill($true) } }
        finally { $process.Dispose() }
    }
    $invocation | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $logDirectory 'invocation.json') -Encoding utf8
    $result.finished = (Get-Date).ToString('o')
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $logDirectory 'result.json') -Encoding utf8
    Write-Output ('Build ' + $result.status + '; preserved output: ' + $logDirectory)
}
if ($result.status -ne 'passed') { throw $result.error }
