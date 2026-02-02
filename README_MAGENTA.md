# GrooVAE Dual Environment Setup

This project uses a dual-environment setup to support **Magenta GrooVAE** (which requires Python 3.9 and TensorFlow 2.11) while keeping the main project on a newer Python version (3.12).

## Prerequisite: Install Miniconda (If not installed)

Since your system (Ubuntu 24.04) defaults to Python 3.12, you must use Conda to get Python 3.9.

```bash
# 1. Download installer
mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh

# 2. Install
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm -rf ~/miniconda3/miniconda.sh

# 3. Initialize shell (bash)
~/miniconda3/bin/conda init bash

# 4. **IMPORTANT**: Close and reopen your terminal (or run: source ~/.bashrc)
source ~/.bashrc
```

## Prerequisite: Create the Magenta Environment

You need to create a separate Python environment (e.g., via Conda) for Magenta.

```bash
# 0. Install system dependencies (Ubuntu) - Fixes rtmidi errors
apt-get update && apt-get install -y libasound2-dev libjack-dev

# 1. Create the environment
conda create -n magenta_env python=3.9 -y

# 2. Activate
conda activate magenta_env

# 3. Install binary dependencies via Conda (Crucial: link numba to old numpy)
conda install -c conda-forge -y "numpy<1.24" numba llvmlite python-rtmidi

# 4. Install remaining dependencies via Pip
pip install -r requirements-magenta.txt

# 5. Locate the python executable
which python
# Example output: /home/dh/miniconda3/envs/magenta_env/bin/python
# Copy this path.
```

## Prerequisite: Download Checkpoint

You need the `groovae_2bar_humanize` checkpoint.

```bash
mkdir -p checkpoints
cd checkpoints
wget https://storage.googleapis.com/magentadata/models/music_vae/checkpoints/groovae_2bar_humanize.tar
tar -xvf groovae_2bar_humanize.tar
cd ..
```

## How to Run

When running the main pipeline, you will need to provide the path to the Python executable of the `magenta_env`.

### Testing the Setup

A verification script is provided in `stage4_model_gen/groovae/bridge/verify_setup.py`.

```bash
# From the project root (using your MAIN environment)
python stage4_model_gen/groovae/bridge/verify_setup.py \
  --python_path /path/to/magenta_env/bin/python \
  --checkpoint_dir /path/to/checkpoints
```

### Integration Code

The wrapper class `GrooVAESubprocessRunner` in `stage4_model_gen/groovae/bridge/run_groovae_subprocess.py` handles the cross-environment execution.

```python
from stage4_model_gen.groovae.bridge.run_groovae_subprocess import GrooVAESubprocessRunner

runner = GrooVAESubprocessRunner(
    python_path="/path/to/magenta_env/bin/python",
    checkpoint_dir="/path/to/checkpoints"
)
output_ns = runner.run(input_ns)
```
