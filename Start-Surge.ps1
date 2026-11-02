$ErrorActionPreference = 'Stop'
$desktopFolder = Join-Path $PSScriptRoot 'desktop'
$electronPath = Join-Path $desktopFolder 'node_modules/electron/dist/electron.exe'
$rendererPath = Join-Path $desktopFolder 'dist/index.html'
if (!(Test-Path -LiteralPath $electronPath) -or !(Test-Path -LiteralPath $rendererPath)) {
    throw 'Surge setup is incomplete. Run Setup-Surge.ps1 first.'
}
# Some terminal environments set this flag; it prevents an interactive launch.
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$presentationPath = Join-Path $PSScriptRoot 'verification/window-placement.json'
if (!$env:SURGE_PRESENTATION -and (Test-Path -LiteralPath $presentationPath)) {
    # Optional local display preference; never included in the product archive.
    $env:SURGE_PRESENTATION = Get-Content -LiteralPath $presentationPath -Raw
}
Start-Process -FilePath $electronPath -ArgumentList @(('"' + $desktopFolder + '"')) -WorkingDirectory $desktopFolder -WindowStyle Normal
