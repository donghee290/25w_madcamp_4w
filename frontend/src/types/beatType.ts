import type { Dispatch, SetStateAction } from 'react';
export type RoleType = 'CORE' | 'ACCENT' | 'MOTION' | 'FILL' | 'TEXTURE';

export interface SoundFile {
    id: string; // usually filename
    file: File | null;
    name: string;
    url?: string;
    duration?: number;
    status: 'idle' | 'uploading' | 'done' | 'error';
}

export interface GridEvent {
    bar: number;     // 0-based bar index
    step: number;    // 0-based step index within the bar (0-15)
    role: RoleType;
    velocity: number; // 0-127 or 0-1
    duration: number; // in steps usually
    offset?: number;  // micro-timing
    sampleId?: string; // specific sample used
}

export interface BeatGrid {
    bars: number;
    stepsPerBar: number;
    bpm: number;
    events: GridEvent[];
}

export interface PipelineConfig {
    bpm: number;
    style: string;
    seed: number;
    progressive: boolean;
    repeat_full: number;
    export_format: 'wav' | 'mp3' | 'flac' | 'ogg' | 'm4a';
}

// Maps to the backend ProjectState but cleaned up for UI
export interface JobStatus {
    job_id: string;
    beat_name: string; // Renamed from project_name
    status: 'running' | 'completed' | 'failed';
    progress: string;
    result?: unknown;
    error?: string;
    created_at: number;
}

export interface ProjectContextState {
    beatName: string;
    isConnected: boolean;
    jobStatus: 'idle' | 'running' | 'completed' | 'failed';
    jobProgress: string;

    // Operational Flags
    isUploading: boolean;
    isGenerating: boolean;

    // Data
    config: PipelineConfig;
    uploadedFiles: SoundFile[];

    // Generation Results
    grid: BeatGrid | null;
    rolePools: Record<RoleType, string[]> | null;

    // Actions
    createBeat: () => Promise<void>;
    uploadFiles: (files: File[]) => Promise<void>;
    removeFile: (filename: string) => Promise<void>;
    generateBeat: (customName?: string) => Promise<void>;
    regenerate: (fromStage: number, params?: Partial<PipelineConfig>) => Promise<void>;
    updateConfig: (updates: Partial<PipelineConfig>) => Promise<void>;
    saveRoles: () => Promise<void>;
    downloadUrl: (format?: string) => string;
    previewUrl: () => string;

    // Playback Sync
    playbackState: {
        isPlaying: boolean;
        currentTime: number;
        duration: number;
    };
    setPlaybackState: Dispatch<SetStateAction<{ isPlaying: boolean; currentTime: number; duration: number }>>;

    // Global Modals
    modalState: {
        type: 'PREVIEW' | 'DELETE' | null;
        data?: any; // File for preview, filename string for delete
    };
    setModalState: Dispatch<SetStateAction<{ type: 'PREVIEW' | 'DELETE' | null; data?: any }>>;
    setRolePools: (pools: Record<RoleType, string[]>) => void;
}
