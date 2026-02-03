
# Expose key modules from subdirectories to maintain some backward compatibility or cleaner imports
# Note: Imports have been moved to subdirectories.
# If you see ImportErrors, please update your imports to use the new structure (e.g. stage1_preprocess.io.utils).

from .io.ingest import load_dataset
from .io.utils import load_audio, save_audio
from .separation.separator import extract_drum_stem
from .analysis.features import extract_features
from .analysis.detector import detect_onsets
from .slicing.slicer import slice_hits
from .cleaning.dedup import deduplicate_hits
