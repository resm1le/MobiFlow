param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,
    [string]$BaseUrl = "http://127.0.0.1:8080",
    [string]$BearerToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN
)

. (Join-Path $PSScriptRoot "common.ps1")

Invoke-ControlPlaneJson -Uri "$BaseUrl/api/runs/$RunId/cancel" -Method Post -BearerToken $BearerToken
