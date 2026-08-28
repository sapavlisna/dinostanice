param([int]$Port = 8100, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path $PSScriptRoot

function Get-LanIp {
    try {
        $sock = New-Object System.Net.Sockets.UdpClient
        $sock.Connect("8.8.8.8", 80)
        $ip = $sock.Client.LocalEndPoint.Address.ToString()
        $sock.Close()
        return $ip
    } catch {
        return "127.0.0.1"
    }
}

function Test-PortBusy([int]$p) {
    $used = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return ($used | Where-Object { $_.Port -eq $p }).Count -gt 0
}

# Nestaci vedet, ze kontejner bezi — musi drzet PRAVE tenhle port, jinak by
# se hlaska objevila i kvuli cizi sluzbe na 8000
function Test-DockerOnPort([int]$p) {
    try {
        $ports = docker ps --filter name=dinostanice --format "{{.Ports}}" 2>$null
        return ($ports -join " ") -match ":$p->"
    } catch {
        return $false
    }
}

# Python a zavislosti: bez nich se server nespusti a hlaska z uvicornu by
# uzivatele u televize neposunula nikam
try {
    $null = python -c "import sys; sys.exit(0)"
} catch {
    Write-Host ""
    Write-Host "  Python 3 nenalezen. Nainstaluj ho z python.org a spust znovu." -ForegroundColor Red
    Write-Host ""
    Read-Host "  Enter zavre okno"
    exit 1
}
python -c "import cv2, numpy, fastapi, uvicorn, PIL, qrcode, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  Chybi knihovny, doinstaluji (jednorazove, chvili to trva)..." -ForegroundColor Yellow
    python -m pip install --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Instalace selhala." -ForegroundColor Red
        Read-Host "  Enter zavre okno"
        exit 1
    }
}

# Stejny port muze drzet kontejner te same stanice — pak nema smysl startovat
# druhou instanci nad tymiz ulovky, spis otevrit tu bezici
if (Test-PortBusy $Port) {
    if (Test-DockerOnPort $Port) {
        Write-Host ""
        Write-Host "  Na portu $Port uz bezi DinoStanice v Dockeru." -ForegroundColor Yellow
        Write-Host "  [O] otevrit ji v prohlizeci   [Z] zastavit Docker a spustit lokalne   [K] konec"
        $key = "$(Read-Host '  Volba')".Trim().ToUpper()
        if ($key -eq "O") {
            Start-Process "http://127.0.0.1:$Port/"
            exit 0
        } elseif ($key -eq "Z") {
            docker compose stop | Out-Null
            Start-Sleep -Seconds 2
        } else {
            exit 0
        }
    } else {
        $free = $Port
        while (Test-PortBusy $free) { $free++ }
        Write-Host ""
        Write-Host "  Port $Port drzi neco jineho, beru $free." -ForegroundColor Yellow
        $Port = $free
    }
}

$ip = Get-LanIp
$env:DINO_PORT = $Port

Write-Host ""
Write-Host "  DinoStanice" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Scena na televizi:  " -NoNewline; Write-Host "http://${ip}:$Port/" -ForegroundColor Cyan
Write-Host "  Mobil - foceni:     " -NoNewline; Write-Host "http://${ip}:$Port/pridat" -ForegroundColor Cyan
Write-Host "  Sablony k tisku:    " -NoNewline; Write-Host "http://${ip}:$Port/sablony" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Mobil musi byt na stejne wifi. Ukonceni serveru: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

if (-not $NoBrowser) {
    # scena se otevre az server odpovi, jinak by prohlizec ukazal chybu
    Start-Job -ScriptBlock {
        param($url)
        for ($i = 0; $i -lt 40; $i++) {
            try {
                Invoke-WebRequest -Uri "$url/api/scenes" -UseBasicParsing -TimeoutSec 2 | Out-Null
                Start-Process $url
                return
            } catch { Start-Sleep -Milliseconds 500 }
        }
    } -ArgumentList "http://127.0.0.1:$Port" | Out-Null
}

python -m uvicorn server:app --host 0.0.0.0 --port $Port
