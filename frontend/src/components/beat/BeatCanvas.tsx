import { useEffect } from 'react';
import { useProject } from '../../context/ProjectContext';
import type { RoleType } from '../../types/beatType';

const ROLE_COLORS: Record<RoleType, string> = {
    CORE: 'bg-orange-500',
    ACCENT: 'bg-yellow-400',
    MOTION: 'bg-blue-500',
    FILL: 'bg-purple-600',
    TEXTURE: 'bg-green-500',
};

// Simple row order
const ROW_ORDER: RoleType[] = ['CORE', 'ACCENT', 'MOTION', 'FILL', 'TEXTURE'];

const BeatCanvas = () => {
    const { grid, playbackState } = useProject();

    // DEBUG: Check events
    useEffect(() => {
        if (grid?.events) {
            console.log("[BeatCanvas] Received events:", grid.events.length, grid.events);
        } else {
            console.log("[BeatCanvas] No events in grid");
        }
    }, [grid]);

    if (!grid) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center bg-gray-50 text-gray-400">
                <div className="text-center">
                    <h3 className="text-xl font-bold text-gray-300 mb-2">Beat Canvas</h3>
                    <p className="text-sm">Upload sounds and click "Generate BEAT" to start.</p>
                </div>
            </div>
        )
    }

    // Grid Params
    const { bars, stepsPerBar } = grid;

    // Calculate Playhead Position
    const safeBpm = grid.bpm || 120;
    const secPerStep = (60 / safeBpm) / 4;
    // Current step in floating point
    const currentStep = playbackState.currentTime / secPerStep;

    const renderBar = (barIndex: number) => {
        const startStep = barIndex * stepsPerBar;
        const endStep = startStep + stepsPerBar;

        // Filter events for this bar (overlapping)
        const barEvents = grid.events.filter(e => {
            const eStart = e.step;
            const eDur = (e as any).dur_steps || (e as any).duration || 1;
            const eEnd = eStart + eDur;
            return eStart < endStep && eEnd > startStep;
        });

        // Playhead local calculation
        const isPlayheadInBar = currentStep >= startStep && currentStep < endStep;
        const playheadOffsetPercent = isPlayheadInBar
            ? ((currentStep - startStep) / stepsPerBar) * 100
            : 0;

        return (
            <div key={barIndex} className="mb-6 bg-white border border-gray-200 rounded-lg p-4 shadow-sm relative">
                {/* Bar Header */}
                <div className="flex items-center mb-3">
                    <span className="font-mono text-xs font-bold text-gray-500 bg-gray-100 px-2 py-1 rounded">
                        Bar {barIndex + 1}
                    </span>
                </div>

                {/* Step Grid Table */}
                <div className="grid grid-cols-[80px_1fr] gap-4">
                    {/* Row Labels */}
                    <div className="flex flex-col gap-1 pt-6 text-right">
                        {ROW_ORDER.map(role => (
                            <div key={role} className="h-8 flex items-center justify-end">
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded text-white ${ROLE_COLORS[role]}`}>
                                    {role}
                                </span>
                            </div>
                        ))}
                    </div>

                    {/* Grid Cells */}
                    <div className="relative">
                        {/* Playhead Overlay */}
                        {isPlayheadInBar && (
                            <div
                                className="absolute top-8 bottom-0 w-0.5 bg-yellow-400 z-10 shadow-[0_0_10px_rgba(250,204,21,0.8)] pointer-events-none transition-all duration-75 ease-linear"
                                style={{ left: `${playheadOffsetPercent}%` }}
                            />
                        )}

                        {/* Step Markers (Header) */}
                        <div className="flex h-6 mb-1 border-b border-gray-200">
                            {Array.from({ length: stepsPerBar }).map((_, i) => (
                                <div key={i} className={`flex-1 flex items-center justify-center text-[10px] text-gray-400 font-mono ${i % 4 === 0 ? 'font-bold text-gray-600' : ''}`}>
                                    {(i % 4) + 1}
                                </div>
                            ))}
                        </div>

                        {/* Lanes */}
                        <div className="flex flex-col gap-1 relative">
                            {/* Vertical Grid Lines every 4 steps (quarter note) */}
                            <div className="absolute inset-0 flex pointer-events-none">
                                {Array.from({ length: stepsPerBar }).map((_, i) => (
                                    <div key={i} className={`flex-1 border-r ${i % 4 === 3 ? 'border-gray-200' : 'border-gray-50/50'}`}></div>
                                ))}
                            </div>

                            {ROW_ORDER.map(role => (
                                <div key={role} className="h-8 flex bg-gray-50/50 rounded-sm overflow-hidden relative">
                                    {Array.from({ length: stepsPerBar }).map((_, stepOffset) => {
                                        const currentStep = startStep + stepOffset;

                                        const event = barEvents.find(e => {
                                            const eStart = e.step;
                                            const eDur = (e as any).dur_steps || (e as any).duration || 1;
                                            const eEnd = eStart + eDur;
                                            return e.role === role && currentStep >= eStart && currentStep < eEnd;
                                        });

                                        return (
                                            <div key={stepOffset} className="flex-1 p-0.5 border-r border-transparent">
                                                {event && (
                                                    <div
                                                        className={`w-full h-full rounded shadow-sm hover:scale-110 transition-transform cursor-pointer`}
                                                        style={{
                                                            backgroundColor: ROLE_COLORS[role].replace('bg-', '').replace('orange-500', '#f97316').replace('yellow-400', '#facc15').replace('blue-500', '#3b82f6').replace('purple-600', '#9333ea').replace('green-500', '#22c55e'),
                                                            minHeight: '20px',
                                                            width: '100%',
                                                            display: 'block'
                                                        }}
                                                        title={`Step: ${currentStep}, Vel: ${event.velocity}`}
                                                    ></div>
                                                )}
                                            </div>
                                        )
                                    })}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        )
    };

    return (
        <div className="flex-1 bg-gray-50 overflow-y-auto p-8">
            <div className="max-w-5xl mx-auto">
                <div className="flex justify-between items-center mb-6">
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        Beat Canvas
                        <span className="text-sm font-normal text-gray-400 bg-white px-2 py-1 rounded border border-gray-100">
                            {grid.bpm} BPM / {grid.bars} Bars
                        </span>
                    </h1>
                </div>

                <div className="space-y-4">
                    {Array.from({ length: bars }).map((_, i) => renderBar(i))}
                </div>
            </div>
        </div>
    );
};

export default BeatCanvas;
