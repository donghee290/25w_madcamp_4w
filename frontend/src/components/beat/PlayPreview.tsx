import React, { useRef, useState, useEffect } from 'react';
import { useProject } from '../../context/ProjectContext';
import { Play, Pause, SkipBack, SkipForward } from 'lucide-react';

const PlayPreview = () => {
    const { grid, isConnected, previewUrl, playbackState, setPlaybackState } = useProject();

    // Playback State
    const [isPlaying, setIsPlaying] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [audioUrl, setAudioUrl] = useState<string>('');
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);

    // Fetch Preview URL when available
    useEffect(() => {
        if (isConnected && grid) {
            // Use preview endpoint which doesn't force render
            const url = previewUrl();
            console.log("[PlayPreview] Setting audioUrl:", url);
            setAudioUrl(url);
        } else {
            setAudioUrl('');
        }
    }, [isConnected, grid]);

    // Sync with Context State (Remote Control)
    useEffect(() => {
        if (!audioRef.current) return;

        // If context says playing but audio is paused -> play
        if (playbackState.isPlaying && audioRef.current.paused) {
            audioRef.current.play().catch(e => console.error("Remote play failed", e));
            setIsPlaying(true);
        }
        // If context says paused but audio is playing -> pause
        else if (!playbackState.isPlaying && !audioRef.current.paused) {
            audioRef.current.pause();
            setIsPlaying(false);
        }
    }, [playbackState.isPlaying]);

    // Audio Events
    const togglePlay = () => {
        if (!audioRef.current) return;
        if (isPlaying) {
            audioRef.current.pause();
        } else {
            audioRef.current.play().catch(e => console.error("Play failed", e));
        }
        const newPlayingState = !isPlaying;
        setIsPlaying(newPlayingState);

        // Sync to context immediately
        setPlaybackState((prev: { isPlaying: boolean; currentTime: number; duration: number }) => ({ ...prev, isPlaying: newPlayingState, currentTime, duration }));
    };

    const onTimeUpdate = () => {
        if (audioRef.current) {
            const curr = audioRef.current.currentTime;
            const dur = audioRef.current.duration || 0;
            setCurrentTime(curr);
            setDuration(dur);
            // Sync to context
            // Note: We don't partial update here anymore to avoid race loops, or we just push time
            setPlaybackState((prev: { isPlaying: boolean; currentTime: number; duration: number }) => ({ ...prev, currentTime: curr, duration: dur }));
        }
    };

    const handleEnded = () => {
        setIsPlaying(false);
        setCurrentTime(0);
        setPlaybackState((prev: { isPlaying: boolean; currentTime: number; duration: number }) => ({ ...prev, isPlaying: false, currentTime: 0, duration }));
    };

    const onLoadedMetadata = () => {
        if (audioRef.current) {
            setDuration(audioRef.current.duration);
        }
    };

    const handleProgressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const time = parseFloat(e.target.value);
        if (audioRef.current) {
            audioRef.current.currentTime = time;
            setCurrentTime(time);
            setPlaybackState((prev: { isPlaying: boolean; currentTime: number; duration: number }) => ({ ...prev, currentTime: time }));
        }
    };

    return (
        <div className="h-16 bg-white border-t border-gray-200 flex items-center px-6 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] z-10 w-full">
            <audio
                ref={audioRef}
                src={audioUrl}
                onTimeUpdate={onTimeUpdate}
                onEnded={handleEnded}
                onLoadedMetadata={onLoadedMetadata}
            />

            {/* Transport Controls */}
            <div className="flex-1 flex items-center justify-center gap-4">
                <div className="flex items-center gap-4">
                    <button className="text-gray-400 hover:text-gray-600"><SkipBack className="w-5 h-5" /></button>
                    <button
                        onClick={togglePlay}
                        disabled={!audioUrl}
                        className={`w-10 h-10 rounded-full flex items-center justify-center hover:scale-105 transition-transform shadow-md
                            ${!audioUrl ? 'bg-gray-200 text-gray-400 cursor-not-allowed' : 'bg-black text-white'}
                        `}
                    >
                        {isPlaying ? <Pause className="fill-current w-4 h-4 ml-0.5" /> : <Play className="fill-current w-4 h-4 ml-1" />}
                    </button>
                    <button className="text-gray-400 hover:text-gray-600"><SkipForward className="w-5 h-5" /></button>
                </div>

                {/* Scrubber */}
                <div className="w-full max-w-xl flex items-center gap-3 text-xs font-mono text-gray-500 ml-4">
                    <span>{formatTime(currentTime)}</span>
                    <input
                        type="range"
                        min="0"
                        max={duration || 100}
                        value={currentTime}
                        onChange={handleProgressChange}
                        className="flex-1 h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-black"
                    />
                    <span>{formatTime(duration)}</span>
                </div>
            </div>
        </div>
    );
};

const formatTime = (sec: number) => {
    if (!sec) return "0:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
};

export default PlayPreview;
