param(
    [string]$SpringProfile = "local-docker",
    [string]$DeviceId = $env:PLATFORM_CONTROL_DEVICE_ID,
    [string]$DeviceToken = $env:PLATFORM_CONTROL_DEVICE_TOKEN,
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
