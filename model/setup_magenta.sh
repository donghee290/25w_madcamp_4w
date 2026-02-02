#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status.

echo "========================================="
echo "  Retrying Magenta Environment Setup"
echo "========================================="

# 1. Install System Dependencies (Root required)
echo "[1/5] Installing system libraries (alsa, jack, sndfile)..."
apt-get update && apt-get install -y libasound2-dev libjack-dev libsndfile1-dev

# 2. Reset Conda Environment
echo "[2/5] Resetting Conda environment 'magenta_env'..."
# Source conda.sh to ensure 'conda' command works in script
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "/root/miniconda3/etc/profile.d/conda.sh" ]; then
    source "/root/miniconda3/etc/profile.d/conda.sh"
fi

conda deactivate 2>/dev/null || true
conda remove -n magenta_env --all -y 2>/dev/null || true
conda create -n magenta_env python=3.9 -y
conda activate magenta_env

# 3. Install Hard-to-Build Binaries via Conda (Including CUDA for GPU support)
echo "[3/5] Installing binary dependencies via Conda..."
conda install -c conda-forge -y "numpy<1.24" numba llvmlite cudatoolkit=11.2 cudnn=8.1.0

# 4. Install TensorFlow
echo "[4/5] Installing TensorFlow 2.9.1..."
pip install tensorflow==2.9.1

# 5. Install Magenta & Others
echo "[5/5] Installing Magenta and other requirements..."
# --prefer-binary tells pip to use wheels instead of source if possible
# We exclude numba dependency from magenta to trust the Conda version
pip install "magenta==2.1.4" --no-deps 
pip install note-seq pretty_midi mido "protobuf==3.20.3" "tensorflow-probability==0.17.0" "tf-slim" "tensorflow-datasets"

# Force downgrade protobuf again to be safe (tf-ds might have upgraded it)
pip install "protobuf==3.20.3"

echo "========================================="
echo "  Setup Completed Successfully!"
echo "========================================="
which python
