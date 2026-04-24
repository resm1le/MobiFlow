param(
    [string]$DeviceId = "492b48579dd8e614",
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$BearerToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN
)

. (Join-Path $PSScriptRoot "common.ps1")

Invoke-ControlPlaneJson -Uri "$BaseUrl/api/devices/$DeviceId" -Method Get -BearerToken $BearerToken -Depth 8
