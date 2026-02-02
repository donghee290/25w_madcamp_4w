"""CLI entry point for DrumGen-X."""

import argparse
from pathlib import Path

from .config import PipelineConfig, SequencerConfig
from .utils import setup_logging, logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DrumGen-X: AI drum kit separation & generative sequencer"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- scan ---
    scan_p = subparsers.add_parser("scan", help="Scan dataset and print stats")
    scan_p.add_argument("--dataset-root", type=Path, default=None,
                        help="Dataset root directory (default: config)")
    scan_p.add_argument("--sample-n", type=int, default=5,
                        help="Number of files to check duration")

    # --- separate ---
    sep_p = subparsers.add_parser("separate", help="Extract drum stem from audio")
    sep_p.add_argument("input", type=Path, help="Input audio file")
    sep_p.add_argument("--output-dir", type=Path, default=None)
    sep_p.add_argument("--device", type=str, default="cuda")
    sep_p.add_argument("--model", type=str, default="htdemucs")
    sep_p.add_argument("--sr", type=int, default=44100)

    # --- detect ---
    det_p = subparsers.add_parser("detect", help="Detect drum onsets")
    det_p.add_argument("input", type=Path, help="Drum stem WAV file")
    det_p.add_argument("--sr", type=int, default=44100)
    det_p.add_argument("--merge-ms", type=float, default=30.0)

    # --- classify ---
    cls_p = subparsers.add_parser("classify", help="Detect + classify drum hits")
    cls_p.add_argument("input", type=Path, help="Drum stem WAV file")
    cls_p.add_argument("--sr", type=int, default=44100)
    cls_p.add_argument("--output-dir", type=Path, default=None)

    # --- build-kit ---
    kit_p = subparsers.add_parser("build-kit", help="Full: separate -> detect -> classify -> slice")
    kit_p.add_argument("input", type=Path, help="Input audio file")
    kit_p.add_argument("--output-dir", type=Path, default=None)
    kit_p.add_argument("--device", type=str, default="cuda")
    kit_p.add_argument("--model", type=str, default="htdemucs")
    kit_p.add_argument("--sr", type=int, default=44100)

    # --- sequence ---
    seq_p = subparsers.add_parser("sequence", help="Generate drum loop from kit")
    seq_p.add_argument("kit_dir", type=Path, help="Kit directory")
    seq_p.add_argument("--output-dir", type=Path, default=None)
    seq_p.add_argument("--pattern", type=str, default="rock",
                       choices=["rock", "hiphop", "jazz"])
    seq_p.add_argument("--bpm", type=float, default=120.0)
    seq_p.add_argument("--bars", type=int, default=4)
    seq_p.add_argument("--sr", type=int, default=44100)

    # --- pipeline ---
    pipe_p = subparsers.add_parser("pipeline", help="Full automated pipeline")
    pipe_p.add_argument("--dataset-root", type=Path, default=None)
    pipe_p.add_argument("--output-root", type=Path, default=None)
    pipe_p.add_argument("--n-files", type=int, default=5)
    pipe_p.add_argument("--device", type=str, default="cuda")
    pipe_p.add_argument("--model", type=str, default="htdemucs")
    pipe_p.add_argument("--sr", type=int, default=44100)
    pipe_p.add_argument("--bpm", type=float, default=120.0)
    pipe_p.add_argument("--best-per-class", type=int, default=10)

    # --- show ---
    show_p = subparsers.add_parser("show", help="Display event grid as ASCII score")
    show_p.add_argument("grid", type=Path, help="Path to event_grid.json")

    # --- generate ---
    gen_p = subparsers.add_parser("generate", help="Generate skeleton pattern")
    gen_p.add_argument("output", type=Path, help="Output event_grid.json path")
    gen_p.add_argument("--bpm", type=float, default=120.0)
    gen_p.add_argument("--bars", type=int, default=4)
    gen_p.add_argument("--kit-dir", type=str, default=None)

    # --- set ---
    set_p = subparsers.add_parser("set", help="Set event at grid position")
    set_p.add_argument("grid", type=Path, help="Path to event_grid.json")
    set_p.add_argument("--bar", type=int, required=True)
    set_p.add_argument("--step", type=int, required=True)
    set_p.add_argument("--role", type=str, required=True,
                       choices=["core", "accent", "motion", "fill", "texture"])
    set_p.add_argument("--vel", type=float, default=0.8)
    set_p.add_argument("--dur", type=int, default=1)
    set_p.add_argument("--sample-id", type=str, default=None)

    # --- remove ---
    rm_p = subparsers.add_parser("remove", help="Remove events at grid position")
    rm_p.add_argument("grid", type=Path, help="Path to event_grid.json")
    rm_p.add_argument("--bar", type=int, required=True)
    rm_p.add_argument("--step", type=int, required=True)
    rm_p.add_argument("--role", type=str, default=None,
                      choices=["core", "accent", "motion", "fill", "texture"])

    # --- velocity ---
    vel_p = subparsers.add_parser("velocity", help="Adjust event velocities")
    vel_p.add_argument("grid", type=Path, help="Path to event_grid.json")
    vel_p.add_argument("--role", type=str, default=None,
                       choices=["core", "accent", "motion", "fill", "texture"])
    vel_group = vel_p.add_mutually_exclusive_group(required=True)
    vel_group.add_argument("--value", type=float, help="Set absolute velocity (0-1)")
    vel_group.add_argument("--scale", type=float, help="Scale velocity by factor")

    # --- render ---
    rend_p = subparsers.add_parser("render", help="Render event grid to audio")
    rend_p.add_argument("grid", type=Path, help="Path to event_grid.json")
    rend_p.add_argument("--output", type=Path, required=True)
    rend_p.add_argument("--kit-dir", type=Path, default=None)
    rend_p.add_argument("--sr", type=int, default=44100)
    rend_p.add_argument("--reverb", action="store_true")
    rend_p.add_argument("--format", type=str, default="wav", choices=["wav", "mp3"])

    # --- export-midi ---
    midi_p = subparsers.add_parser("export-midi", help="Export event grid to MIDI")
    midi_p.add_argument("grid", type=Path, help="Path to event_grid.json")
    midi_p.add_argument("--output", type=Path, required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging()

    if args.command == "scan":
        from .ingest import generate_report
        config = PipelineConfig()
        root = args.dataset_root or config.dataset_root
        report = generate_report(root, sample_n=args.sample_n)
        print(report.to_json())

    elif args.command == "separate":
        from .separator import extract_drum_stem
        output_dir = args.output_dir or (args.input.parent / f"{args.input.stem}_drums")
        drums_path = extract_drum_stem(
            args.input, output_dir,
            model=args.model, device=args.device, sr=args.sr,
        )
        print(f"Drums extracted: {drums_path}")

    elif args.command == "detect":
        from .detector import detect_onsets
        from .utils import load_audio
        y, _ = load_audio(args.input, sr=args.sr)
        onsets = detect_onsets(y, args.sr, merge_ms=args.merge_ms)
        print(f"Detected {len(onsets)} onsets")
        for i, onset in enumerate(onsets[:20]):
            print(f"  {i+1}: {onset/args.sr:.3f}s")
        if len(onsets) > 20:
            print(f"  ... and {len(onsets)-20} more")

    elif args.command == "classify":
        from .detector import detect_onsets
        from .slicer import build_kit_from_audio
        from .utils import load_audio
        y, _ = load_audio(args.input, sr=args.sr)
        onsets = detect_onsets(y, args.sr)
        output_dir = args.output_dir or (args.input.parent / f"{args.input.stem}_kit")
        manifest_path, organized = build_kit_from_audio(
            y, args.sr, onsets, output_dir,
        )
        print(f"Kit manifest: {manifest_path}")

    elif args.command == "build-kit":
        from .run_pipeline import process_single_file
        config = PipelineConfig(
            sr=args.sr,
            demucs_model=args.model,
            demucs_device=args.device,
        )
        output_dir = args.output_dir or (args.input.parent / f"{args.input.stem}_drumkit")
        kit_dir = process_single_file(args.input, output_dir, config)
        if kit_dir:
            print(f"Kit built: {kit_dir}")
        else:
            print("Kit build failed: no onsets detected")

    elif args.command == "sequence":
        from .test_synth import quick_test
        output_dir = args.output_dir or (args.kit_dir / "test_loops")
        output = quick_test(
            args.kit_dir, output_dir,
            sr=args.sr, bpm=args.bpm, bars=args.bars,
            pattern_name=args.pattern,
        )
        print(f"Loop generated: {output}")

    elif args.command == "pipeline":
        from .run_pipeline import run_full_pipeline
        config = PipelineConfig(
            sr=args.sr,
            demucs_model=args.model,
            demucs_device=args.device,
            n_files=args.n_files,
            best_per_class=args.best_per_class,
        )
        if args.dataset_root:
            config.dataset_root = args.dataset_root
        if args.output_root:
            config.output_root = args.output_root
        run_dir = run_full_pipeline(config)
        print(f"Pipeline output: {run_dir}")

    elif args.command == "show":
        from .editor import cmd_show
        cmd_show(args.grid)

    elif args.command == "generate":
        from .editor import cmd_generate
        cmd_generate(args.output, bpm=args.bpm, bars=args.bars, kit_dir=args.kit_dir)

    elif args.command == "set":
        from .editor import cmd_set
        cmd_set(args.grid, bar=args.bar, step=args.step, role=args.role,
                vel=args.vel, sample_id=args.sample_id, dur_steps=args.dur)

    elif args.command == "remove":
        from .editor import cmd_remove
        cmd_remove(args.grid, bar=args.bar, step=args.step, role=args.role)

    elif args.command == "velocity":
        from .editor import cmd_velocity
        cmd_velocity(args.grid, role=args.role, value=args.value, scale=args.scale)

    elif args.command == "render":
        from .editor import cmd_render
        cmd_render(args.grid, output_path=args.output, kit_dir=args.kit_dir,
                   sr=args.sr, reverb=args.reverb, fmt=args.format)

    elif args.command == "export-midi":
        from .editor import cmd_export_midi
        cmd_export_midi(args.grid, output_path=args.output)


if __name__ == "__main__":
    main()
