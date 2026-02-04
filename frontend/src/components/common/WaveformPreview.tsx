import React, { useEffect, useRef, useState } from 'react';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';

interface WaveformPreviewProps {
    file: File;
}

const WaveformPreview: React.FC<WaveformPreviewProps> = ({ file }) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    const [isPlaying, setIsPlaying] = useState(false);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);
    const [isDecoded, setIsDecoded] = useState(false);

    // 1. Initial Load & Decode
    useEffect(() => {
        if (!file) return;

        // Create HTML Audio for playback (sourcing from blob)
        const url = URL.createObjectURL(file);
        const audio = new Audio(url);
        audioRef.current = audio;

        // Decode for Waveform
        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
        const reader = new FileReader();

        reader.onload = async (e) => {
            if (e.target?.result) {
                try {
                    const arrayBuffer = e.target.result as ArrayBuffer;
                    const decoded = await ctx.decodeAudioData(arrayBuffer);
                    setAudioBuffer(decoded);
                    setIsDecoded(true);
                } catch (err) {
                    console.error("Error decoding audio data", err);
                }
            }
        };
        reader.readAsArrayBuffer(file);

        // Bind Audio Events
        audio.addEventListener('loadedmetadata', () => setDuration(audio.duration));
        audio.addEventListener('timeupdate', () => setCurrentTime(audio.currentTime));
        audio.addEventListener('ended', () => setIsPlaying(false));
        audio.addEventListener('play', () => setIsPlaying(true));
        audio.addEventListener('pause', () => setIsPlaying(false));

        return () => {
            audio.pause();
            audio.src = '';
            URL.revokeObjectURL(url);
            ctx.close();
        };
    }, [file]);

    // 2. Draw Waveform
    useEffect(() => {
        if (!isDecoded || !audioBuffer || !canvasRef.current || !containerRef.current) return;

        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;

        // Handle HiDPI
        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);

        // Styling
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#374151'; // Dark gray bg
        ctx.fillRect(0, 0, width, height);

        // Draw Bars
        const rawData = audioBuffer.getChannelData(0); // Use Left channel
        // Let's use bar width logic
        const barWidth = 4;
        const gap = 2;
        const totalBars = Math.floor(width / (barWidth + gap));

        // Calculate step size (samples per bar)
        const step = Math.floor(rawData.length / totalBars);

        ctx.fillStyle = '#facc15'; // Yellow/Orange accent (text-yellow-400 approx)

        for (let i = 0; i < totalBars; i++) {
            let min = 1.0;
            let max = -1.0;

            // Find peak in this chunk
            for (let j = 0; j < step; j++) {
                const val = rawData[(i * step) + j];
                if (val < min) min = val;
                if (val > max) max = val;
            }

            // Normalize header
            const magnitude = Math.max(Math.abs(min), Math.abs(max));
            // Scale height (use 80% of canvas height max)
            const barHeight = Math.max(2, magnitude * height * 0.8);

            const x = i * (barWidth + gap);
            const y = (height - barHeight) / 2;

            // Rounded bar rect?
            ctx.fillRect(x, y, barWidth, barHeight);
        }

    }, [isDecoded, audioBuffer]);

    // 3. Toggle Playback
    const togglePlay = () => {
        if (audioRef.current) {
            if (isPlaying) audioRef.current.pause();
            else audioRef.current.play();
        }
    };

    // 4. Seek Helper
    const seek = (seconds: number) => {
        if (audioRef.current) {
            audioRef.current.currentTime = Math.min(Math.max(audioRef.current.currentTime + seconds, 0), duration);
        }
    };

    // 5. Click to Seek (Canvas interaction)
    const handleCanvasClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (!audioRef.current || !containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = x / rect.width;
        audioRef.current.currentTime = percent * duration;
    };

    // Formatted time
    const formatTime = (t: number) => {
        const m = Math.floor(t / 60);
        const s = Math.floor(t % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    // Progress Overlay Width
    const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;

    return (
        <div className="w-full">
            <p className="font-bold mb-2 truncate text-sm">{file.name}</p>

            {/* Waveform Container */}
            <div
                ref={containerRef}
                className="relative w-full h-32 bg-gray-700 rounded-lg overflow-hidden cursor-pointer group"
                onClick={handleCanvasClick}
            >
                <canvas
                    ref={canvasRef}
                    className="w-full h-full block"
                    style={{ width: '100%', height: '100%' }}
                />

                {/* Playhead Overlay */}
                <div
                    className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_8px_rgba(255,255,255,0.8)] pointer-events-none transition-all duration-75 ease-linear z-10"
                    style={{ left: `${progressPercent}%` }}
                />

                {/* Duration text */}
                <div className="absolute bottom-1 right-2 text-[10px] text-white/80 font-mono pointer-events-none">
                    {formatTime(currentTime)} / {formatTime(duration)}
                </div>
            </div>

            {/* Controls */}
            <div className="flex justify-center items-center gap-6 mt-4">
                <button onClick={() => seek(-1)} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                    <SkipBack className="w-6 h-6 fill-black" />
                </button>

                <button onClick={togglePlay} className="p-3 hover:bg-gray-100 rounded-full transition-colors">
                    {isPlaying ? (
                        <Pause className="w-8 h-8 fill-black" />
                    ) : (
                        <Play className="w-8 h-8 fill-black ml-1" />
                    )}
                </button>

                <button onClick={() => seek(1)} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                    <SkipForward className="w-6 h-6 fill-black" />
                </button>
            </div>
        </div>
    );
};

export default WaveformPreview;
