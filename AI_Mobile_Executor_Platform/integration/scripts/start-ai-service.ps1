param(
    [string]$ProviderMode = $env:EXECUTOR_AI_PROVIDER_MODE
)

. (Join-Path $PSScriptRoot "common.ps1")

Ensure-Java17
$maven = Resolve-MavenCommand
$serviceDir = Join-Path (Get-PlatformRepoRoot) "services\\executor-ai-service"

if (-not $ProviderMode) {
    $ProviderMode = "stub"
}
$env:EXECUTOR_AI_PROVIDER_MODE = $ProviderMode

Push-Location $serviceDir
try {
    $arguments = @("spring-boot:run")
    if ($env:AI_SERVICE_JVM_ARGS) {
        $arguments += "-Dspring-boot.run.jvmArguments=$($env:AI_SERVICE_JVM_ARGS)"
    }

    & $maven @arguments
}
finally {
    Pop-Location
}
