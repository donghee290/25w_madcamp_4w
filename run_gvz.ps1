param(
  [Parameter(Mandatory=$true)][string]$InputDir,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [string]$ReportsDir = (Join-Path $OutputDir "reports"),
  [double]$LowThreshold = 0.08,
  [double]$HighThreshold = 0.18,
  [int]$NumWorkers = 0,
  [switch]$UseDemucs,
  [string]$DemucsDevice = "cuda",
  [string]$DemucsModel = "htdemucs",
  [double]$NoiseThresholdDb = -35.0,
  [double]$NoiseWindowSec = 0.5
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pipeline = Join-Path $root "gvz_pipeline.py"

if ($NumWorkers -le 0) {
  $NumWorkers = [Environment]::ProcessorCount
}

$allFiles = Get-ChildItem -Path $InputDir -File -Recurse | Where-Object { $_.Extension -match '\.(wav|flac|mp3|m4a|ogg|aif|aiff)$' }
if (-not $allFiles) { throw "No audio files found in $InputDir" }

$cpuFiles = @()
$gpuFiles = @()

$noiseProbe = @"
import sys
import librosa
import numpy as np
path = sys.argv[1]
window = float(sys.argv[2])
y, sr = librosa.load(path, sr=16000, mono=True)
rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
rms = rms if rms.size else np.array([0.0])
p90 = np.percentile(rms, 90)
db = 20 * np.log10(p90 + 1e-12)
print(db)
"@

foreach ($f in $allFiles) {
  $db = & python -c $noiseProbe $f.FullName $NoiseWindowSec
  if ([double]$db -lt $NoiseThresholdDb) {
    $cpuFiles += $f
    Write-Host "CPU  $($f.Name)  p90_dB=$db"
  } else {
    $gpuFiles += $f
    Write-Host "GPU  $($f.Name)  p90_dB=$db"
  }
}

$runPass1 = {
  param($inputPath, $reportPath, $includeName)
  $args = @(
    "pass1",
    "--input-dir", $inputPath,
    "--report-dir", $reportPath,
    "--low-threshold", $LowThreshold,
    "--high-threshold", $HighThreshold,
    "--num-workers", $NumWorkers,
    "--auto-threshold"
  )
  if ($includeName) { $args += @("--include-name", $includeName) }
  python $pipeline @args | Out-Null

  $manifest = Get-ChildItem -Path $reportPath -Filter "manifest_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $manifest) { throw "Manifest not found in $reportPath" }
  return $manifest.FullName
}

$runPass2Cpu = {
  param($manifestPath)
  python $pipeline pass2 `
    --manifest $manifestPath `
    --output-dir "$OutputDir" `
    --notch-hz 50 --notch-q 30 `
    --highcut-hz 10000 --highcut-order 6 `
    --eq-5k-db -3 --eq-10k-db -3 --eq-q 1.0 `
    --gate --gate-threshold-db -55 --gate-attack-ms 5 --gate-release-ms 200
}

$runPass2Gpu = {
  param($manifestPath)
  python $pipeline pass2 `
    --manifest $manifestPath `
    --output-dir "$OutputDir" `
    --notch-hz 50 --notch-q 30 `
    --highcut-hz 10000 --highcut-order 6 `
    --eq-5k-db -3 --eq-10k-db -3 --eq-q 1.0 `
    --denoise --denoise-strength 0.7 --denoise-quantile 0.2 --denoise-profile-sec 0.5 --denoise-time-smooth 5 `
    --deesser --deesser-low-hz 4000 --deesser-high-hz 10000 --deesser-threshold-db -30 --deesser-ratio 4
}

# --- CPU path: low noise files (light filters) ---
if ($cpuFiles.Count -gt 0) {
  $cpuTemp = Join-Path $OutputDir "_cpu_only"
  New-Item -ItemType Directory -Force -Path $cpuTemp | Out-Null
  foreach ($f in $cpuFiles) { Copy-Item -Force $f.FullName $cpuTemp }
  $cpuReport = Join-Path $ReportsDir "cpu"
  New-Item -ItemType Directory -Force -Path $cpuReport | Out-Null
  $manifestCpu = & $runPass1 $cpuTemp $cpuReport $null
  & $runPass2Cpu $manifestCpu
}

# --- GPU path: high noise files (heavy filters) ---
if ($gpuFiles.Count -gt 0) {
  if ($UseDemucs) {
    $demucsOut = Join-Path $OutputDir "demucs"
    foreach ($f in $gpuFiles) {
      python -m demucs --two-stems vocals -n $DemucsModel -d $DemucsDevice -o $demucsOut "$($f.FullName)"
    }
    $inputForPass1 = Join-Path $demucsOut $DemucsModel
    $gpuReport = Join-Path $ReportsDir "gpu"
    New-Item -ItemType Directory -Force -Path $gpuReport | Out-Null
    $manifestGpu = & $runPass1 $inputForPass1 $gpuReport "no_vocals.wav"
    & $runPass2Gpu $manifestGpu
  } else {
    $gpuTemp = Join-Path $OutputDir "_gpu_noisy"
    New-Item -ItemType Directory -Force -Path $gpuTemp | Out-Null
    foreach ($f in $gpuFiles) { Copy-Item -Force $f.FullName $gpuTemp }
    $gpuReport = Join-Path $ReportsDir "gpu"
    New-Item -ItemType Directory -Force -Path $gpuReport | Out-Null
    $manifestGpu = & $runPass1 $gpuTemp $gpuReport $null
    & $runPass2Gpu $manifestGpu
  }
}
