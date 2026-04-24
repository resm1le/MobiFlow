$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-PlatformRepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
}

function Get-DefaultPayloadPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FileName
    )

    return (Join-Path (Get-PlatformRepoRoot) "integration\\payloads\\$FileName")
}

function Add-ToPathIfMissing {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    if (-not (Test-Path $Directory)) {
        return
    }

    $pathEntries = $env:Path -split ";"
    if ($pathEntries -contains $Directory) {
        return
    }

    $env:Path = "$Directory;$($env:Path)"
}

function Resolve-ToolPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName,
        [string[]]$Fallbacks = @()
    )

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        return $command.Source
    }

    foreach ($candidate in $Fallbacks) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    throw "Unable to locate tool '$CommandName'. Checked PATH and fallbacks: $($Fallbacks -join ', ')"
}

function Ensure-Java17 {
    $javaHomeCandidates = @()
    if ($env:JAVA_HOME) {
        $javaHomeCandidates += $env:JAVA_HOME
    }
    $javaHomeCandidates += @(
        "D:\\java\\jdk17",
        "C:\\Program Files\\Java\\jdk-17",
        "C:\\Program Files\\Eclipse Adoptium\\jdk-17"
    )

    foreach ($candidate in $javaHomeCandidates | Select-Object -Unique) {
        if ($candidate -and (Test-Path (Join-Path $candidate "bin\\java.exe"))) {
            $env:JAVA_HOME = $candidate
            Add-ToPathIfMissing (Join-Path $candidate "bin")
            return
        }
    }

    throw "Unable to locate JDK 17. Set JAVA_HOME or install JDK 17."
}

function Resolve-MavenCommand {
    return Resolve-ToolPath -CommandName "mvn.cmd" -Fallbacks @(
        "D:\\maven\\apache-maven-3.9.8\\bin\\mvn.cmd",
        "C:\\Program Files\\apache-maven-3.9.8\\bin\\mvn.cmd"
    )
}

function Resolve-NodeCommand {
    return Resolve-ToolPath -CommandName "node.exe" -Fallbacks @(
        "D:\\programming\\nodejs\\node.exe",
        "C:\\Program Files\\nodejs\\node.exe"
    )
}

function Resolve-NpmCommand {
    return Resolve-ToolPath -CommandName "npm.cmd" -Fallbacks @(
        "D:\\programming\\nodejs\\npm.cmd",
        "C:\\Program Files\\nodejs\\npm.cmd"
    )
}

function Resolve-AdminBearerToken {
    param(
        [string]$BearerToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN
    )

    if (-not $BearerToken -or [string]::IsNullOrWhiteSpace($BearerToken)) {
        throw "Admin bearer token is required. Pass -BearerToken or set PLATFORM_CONTROL_ADMIN_AUTH_TOKEN."
    }

    return $BearerToken
}

function Invoke-ControlPlaneJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [ValidateSet("Get", "Post")]
        [string]$Method = "Get",
        [string]$BearerToken = $env:PLATFORM_CONTROL_ADMIN_AUTH_TOKEN,
        [string]$Body,
        [int]$Depth = 10
    )

    $resolvedToken = Resolve-AdminBearerToken -BearerToken $BearerToken
    $headers = @{
        Authorization = "Bearer $resolvedToken"
    }

    if ($PSBoundParameters.ContainsKey("Body")) {
        Invoke-RestMethod -Uri $Uri -Method $Method -Headers $headers -ContentType "application/json" -Body $Body |
            ConvertTo-Json -Depth $Depth
        return
    }

    Invoke-RestMethod -Uri $Uri -Method $Method -Headers $headers |
        ConvertTo-Json -Depth $Depth
}
