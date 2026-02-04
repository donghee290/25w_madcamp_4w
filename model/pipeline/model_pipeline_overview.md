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
**Goal**: Ingest raw audio, isolate drums, slice hits, and create a "Master Kit".
- **Input**: Raw audio files (or directory).
- **Process**:
    1.  **Duration Check**: Rapidly filters files; treats short files (< 1s) as one-shots immediately.
    2.  **Demucs**: Extracts drum stems from full tracks (GPU/CPU auto-detect) if essential.
    3.  **Onset Detection**: Finds hit points (onsets) in the drum stem.
    4.  **Slicing**: Cuts audio into individual hits (samples).
    5.  **Deduplication**: Removes duplicate hits (cosine similarity) to clean the dataset.
    6.  **Master Kit**: Merges processed hits into a "Master Kit" directory.
- **Output**: A directory of processed samples (`stage1_output/.../samples`) and a `pipeline_report.json`.

## Step 2: Role Assignment (`step2_run_role_assignment.py`)
**Goal**: Assign musical roles (Core, Accent, Motion, Fill, Texture) to samples.
- **Input**: Processed samples from Step 1.
- **Process**:
    1.  **DSP Analysis**: Extracts features like energy, spectral flatness, attack/decay.
    2.  **Rule Scoring**: Uses DSP features to score samples against role definitions (e.g., Kicks have high energy/low freq).
    3.  **CLAP Scoring**: Uses a CLAP model to match samples against text prompts (e.g., "heavy kick drum").
    4.  **Fusion**: Combines Rule and CLAP scores with guards (e.g., texture suppression).
    5.  **Pool Building**: Groups samples into pools (`kick_POOL`, `snare_POOL`, etc.) based on best matching roles.
- **Output**: 
    - `role_pools_{ver}.json` (Sample paths grouped by role)
    - `role_assignment_debug_{ver}.json` (Detailed debug scores)



## Step 3: Grid & Skeleton Setup (`step3_run_grid_and_skeleton.py`)
**Goal**: Create the "Container" (Grid, BPM, Bars) and the "Structural Constraints" (Skeleton).
- **Input**: BPM, bars, style (e.g., House, HipHop, Funk).
- **Process**:
    1.  **Grid Setup**: Defines the timeline (BPM, meter, steps).
    2.  **Skeleton Generation**: Creates a "rhythm skeleton" (Kick/Snare patterns) based on the selected style.
        - Provides a stable foundation for the AI to build upon.
        - Ensures the output respects the genre's characteristic groove.
- **Output**: 
    - `grid_{ver}.json` (The essential "Container")
    - `skeleton_{ver}.json` (The "Constraint Map")


## Step 4: AI Generator (`step4_run_model_transformer.py`)
**Goal**: Generate complex rhythmic patterns using a trained Transformer model (Causal LM), strictly enforced by the Skeleton.
- **Input**: `grid.json`, `skeleton.json`, `role_pools.json`.
- **Process**:
    1.  **Candidate Generation**: Generates multiple candidate beat variations using the Transformer model.
    2.  **Selection**: Compares candidates against the `skeleton.json` structure and selects the best statistical match.
    3.  **Hybrid Merge**: Merges the selected AI candidate with the Skeleton.
        - **Enforces** structural events (Core, Accent, Motion - Fill/Texture).
        - **Retains** AI's creative details (Velocity nuances, Micro-timing, Variations).
    4.  **Event Mapping**: Parses tokens into the pipeline's event format.
- **Output**: 
    - `event_grid_transformer_{ver}.json` (The "AI Generated + Merged" Content)


## Step 5: Note & Layout (`step5_run_note_and_midi.py`)
**Goal**: Finalize note placement, assign specific samples, and build song structure via Progressive Layering.
- **Input**: Transformer/Skeleton events, Role Pools, Notes JSON.
- **Process**:
    1.  **Dynamic Expansion**: Automatically expands the Grid if the AI's generated content (e.g., 32 bars) exceeds the initial grid size (e.g., 4 bars).
    2.  **Sample Selection**: Picks specific wav files from the pools.
    3.  **Normalization**: Aligns notes to the grid.
    4.  **Progressive Layering**: Builds a full song structure (~1 min+) by layering roles (Core -> Core+Accent -> Full Loop) for a dynamic arrangement.
- **Output**: 
    - `event_grid_{ver}.json` (Main output with finalized sample IDs)
    - `notes_{ver}.mid` (Standard MIDI file)
    - `note_meta_{ver}.json`

## Step 6: Editor (`step6_run_editor.py`)
**Goal**: Post-processing, editing, and format conversion.
- **Input**: Event Grid.
- **Process**:
    1.  **Ops**: Applies modifications like Velocity Scaling, Muting.
    2.  **Snap**: Snaps events to the UI grid (quantization) for visual display while preserving micro-offsets.
    3.  **Progressive Export**: Can split the output into multiple layer files (e.g., `progress_1_core.json`, `progress_2_core_accent.json`) for stems.
- **Output**: 
    - `event_grid_{ver}.json` (Finalized events)
    - `preview_{ver}.wav` (Quick render if enabled)
    - Progressive layer files (optional)

## Step 7: Render Final (`step7_run_render_final.py`)
**Goal**: High-quality audio rendering and format export.
- **Input**: Final Event Grid, Sample Library.
- **Process**:
    1.  **Audio Engine**: Places samples at exact timestamps (ms precision) using `audio_renderer.py`.
    2.  **Mixing**: Applies volume/velocity adjustments.
    3.  **Export**: Writes the final mixed audio to WAV.
    4.  **Conversion**: Converts WAV to target format (`mp3`, `flac`, `ogg`, `m4a`) using `export_audio.py` (ffmpeg wrapper).
- **Output**: 
    - `{name}_{ver}.wav` (High quality master)
    - `{name}_{ver}.{format}` (Encoded output if requested)
