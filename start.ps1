param([int]$Port = 8000)

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

$ip = Get-LanIp
$env:DINO_PORT = $Port

Write-Host ""
Write-Host "  DinoStanice" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Scéna na televizi:  " -NoNewline; Write-Host "http://${ip}:$Port/" -ForegroundColor Cyan
Write-Host "  Mobil — focení:     " -NoNewline; Write-Host "http://${ip}:$Port/pridat" -ForegroundColor Cyan
Write-Host "  QR kód pro mobil:   " -NoNewline; Write-Host "http://${ip}:$Port/api/qr" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  Mobil musí být na stejné wifi. Ukončení serveru: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

python -m uvicorn server:app --host 0.0.0.0 --port $Port
