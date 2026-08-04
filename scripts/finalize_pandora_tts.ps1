[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# 1. Safely resolve project root
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..") | Select-Object -ExpandProperty Path
Set-Location $ProjectRoot

Write-Host "==> Prometheus Pandora Local Voice Finalization <=="
Write-Host "Project Root: $ProjectRoot"

$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE ".local\share" }
$TtsVenvDir = Join-Path $LocalAppData "Prometheus\venvs\pandora-tts"
$TtsPython = Join-Path $TtsVenvDir "Scripts\python.exe"
$MainPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $MainPython)) {
    $MainPython = "python.exe"
}

function Exit-WithStatus {
    param(
        [string]$Status,
        [int]$Code = 1,
        [string]$Reason = ""
    )
    Write-Host "Terminal Status: $Status"
    if ($Reason) {
        Write-Error "Finalization Failed ($Status): $Reason"
    }
    exit $Code
}

# Step 1: Setup Pandora TTS Venv (-Apply)
Write-Host "1. Running setup_pandora_tts.ps1 -Apply..."
$SetupApplyScript = Join-Path $ProjectRoot "scripts\setup_pandora_tts.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupApplyScript -Apply
if ($LASTEXITCODE -ne 0) {
    Exit-WithStatus -Status "ENVIRONMENT_INVALID" -Code 1 -Reason "setup_pandora_tts.ps1 -Apply failed."
}

if (-not (Test-Path $TtsPython)) {
    Exit-WithStatus -Status "ENVIRONMENT_INVALID" -Code 1 -Reason "TTS venv python not found at $TtsPython."
}

# Step 2: Download or verify model snapshot
Write-Host "2. Downloading / verifying Pandora model snapshot..."
$ConfigPath = Join-Path $ProjectRoot "config\pandora_voice_models.json"
$ModelCacheDir = Join-Path $LocalAppData "Prometheus\models\pandora"
$DownloadScript = Join-Path $ProjectRoot "scripts\download_pandora_model.py"

$DownloadProc = & $TtsPython $DownloadScript --config $ConfigPath --cache-dir $ModelCacheDir 2>&1
$DownloadExitCode = $LASTEXITCODE

if ($DownloadExitCode -ne 0) {
    $OutStr = $DownloadProc -join "`n"
    if ($OutStr -like "*Ağ/DNS Hatası*" -or $OutStr -like "*huggingface.co*") {
        Exit-WithStatus -Status "MODEL_DOWNLOAD_FAILED" -Code 3 -Reason "Ağ/DNS Hatası: Şirket ağında huggingface.co adresine erişilemiyor. Model indirme ev internetinde yapılmalıdır."
    } elseif ($OutStr -like "*Disk Yetersizliği*") {
        Exit-WithStatus -Status "MODEL_DOWNLOAD_FAILED" -Code 5 -Reason "Disk Yetersizliği Hatası."
    } elseif ($OutStr -like "*Revision Bulunamadı*") {
        Exit-WithStatus -Status "MODEL_DOWNLOAD_FAILED" -Code 4 -Reason "Model Revision Bulunamadı."
    } else {
        Exit-WithStatus -Status "MODEL_DOWNLOAD_FAILED" -Code 3 -Reason "Model download failed: $OutStr"
    }
}
Write-Host "Model snapshot verified."

# Step 3: Verify environment ONCE
Write-Host "3. Verifying environment..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupApplyScript -VerifyOnly
if ($LASTEXITCODE -ne 0) {
    Exit-WithStatus -Status "ENVIRONMENT_INVALID" -Code 1 -Reason "setup_pandora_tts verification failed."
}

# Step 4: Validate pandora-11 profile and master reference WAV
Write-Host "4. Validating pandora-11 voice profile and reference WAV..."
$MasterDir = Join-Path $LocalAppData "Prometheus\pandora_voice\master"
$ProfilePath = Join-Path $MasterDir "pandora_voice_profile.json"
$ReferenceWav = Join-Path $MasterDir "pandora_reference.wav"

