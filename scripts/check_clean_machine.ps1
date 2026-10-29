param(
    [string]$Provenance,
    [string]$OutputRoot = (Join-Path $env:PUBLIC 'Documents/SQ'),
    [switch]$HostedSelfCheck
)
$ErrorActionPreference = 'Stop'
$kit = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $kit 'kit-manifest.json') -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'surge-clean-windows-kit-v1') { throw 'Unexpected qualification kit.' }
$archive = Join-Path $kit 'inputs/product.zip'
$packageManifest = Join-Path $kit 'inputs/package-manifest.json'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.product_sha256) { throw 'Product ZIP changed.' }
if ((Get-FileHash -LiteralPath $packageManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.package_manifest_sha256) { throw 'Package manifest changed.' }
if ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.bootstrap_sha256) { throw 'Bootstrap script changed.' }
$tools = [IO.Path]::GetFullPath((Join-Path $kit 'tools')) + [IO.Path]::DirectorySeparatorChar
$toolEntries = @($manifest.tool_files.PSObject.Properties)
$toolFiles = @(Get-ChildItem -LiteralPath $tools -Recurse -File)
if ($toolEntries.Count -gt 4000 -or $toolFiles.Count -ne $toolEntries.Count) { throw 'Qualification tooling file inventory changed.' }
foreach ($entry in $toolEntries) {
    $path = [IO.Path]::GetFullPath((Join-Path $tools $entry.Name))
    if (-not $path.StartsWith($tools, [StringComparison]::OrdinalIgnoreCase)) { throw 'Qualification tooling path escaped its root.' }
    $file = Get-Item -LiteralPath $path
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.Length -ne $entry.Value.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) { throw 'Qualification tooling bytes changed.' }
}
if (-not $HostedSelfCheck -and -not $Provenance) { throw 'Supply a fresh-guest provenance JSON file; hosted tests cannot qualify a clean machine.' }
$root = [IO.Path]::GetFullPath($OutputRoot)
if ($root.StartsWith('\\') -or $root.Length -gt 50) { throw 'Use a short absolute local output root (50 characters or fewer).' }
$attempt = Join-Path $root ('q' + [Guid]::NewGuid().ToString('N').Substring(0,8))
if (Test-Path -LiteralPath $attempt) { throw 'Qualification output already exists.' }
New-Item -ItemType Directory -Path $attempt | Out-Null
$drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($attempt).Substring(0,1))
if ($drive.Free -lt 12GB) { throw 'Qualification requires 12 GiB of free workspace space.' }
$application = Join-Path $attempt 'bootstrap'
Expand-Archive -LiteralPath $archive -DestinationPath $application
$python = Join-Path $application 'resources/python/python.exe'
$script = Join-Path $kit 'tools/scripts/check_clean_machine.py'
$arguments = @('-I','-B',$script,'guest','--kit',$kit,'--bootstrap',$application,'--output',$attempt)
if ($Provenance) { $arguments += @('--provenance', [IO.Path]::GetFullPath($Provenance)) }
if ($HostedSelfCheck) { $arguments += '--hosted-self-check' }
& $python @arguments
exit $LASTEXITCODE
