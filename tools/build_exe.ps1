param([switch]$OneFile, [switch]$NoZip)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Doinstalovavam PyInstaller..." -ForegroundColor Yellow
    python -m pip install --quiet -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "instalace PyInstalleru selhala" }
}

if ($OneFile) { $env:DINO_ONEFILE = "1" } else { Remove-Item Env:DINO_ONEFILE -ErrorAction SilentlyContinue }

python -m PyInstaller --noconfirm --clean dinostanice.spec
if ($LASTEXITCODE -ne 0) { throw "build selhal" }

if ($OneFile) {
    $exe = "dist\DinoStanice.exe"
    Write-Host ""
    Write-Host "  Hotovo: $exe ($([math]::Round((Get-Item $exe).Length / 1MB)) MB)" -ForegroundColor Green
    exit 0
}

$size = [math]::Round((Get-ChildItem dist\DinoStanice -Recurse -File | Measure-Object -Sum Length).Sum / 1MB)
Write-Host ""
Write-Host "  Hotovo: dist\DinoStanice\DinoStanice.exe (slozka $size MB)" -ForegroundColor Green

if (-not $NoZip) {
    $zip = "dist\DinoStanice-win64.zip"
    if (Test-Path $zip) { Remove-Item $zip }
    Write-Host "  Zipuji (chvili to trva)..." -ForegroundColor DarkGray
    Compress-Archive -Path dist\DinoStanice -DestinationPath $zip
    Write-Host "  Prenosny balik: $zip ($([math]::Round((Get-Item $zip).Length / 1MB)) MB)" -ForegroundColor Green
}
