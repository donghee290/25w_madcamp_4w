"""DSP-based Sequencing Loop Generator (EventGrid Edition)"""

from pathlib import Path
from drumgenx.sequencer import load_kit, render_and_save
from drumgenx.events import EventGrid, DrumEvent
from drumgenx.scoring import DrumRole

def create_user_ex1_grid(bars: int = 4, bpm: float = 70.0) -> EventGrid:
    """Implement Ex.1 using new EventGrid system."""
    grid = EventGrid(bpm=bpm, bars=bars)
    
    # 1. MOTION (Hi-hat): 8th notes
    # 2. CORE (Kick): 1, 3
    # 3. ACCENT (Snare): 2, 4
    
    for bar in range(bars):
        # MOTION: 0, 2, 4, 6... (8th notes)
        for step in range(0, 16, 2):
            if bar == bars - 1 and step in [12, 14]: continue # Skip hihat during fill
            
            grid.add_event(DrumEvent(
                bar=bar, step=step, role=DrumRole.MOTION,
                sample_id="motion", vel=0.7, dur_steps=1
            ))
            
        # CORE: 0, 8 (Beats 1, 3)
        grid.add_event(DrumEvent(bar=bar, step=0, role=DrumRole.CORE, sample_id="core", vel=1.0))
        grid.add_event(DrumEvent(bar=bar, step=8, role=DrumRole.CORE, sample_id="core", vel=1.0))
        
        # ACCENT: 4, 12 (Beats 2, 4)
        if bar == bars - 1:
            # Fill (Bar 4)
            grid.add_event(DrumEvent(bar=bar, step=4, role=DrumRole.ACCENT, sample_id="accent", vel=1.0))
            
            # RLRL Roll on beat 4 (steps 12, 13, 14, 15)
            # R L R L -> Accent Accent Accent Accent
            grid.add_event(DrumEvent(bar=bar, step=12, role=DrumRole.ACCENT, sample_id="accent", vel=0.9))
            grid.add_event(DrumEvent(bar=bar, step=13, role=DrumRole.ACCENT, sample_id="accent", vel=0.8))
            grid.add_event(DrumEvent(bar=bar, step=14, role=DrumRole.ACCENT, sample_id="accent", vel=0.9))
            grid.add_event(DrumEvent(bar=bar, step=15, role=DrumRole.ACCENT, sample_id="accent", vel=0.8))
        else:
            grid.add_event(DrumEvent(bar=bar, step=4, role=DrumRole.ACCENT, sample_id="accent", vel=1.0))
            grid.add_event(DrumEvent(bar=bar, step=12, role=DrumRole.ACCENT, sample_id="accent", vel=1.0))
            
    return grid

def generate_dsp_loop(kit_dir: Path, output_path: Path):
    print(f"Loading kit from {kit_dir}")
    kit = load_kit(kit_dir)
    
    print("Generating User Ex.1 Pattern (EventGrid)...")
    grid = create_user_ex1_grid(bars=4, bpm=70.0)
    
    # Render with Reverb
    print(f"Rendering to {output_path} (BPM=70, Reverb=1.2s)...")
    render_and_save(grid, kit, output_path, reverb=True)
    print("Done!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        pass # Allow running without args for testing inside agent
        # print("Usage: python -m drumgenx.gen_dsp_loop <kit_dir> <output_wav>")
        # sys.exit(1)
    
    if len(sys.argv) >= 3:
        generate_dsp_loop(Path(sys.argv[1]), Path(sys.argv[2]))
