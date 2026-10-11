param(
    [string]$Python = "",
    [string]$LogsRoot = "",
    [string]$DataRoot = "",
    [string]$Checkpoint = "",
    [switch]$Build
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $repoRoot ".venv/Scripts/python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found. Pass -Python with your existing venv executable." }
if ($Build -or -not (Test-Path -LiteralPath (Join-Path $repoRoot "apps/overlay-ui/dist/index.html"))) {
    Push-Location (Join-Path $repoRoot "apps/overlay-ui")
    try {
        & pnpm.cmd install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed" }
        & pnpm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Vue build failed" }
    } finally { Pop-Location }
}
$liveArguments = @((Join-Path $repoRoot "scripts/run_manamind.py"), "--overlay")
if ($LogsRoot) { $liveArguments += @("--logs-root", $LogsRoot) }
if ($DataRoot) { $liveArguments += @("--data-root", $DataRoot) }
if ($Checkpoint) { $liveArguments += @("--checkpoint", $Checkpoint) }
& $Python @liveArguments
exit $LASTEXITCODE
