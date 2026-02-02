# Audio Preprocessing Runner
How to run the drum extraction pipeline.

## 1. Setup
Install requirements if you haven't:
```bash
pip install -r requirements.txt
```
(Ensure you have `torch`, `demucs`, `librosa`, etc.)

## 2. Prepare Audio
Put your audio files (mp3, wav, m4a) into the `sample_input/` folder.
(Or anywhere else, but this folder is created for convenience).

## 3. Run
Execute the script with the file path:

```bash
# Example
python run_preprocess.py "sample_input/my_hospital_sound.wav"
```

## 4. Output
The results will be saved in `preprocess_output/`:
- `demucs/`: Separated drum stems
- `kit/`: Sliced and classified drum samples (kick, snare, etc.)
- `kit/kit_manifest.json`: Detailed info about the samples
