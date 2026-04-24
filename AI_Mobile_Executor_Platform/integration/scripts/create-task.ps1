param(
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$BearerToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN,
    [string]$PayloadPath
)

. (Join-Path $PSScriptRoot "common.ps1")

if (-not $PayloadPath) {
    $PayloadPath = Get-DefaultPayloadPath -FileName "create-task-googlemaps.json"
}

$body = Get-Content -Raw $PayloadPath
Invoke-ControlPlaneJson -Uri "$BaseUrl/api/tasks" -Method Post -BearerToken $BearerToken -Body $body -Depth 8
