import argparse
from multiprocessing import cpu_count
from pathlib import Path

from .config import Pass1Config, Pass2Config
from .pass1 import pass1
from .pass2 import pass2
from .splitter import split_audio, split_directory, split_to_samples
from .splitter_ai import split_audio_ai, split_to_samples_ai
from .stages import export_stage_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ghost Vocal Zero (GVZ)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pass1_parser = subparsers.add_parser("pass1", help="Score dataset and generate manifest")
    pass1_parser.add_argument("--input-dir", type=Path, required=True)
    pass1_parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    pass1_parser.add_argument("--sr", type=int, default=16000)
    pass1_parser.add_argument("--n-mfcc", type=int, default=13)
    pass1_parser.add_argument("--low-threshold", type=float, required=True)
    pass1_parser.add_argument("--high-threshold", type=float, required=True)
    pass1_parser.add_argument("--num-workers", type=int, default=cpu_count())
    pass1_parser.add_argument("--dbscan-eps", type=float, default=0.5)
    pass1_parser.add_argument("--dbscan-min-samples", type=int, default=5)
    pass1_parser.add_argument("--no-harmonic", dest="use_harmonic", action="store_false")
    pass1_parser.set_defaults(use_harmonic=True)
    pass1_parser.add_argument("--auto-threshold", action="store_true", default=False)
    pass1_parser.add_argument("--auto-low-quantile", type=float, default=0.75)
    pass1_parser.add_argument("--auto-high-quantile", type=float, default=0.90)
    pass1_parser.add_argument("--include-name", type=str, default=None)

    pass2_parser = subparsers.add_parser("pass2", help="Apply actions from manifest")
    pass2_parser.add_argument("--manifest", type=Path, required=True)
    pass2_parser.add_argument("--output-dir", type=Path, required=True)
    pass2_parser.add_argument("--sr", type=int, default=16000)
    pass2_parser.add_argument("--gain-db", type=float, default=-10.0)
    pass2_parser.add_argument("--highcut-hz", type=float, default=None)
    pass2_parser.add_argument("--highcut-order", type=int, default=8)
    pass2_parser.add_argument("--notch-hz", type=float, default=None)
    pass2_parser.add_argument("--notch-q", type=float, default=30.0)
    pass2_parser.add_argument("--eq-5k-db", type=float, default=-3.0)
    pass2_parser.add_argument("--eq-10k-db", type=float, default=-3.0)
    pass2_parser.add_argument("--eq-q", type=float, default=1.0)
    pass2_parser.add_argument("--gate", dest="gate_enabled", action="store_true", default=False)
    pass2_parser.add_argument("--gate-threshold-db", type=float, default=-40.0)
    pass2_parser.add_argument("--gate-attack-ms", type=float, default=10.0)
    pass2_parser.add_argument("--gate-release-ms", type=float, default=100.0)
    pass2_parser.add_argument("--denoise", dest="denoise_enabled", action="store_true", default=False)
    pass2_parser.add_argument("--denoise-strength", type=float, default=0.7)
    pass2_parser.add_argument("--denoise-quantile", type=float, default=0.2)
    pass2_parser.add_argument("--denoise-profile-sec", type=float, default=None)
    pass2_parser.add_argument("--denoise-time-smooth", type=int, default=0)
    pass2_parser.add_argument("--deesser", dest="deesser_enabled", action="store_true", default=False)
    pass2_parser.add_argument("--deesser-low-hz", type=float, default=4000.0)
    pass2_parser.add_argument("--deesser-high-hz", type=float, default=10000.0)
    pass2_parser.add_argument("--deesser-threshold-db", type=float, default=-30.0)
    pass2_parser.add_argument("--deesser-ratio", type=float, default=4.0)
    pass2_parser.add_argument("--deesser-attack-ms", type=float, default=5.0)
    pass2_parser.add_argument("--deesser-release-ms", type=float, default=80.0)
    pass2_parser.add_argument("--noise-split", dest="noise_split_enabled", action="store_true", default=False)
    pass2_parser.add_argument("--noise-threshold-db", type=float, default=-35.0)
    pass2_parser.add_argument("--noise-window-sec", type=float, default=0.5)
    pass2_parser.add_argument("--clean-gain-db", type=float, default=-15.0)
    pass2_parser.add_argument("--clean-denoise-strength", type=float, default=0.4)
    pass2_parser.add_argument("--clean-deesser-threshold-db", type=float, default=-25.0)
    pass2_parser.add_argument("--clean-deesser-ratio", type=float, default=3.0)
    pass2_parser.add_argument("--noisy-gain-db", type=float, default=-20.0)
    pass2_parser.add_argument("--noisy-denoise-strength", type=float, default=0.7)
    pass2_parser.add_argument("--noisy-deesser-threshold-db", type=float, default=-35.0)
    pass2_parser.add_argument("--noisy-deesser-ratio", type=float, default=6.0)

    stages_parser = subparsers.add_parser("stages", help="Export stage-by-stage audio outputs")
    stages_parser.add_argument("--input-file", type=Path, required=True)
    stages_parser.add_argument("--output-dir", type=Path, required=True)
    stages_parser.add_argument("--sr", type=int, default=16000)
    stages_parser.add_argument("--n-mfcc", type=int, default=13)
    stages_parser.add_argument("--low-threshold", type=float, required=True)
    stages_parser.add_argument("--high-threshold", type=float, required=True)
    stages_parser.add_argument("--gain-db", type=float, default=-10.0)
    stages_parser.add_argument("--highpass-hz", type=float, default=None)
    stages_parser.add_argument("--highpass-order", type=int, default=4)
    stages_parser.add_argument("--highcut-hz", type=float, default=None)
    stages_parser.add_argument("--highcut-order", type=int, default=8)
    stages_parser.add_argument("--notch-hz", type=float, default=None)
    stages_parser.add_argument("--notch-q", type=float, default=30.0)
    stages_parser.add_argument("--eq-5k-db", type=float, default=-3.0)
    stages_parser.add_argument("--eq-10k-db", type=float, default=-3.0)
    stages_parser.add_argument("--eq-q", type=float, default=1.0)
    stages_parser.add_argument("--gate", dest="gate_enabled", action="store_true", default=False)
    stages_parser.add_argument("--gate-threshold-db", type=float, default=-40.0)
    stages_parser.add_argument("--gate-attack-ms", type=float, default=10.0)
    stages_parser.add_argument("--gate-release-ms", type=float, default=100.0)
    stages_parser.add_argument("--denoise", dest="denoise_enabled", action="store_true", default=False)
    stages_parser.add_argument("--denoise-strength", type=float, default=0.7)
    stages_parser.add_argument("--denoise-quantile", type=float, default=0.2)
    stages_parser.add_argument("--denoise-profile-sec", type=float, default=None)
    stages_parser.add_argument("--denoise-time-smooth", type=int, default=0)
    stages_parser.add_argument("--deesser", dest="deesser_enabled", action="store_true", default=False)
    stages_parser.add_argument("--deesser-low-hz", type=float, default=4000.0)
    stages_parser.add_argument("--deesser-high-hz", type=float, default=10000.0)
    stages_parser.add_argument("--deesser-threshold-db", type=float, default=-30.0)
    stages_parser.add_argument("--deesser-ratio", type=float, default=4.0)
    stages_parser.add_argument("--deesser-attack-ms", type=float, default=5.0)
    stages_parser.add_argument("--deesser-release-ms", type=float, default=80.0)
    stages_parser.add_argument("--noise-split", dest="noise_split_enabled", action="store_true", default=False)
    stages_parser.add_argument("--noise-threshold-db", type=float, default=-35.0)
    stages_parser.add_argument("--noise-window-sec", type=float, default=0.5)
    stages_parser.add_argument("--clean-gain-db", type=float, default=-15.0)
    stages_parser.add_argument("--clean-denoise-strength", type=float, default=0.4)
    stages_parser.add_argument("--clean-deesser-threshold-db", type=float, default=-25.0)
    stages_parser.add_argument("--clean-deesser-ratio", type=float, default=3.0)
    stages_parser.add_argument("--noisy-gain-db", type=float, default=-20.0)
    stages_parser.add_argument("--noisy-denoise-strength", type=float, default=0.7)
    stages_parser.add_argument("--noisy-deesser-threshold-db", type=float, default=-35.0)
    stages_parser.add_argument("--noisy-deesser-ratio", type=float, default=6.0)
    stages_parser.add_argument("--no-harmonic", dest="use_harmonic", action="store_false")
    stages_parser.set_defaults(use_harmonic=True)
    stages_parser.add_argument("--primary-removal", choices=["none", "demucs"], default="none")
    stages_parser.add_argument("--demucs-model", type=str, default="htdemucs")
    stages_parser.add_argument("--demucs-device", type=str, default="cuda")
    stages_parser.add_argument("--demucs-if-speech", action="store_true", default=False)
    # Split options (auto-split after preprocessing)
    stages_parser.add_argument("--split", dest="split_enabled", action="store_true", default=False, help="Split into sample1,sample2,... after preprocessing")
    stages_parser.add_argument("--split-top-db", type=float, default=25.0, help="Silence threshold for splitting")
    stages_parser.add_argument("--split-min-duration-ms", type=float, default=1000.0, help="Min sample duration (ms)")
    stages_parser.add_argument("--split-merge-gap-ms", type=float, default=50.0, help="Merge segments closer than this (ms)")
    stages_parser.add_argument("--split-pad-ms", type=float, default=30.0, help="Padding around each sample (ms)")
    stages_parser.add_argument("--split-normalize", action="store_true", default=False, help="Normalize each sample to peak")
    stages_parser.add_argument("--split-gain-db", type=float, default=0.0, help="Gain in dB for each sample")
    stages_parser.add_argument("--split-max-duration-s", type=float, default=30.0, help="Max sample duration in seconds (longer segments are chunked)")

    # --- split ---
    split_parser = subparsers.add_parser("split", help="Split audio into individual sound segments")
    split_parser.add_argument("--input-file", type=Path, default=None, help="Single file to split")
    split_parser.add_argument("--input-dir", type=Path, default=None, help="Directory of files to split")
    split_parser.add_argument("--output-dir", type=Path, required=True)
    split_parser.add_argument("--sr", type=int, default=16000)
    split_parser.add_argument("--top-db", type=float, default=30.0, help="Silence threshold in dB")
    split_parser.add_argument("--min-duration-ms", type=float, default=50.0, help="Min segment length")
    split_parser.add_argument("--merge-gap-ms", type=float, default=100.0, help="Merge segments closer than this")
    split_parser.add_argument("--pad-ms", type=float, default=30.0, help="Padding around each segment")

    # --- split-ai ---
    split_ai_parser = subparsers.add_parser("split-ai", help="AI-based audio segmentation")
    split_ai_parser.add_argument("--input-file", type=Path, required=True)
    split_ai_parser.add_argument("--output-dir", type=Path, required=True)
    split_ai_parser.add_argument("--sr", type=int, default=16000)
    split_ai_parser.add_argument("--device", type=str, default="cuda")
    split_ai_parser.add_argument("--threshold-factor", type=float, default=1.5, help="Novelty peak threshold (lower=more splits)")
    split_ai_parser.add_argument("--min-segment-ms", type=float, default=100.0)
    split_ai_parser.add_argument("--min-gap-frames", type=int, default=20)
    split_ai_parser.add_argument("--kernel-size", type=int, default=15, help="Novelty kernel size (larger=smoother)")
    split_ai_parser.add_argument("--pad-ms", type=float, default=50.0)
    split_ai_parser.add_argument("--denoise", action="store_true", default=False, help="Apply spectral gating denoise")
    split_ai_parser.add_argument("--denoise-strength", type=float, default=0.8)

    # --- split-samples ---
    samples_parser = subparsers.add_parser("split-samples", help="Split preprocessed audio into sample1, sample2, ...")
    samples_parser.add_argument("--input", type=Path, required=True, help="Wav file or stages run directory (uses 05_keep.wav)")
    samples_parser.add_argument("--output-dir", type=Path, default=None, help="Output directory (default: samples/ in input dir)")
    samples_parser.add_argument("--sr", type=int, default=16000)
    samples_parser.add_argument("--mode", choices=["cpu", "gpu"], default="cpu", help="cpu=silence detection, gpu=AI novelty detection")
    # CPU params
    samples_parser.add_argument("--top-db", type=float, default=30.0, help="[CPU] Silence threshold in dB")
    samples_parser.add_argument("--min-duration-ms", type=float, default=50.0, help="[CPU] Min segment length")
    samples_parser.add_argument("--merge-gap-ms", type=float, default=100.0, help="[CPU] Merge segments closer than this")
    samples_parser.add_argument("--pad-ms", type=float, default=30.0, help="Padding around each segment")
    # GPU params
    samples_parser.add_argument("--device", type=str, default="cuda", help="[GPU] Device")
    samples_parser.add_argument("--threshold-factor", type=float, default=1.5, help="[GPU] Novelty threshold factor")
    samples_parser.add_argument("--min-segment-ms", type=float, default=100.0, help="[GPU] Min segment length")
    samples_parser.add_argument("--min-gap-frames", type=int, default=20, help="[GPU] Min gap between boundaries")
    samples_parser.add_argument("--kernel-size", type=int, default=15, help="[GPU] Novelty kernel size")
    samples_parser.add_argument("--denoise", action="store_true", default=False, help="[GPU] Apply spectral denoise")
    samples_parser.add_argument("--denoise-strength", type=float, default=0.8, help="[GPU] Denoise strength")
    # Volume params
    samples_parser.add_argument("--normalize", action="store_true", default=False, help="Normalize each sample to peak volume")
    samples_parser.add_argument("--gain-db", type=float, default=0.0, help="Apply gain in dB (e.g. 6.0 = 2x louder)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "pass1":
        config = Pass1Config(
            input_dir=args.input_dir,
            report_dir=args.report_dir,
            sr=args.sr,
            n_mfcc=args.n_mfcc,
            low_threshold=args.low_threshold,
            high_threshold=args.high_threshold,
            num_workers=args.num_workers,
            dbscan_eps=args.dbscan_eps,
            dbscan_min_samples=args.dbscan_min_samples,
            use_harmonic=args.use_harmonic,
            auto_threshold=args.auto_threshold,
            auto_low_quantile=args.auto_low_quantile,
            auto_high_quantile=args.auto_high_quantile,
            include_name=args.include_name,
        )
        json_path, csv_path = pass1(config)
        print(f"Manifest JSON: {json_path}")
        print(f"Manifest CSV: {csv_path}")

    elif args.command == "pass2":
        config = Pass2Config(
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            sr=args.sr,
            gain_db=args.gain_db,
            highcut_hz=args.highcut_hz,
            highcut_order=args.highcut_order,
            notch_hz=args.notch_hz,
            notch_q=args.notch_q,
            eq_5k_db=args.eq_5k_db,
            eq_10k_db=args.eq_10k_db,
            eq_q=args.eq_q,
            gate_enabled=args.gate_enabled,
            gate_threshold_db=args.gate_threshold_db,
            gate_attack_ms=args.gate_attack_ms,
            gate_release_ms=args.gate_release_ms,
            denoise_enabled=args.denoise_enabled,
            denoise_strength=args.denoise_strength,
            denoise_quantile=args.denoise_quantile,
            denoise_profile_sec=args.denoise_profile_sec,
            denoise_time_smooth=args.denoise_time_smooth,
            deesser_enabled=args.deesser_enabled,
            deesser_low_hz=args.deesser_low_hz,
            deesser_high_hz=args.deesser_high_hz,
            deesser_threshold_db=args.deesser_threshold_db,
            deesser_ratio=args.deesser_ratio,
            deesser_attack_ms=args.deesser_attack_ms,
            deesser_release_ms=args.deesser_release_ms,
            noise_split_enabled=args.noise_split_enabled,
            noise_threshold_db=args.noise_threshold_db,
            noise_window_sec=args.noise_window_sec,
            clean_gain_db=args.clean_gain_db,
            clean_denoise_strength=args.clean_denoise_strength,
            clean_deesser_threshold_db=args.clean_deesser_threshold_db,
            clean_deesser_ratio=args.clean_deesser_ratio,
            noisy_gain_db=args.noisy_gain_db,
            noisy_denoise_strength=args.noisy_denoise_strength,
            noisy_deesser_threshold_db=args.noisy_deesser_threshold_db,
            noisy_deesser_ratio=args.noisy_deesser_ratio,
        )
        delete_path = pass2(config)
        print(f"Output dir: {delete_path}")

    elif args.command == "stages":
        report_path = export_stage_outputs(
            input_file=args.input_file,
            output_dir=args.output_dir,
            sr=args.sr,
            n_mfcc=args.n_mfcc,
            low_threshold=args.low_threshold,
            high_threshold=args.high_threshold,
            use_harmonic=args.use_harmonic,
            gain_db=args.gain_db,
            primary_removal=args.primary_removal,
            highpass_hz=args.highpass_hz,
            highpass_order=args.highpass_order,
            highcut_hz=args.highcut_hz,
            highcut_order=args.highcut_order,
            notch_hz=args.notch_hz,
            notch_q=args.notch_q,
            eq_5k_db=args.eq_5k_db,
            eq_10k_db=args.eq_10k_db,
            eq_q=args.eq_q,
            gate_enabled=args.gate_enabled,
            gate_threshold_db=args.gate_threshold_db,
            gate_attack_ms=args.gate_attack_ms,
            gate_release_ms=args.gate_release_ms,
            denoise_enabled=args.denoise_enabled,
            denoise_strength=args.denoise_strength,
            denoise_quantile=args.denoise_quantile,
            denoise_profile_sec=args.denoise_profile_sec,
            denoise_time_smooth=args.denoise_time_smooth,
            deesser_enabled=args.deesser_enabled,
            deesser_low_hz=args.deesser_low_hz,
            deesser_high_hz=args.deesser_high_hz,
            deesser_threshold_db=args.deesser_threshold_db,
            deesser_ratio=args.deesser_ratio,
            deesser_attack_ms=args.deesser_attack_ms,
            deesser_release_ms=args.deesser_release_ms,
            demucs_model=args.demucs_model,
            demucs_device=args.demucs_device,
            demucs_if_speech=args.demucs_if_speech,
            noise_split_enabled=args.noise_split_enabled,
            noise_threshold_db=args.noise_threshold_db,
            noise_window_sec=args.noise_window_sec,
            clean_gain_db=args.clean_gain_db,
            clean_denoise_strength=args.clean_denoise_strength,
            clean_deesser_threshold_db=args.clean_deesser_threshold_db,
            clean_deesser_ratio=args.clean_deesser_ratio,
            noisy_gain_db=args.noisy_gain_db,
            noisy_denoise_strength=args.noisy_denoise_strength,
            noisy_deesser_threshold_db=args.noisy_deesser_threshold_db,
            noisy_deesser_ratio=args.noisy_deesser_ratio,
            split_enabled=args.split_enabled,
            split_top_db=args.split_top_db,
            split_min_duration_ms=args.split_min_duration_ms,
            split_merge_gap_ms=args.split_merge_gap_ms,
            split_pad_ms=args.split_pad_ms,
            split_normalize=args.split_normalize,
            split_gain_db=args.split_gain_db,
            split_max_duration_s=args.split_max_duration_s,
        )
        print(f"Stage report: {report_path}")

    elif args.command == "split":
        if args.input_file:
            manifest_path = split_audio(
                input_file=args.input_file,
                output_dir=args.output_dir,
                sr=args.sr,
                top_db=args.top_db,
                min_duration_ms=args.min_duration_ms,
                merge_gap_ms=args.merge_gap_ms,
                pad_ms=args.pad_ms,
            )
            print(f"Split manifest: {manifest_path}")
        elif args.input_dir:
            summary_path = split_directory(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                sr=args.sr,
                top_db=args.top_db,
                min_duration_ms=args.min_duration_ms,
                merge_gap_ms=args.merge_gap_ms,
                pad_ms=args.pad_ms,
            )
            print(f"Split summary: {summary_path}")
        else:
            print("Error: --input-file or --input-dir required")

    elif args.command == "split-ai":
        manifest_path = split_audio_ai(
            input_file=args.input_file,
            output_dir=args.output_dir,
            sr=args.sr,
            device=args.device,
            threshold_factor=args.threshold_factor,
            min_segment_ms=args.min_segment_ms,
            min_gap_frames=args.min_gap_frames,
            kernel_size=args.kernel_size,

            pad_ms=args.pad_ms,
            denoise=args.denoise,
            denoise_strength=args.denoise_strength,
        )
        print(f"AI split manifest: {manifest_path}")

    elif args.command == "split-samples":
        if args.mode == "cpu":
            out = split_to_samples(
                input_path=args.input,
                output_dir=args.output_dir,
                sr=args.sr,
                top_db=args.top_db,
                min_duration_ms=args.min_duration_ms,
                merge_gap_ms=args.merge_gap_ms,
                pad_ms=args.pad_ms,
                normalize=args.normalize,
                gain_db=args.gain_db,
            )
        else:
            out = split_to_samples_ai(
                input_path=args.input,
                output_dir=args.output_dir,
                sr=args.sr,
                device=args.device,
                threshold_factor=args.threshold_factor,
                min_segment_ms=args.min_segment_ms,
                min_gap_frames=args.min_gap_frames,
                kernel_size=args.kernel_size,
                pad_ms=args.pad_ms,
                denoise=args.denoise,
                denoise_strength=args.denoise_strength,
            )
        print(f"Samples output: {out}")


if __name__ == "__main__":
    main()
