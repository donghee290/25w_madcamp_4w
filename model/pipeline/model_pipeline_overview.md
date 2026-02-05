# Model Pipeline Analysis

This document details the 7-step pipeline for the SoundRoutine model generation process.

## Pipeline Overview

The pipeline transforms raw audio inputs into a fully produced, role-assigned, and rhythmically structured drum track. It operates in 7 distinct stages, each handled by a specific script in `model/pipeline/`.

### Directory Structure
- **Root**: `model/`
- **Orchestration**: `model/pipeline/step{N}_run_{activity}.py`
- **Modules**:
    - `stage1_preprocess/`
    - `stage2_role_assignment/`
    - `stage3_beat_grid/`
    - `stage4_model_gen/`
    - `stage5_note_gen/`
    - `stage6_event_editor/`
    - `stage7_render/`

---

## Step 1: Preprocessing (`step1_run_preprocess.py`)
**Goal**: Ingest raw audio, isolate drums, slice hits, and create a "Master Kit".
- **Input**: Raw audio files (or directory).
- **Process**:
    1.  **Duration Check**: Rapidly filters files; treats short files (< 1s) as one-shots immediately.
    2.  **Demucs**: Extracts drum stems from full tracks (GPU/CPU auto-detect).
    3.  **Onset Detection**: Finds hit points (onsets) in the drum stem.
    4.  **Slicing**: Cuts audio into individual hits (samples).
    5.  **Deduplication**: Removes duplicate hits (cosine similarity) to clean the dataset.
    6.  **Master Kit**: Merges processed hits into a "Master Kit" directory.
- **Output**: A directory of processed samples (`stage1_output/.../samples`) and a `pipeline_report.json`.

## Step 2: Role Assignment (`step2_run_role_assignment.py`)
**Goal**: Assign musical roles (Core, Accent, Motion, Fill, Texture) to samples using a hybrid scoring system.
- **Input**: Processed samples from Step 1.
- **Process**:
    1.  **DSP Analysis**: Extracts features like energy, spectral flatness, attack/decay, and frequency band ratios.
    2.  **Rule Scoring**: Uses DSP features to score samples against role definitions (e.g., Kicks have high energy/low freq).
    3.  **CLAP Scoring**: Uses a CLAP (Contrastive Language-Audio Pretraining) model to match samples against text prompts.
    4.  **Fusion & Guards**: Combines Rule and CLAP scores with safety guards (e.g., suppressing sustained noise as texture).
    5.  **Pool Building**: Groups samples into roles (`CORE`, `ACCENT`, `MOTION`, `FILL`, `TEXTURE`).
- **Output**: 
    - `role_pools_{ver}.json` (Sample paths grouped by role)
    - `role_assignment_debug_{ver}.json` (Detailed DSP and CLAP scores)

## Step 3: Grid & Skeleton Setup (`step3_run_grid_and_skeleton.py`)
**Goal**: Create the "Container" (Grid) and the "Structural Foundation" (Skeleton).
- **Input**: BPM, bars, style (e.g., House, HipHop, Funk, Rock).
- **Process**:
    1.  **Grid Setup**: Defines the timeline (BPM, meter, steps-per-bar).
    2.  **Style Selection**: Supports "Auto" mode which suggests a style based on the provided BPM.
    3.  **Skeleton Generation**: Creates a "rhythm skeleton" (Kick/Snare patterns) based on the selected musical style.
- **Output**: 
    - `grid_{ver}.json` (The timeline configuration)
    - `skeleton_{ver}.json` (The style-specific rhythm foundation)

## Step 4: AI Generator (`step4_run_model_transformer.py`)
**Goal**: Generate complex rhythmic patterns using a trained Transformer model, guided by the Skeleton.
- **Input**: `grid.json`, `skeleton.json`, `role_pools.json`.
- **Process**:
    1.  **Transformer Generation**: Generates candidate beat variations using a causal language model architecture.
    2.  **Skeleton Enforcement**: Merges AI-generated creative details (velocity, micro-timing) with the structural stability of the Skeleton.
    3.  **Event Mapping**: Converts model tokens into the internal event format.
- **Output**: 
    - `event_grid_transformer_{ver}.json` (The raw AI-generated content)

## Step 5: Note & Layout (`step5_run_note_and_midi.py`)
**Goal**: Finalize note placement, assign specific samples, and build the song structure.
- **Input**: Transformer events, Role Pools, Grid JSON.
- **Process**:
    1.  **Sample Selection**: Picks specific wav files from the role pools for each event.
    2.  **Normalization**: Aligns notes to the grid and resolves conflicts.
    3.  **Progressive Layering**: Arranges the track into 8-bar segments, progressively adding layers (CORE -> CORE+ACCENT -> ... -> FULL) to create a dynamic song structure (buildup).
- **Output**: 
    - `event_grid_{ver}.json` (Main event list with sample IDs)
    - `grid_{ver}.json` (Updated grid if bars were expanded for arrangement)
    - `notes_{ver}.mid` (Standard MIDI file)

## Step 6: Editor (`step6_run_editor.py`)
**Goal**: Post-processing, UI optimization, and quick preview.
- **Input**: Event Grid, Grid JSON.
- **Process**:
    1.  **Quantization**: Snaps events to the UI grid for visual clarity while preserving musical micro-offsets.
    2.  **Velocity Scaling**: Finalizes velocity ranges for the render.
    3.  **Preview Render**: Generates a quick low-latency audio preview if requested.
- **Output**: 
    - `event_grid_{ver}.json` (Cleaned events for frontend and renderer)
    - `preview_{ver}.wav` (Optional preview audio)

## Step 7: Render Final (`step7_run_render_final.py`)
**Goal**: High-quality audio rendering and multi-format export.
- **Input**: Final Event Grid, Sample Library.
- **Process**:
    1.  **Audio Engine**: Places samples at exact millisecond timestamps using `audio_renderer.py`.
    2.  **Mixing**: Applies volume normalization and basic mixing across all active roles.
    3.  **Conversion**: Encodes the final WAV into requested formats (`mp3`, `flac`, `ogg`, `m4a`) using FFmpeg.
- **Output**: 
    - `{name}_final.wav` (High-quality master)
    - `{name}_final.{format}` (Compressed output for user download)
