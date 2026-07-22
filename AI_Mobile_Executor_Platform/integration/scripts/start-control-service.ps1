param(
    [string]$SpringProfile = "local-docker",
    [string]$DeviceId = $env:PLATFORM_CONTROL_DEVICE_ID,
    [string]$DeviceToken = $env:PLATFORM_CONTROL_DEVICE_TOKEN,
    [string]$DeviceTokensJson = $env:P2_3C_DEVICE_TOKENS_JSON,
    [string]$AdminAuthToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN,
    [string]$MinioEndpoint = $env:MINIO_ENDPOINT,
    [switch]$AllowUnsignedDevices
)

. (Join-Path $PSScriptRoot "common.ps1")

Ensure-Java17
$maven = Resolve-MavenCommand
$serviceDir = Join-Path (Get-PlatformRepoRoot) "services\\executor-control-service"
$jvmArgs = @()

if ($DeviceId -or $DeviceToken) {
    if (-not $DeviceId -or -not $DeviceToken) {
        throw "DeviceId and DeviceToken must be provided together."
    }
    $jvmArgs += "-Dplatform.control.auth.device-tokens[$DeviceId]=$DeviceToken"
}

if ($DeviceTokensJson) {
    try {
        $deviceTokens = $DeviceTokensJson | ConvertFrom-Json
    }
    catch {
        throw "DeviceTokensJson must be a JSON object mapping device IDs to non-blank tokens."
    }
    if (-not ($deviceTokens -is [PSCustomObject])) {
        throw "DeviceTokensJson must be a JSON object mapping device IDs to non-blank tokens."
    }
    $deviceTokenEntries = @($deviceTokens.PSObject.Properties)
    if ($deviceTokenEntries.Count -eq 0) {
        throw "DeviceTokensJson must contain at least one device token."
    }
    foreach ($entry in $deviceTokenEntries) {
        $configuredDeviceId = [string]$entry.Name
        $configuredToken = [string]$entry.Value
        if (-not ($entry.Value -is [string]) -or [string]::IsNullOrWhiteSpace($configuredDeviceId) -or [string]::IsNullOrWhiteSpace($configuredToken)) {
            throw "DeviceTokensJson device IDs and tokens must be non-blank strings."
        }
        if ($DeviceId -and $configuredDeviceId -eq $DeviceId) {
            throw "Device $configuredDeviceId is configured by both DeviceId/DeviceToken and DeviceTokensJson."
        }
        $jvmArgs += "-Dplatform.control.auth.device-tokens[$configuredDeviceId]=$configuredToken"
    }
}

if ($AdminAuthToken) {
    $jvmArgs += "-Dplatform.control.admin.auth-token=$AdminAuthToken"
}

if ($MinioEndpoint) {
    $absoluteUri = $null
    if (-not [Uri]::TryCreate($MinioEndpoint, [UriKind]::Absolute, [ref]$absoluteUri)) {
        throw "MinioEndpoint must be an absolute URL, for example http://192.168.3.18:9000."
    }
}

if ($AllowUnsignedDevices.IsPresent) {
    $jvmArgs += "-Dplatform.control.auth.allow-unsigned-devices=true"
}

if ($env:CONTROL_SERVICE_JVM_ARGS) {
    $jvmArgs += $env:CONTROL_SERVICE_JVM_ARGS
}

Push-Location $serviceDir
try {
    $previousMinioEndpoint = $env:MINIO_ENDPOINT
    if ($MinioEndpoint) {
        $env:MINIO_ENDPOINT = $MinioEndpoint
    }

    $arguments = @(
        "spring-boot:run",
        "-Dspring-boot.run.profiles=$SpringProfile"
    )
    if ($jvmArgs.Count -gt 0) {
        $arguments += "-Dspring-boot.run.jvmArguments=$($jvmArgs -join ' ')"
    }

    & $maven @arguments
}
finally {
    if ($PSBoundParameters.ContainsKey("MinioEndpoint")) {
        if ($previousMinioEndpoint) {
            $env:MINIO_ENDPOINT = $previousMinioEndpoint
        } else {
            Remove-Item Env:\MINIO_ENDPOINT -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
