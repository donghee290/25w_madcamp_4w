import { useEffect, useState } from 'react';
import { useProject } from '../../context/ProjectContext';
import { Play, Pause, ChevronLeft, ChevronRight } from 'lucide-react';
import type { RoleType } from '../../types/beatType';

// Single Source of Truth for Colors (Hex for reliability)
const ROLE_COLORS: Record<RoleType, string> = {
    CORE: '#f97316',   // orange-500
    ACCENT: '#facc15', // yellow-400
    MOTION: '#3b82f6', // blue-500
    FILL: '#9333ea',   // purple-600
    TEXTURE: '#22c55e', // green-500
};

const ROW_ORDER: RoleType[] = ['CORE', 'ACCENT', 'MOTION', 'FILL', 'TEXTURE'];

const BeatCanvas = () => {
    const { grid, playbackState, setPlaybackState } = useProject();

    // Local State for Pagination
    const [currentPage, setCurrentPage] = useState(0);

    // Constants
    const BARS_PER_PAGE = 4;

    // Grid Params
    const bars = grid?.bars || 4;
    const stepsPerBar = grid?.stepsPerBar || 16;
    const totalPages = Math.ceil(bars / BARS_PER_PAGE);

    // Playback Calculations
    const safeBpm = grid?.bpm || 120;
    const secPerStep = (60 / safeBpm) / 4;
    const currentTotalStep = playbackState.currentTime / secPerStep;
    const currentBarIndex = Math.floor(currentTotalStep / stepsPerBar);

    // Auto-Scroll Logic
    useEffect(() => {
        if (playbackState.isPlaying) {
            const pageForCurrentBar = Math.floor(currentBarIndex / BARS_PER_PAGE);
            if (pageForCurrentBar !== currentPage && pageForCurrentBar < totalPages) {
                setCurrentPage(pageForCurrentBar);
            }
        }
    }, [currentBarIndex, playbackState.isPlaying, totalPages, currentPage]);

    // Handlers
    const togglePlay = () => {
        setPlaybackState(prev => ({ ...prev, isPlaying: !prev.isPlaying }));
    };

    const prevPage = () => setCurrentPage(p => Math.max(0, p - 1));
    const nextPage = () => setCurrentPage(p => Math.min(totalPages - 1, p + 1));

    if (!grid) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center bg-gray-50 text-gray-400">
                <div className="text-center">
                    <h3 className="text-xl font-bold text-gray-300 mb-2">Beat Canvas</h3>
                    <p className="text-sm">Upload sounds and click "Generate BEAT" to start.</p>
                </div>
            </div>
        );
    }

    const renderBar = (barIndex: number) => {
        const startStep = barIndex * stepsPerBar;
        const endStep = startStep + stepsPerBar;

        // Filter events for this bar logic
        // We assume 'e.step' is ABSOLUTE because backend sends it that way.
        const barEvents = grid.events.filter(e => {
            const eStart = Number(e.step); // Absolute step
            const eDur = Number((e as any).dur_steps || (e as any).duration || 1);
            const eEnd = eStart + eDur;
            // Overlap check
            return eStart < endStep && eEnd > startStep;
        });

        // Playhead local calculation
        const isPlayheadInBar = currentTotalStep >= startStep && currentTotalStep < endStep;
        const playheadOffsetPercent = isPlayheadInBar
            ? ((currentTotalStep - startStep) / stepsPerBar) * 100
            : 0;

        return (
            <div key={barIndex} className="mb-6 bg-white border border-gray-200 rounded-lg p-4 shadow-sm relative overflow-hidden">
                {/* Bar Header */}
                <div className="flex items-center mb-3">
                    <span className="font-mono text-xs font-bold text-gray-500 bg-gray-100 px-2 py-1 rounded">
                        Bar {barIndex + 1}
                    </span>
                    {/* Visual active indicator */}
                    {isPlayheadInBar && playbackState.isPlaying && (
                        <span className="ml-2 w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    )}
                </div>

                {/* Grid Container */}
                <div className="relative">

                    {/* Timeline Header */}
                    <div className="flex h-8 mb-2">
                        {/* Spacer for labels */}
                        <div className="w-[80px] shrink-0 border-r border-transparent"></div>

                        {/* Steps Header */}
                        <div className="flex-1 flex">
                            {Array.from({ length: stepsPerBar }).map((_, i) => {
                                const sub = i % 4;
                                const beat = Math.floor(i / 4) + 1;
                                const label = sub === 0 ? beat : sub === 1 ? 'e' : sub === 2 ? '&' : 'a';
                                return (
                                    <div key={i} className={`flex-1 flex items-center justify-center text-[10px] font-mono border-l border-gray-100 ${sub === 0 ? 'font-bold text-gray-700' : 'text-gray-400'}`}>
                                        {label}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Playhead Overlay (Global for this bar) */}
                    {isPlayheadInBar && (
                        <div
                            className="absolute top-0 bottom-0 w-[2px] bg-red-500 z-50 pointer-events-none transition-all duration-75 linear shadow-[0_0_8px_rgba(239,68,68,0.4)]"
                            style={{
                                left: `calc(80px + (100% - 80px) * ${playheadOffsetPercent / 100})`,
                                transform: 'translateX(-50%)' // Center exactly on the point
                            }}
                        />
                    )}

                    {/* Lanes Container */}
                    <div className="flex flex-col">
                        {ROW_ORDER.map((role, idx) => (
                            <div key={role} className={`flex h-12 border-b border-gray-100 ${idx === 0 ? 'border-t' : ''} hover:bg-gray-50 transition-colors`}>
                                {/* Role Label */}
                                <div className="w-[80px] shrink-0 flex items-center justify-end pr-3 border-r border-gray-100">
                                    <span
                                        className="px-2 py-1 text-[10px] font-bold rounded text-white shadow-sm tracking-wide"
                                        style={{ backgroundColor: ROLE_COLORS[role] }}
                                    >
                                        {role}
                                    </span>
                                </div>

                                {/* Step Lane */}
                                <div className="flex-1 flex relative">
                                    {/* Vertical Grid Lines (Background for this row) */}
                                    <div className="absolute inset-0 flex pointer-events-none z-0">
                                        {Array.from({ length: stepsPerBar }).map((_, i) => (
                                            <div key={i} className={`flex-1 border-r ${i % 4 === 3 ? 'border-gray-200' : 'border-gray-50'}`}></div>
                                        ))}
                                    </div>

                                    {/* Notes */}
                                    {Array.from({ length: stepsPerBar }).map((_, stepOffset) => {
                                        const currentStep = startStep + stepOffset;

                                        // Find if this step is part of an event for this role
                                        const event = barEvents.find(e => {
                                            const eStart = Number(e.step);
                                            const eDur = Number((e as any).dur_steps || (e as any).duration || 1);
                                            const eEnd = eStart + eDur;
                                            const eRole = e.role ? e.role.toUpperCase() : '';
                                            return eRole === role && currentStep >= eStart && currentStep < eEnd;
                                        });

                                        return (
                                            <div key={stepOffset} className="flex-1 p-1 z-10 relative">
                                                {event && (
                                                    <div
                                                        className="w-full h-full rounded shadow-sm hover:scale-105 transition-all cursor-pointer ring-1 ring-black/5"
                                                        style={{
                                                            backgroundColor: ROLE_COLORS[role],
                                                        }}
                                                        title={`Vel: ${event.velocity}`}
                                                    />
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        );
    };

    // Pagination Range
    const startBarIdx = currentPage * BARS_PER_PAGE;
    const endBarIdx = Math.min(startBarIdx + BARS_PER_PAGE, bars);
    const visibleBarIndices = Array.from({ length: Math.max(0, endBarIdx - startBarIdx) }).map((_, i) => startBarIdx + i);

    return (
        <div className="flex-1 overflow-y-auto p-8 text-gray-800">
            <div className="max-w-5xl mx-auto">
                <div className="flex justify-between items-center mb-6">
                    <h1 className="text-2xl font-bold flex items-center gap-2 text-gray-800">
                        Beat Canvas
                    </h1>

                    <div className="flex items-center gap-4 bg-white p-2 rounded-lg shadow-sm border border-gray-200">
                        <button
                            onClick={togglePlay}
                            className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${playbackState.isPlaying ? 'bg-red-50 text-red-600 hover:bg-red-100' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                            title={playbackState.isPlaying ? "Pause" : "Play"}
                        >
                            {playbackState.isPlaying ? (
                                <Pause className="w-5 h-5 fill-current" />
                            ) : (
                                <Play className="w-5 h-5 fill-current ml-1" />
                            )}
                        </button>

                        <div className="h-6 w-px bg-gray-200 mx-1"></div>

                        <button
                            onClick={prevPage}
                            disabled={currentPage === 0}
                            className="p-2 rounded hover:bg-gray-100 text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            <ChevronLeft className="w-5 h-5" />
                        </button>

                        <span className="text-sm font-mono text-gray-600 min-w-[100px] text-center">
                            Bar {startBarIdx + 1}-{endBarIdx}
                            <span className="text-gray-400 mx-1">/</span>
                            {bars}
                        </span>

                        <button
                            onClick={nextPage}
                            disabled={currentPage >= totalPages - 1}
                            className="p-2 rounded hover:bg-gray-100 text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            <ChevronRight className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                <div className="space-y-4">
                    {visibleBarIndices.map(i => renderBar(i))}
                </div>

                {visibleBarIndices.length === 0 && (
                    <div className="text-center py-12 text-gray-400">
                        No bars in this range.
                    </div>
                )}
            </div>
        </div>
    );
};

export default BeatCanvas;
