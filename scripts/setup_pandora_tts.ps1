param(
    [switch]$Apply,
    [switch]$DownloadRuntimeModel,
    [switch]$VerifyOnly,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$LocalBase = Join-Path $env:LOCALAPPDATA "Prometheus"
$VenvDir = Join-Path $LocalBase "venvs\pandora-tts"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$ModelCache = Join-Path $LocalBase "models\pandora\chatterbox-v3"
$AudioCache = Join-Path $LocalBase "cache\pandora_tts"
$RuntimeDir = Join-Path $LocalBase "runtime"
$ConfigPath = Join-Path $Project "config\pandora_voice_models.json"
$DownloadScript = Join-Path $Project "scripts\download_pandora_model.py"

$PythonMinor = "3.11"
$TorchVersion = "2.6.0"
$ChatterboxVersion = "0.1.7"
$ChatterboxSourceRevision = "3f35dfc8fbe63e5b29793289dc68f1875bb317a5"
$ChatterboxSource = "git+https://github.com/resemble-ai/chatterbox.git@$ChatterboxSourceRevision"
$AiohttpVersion = "3.11.18"
$HuggingFaceHubVersion = "1.3.0"
$MinDiskGB = 18

function Write-Step([string]$Message) {
    Write-Host "[Pandora TTS] $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param([Parameter(Mandatory=$true)][string]$FilePath, [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Find-Python311 {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & $pyLauncher.Source -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)"
        if ($LASTEXITCODE -eq 0) { return @($pyLauncher.Source, "-3.11") }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; assert sys.version_info[:2] == (3, 11)"
        if ($LASTEXITCODE -eq 0) { return @($python.Source) }
    }
    throw "Python 3.11 was not found. Install Python 3.11 without changing the Prometheus main .venv."
}

function Test-FreeDisk {
    $drive = Get-PSDrive -Name C
    $free = [math]::Round($drive.Free / 1GB, 2)
    Write-Step "C: free space: $free GB"
    if ($free -lt $MinDiskGB) { throw "At least $MinDiskGB GB free disk is required." }
}

function Verify-Environment {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "Pandora TTS venv is missing: $VenvPython"
    }

    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    $verifyScript = Join-Path $RuntimeDir "verify_pandora_environment.py"
    $verificationCode = @'
import importlib.metadata as md
import inspect
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

assert md.version("chatterbox-tts") == "0.1.7"
assert md.version("aiohttp") == "3.11.18"
assert md.version("huggingface-hub") == "1.3.0"
assert list(inspect.signature(ChatterboxMultilingualTTS.from_pretrained).parameters) == ["device", "t3_model"]
assert list(inspect.signature(ChatterboxMultilingualTTS.from_local).parameters) == ["ckpt_dir", "device", "t3_model"]
assert "tr" in ChatterboxMultilingualTTS.get_supported_languages()

print("python=ok")
print("torch=", torch.__version__)
print("cuda_available=", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu=", torch.cuda.get_device_name(0))
'@

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $verifyScript,
        $verificationCode,
        $utf8NoBom
    )

    try {
        Invoke-Checked $VenvPython $verifyScript
    } finally {
        Remove-Item `
            -LiteralPath $verifyScript `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

if ($Remove) {
    Write-Step "Removing isolated runtime. Pandora master voice assets are preserved."
    foreach ($path in @($VenvDir, $ModelCache, $AudioCache, $RuntimeDir)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
            Write-Step "Removed $path"
        }
    }
    exit 0
}

if ($VerifyOnly) {
    Verify-Environment
    exit 0
}

Test-FreeDisk
$PythonCommand = Find-Python311

if (-not $Apply) {
    Write-Host "[DRY-RUN] Venv: $VenvDir" -ForegroundColor Yellow
    Write-Host "[DRY-RUN] torch==$TorchVersion + cu124" -ForegroundColor Yellow
    Write-Host "[DRY-RUN] Chatterbox V3 source revision: $ChatterboxSourceRevision" -ForegroundColor Yellow
    Write-Host "[DRY-RUN] aiohttp==$AiohttpVersion" -ForegroundColor Yellow
    if ($DownloadRuntimeModel) {
        Write-Host "[DRY-RUN] Download exact model revision from $ConfigPath to $ModelCache" -ForegroundColor Yellow
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $VenvDir) -Force | Out-Null
    if ($PythonCommand.Count -eq 2) {
        Invoke-Checked $PythonCommand[0] $PythonCommand[1] "-m" "venv" $VenvDir
    } else {
        Invoke-Checked $PythonCommand[0] "-m" "venv" $VenvDir
    }
}

Invoke-Checked $VenvPython "-m" "pip" "install" "--upgrade" "pip==25.1.1"
Invoke-Checked $VenvPython "-m" "pip" "install" `
    "torch==$TorchVersion" "torchaudio==$TorchVersion" `
    "--index-url" "https://download.pytorch.org/whl/cu124"
Invoke-Checked $VenvPython "-m" "pip" "install" `
    $ChatterboxSource `
    "aiohttp==$AiohttpVersion" `
    "huggingface-hub==$HuggingFaceHubVersion"

New-Item -ItemType Directory -Path $ModelCache, $AudioCache, $RuntimeDir -Force | Out-Null

if ($DownloadRuntimeModel) {
    Invoke-Checked $VenvPython $DownloadScript "--config" $ConfigPath "--cache-dir" $ModelCache
}

Verify-Environment
Write-Step "Setup completed. Main Prometheus .venv was not modified."
