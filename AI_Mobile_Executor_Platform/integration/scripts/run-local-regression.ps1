param(
    [switch]$SkipGovernance,
    [switch]$SkipControl,
    [switch]$SkipAi,
    [switch]$SkipConsole
)

. (Join-Path $PSScriptRoot "common.ps1")

Ensure-Java17
$repoRoot = Get-PlatformRepoRoot
$maven = Resolve-MavenCommand
$npm = Resolve-NpmCommand

function Invoke-RepoCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "==> $WorkingDirectory :: $Command $($Arguments -join ' ')"
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipGovernance) {
    Invoke-RepoCommand -WorkingDirectory $repoRoot -Command "powershell" -Arguments @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "integration\\scripts\\check-repository-governance.ps1"))
}

if (-not $SkipControl) {
    Invoke-RepoCommand -WorkingDirectory (Join-Path $repoRoot "services\\executor-control-service") -Command $maven -Arguments @("test")
}

if (-not $SkipAi) {
    Invoke-RepoCommand -WorkingDirectory (Join-Path $repoRoot "services\\executor-ai-service") -Command $maven -Arguments @("test")
}

if (-not $SkipConsole) {
    Invoke-RepoCommand -WorkingDirectory (Join-Path $repoRoot "apps\\executor-console-web") -Command $npm -Arguments @("run", "test")
}
