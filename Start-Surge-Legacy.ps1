$ErrorActionPreference = 'Stop'
$runtimePath = if ($env:SURGE_PYTHON) { $env:SURGE_PYTHON } else { Join-Path $PSScriptRoot '.venv/Scripts/python.exe' }
if (!(Test-Path -LiteralPath $runtimePath -PathType Leaf)) { throw 'Run Setup-Surge.ps1 first.' }
$applicationPath = Join-Path $PSScriptRoot 'app.py'
Start-Process -FilePath $runtimePath -ArgumentList @('-B', ('"' + $applicationPath + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
