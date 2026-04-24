param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$BearerToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN,
    [string]$PayloadPath,
    [string]$DevicePoolId
)

. (Join-Path $PSScriptRoot "common.ps1")

if (-not $PayloadPath) {
    $PayloadPath = Get-DefaultPayloadPath -FileName "create-run-tiktok-smoke.json"
}

$payload = Get-Content -Raw $PayloadPath | ConvertFrom-Json
if ($DevicePoolId) {
    $payload.devicePoolId = $DevicePoolId
}
$body = $payload | ConvertTo-Json -Depth 10
Invoke-ControlPlaneJson -Uri "$BaseUrl/api/runs" -Method Post -BearerToken $BearerToken -Body $body -Depth 10
