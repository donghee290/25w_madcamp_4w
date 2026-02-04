import React, { createContext, useContext, useEffect, useState, useRef } from 'react';
import { beatApi } from '../api/beatApi';
import type {
    ProjectContextState,
    PipelineConfig, // Alias for BeatConfig in API
    SoundFile,
    BeatGrid,
    RoleType
} from '../types/beatType';

const ProjectContext = createContext<ProjectContextState | null>(null);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    // State
    const [beatName, setBeatName] = useState<string>('');
    const [isConnected, setIsConnected] = useState<boolean>(false);

    // Job Status
    const [jobStatus, setJobStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');
    const [jobProgress, setJobProgress] = useState<string>('');
    const [jobId, setJobId] = useState<string | null>(null);

    // Operational Flags
    const [isUploading, setIsUploading] = useState<boolean>(false);
    const [isGenerating, setIsGenerating] = useState<boolean>(false);

    // Data
    const [config, setConfig] = useState<PipelineConfig>({
        bpm: 120,
        style: 'rock',
        seed: 42,
        progressive: true,
        repeat_full: 8,
        export_format: 'mp3'
    });

    const [uploadedFiles, setUploadedFiles] = useState<SoundFile[]>([]);

    // Results
    const [grid, setGrid] = useState<BeatGrid | null>(null);
    const [rolePools, setRolePools] = useState<Record<RoleType, string[]> | null>(null);

    // Playback
    const [playbackState, setPlaybackState] = useState<{ isPlaying: boolean; currentTime: number; duration: number }>({
        isPlaying: false,
        currentTime: 0,
        duration: 0
    });

    // Polling ref
    const pollInterval = useRef<number | null>(null);

    // 1. Init Session on Mount
    useEffect(() => {
        const init = async () => {
            try {
                const res = await beatApi.createBeat();
                if (res.ok && res.beat_name) {
                    setBeatName(res.beat_name);
                    setIsConnected(true);
                    console.log(`[ProjectContext] Created beat session: ${res.beat_name}`);
                }
            } catch (e) {
                console.error("Failed to init beat session", e);
            }
        };
        init();
    }, []);

    // Helper to fetch full state
    const refreshState = async () => {
        if (!beatName) return;
        try {
            const res = await beatApi.getBeatState(beatName);
            if (res.ok && res.state) {
                if (res.state.config) {
                    setConfig(prev => ({ ...prev, ...res.state!.config }));
                }
                if (res.state.grid_content) {
                    setGrid(res.state.grid_content);
                }
                if (res.state.pools_content) {
                    setRolePools(res.state.pools_content);
                }
            }
        } catch (e) {
            console.error("Fetch state error", e);
        }
    };

    // Polling Logic
    useEffect(() => {
        if (!jobId) return;

        setJobStatus('running');
        // Clear existing interval if any (shouldn't happen with useEffect cleanup but safe)
        if (pollInterval.current) window.clearInterval(pollInterval.current);

        pollInterval.current = window.setInterval(async () => {
            try {
                const res = await beatApi.getJobStatus(jobId);
                if (res.ok && res.job) {
                    setJobProgress(res.job.progress);
                    // console.log(`[Job Progress] ${res.job.progress}`);

                    if (res.job.status === 'completed') {
                        setJobStatus('completed');
                        setIsGenerating(false);
                        setJobId(null); // Stop polling
                        await refreshState();
                    } else if (res.job.status === 'failed') {
                        setJobStatus('failed');
                        setJobProgress(res.job.error || 'Unknown error');
                        setIsGenerating(false);
                        setJobId(null); // Stop polling
                        alert(`Job failed: ${res.job.error}`);
                    }
                }
            } catch (e) {
                console.error("Polling error", e);
            }
        }, 1000);

        return () => {
            if (pollInterval.current) {
                window.clearInterval(pollInterval.current);
                pollInterval.current = null;
            }
        };
    }, [jobId]);

    // Actions
    const createBeat = async () => {
        window.location.reload();
    };

    const handleUpload = async (files: File[]) => {
        if (!beatName) return;

        const newFiles: SoundFile[] = files.map(f => ({
            id: f.name,
            file: f,
            name: f.name,
            status: 'uploading'
        }));
        setUploadedFiles(prev => [...prev, ...newFiles]);
        setIsUploading(true);

        try {
            await beatApi.uploadFiles(beatName, files);
            setUploadedFiles(prev => prev.map(f =>
                newFiles.some(nf => nf.id === f.id) ? { ...f, status: 'done' } : f
            ));
            await refreshState();
        } catch (e) {
            console.error(e);
            setUploadedFiles(prev => prev.map(f =>
                newFiles.some(nf => nf.id === f.id) ? { ...f, status: 'error' } : f
            ));
            alert("Upload failed");
        } finally {
            setIsUploading(false);
        }
    };

    const handleRemove = async (filename: string) => {
        if (!beatName) return;

        // Optimistic Remove
        setUploadedFiles(prev => prev.filter(f => f.name !== filename));

        try {
            await beatApi.deleteFile(beatName, filename);
            await refreshState();
        } catch (e) {
            console.error(e);
            alert("Remove failed");
            // Revert on fail? For now relying on refreshState or just alert.
            await refreshState();
        }
    };

    const generateBeat = async (customName?: string) => {
        if (!beatName) return;
        setIsGenerating(true);
        try {
            // Include beat_title in config if provided
            const finalConfig = customName ? { ...config, beat_title: customName } : config;
            const res = await beatApi.generateInitial(beatName, finalConfig);
            if (res.ok && res.job_id) {
                setJobId(res.job_id); // Start polling
            } else {
                setIsGenerating(false);
            }
        } catch (e) {
            console.error(e);
            setIsGenerating(false);
            alert("Generation failed");
        }
    };

    const regenerate = async (fromStage: number, params?: Partial<PipelineConfig>) => {
        if (!beatName) return;
        setIsGenerating(true);
        try {
            const res = await beatApi.regenerate(beatName, fromStage, params);
            if (res.ok && res.job_id) {
                setJobId(res.job_id); // Start polling
            } else {
                setIsGenerating(false);
            }
        } catch (e) {
            console.error(e);
            setIsGenerating(false);
            alert("Regeneration failed");
        }
    };

    const updateConfig = async (updates: Partial<PipelineConfig>) => {
        if (!beatName) return;
        setConfig(prev => ({ ...prev, ...updates }));
        await beatApi.updateConfig(beatName, updates);
    };

    const downloadUrl = (format: string = 'mp3') => {
        if (!beatName) {
            return '';
        }
        return beatApi.getDownloadUrl(beatName, format);
    };

    const value: ProjectContextState = {
        beatName,
        isConnected,
        jobStatus,
        jobProgress,

        isGenerating,
        isUploading,

        config,
        uploadedFiles,

        grid,
        rolePools,

        createBeat,
        uploadFiles: handleUpload,
        removeFile: handleRemove,
        generateBeat,
        regenerate,
        updateConfig,
        downloadUrl,

        playbackState,
        setPlaybackState
    };

    return (
        <ProjectContext.Provider value={value}>
            {children}
        </ProjectContext.Provider>
    );
};

export const useProject = () => {
    const ctx = useContext(ProjectContext);
    if (!ctx) throw new Error("useProject must be used within ProjectProvider");
    return ctx;
};
