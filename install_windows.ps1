param(
    [ValidateSet('cu128', 'cpu')]
    [string]$TorchBackend = 'cu128',
    [switch]$InstallNarration,
    [switch]$SkipModelDownload
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:TEMP = Join-Path $PSScriptRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache\uv'
New-Item -ItemType Directory -Path $env:TEMP,$env:PIP_CACHE_DIR,$env:UV_CACHE_DIR -Force | Out-Null
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskUv = Get-Command uv.exe,uv -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not (Test-Path -LiteralPath $projectPython)) {
    $taskLauncher = Get-Command py.exe,py -ErrorAction SilentlyContinue | Select-Object -First 1
    $taskPython = Get-Command python.exe,python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($taskLauncher) { & $taskLauncher.Source -3.11 -m venv .venv }
    elseif ($taskUv) { & $taskUv.Source venv --python 3.11 .venv }
    elseif ($taskPython) {
        & $taskPython.Source -c 'import sys; assert sys.version_info[:2] == (3, 11), "Python 3.11 is required"'
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or uv, then retry.' }
        & $taskPython.Source -m venv .venv
    }
    else { throw 'Install Python 3.11 (with the py launcher) or uv, then retry.' }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 environment creation failed.' }
}
& $projectPython -c 'import sys; assert sys.version_info[:2] == (3, 11), "The project environment must use Python 3.11"'
if ($LASTEXITCODE -ne 0) { throw 'Existing .venv is not Python 3.11; preserve it and choose a new project checkout.' }

# Select torch separately so CPU installs cannot be overwritten by the recorded CUDA pin.
$installLock = Join-Path $env:TEMP 'landscapesound-requirements.txt'
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'requirements-lock.txt') |
    Where-Object { $_ -notmatch '^torch==' } | Set-Content -LiteralPath $installLock -Encoding UTF8
$torchIndex = "https://download.pytorch.org/whl/$TorchBackend"
if ($taskUv) {
    & $taskUv.Source pip install --python $projectPython torch==2.8.0 --index-url $torchIndex
    if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
    & $taskUv.Source pip install --python $projectPython -r $installLock
} else {
    & $projectPython -m pip install torch==2.8.0 --index-url $torchIndex
    if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
    & $projectPython -m pip install -r $installLock
}
if ($LASTEXITCODE -ne 0) { throw 'Application dependency installation failed.' }

if ($InstallNarration) {
    $narrationPython = Join-Path $PSScriptRoot '.venv_narration\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $narrationPython)) {
        & $projectPython -m venv (Join-Path $PSScriptRoot '.venv_narration')
        if ($LASTEXITCODE -ne 0) { throw 'Narration environment creation failed.' }
    }
    & $narrationPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-narration-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Narration dependency installation failed.' }
}

& $projectPython (Join-Path $PSScriptRoot 'generate_demo_audio.py')
if ($LASTEXITCODE -ne 0) { throw 'Procedural comparison audio preparation failed.' }
if (-not $SkipModelDownload) {
    & $projectPython (Join-Path $PSScriptRoot 'download_models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Visual-model download failed.' }
}
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'outputs') -Force | Out-Null
& $projectPython (Join-Path $PSScriptRoot 'diagnose.py')
if ($LASTEXITCODE -ne 0) { throw 'Application diagnostics failed.' }
Write-Output 'Main environment ready. For generated scene audio, install the separate audio_model runtime; see README.md.'
