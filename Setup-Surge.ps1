param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE." }
}

$pythonPath = (Get-Command $Python -ErrorAction Stop).Source
Invoke-Checked $pythonPath @('-I', '-c', "import sys, tkinter; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'")
Invoke-Checked 'node' @('-e', "const [a,b]=process.versions.node.split('.').map(Number); if(a<22 || (a===22 && b<12)) throw Error('Node 22.12 or newer is required');")
Invoke-Checked 'pnpm' @('--version')
$environmentPath = Join-Path $PSScriptRoot '.venv'
if (!(Test-Path -LiteralPath (Join-Path $environmentPath 'Scripts/python.exe'))) {
    Invoke-Checked $pythonPath @('-m', 'venv', '--without-pip', $environmentPath)
}
Invoke-Checked (Join-Path $environmentPath 'Scripts/python.exe') @('-I', '-c', 'import sys, tkinter; assert sys.version_info >= (3, 11)')
Push-Location (Join-Path $PSScriptRoot 'desktop')
try {
    Invoke-Checked 'pnpm' @('install', '--frozen-lockfile')
    Invoke-Checked 'node' @('node_modules/electron/install.js')
    Invoke-Checked 'pnpm' @('run', 'build')
} finally { Pop-Location }
Write-Output 'Surge is ready. Open Start-Surge.cmd.'
