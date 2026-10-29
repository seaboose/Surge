param(
    [ValidateRange(5, 120)][int]$TimeoutSeconds = 60
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$attempt = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDirectory = [IO.Path]::GetFullPath((Join-Path $projectRoot ('Saved\Verification\portable-' + $attempt)))
if (-not $runDirectory.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Verification output must remain inside this project.'
}
New-Item -ItemType Directory -Path $runDirectory | Out-Null

# Use only this already-installed compiler and SDK. No installer, engine build,
# registry mutation, environment persistence, cleanup, or network access occurs.
$vcRoot = 'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207'
$sdkRoot = 'C:\Program Files (x86)\Windows Kits\10'
$sdkVersion = '10.0.26100.0'
$compilerDirectory = Join-Path $vcRoot 'bin\Hostx64\x64'
$compiler = Join-Path $compilerDirectory 'cl.exe'
$source = Join-Path $projectRoot 'portable\survive_sim_checks.cpp'
$header = Join-Path $projectRoot 'Source\SurgeMovementLab\SurviveSim.h'
$executable = Join-Path $runDirectory 'survive_sim_checks.exe'
$object = Join-Path $runDirectory 'survive_sim_checks.obj'
$pdb = Join-Path $runDirectory 'survive_sim_checks.pdb'
$includePaths = @(
    (Join-Path $vcRoot 'include'),
    (Join-Path $sdkRoot ('Include\' + $sdkVersion + '\ucrt')),
    (Join-Path $sdkRoot ('Include\' + $sdkVersion + '\shared')),
    (Join-Path $sdkRoot ('Include\' + $sdkVersion + '\um'))
)
$libraryPaths = @(
    (Join-Path $vcRoot 'lib\x64'),
    (Join-Path $sdkRoot ('Lib\' + $sdkVersion + '\ucrt\x64')),
    (Join-Path $sdkRoot ('Lib\' + $sdkVersion + '\um\x64'))
)
$compileArguments = @('/nologo', '/std:c++17', '/permissive-', '/Zc:__cplusplus', '/W4', '/WX', '/EHsc', '/MT', '/fp:precise',
    ('/Fo' + $object), ('/Fe' + $executable), ('/Fd' + $pdb), $source,
    '/link', '/INCREMENTAL:NO', ('/PDB:' + $pdb))
$started = (Get-Date).ToString('o')
$result = [ordered]@{
    started = $started
    finished = $null
    status = 'starting'
    compile_exit_code = $null
    checks_exit_code = $null
    error = $null
    scope = 'Shared C++17 math only; not Unreal/UHT, gameplay integration, or playtest validation.'
}
$invocation = [ordered]@{
    started = $started
    project = $projectRoot
    working_directory = $runDirectory
    compiler = $compiler
    compiler_file_version = $null
    compiler_sha256 = $null
    source = $source
    source_sha256 = $null
    shared_header = $header
    shared_header_sha256 = $null
    runner_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
    compile_arguments = $compileArguments
    include_paths = $includePaths
    library_paths = $libraryPaths
    sdk_version = $sdkVersion
    process_timeout_seconds = $TimeoutSeconds
    shutdown_and_output_grace_seconds = 10
    executable = $executable
    checks_arguments = @()
    inherited_compiler_flags_cleared = @('CL', '_CL_', 'LINK', '_LINK_')
    scope = $result.scope
}
$invocationPath = Join-Path $runDirectory 'invocation.json'
# Record the intended invocation even when dependency validation fails.
$invocation | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $invocationPath -Encoding utf8

function Invoke-RecordedProcess {
    param([string]$File, [string[]]$Arguments, [string]$Name, [hashtable]$Environment)
    if ($null -eq [Diagnostics.Process].GetMethod('Kill', [type[]]@([bool]))) {
        throw 'Use pwsh (PowerShell 7 or newer), which supports bounded process-tree termination.'
    }
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $File
    # Every argument is a known path or constant; quotes are not allowed inside.
    # Do not invoke a shell: filenames cannot become executable shell syntax.
    foreach ($argument in $Arguments) {
        if ($argument.Contains('"')) { throw 'An unexpected quote was present in a process argument.' }
    }
    $startInfo.Arguments = (($Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' ')
    $startInfo.WorkingDirectory = $runDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($key in $Environment.Keys) { $startInfo.EnvironmentVariables[$key] = $Environment[$key] }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    $processStarted = $false
    $stdoutPath = Join-Path $runDirectory ($Name + '.stdout.log')
    $stderrPath = Join-Path $runDirectory ($Name + '.stderr.log')
    '' | Set-Content -LiteralPath $stdoutPath -Encoding utf8
    '' | Set-Content -LiteralPath $stderrPath -Encoding utf8
    try {
        if (-not $process.Start()) { throw ($Name + ' could not start.') }
        $processStarted = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
        if ($timedOut) {
            # Terminate only this owned process and its compiler/linker children.
            $process.Kill($true)
            if (-not $process.WaitForExit(5000)) {
                throw ($Name + ' exceeded its timeout and did not terminate within the five-second shutdown limit.')
            }
        }
        $outputTasks = [Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
        if (-not [Threading.Tasks.Task]::WaitAll($outputTasks, 5000)) {
            '[Output did not finish draining within the five-second limit.]' |
                Set-Content -LiteralPath $stderrPath -Encoding utf8
            throw ($Name + ' output did not finish within its bounded drain limit.')
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $stdout | Set-Content -LiteralPath $stdoutPath -Encoding utf8
        $stderr | Set-Content -LiteralPath $stderrPath -Encoding utf8
        if ($stdout) { Write-Host $stdout.TrimEnd() }
        if ($stderr) { Write-Host $stderr.TrimEnd() }
        if ($timedOut) { throw ($Name + ' exceeded its bounded ' + $TimeoutSeconds + '-second limit.') }
        return $process.ExitCode
    }
    finally {
        try {
            if ($processStarted -and -not $process.HasExited) { $process.Kill($true) }
        }
        finally { $process.Dispose() }
    }
}

try {
    $requiredPaths = @($compiler, $source, $header) + $includePaths + $libraryPaths
    foreach ($path in $requiredPaths) {
        if (-not (Test-Path -LiteralPath $path)) { throw ('Required installed dependency or source missing: ' + $path) }
    }
    $processEnvironment = @{
        INCLUDE = ($includePaths -join ';')
        LIB = ($libraryPaths -join ';')
        PATH = $compilerDirectory + ';' + $env:PATH
        TEMP = $runDirectory
        TMP = $runDirectory
        # Prevent inherited compiler flags from changing the reviewed invocation.
        CL = ''
        _CL_ = ''
        LINK = ''
        _LINK_ = ''
    }
    $invocation.compiler_file_version = (Get-Item -LiteralPath $compiler).VersionInfo.FileVersion
    $invocation.compiler_sha256 = (Get-FileHash -LiteralPath $compiler -Algorithm SHA256).Hash
    $invocation.source_sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $invocation.shared_header_sha256 = (Get-FileHash -LiteralPath $header -Algorithm SHA256).Hash
    $invocation | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $invocationPath -Encoding utf8
    Copy-Item -LiteralPath $source -Destination (Join-Path $runDirectory 'survive_sim_checks.cpp.snapshot')
    Copy-Item -LiteralPath $header -Destination (Join-Path $runDirectory 'SurviveSim.h.snapshot')
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $runDirectory 'check-portable.ps1.snapshot')
    $result.status = 'compiling'
    $result.compile_exit_code = Invoke-RecordedProcess -File $compiler -Arguments $compileArguments -Name 'compile' -Environment $processEnvironment
    if ($result.compile_exit_code -ne 0) { throw ('Portable compilation failed with exit code ' + $result.compile_exit_code + '.') }
    $result.status = 'checking'
    $result.checks_exit_code = Invoke-RecordedProcess -File $executable -Arguments @() -Name 'checks' -Environment $processEnvironment
    if ($result.checks_exit_code -ne 0) { throw ('Portable checks failed with exit code ' + $result.checks_exit_code + '.') }
    $result['executable_sha256'] = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash
    $result['source_after_sha256'] = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $result['shared_header_after_sha256'] = (Get-FileHash -LiteralPath $header -Algorithm SHA256).Hash
    if ($result.source_after_sha256 -ne $invocation.source_sha256 -or
        $result.shared_header_after_sha256 -ne $invocation.shared_header_sha256) {
        throw 'Sources changed during verification; run the saved invocation again against stable sources.'
    }
    $result.status = 'passed'
}
catch {
    $result.status = 'failed'
    $result.error = $_.Exception.Message
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $runDirectory 'runner-error.log') -Encoding utf8
}
finally {
    $result.finished = (Get-Date).ToString('o')
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding utf8
    Write-Output ('Preserved portable verification: ' + $runDirectory)
}
if ($result.status -ne 'passed') { throw $result.error }
Write-Output 'Portable shared-math checks passed. Unreal compilation and runtime integration remain unverified.'
