param(
    [switch]$UseExistingServer,
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

function Get-Settings {
    $json = python -c "import json; from app.core.config import get_settings; s=get_settings(); print(json.dumps({'ui_host': s.ui_host, 'ui_port': s.ui_port, 'proxy_host': s.proxy_host, 'proxy_port': s.proxy_port}))"
    return $json | ConvertFrom-Json
}

function Invoke-Api {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Url,
        [object]$Body
    )

    if ($null -ne $Body) {
        $payload = $Body | ConvertTo-Json -Depth 10
        return Invoke-RestMethod -Method $Method -Uri $Url -Body $payload -ContentType "application/json"
    }
    return Invoke-RestMethod -Method $Method -Uri $Url
}

function Wait-Health {
    param(
        [Parameter(Mandatory = $true)][string]$HealthUrl,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Method GET -Uri $HealthUrl -TimeoutSec 2
            if ($health.status -eq "healthy") {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Wait-Port {
    param(
        [Parameter(Mandatory = $true)][string]$BindHost,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $conn = Get-NetTCPConnection -LocalAddress $BindHost -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            return $true
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

function Receive-WebSocketMessage {
    param(
        [Parameter(Mandatory = $true)]$WebSocket
    )

    $buffer = New-Object byte[] 8192
    $segment = [System.ArraySegment[byte]]::new($buffer)
    $builder = New-Object System.Text.StringBuilder
    do {
        $result = $WebSocket.ReceiveAsync($segment, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()
        if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
            throw "WebSocket closed before receiving expected message"
        }
        $chunk = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)
        [void]$builder.Append($chunk)
    } while (-not $result.EndOfMessage)
    return $builder.ToString()
}

function Send-WebSocketText {
    param(
        [Parameter(Mandatory = $true)]$WebSocket,
        [Parameter(Mandatory = $true)][string]$Text
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $segment = [System.ArraySegment[byte]]::new($bytes)
    $null = $WebSocket.SendAsync(
        $segment,
        [System.Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        [System.Threading.CancellationToken]::None
    ).GetAwaiter().GetResult()
}

$serverProcess = $null
$proxyProcess = $null
$startedServer = $false
$startedProxy = $false
$originalConfig = $null

try {
    $settings = Get-Settings
    $uiHost = [string]$settings.ui_host
    $uiPort = [int]$settings.ui_port
    $proxyHost = [string]$settings.proxy_host
    $proxyPort = [int]$settings.proxy_port
    $baseUrl = "http://$uiHost`:$uiPort"
    $healthUrl = "$baseUrl/health"

    Write-Host "Smoke test target: $baseUrl"

    $serverAvailable = Wait-Health -HealthUrl $healthUrl -TimeoutSeconds 2
    if (-not $serverAvailable -and -not $UseExistingServer) {
        Write-Host "Starting API server..."
        $serverProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList @("-m", "uvicorn", "app.api.server:app", "--host", $uiHost, "--port", "$uiPort") `
            -WorkingDirectory $PSScriptRoot `
            -PassThru `
            -WindowStyle Hidden
        $startedServer = $true
    }

    if (-not (Wait-Health -HealthUrl $healthUrl -TimeoutSeconds $TimeoutSeconds)) {
        throw "Server did not become healthy at $healthUrl"
    }

    Write-Host "1/7 Health check..."
    $health = Invoke-Api -Method GET -Url $healthUrl
    if ($health.status -ne "healthy") {
        throw "Health check returned unexpected payload"
    }

    Write-Host "2/7 Config API..."
    $configEnvelope = Invoke-Api -Method GET -Url "$baseUrl/api/config"
    if (-not $configEnvelope.ok) {
        throw "GET /api/config returned ok=false"
    }
    $originalConfig = $configEnvelope.data

    Write-Host "3/7 Flows list API..."
    $flowsEnvelope = Invoke-Api -Method GET -Url "$baseUrl/api/flows?limit=5"
    if (-not $flowsEnvelope.ok) {
        throw "GET /api/flows returned ok=false"
    }

    Write-Host "4/7 WebSocket init..."
    $wsScheme = if ($baseUrl.StartsWith("https")) { "wss" } else { "ws" }
    $wsUri = [Uri]("${wsScheme}://${uiHost}:${uiPort}/ws")
    $ws = [System.Net.WebSockets.ClientWebSocket]::new()
    $null = $ws.ConnectAsync($wsUri, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()

    $initRaw = Receive-WebSocketMessage -WebSocket $ws
    $initMsg = $initRaw | ConvertFrom-Json
    if ($initMsg.event -ne "init") {
        throw "Expected first WebSocket event to be init, got: $($initMsg.event)"
    }
    Send-WebSocketText -WebSocket $ws -Text '{"event":"pong","data":{"ts":0}}'
    $null = $ws.CloseAsync(
        [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
        "ok",
        [System.Threading.CancellationToken]::None
    ).GetAwaiter().GetResult()

    Write-Host "5/7 Flow create + queue..."
    $flowId = "smoke-" + [Guid]::NewGuid().ToString("N")
    $upsertBody = @{
        id = $flowId
        request = @{
            method = "GET"
            url = "http://example.com/smoke"
            http_version = "HTTP/1.1"
            headers_raw = "Host: example.com"
            body_text = ""
            body_is_json = $false
            client_ip = "127.0.0.1"
            server_ip = "example.com"
        }
    }
    $flowEnvelope = Invoke-Api -Method POST -Url "$baseUrl/api/flows" -Body $upsertBody
    if (-not $flowEnvelope.ok -or $flowEnvelope.data.id -ne $flowId) {
        throw "Flow upsert failed"
    }

    $queueEnvelope = Invoke-Api -Method GET -Url "$baseUrl/api/flows/queue"
    if (-not $queueEnvelope.ok) {
        throw "Queue API failed"
    }
    if ($queueEnvelope.data.active -ne $flowId) {
        throw "Expected queue head '$flowId', got '$($queueEnvelope.data.active)'"
    }

    Write-Host "6/7 Request decision lifecycle..."
    $requestDecisionBody = @{
        action = "forward"
        method = "GET"
        url = "http://example.com/smoke"
        headers_raw = "Host: example.com"
        body_text = ""
        intercept_response = $true
    }
    $setReqEnvelope = Invoke-Api -Method POST -Url "$baseUrl/api/flows/$flowId/request/decision" -Body $requestDecisionBody
    if (-not $setReqEnvelope.ok) {
        throw "Setting request decision failed"
    }

    $takeReqEnvelope = Invoke-Api -Method GET -Url "$baseUrl/api/flows/$flowId/request/decision"
    if (-not $takeReqEnvelope.ok -or $null -eq $takeReqEnvelope.data.decision) {
        throw "Taking request decision failed"
    }

    Write-Host "7/7 Response attach + decision + completion..."
    $responseBody = @{
        response = @{
            method = "RESPONSE"
            url = ""
            http_version = "HTTP/1.1"
            headers_raw = "Content-Type: text/plain"
            body_text = "ok"
            body_is_json = $false
            status_code = 200
            reason = "OK"
        }
    }
    $attachEnvelope = Invoke-Api -Method PUT -Url "$baseUrl/api/flows/$flowId/response" -Body $responseBody
    if (-not $attachEnvelope.ok) {
        throw "Attaching response failed"
    }

    $respDecisionBody = @{
        action = "forward"
        status_code = 200
        reason = "OK"
        headers_raw = "Content-Type: text/plain"
        body_text = "ok"
    }
    $setRespEnvelope = Invoke-Api -Method POST -Url "$baseUrl/api/flows/$flowId/response/decision" -Body $respDecisionBody
    if (-not $setRespEnvelope.ok) {
        throw "Setting response decision failed"
    }

    $flowGetEnvelope = Invoke-Api -Method GET -Url "$baseUrl/api/flows/$flowId"
    if (-not $flowGetEnvelope.ok) {
        throw "GET /api/flows/$flowId failed"
    }
    if ($flowGetEnvelope.data.status -ne "completed") {
        throw "Expected completed status, got '$($flowGetEnvelope.data.status)'"
    }

    Write-Host "8/8 Proxy capture e2e..."
    $proxyListening = Wait-Port -BindHost $proxyHost -Port $proxyPort -TimeoutSeconds 2
    if (-not $proxyListening -and -not $UseExistingServer) {
        Write-Host "Starting proxy listener..."
        $proxyProcess = Start-Process `
            -FilePath "python" `
            -ArgumentList @("main.py", "proxy") `
            -WorkingDirectory $PSScriptRoot `
            -PassThru `
            -WindowStyle Hidden
        $startedProxy = $true
    }

    if (-not (Wait-Port -BindHost $proxyHost -Port $proxyPort -TimeoutSeconds $TimeoutSeconds)) {
        throw "Proxy did not start listening at $proxyHost`:$proxyPort"
    }

    $captureConfig = $originalConfig.PSObject.Copy()
    $captureConfig.intercept_enabled = $false
    $captureConfig.intercept_all = $true
    $captureConfig.target_ips = @()
    $setCaptureConfig = Invoke-Api -Method PUT -Url "$baseUrl/api/config" -Body $captureConfig
    if (-not $setCaptureConfig.ok) {
        throw "Failed to set temporary capture config"
    }

    $marker = "proxy_smoke_" + [Guid]::NewGuid().ToString("N")
    $targetUrl = "http://example.com/?$marker"
    $proxyUri = "http://$proxyHost`:$proxyPort"
    try {
        Invoke-WebRequest -Uri $targetUrl -Proxy $proxyUri -UseBasicParsing -TimeoutSec 15 | Out-Null
    } catch {
        # Upstream/network failures are acceptable as long as request reaches proxy.
    }

    $found = $false
    $encodedMarker = [Uri]::EscapeDataString($marker)
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Milliseconds 500
        $searchEnvelope = Invoke-Api -Method GET -Url "$baseUrl/api/flows?limit=50&search=$encodedMarker"
        if ($searchEnvelope.ok -and $searchEnvelope.data) {
            $match = $searchEnvelope.data | Where-Object { $_.url -like "*$marker*" } | Select-Object -First 1
            if ($null -ne $match) {
                $found = $true
                break
            }
        }
    }
    if (-not $found) {
        throw "Proxy capture check failed: request marker '$marker' not found in flow history"
    }

    Write-Host ""
    Write-Host "Smoke test PASSED." -ForegroundColor Green
    Write-Host "Validated: health, config, flow list, websocket init, decision lifecycle, and real proxy-capture path."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Smoke test FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if ($null -ne $originalConfig) {
        try {
            Invoke-Api -Method PUT -Url "$baseUrl/api/config" -Body $originalConfig | Out-Null
        } catch { }
    }
    if ($null -ne $ws) {
        try { $ws.Dispose() } catch { }
    }
    if ($startedProxy -and $null -ne $proxyProcess) {
        Write-Host "Stopping temporary proxy..."
        try {
            Stop-Process -Id $proxyProcess.Id -Force
        } catch { }
    }
    if ($startedServer -and $null -ne $serverProcess) {
        Write-Host "Stopping temporary API server..."
        try {
            Stop-Process -Id $serverProcess.Id -Force
        } catch { }
    }
}
