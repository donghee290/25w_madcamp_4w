# Comparison Report: Rule-based (Method A) vs. CLAP (Method B)

## 1. Overview
The user proposed a new 5-rule classification system (**Method A**) using DSP features (Energy, Sharpness, Band Ratios, Attack/Decay). We implemented this and compared it against the original 8-class classifier. We also analyzed the feasibility of **CLAP (Method B)**.

## 2. Method A: DSP + Rule-based Results
We ran the new classifier on the kit extracted from `r-1-1-002-026.wav`.

### Results Summary
- **Total Hits Analyzed**: ~930
- **Distribution**:
  - `MOTION`: ~650 (Mapped from Hihat/Ride)
  - `CORE`: ~200 (Mapped from heavy Rides/low-mid thumps)
  - `TEXTURE`: ~80 (Mapped from long decaying crashes/rides)
  - `ACCENT/FILL`: Minor counts.

### Key Observations
1.  **Hi-hats Correctly Mapped to MOTION**:
    - Most `hihat_xxx.wav` files were classified as `MOTION` (Score ~0.7-0.8). This aligns perfectly with the spec (High freq, rapid).
2.  **Rides Split between CORE and MOTION**:
    - Some "Rhodes/Ride" sounds with heavy mid-low bodies were classified as `CORE` (Score ~0.55).
    - Brighter rides went to `MOTION`.
3.  **Crashes mapped to TEXTURE**:
    - Long decay samples (`crash_001.wav`, decay=0.53s) were correctly classified as `TEXTURE` (Score 0.62). This is a huge improvement over the previous classifier which struggled to distinguish Crash from Noise.

### Pros & Cons
- **Pros**: extremely fast, interpretable, successful at strictly physical classification (High freq = Motion).
- **Cons**: Semantic gap. A "Heavy box drop" might look like a Kick (CORE) spectrally, but semantically it's an "Impact".

## 3. Method B: CLAP (Zero-Shot) Analysis
**CLAP (Contrastive Language-Audio Pretraining)** uses a transformer model to match audio to text prompts.

### Concept
Instead of calculating `score = 0.4*Low + ...`, we ask CLAP:
> *"What is the probability this sound matches 'A deep thumping kick drum' vs 'A sharp metallic hi-hat'?"*

### Comparison
| Feature | DSP Rules (Current) | CLAP (Proposed) |
| :--- | :--- | :--- |
| **Speed** | < 10ms per file | ~100-500ms per file (GPU) |
| **Installation** | Light (Librosa) | Heavy (Torch, Transformers, >1GB Weights) |
| **Accuracy** | **High for standard drums**. <br>Low for abstract sounds. | **High for abstract sounds**. <br> Understands "Thumping", "Clicking". |
| **Customization**| Edit formula weights. | Edit text prompts. |

### Feasibility in Current Setup
- We have `transformers` and `torch` installed.
- **BUT**: Running CLAP requires downloading model weights (laion/clap-htsat-unfused ~600MB).
- **Recommendation**: For environmental audio (e.g. Hospital sounds), **CLAP is theoretically superior** because it understands semantic concepts like "Door slam" vs "Kick drum". However, the **DSP Rules (Method A)** just proved effective at separating distinct sonic textures (Motion vs Texture) in our test.

## 4. Conclusion
The **Method A (DSP Rules)** provided in the spec works surprisingly well. It successfully separated:
- **Hi-hats** -> `MOTION` (High score > 0.7)
- **Long Crashes** -> `TEXTURE` (Decay dominated)
- **Thumps** -> `CORE`

We recommend sticking with **Method A** for now as it is fully implemented and fast. Moving to CLAP is a viable "Premium" upgrade path if we find the DSP rules failing on more complex noise.
