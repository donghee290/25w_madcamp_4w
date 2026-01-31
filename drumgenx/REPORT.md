# DrumGen-X Implementation Report

## 1. Model Selection
We selected **htdemucs** (Hybrid Transformer Demucs) 4-stem model for drum separation. 
- **Reasoning**: Demucs is currently the state-of-the-art open source model that provides a dedicated "drums" stem. 
- **Alternative**: `spleeter:4stems` (older, lower quality), `open-unmix` (lower quality).
- **Configuration**: We use the full 4-stem separation and discard bass/vocals/other, keeping only the drum stem. Code handles "long file chunking" (60s chunks) to manage memory usage on the RTX 4060.

## 2. Classification Strategy
We implemented a rule-based classifier with spectral features, augmented by pitch detection for Toms.

### Tom Classification (pYIN)
- **Problem**: Toms (Low, Mid, High) are difficult to distinguish by spectral centroid alone compared to Kick/Snare.
- **Solution**: We use `librosa.pyin` to estimate fundamental frequency (f0) when the spectral centroid suggests a drum body sound (100-1000 Hz).
- **Ranges**:
  - **L-Tom (Floor)**: 80 - 150 Hz
  - **R-Tom (Mid)**: 150 - 300 Hz
  - **Row-Tom (High)**: 300 - 500 Hz
- **Optimization**: pYIN is computationally expensive, so we only run it when the spectral centroid is within the expected range (50-1000Hz). High-frequency hits (hi-hats, cymbals) skip this step for speed.

## 3. Pipeline Architecture
- **Ingest**: Scans 817 environment files.
- **Separation**: Demucs (via subprocess) -> `drums.wav`.
- **Detection**: Multi-band spectral flux onset detection.
- **Slicing**: Extract hits, normalize, fade-out.
- **Sequencing**: Grid-based generation using Rock/HipHop/Jazz templates.

## 4. Verification
- **Single File Test**: Validated on `r-1-1-002-026.wav`. 
  - Result: ~1000 onsets detected. Kit created with Hihat and Ride samples.
  - Performance: Optimized classification runs in <30s.
- **Full Pipeline**: Currently running on 5 random files to build a master kit.

## 5. Environment
- **Python**: Using local user venv (`.venv`) which contains `demucs`.
- **Torch**: Configured `TORCH_HOME` to avoid Windows path length issues.