if ((-not (Test-Path $ProfilePath)) -or (-not (Test-Path $ReferenceWav))) {
    $ProjectMaster = Join-Path $ProjectRoot "assets\pandora_voice\master"
    if ((Test-Path (Join-Path $ProjectMaster "pandora_voice_profile.json")) -and (Test-Path (Join-Path $ProjectMaster "pandora_reference.wav"))) {
        $ProfilePath = Join-Path $ProjectMaster "pandora_voice_profile.json"
        $ReferenceWav = Join-Path $ProjectMaster "pandora_reference.wav"
    } else {
        Exit-WithStatus -Status "QUALITY_REJECTED" -Code 2 -Reason "pandora-11 master profile or reference WAV missing."
    }
}

try {
    $ProfileData = Get-Content $ProfilePath -Raw | ConvertFrom-Json
    if ($ProfileData.approved_by_user -ne $true -or $ProfileData.candidate_id -ne "pandora-11") {
        Exit-WithStatus -Status "QUALITY_REJECTED" -Code 2 -Reason "Voice profile is not approved or candidate is not pandora-11."
    }
} catch {
    Exit-WithStatus -Status "QUALITY_REJECTED" -Code 2 -Reason "Voice profile JSON invalid: $_"
}

# Step 5: Launch worker & execute benchmark
Write-Host "5. Launching worker and running RTX 3050 Ti benchmark..."
$WorkerScript = Join-Path $ProjectRoot "tools\pandora_tts_worker.py"
$WorkerStateFile = Join-Path $LocalAppData "Prometheus\runtime\pandora_tts_worker.json"

if (Test-Path $WorkerStateFile) {
    Remove-Item $WorkerStateFile -Force -ErrorAction SilentlyContinue
}

$WorkerProc = Start-Process -FilePath $TtsPython -ArgumentList "`"$WorkerScript`"" -PassThru -NoNewWindow

try {
    $Waited = 0
    while ((-not (Test-Path $WorkerStateFile)) -and ($Waited -lt 30)) {
        Start-Sleep -Seconds 1
        $Waited++
        if ($WorkerProc.HasExited) {
            Exit-WithStatus -Status "ENVIRONMENT_INVALID" -Code 1 -Reason "Worker process exited prematurely."
        }
    }

    if (-not (Test-Path $WorkerStateFile)) {
        Exit-WithStatus -Status "ENVIRONMENT_INVALID" -Code 1 -Reason "Worker failed to initialize within timeout."
    }

    $BenchmarkScript = Join-Path $ProjectRoot "scripts\benchmark_pandora_tts.py"
    $BenchmarkOut = Join-Path $LocalAppData "Prometheus\pandora_voice\runtime_benchmark.json"

    & $MainPython $BenchmarkScript --state-file $WorkerStateFile --output $BenchmarkOut
    $BenchmarkExitCode = $LASTEXITCODE

} finally {
    if ($WorkerProc -and (-not $WorkerProc.HasExited)) {
        Stop-Process -Id $WorkerProc.Id -Force -ErrorAction SilentlyContinue
    }
}

# Step 6: Parse benchmark report and determine exit code
$ReportPath = Join-Path $LocalAppData "Prometheus\pandora_voice\runtime_benchmark.json"
if (-not (Test-Path $ReportPath)) {
    Exit-WithStatus -Status "QUALITY_REJECTED" -Code 2 -Reason "Benchmark report file not created."
}

try {
    $Report = Get-Content $ReportPath -Raw | ConvertFrom-Json
    $TerminalStatus = [string]$Report.terminal_status
    if (-not $TerminalStatus) {
        $TerminalStatus = if ($Report.all_gates_passed -eq $true) { "SUCCESS" } else { "QUALITY_REJECTED" }
    }
} catch {
    Exit-WithStatus -Status "QUALITY_REJECTED" -Code 2 -Reason "Failed to parse benchmark report JSON."
}

Write-Host "`n=========================================="
Write-Host "Finalization Complete."
Write-Host "Terminal Status: $TerminalStatus"
Write-Host "==========================================`n"

if ($TerminalStatus -eq "SUCCESS") {
    exit 0
} else {
    $StatusCode = switch ($TerminalStatus) {
        "RUNTIME_MEMORY_BLOCKED" { 2 }
        "QUALITY_REJECTED" { 2 }
        "MODEL_DOWNLOAD_FAILED" { 3 }
        "ENVIRONMENT_INVALID" { 1 }
        Default { 2 }
    }
    exit $StatusCode
}
