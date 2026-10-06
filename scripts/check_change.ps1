param(
    [string]$TestPath = "",
    [string]$Keyword = "",
    [switch]$Packaging,
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Pass([string]$message) { Write-Output ("PASS " + $message) }
function Fail([string]$message) { Write-Output ("FAIL " + $message); exit 1 }

if (-not (Test-Path -LiteralPath $python)) { Fail "project virtual environment is missing" }

& git -C $projectRoot diff --check
if ($LASTEXITCODE -ne 0) { Fail "git diff --check" }
Pass "diff"

$bridgeA = & git -C $projectRoot hash-object "bridge/kompas_bridge.py"
$bridgeB = & git -C $projectRoot hash-object "src/kompas_mcp/assets/bridge/kompas_bridge.py"
if ($bridgeA -ne $bridgeB) { Fail "bridge copies differ" }
Pass "bridge parity"

& $python -m py_compile `
    (Join-Path $projectRoot "src\kompas_mcp\adapter.py") `
    (Join-Path $projectRoot "src\geomwright\studio\registry.py")
if ($LASTEXITCODE -ne 0) { Fail "compile" }
Pass "compile"

$bundledPython = "C:\ProgramData\ASCON\KOMPAS-3D\23\Python 3\App\python.exe"
if (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython -m py_compile (Join-Path $projectRoot "bridge\kompas_bridge.py")
    if ($LASTEXITCODE -ne 0) { Fail "bundled bridge compile (Python 3.2)" }
    Pass "bundled bridge compile"
}

if ($TestPath) {
    $pytestArgs = @("-m", "pytest", $TestPath, "-q", "--tb=short")
    if ($Keyword) { $pytestArgs += @("-k", $Keyword) }
    & $python @pytestArgs
    if ($LASTEXITCODE -ne 0) { Fail "focused tests" }
    Pass "focused tests"
}

if ($Full) {
    $resultDir = Join-Path $projectRoot "test-results"
    New-Item -ItemType Directory -Force -Path $resultDir | Out-Null
    $junit = Join-Path $resultDir "quality-full.xml"
    & $python -m pytest -q --tb=no --junitxml=$junit *> $null
    $testCode = $LASTEXITCODE
    & $python (Join-Path $PSScriptRoot "summarize_junit.py") $junit --output (Join-Path $resultDir "quality-full.json")
    if ($testCode -ne 0) { Fail "full tests; see test-results/quality-full.json" }
    Pass "full tests"
}

$trackedLeak = & git -C $projectRoot grep -n -I -E 'C:\\Users\\|685F~1|BEGIN (RSA|OPENSSH|PRIVATE)' -- 'src/**' 'bridge/**' '*.cmd' 'pyproject.toml'
if ($LASTEXITCODE -eq 0 -and $trackedLeak) { Fail "tracked machine path or private key marker" }
Pass "tracked path scan"

if ($Packaging) {
    $wheelDir = Join-Path $env:TEMP "geomwright-quality-wheel"
    New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
    & $python -m pip wheel $projectRoot --no-deps --wheel-dir $wheelDir --quiet
    if ($LASTEXITCODE -ne 0) { Fail "wheel build" }
    Pass "wheel build"
}

$untracked = & git -C $projectRoot status --short --untracked-files=all
$binary = @($untracked | Where-Object { $_ -match '\.(pdf|bmp|m3d|zip|exe|dll)$' })
if ($binary.Count -gt 0) { Write-Output ("WARN untracked binary/document files: " + $binary.Count) }

Pass "quality gate"
