param(
    [string]$ControlApiBaseUrl = "http://127.0.0.1:8080",
    [string]$BearerToken = $env:VITE_CONTROL_API_BEARER_TOKEN,
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 5173
)

. (Join-Path $PSScriptRoot "common.ps1")

$node = Resolve-NodeCommand
$consoleDir = Join-Path (Get-PlatformRepoRoot) "apps\\executor-console-web"

Push-Location $consoleDir
try {
    if (-not (Test-Path ".\\node_modules\\vite\\bin\\vite.js")) {
        throw "Vite is not installed. Run 'npm install' in apps\\executor-console-web first."
    }

    $env:VITE_CONTROL_API_BASE_URL = $ControlApiBaseUrl
    $env:VITE_CONTROL_API_BEARER_TOKEN = $BearerToken
    & $node ".\\node_modules\\vite\\bin\\vite.js" "--host" $ListenHost "--port" "$Port"
}
finally {
    Pop-Location
}
