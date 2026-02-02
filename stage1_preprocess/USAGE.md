# DrumGen-X Usage Guide

## Setup

1. **Environment**: Ensure your python environment has `demucs`, `librosa`, `numpy`, `soundfile`, `scipy` installed.
   - Requires valid `TORCH_HOME` for Demucs on Windows.

2. **Configuration**:
   - Verify paths in `drumgenx/config.py` if dataset location changes.

## Commands

### 1. Scan Dataset
```bash
python -m drumgenx scan
```

### 2. Process Single File (Build Kit)
Runs separation, detection, classification, and slicing.
```bash
python -m drumgenx build-kit "path/to/audio.wav" --output-dir "output/path"
```

### 3. Generate Sequence
Generate a drum loop from a built kit validation.
```bash
python -m drumgenx sequence "output/path/kit" --pattern rock
```

### 4. Full Pipeline
Process N random files, merge best samples into a Master Kit, and generate loops.
```bash
python -m drumgenx pipeline --n-files 5
```

## Output Structure
- **drumgenx_output/**
  - **run_YYYYMMDD_HHMMSS/**
    - **files/**: Individual file kits (demucs stems + sliced hits)
    - **master_kit/**: Top 10 samples per class merged from all files
    - **test_loops/**: Generated drum loops using the master kit
    - **pipeline_report.json**: Statistics and logs
