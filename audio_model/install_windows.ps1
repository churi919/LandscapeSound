param(
    [switch]$IncludeMedium,
    [switch]$AcceptModelLicense
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $PSScriptRoot
$env:TEMP = Join-Path $PSScriptRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache\uv'
New-Item -ItemType Directory -Path $env:TEMP,$env:PIP_CACHE_DIR,$env:UV_CACHE_DIR -Force | Out-Null

if (-not $AcceptModelLicense) {
    throw 'Review model_LICENSE.md, model_LICENSE_GEMMA.md and the model card. If their licensed-use conditions suit your use, rerun with -AcceptModelLicense. This script does not accept gated-service agreements.'
}

$audioPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$mainPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$taskUv = Get-Command uv.exe,uv -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not (Test-Path -LiteralPath $audioPython)) {
    $taskLauncher = Get-Command py.exe,py -ErrorAction SilentlyContinue | Select-Object -First 1
    if (Test-Path -LiteralPath $mainPython) { & $mainPython -m venv .venv }
    elseif ($taskLauncher) { & $taskLauncher.Source -3.11 -m venv .venv }
    elseif ($taskUv) { & $taskUv.Source venv --python 3.11 .venv }
    else { throw 'Install the main Python 3.11 environment or uv first.' }
    if ($LASTEXITCODE -ne 0) { throw 'Independent audio environment creation failed.' }
}
& $audioPython -c 'import sys; assert sys.version_info[:2] == (3, 11), "The audio environment must use Python 3.11"'
if ($LASTEXITCODE -ne 0) { throw 'Existing audio environment is not Python 3.11.' }

if ($taskUv) { & $taskUv.Source pip install --python $audioPython -r (Join-Path $PSScriptRoot 'requirements-lock.txt') }
else { & $audioPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-lock.txt') }
if ($LASTEXITCODE -ne 0) { throw 'Independent audio dependency installation failed.' }

$runtimeFolder = Join-Path $PSScriptRoot 'stable-audio-3'
$officialRepository = 'https://github.com/Stability-AI/stable-audio-3.git'
$codeRevision = '77e0398c26f7d22d801ec1bb036307e8b231f741'
$taskGit = Get-Command git.exe,git -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $taskGit) { throw 'Install Git for Windows to retrieve the pinned official runtime.' }
if (-not (Test-Path -LiteralPath $runtimeFolder)) {
    & $taskGit.Source clone --no-checkout $officialRepository $runtimeFolder
    if ($LASTEXITCODE -ne 0) { throw 'Official runtime checkout download failed.' }
    & $taskGit.Source -C $runtimeFolder checkout --detach $codeRevision
    if ($LASTEXITCODE -ne 0) { throw 'Pinned official runtime revision was not found.' }
} else {
    $actualRevision = & $taskGit.Source -C $runtimeFolder rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $actualRevision.Trim() -ne $codeRevision) {
        throw 'Existing runtime has a different revision. It was preserved; use a fresh checkout or review it manually.'
    }
    $runtimeChanges = & $taskGit.Source -C $runtimeFolder status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $runtimeChanges) { throw 'Existing official runtime contains changes; preserved without modification.' }
}

if ($IncludeMedium) { & $audioPython (Join-Path $PSScriptRoot 'download_weights.py') --include-medium }
else { & $audioPython (Join-Path $PSScriptRoot 'download_weights.py') }
if ($LASTEXITCODE -ne 0) { throw 'Model download or verification failed. No gated terms were accepted.' }
Write-Output 'Independent pinned Stable Audio runtime ready. Model weights and upstream code remain local and are not committed.'
