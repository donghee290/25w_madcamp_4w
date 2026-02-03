# Model Pipeline Analysis

This document details the 7-step pipeline for the SoundRoutine model generation process.

## Pipeline Overview

The pipeline transforms raw audio inputs into a fully produced, role-assigned, and rhythmically structured drum track. It operates in 7 distinct stages, each handled by a specific script in `model/pipeline/`.

### Directory Structure
- **Root**: `model/`
- **Orchestration**: `model/pipeline/step{N}_run_{activity}.py`
- **Modules**: `model/stage{N}_{name}/` (e.g., `stage1_preprocess`, `stage7_render`)

---

## Step 1: Preprocessing (`step1_run_preprocess.py`)
**Goal**: Ingest raw audio, isolate drums, slice hits, and create a "Kit".
- **Input**: Raw audio files (or directory).
- **Process**:
    1.  **Demucs**: Extracts drum stems from full tracks (GPU/CPU auto-detect).
    2.  **Onset Detection**: Finds hit points (onsets) in the drum stem.
    3.  **Slicing**: Cuts audio into individual hits (samples).
    4.  **Deduplication**: Removes duplicate hits to clean the dataset.
    5.  **Classification**: Assigns initial tags (optional/heuristic).
    6.  **Master Kit**: Merges processed hits into a "Master Kit".
- **Output**: A directory of processed samples and a `kit_manifest.json`.

## Step 2: Role Assignment (`step2_run_role_assignment.py`)
**Goal**: Assign musical roles (Core, Accent, Motion, Fill, Texture) to samples.
- **Input**: Processed samples from Step 1.
- **Process**:
    1.  **DSP Analysis**: Extracts features like energy, spectral flatness, attack/decay.
    2.  **Rule Scoring**: Uses DSP features to score samples against role definitions (e.g., Kicks have high energy/low freq).
    3.  **CLAP Scoring**: Uses a CLAP model to match samples against text prompts (e.g., "heavy kick drum").
    4.  **Fusion**: Combines Rule and CLAP scores.
    5.  **Pool Building**: Groups samples into pools (`kick_POOL`, `snare_POOL`, etc.) based on best matching roles.
- **Output**: `role_pools_{ver}.json` containing categorized sample paths.

## Step 3: Grid & Skeleton (`step3_run_grid_and_skeleton.py`)
**Goal**: Create the rhythmic foundation (Grid) and initial pattern (Skeleton).
- **Input**: `role_pools.json`, BPM, bars, seed.
- **Process**:
    1.  **Grid**: Defines the timeline (BPM, meter, steps).
    2.  **Skeleton**: Generates a base pattern of "events" (Core, Accent, etc.) without specific sample choices yet using a generative algorithm.
    3.  **Generators**: Uses internal logic (likely `beat_grid` module) to create Rock, Dense, or other style skeletons.
- **Output**: 
    - `grid_{ver}.json` (Time structure)
    - `event_grid_{ver}.json` (Abstract events)
    - `skeleton_meta_{ver}.json`

## Step 4: Model Transformer (`step4_run_model_transformer.py`)
**Goal**: Generate complex rhythmic patterns using a Transformer model.
- **Input**: Grid, Pools, and optionally a seed.
- **Process**:
    1.  **DrumsTransformerRunner**: Initializes a transformer model.
    2.  **Inference**: Generates a sequence of tokens representing drum hits.
    3.  **Token to MIDI**: Converts tokens to MIDI.
    4.  **MIDI to Events**: Parses MIDI back into the pipeline's event format (`start`, `velocity`, `role`, `micro_offset`).
- **Output**: 
    - `transformer_output_{ver}.mid`
    - `event_grid_transformer_{ver}.json`

## Step 5: Note & Layout (`step5_run_note_and_midi.py`)
**Goal**: Finalize note placement and assign specific samples from pools.
- **Input**: Transformer/Skeleton events, Role Pools.
- **Process**:
    1.  **Sample Selection**: Picks specific wav files from the pools for each event (Round-Robin, Random, or Fixed).
    2.  **Normalization**: Aligns notes to the grid with optional micro-timing clamping.
    3.  **Progressive Layering**: (Optional) Splits the track into intensity layers (Core only -> Core+Accent -> Full).
- **Output**: 
    - `event_grid_{ver}.json` (Events with assigned sample IDs)
    - `notes_{ver}.mid` (Standard MIDI file)

## Step 6: Editor (`step6_run_editor.py`)
**Goal**: Post-processing and editing operations.
- **Input**: Event Grid.
- **Process**:
    1.  **Ops**: Applies modifications like Velocity Scaling, Muting, or Timing shifts.
    2.  **Snap**: Snaps events to the UI grid (quantization) for visual display while preserving micro-offsets for playback.
    3.  **Progressive Export**: Can structure the output into progressive arrangement layers.
- **Output**: 
    - `event_grid_{ver}.json` (Finalized events)
    - `preview_{ver}.wav` (Quick render if enabled)

## Step 7: Render Final (`step7_run_render_final.py`)
**Goal**: High-quality audio rendering.
- **Input**: Final Event Grid, Sample Library.
- **Process**:
    1.  **Audio Engine**: Places samples at exact timestamps (ms precision).
    2.  **Mixing**: Applies volume/velocity adjustments.
    3.  **Export**: Writes the final mixed audio to disk.
    4.  **Conversion**: Converts WAV to MP3 if requested.
- **Output**: 
    - `{name}.wav`
    - `{name}.mp3`
