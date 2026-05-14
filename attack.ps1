param(
    [int]$DelaySeconds = 2,
    [string]$ApiBase = "http://localhost:8000",
    [string]$Username = "admin",
    [string]$Password = "<Change-me>"
)

Add-Type -AssemblyName System.Net.Http
# ---- Login ----
Write-Host "`n[*] Logging in..." -ForegroundColor Cyan
$login = Invoke-RestMethod -Uri "$ApiBase/api/auth/login" `
    -Method POST -ContentType "application/x-www-form-urlencoded" `
    -Body "username=$Username&password=$Password"

$token = $login.access_token

# 🔥 Use HttpClient (MUCH faster than Invoke-RestMethod loop)
$handler = New-Object System.Net.Http.HttpClientHandler
$client = New-Object System.Net.Http.HttpClient($handler)
$client.DefaultRequestHeaders.Authorization = "Bearer $token"
$client.Timeout = [TimeSpan]::FromSeconds(10)

# ---- Kill chain ----
$kill_chain = @(
    @{ event_type="port_scan"; src_ip="203.0.113.42"; dst_ip="192.0.2.10"; dst_port=22; severity=0.5 },
    @{ event_type="brute_force"; src_ip="203.0.113.42"; dst_ip="192.0.2.10"; dst_port=22; severity=0.7 },
    @{ event_type="exploit"; src_ip="203.0.113.42"; dst_ip="192.0.2.10"; dst_port=22; severity=0.85 },
    @{ event_type="lateral_movement"; src_ip="192.0.2.10"; dst_ip="192.0.2.25"; dst_port=445; severity=0.75 },
    @{ event_type="c2"; src_ip="192.0.2.25"; dst_ip="198.51.100.77"; dst_port=443; severity=0.80 },
    @{ event_type="exfil"; src_ip="192.0.2.25"; dst_ip="198.51.100.77"; dst_port=443; severity=0.95 }
)

Write-Host "`n[*] Injecting events..." -ForegroundColor Cyan

foreach ($evt in $kill_chain) {
    $evt.timestamp = (Get-Date).ToString("o")
    $evt.source = "simulator"
    $evt.protocol = "tcp"

    $json = $evt | ConvertTo-Json -Compress
    $content = New-Object System.Net.Http.StringContent($json, [System.Text.Encoding]::UTF8, "application/json")

    try {
        # 🔥 Send without heavy blocking parsing
        $response = $client.PostAsync("$ApiBase/api/events/ingest", $content).Result

        Write-Host ("[+] {0} → {1}:{2}" -f $evt.event_type, $evt.dst_ip, $evt.dst_port) -ForegroundColor Green
    }
    catch {
        Write-Host ("[-] Failed: {0}" -f $_) -ForegroundColor Red
    }

    Start-Sleep -Seconds $DelaySeconds
}

Write-Host "`n[+] Done." -ForegroundColor Cyan