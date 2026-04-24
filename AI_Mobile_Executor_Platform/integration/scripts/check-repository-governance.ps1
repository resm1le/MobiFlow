param()

. (Join-Path $PSScriptRoot "common.ps1")

$repoRoot = Get-PlatformRepoRoot
$errors = New-Object System.Collections.Generic.List[string]

function Add-Error {
    param([string]$Message)
    $script:errors.Add($Message)
}

function Get-MarkdownFiles {
    $roots = @(
        (Join-Path $repoRoot "README.md"),
        (Join-Path $repoRoot "docs"),
        (Join-Path $repoRoot "services"),
        (Join-Path $repoRoot "apps"),
        (Join-Path $repoRoot "integration")
    )

    foreach ($root in $roots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $item = Get-Item $root
        if (-not $item.PSIsContainer) {
            $item
            continue
        }
        Get-ChildItem $root -Recurse -File | Where-Object { $_.Extension -eq ".md" -or $_.Name -eq "README.md" }
    }
}

function Assert-NoMatches {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Patterns,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $files = Get-MarkdownFiles
    $matches = $files | Select-String -Pattern $Patterns
    foreach ($match in $matches) {
        Add-Error ("{0}: {1}:{2}" -f $Description, $match.Path, $match.LineNumber)
    }
}

function Assert-PathMissing {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $fullPath = Join-Path $repoRoot $RelativePath
    if (Test-Path $fullPath) {
        Add-Error ("Forbidden path exists: {0}" -f $fullPath)
    }
}

function Assert-DirectoryEntries {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string[]]$AllowedEntries
    )

    $fullPath = Join-Path $repoRoot $RelativePath
    if (-not (Test-Path $fullPath)) {
        Add-Error ("Missing directory: {0}" -f $fullPath)
        return
    }

    $actual = Get-ChildItem $fullPath -Force | Select-Object -ExpandProperty Name
    $unexpected = $actual | Where-Object { $_ -notin $AllowedEntries }
    foreach ($entry in $unexpected) {
        Add-Error ("Unexpected entry in {0}: {1}" -f $fullPath, $entry)
    }
}

$rootAllowed = @(".github", "apps", "docs", "integration", "services", ".editorconfig", ".gitattributes", ".gitignore", "LICENSE", "README.md")
Assert-DirectoryEntries -RelativePath "." -AllowedEntries $rootAllowed

$docsAllowed = @("README.md", "project-overview.md", "android-terminal.md", "architecture.md", "protocol.md", "control-plane.md", "agent-tool-server.md", "ai-service.md", "console.md", "data-model.md", "operations.md")
Assert-DirectoryEntries -RelativePath "docs" -AllowedEntries $docsAllowed

$integrationAllowed = @("README.md", "payloads", "scripts", "validation.md")
Assert-DirectoryEntries -RelativePath "integration" -AllowedEntries $integrationAllowed

$forbiddenPaths = @(
    "run-logs",
    "output",
    "integration\checklists",
    "integration\logs",
    ".m2-repo",
    ".m2-repo-ai",
    ".npm-cache",
    ".vscode",
    "apps\executor-console-web\node_modules",
    "apps\executor-console-web\dist",
    "services\executor-control-service\target",
    "services\executor-ai-service\target",
    "services\executor-ai-service\.m2",
    "apps\executor-console-web\tsconfig.app.tsbuildinfo",
    "apps\executor-console-web\tsconfig.node.tsbuildinfo"
)

foreach ($path in $forbiddenPaths) {
    Assert-PathMissing -RelativePath $path
}

$forbiddenNarrativePatterns = @(
    "\binterview\b",
    "\bbrief\b",
    "\bmilestone\b",
    "\bproposal\b",
    "\bpackaging\b",
    "\bhandoff\b",
    "phase 1",
    "phase 2",
    "latest rerun",
    "Current Status",
    "current priority",
    "Date:",
    "resume-worthy",
    "resume-ready",
    "resume project"
)

Assert-NoMatches -Patterns $forbiddenNarrativePatterns -Description "Forbidden narrative term"

$forbiddenLegacyPathPatterns = @(
    "21-delivery",
    "22-kickoff",
    "23-executor-briefs",
    "00-project",
    "01-architecture",
    "02-protocol",
    "03-domain",
    "04-data",
    "10-control",
    "11-ai",
    "12-console",
    "13-integration",
    "14-ops"
)

Assert-NoMatches -Patterns $forbiddenLegacyPathPatterns -Description "Forbidden legacy path"

if ($errors.Count -gt 0) {
    Write-Host "Repository governance check failed:" -ForegroundColor Red
    $errors | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "Repository governance check passed." -ForegroundColor Green
