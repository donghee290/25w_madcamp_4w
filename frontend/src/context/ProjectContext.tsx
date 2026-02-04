import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { beatApi } from '../api/beatApi';
import type {
    ProjectContextState,
    PipelineConfig,
    SoundFile,
    BeatGrid,
    RoleType
} from '../types/beatType';

const ProjectContext = createContext<ProjectContextState | null>(null);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [projectName, setProjectName] = useState<string>('');

    // Job Status
    const [jobStatus, setJobStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle');
    const [jobProgress, setJobProgress] = useState<string>('');

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
    const [grid, _setGrid] = useState<BeatGrid | null>(null);
    const [rolePools, _setRolePools] = useState<Record<RoleType, string[]> | null>(null);
    const [isConnected, setIsConnected] = useState<boolean>(false);

    // Polling ref
    const pollInterval = useRef<number | null>(null);

    // Pending Upload Promise (for chaining generate)
    const currentUploadPromise = useRef<Promise<any> | null>(null);

    // 1. Init Project on Mount
    useEffect(() => {
        const init = async () => {
            try {
                const res = await beatApi.create();
                if (res.ok && res.project_name) {
                    setProjectName(res.project_name);
                    setIsConnected(true);
                }
            } catch (e) {
                console.error("Failed to init project", e);
            }
        };
        init();
    }, []);

    const fetchState = async (name: string) => {
        try {
            const state = await beatApi.getState(name);
            if (state.config) {
                setConfig(prev => ({ ...prev, ...state.config }));
            }
            if (state.grid_content) {
                _setGrid(state.grid_content);
            }
            if (state.pools_content) {
                _setRolePools(state.pools_content);
            }
        } catch (e) {
            console.error("Fetch state error", e);
        }
    };

    // Poll Job Status Logic
    const startPolling = useCallback((jobId: string) => {
        setJobStatus('running');
        if (pollInterval.current) clearInterval(pollInterval.current);

        pollInterval.current = window.setInterval(async () => {
            try {
                const job = await beatApi.getJobStatus(jobId);
                setJobProgress(job.progress);
                console.log(`[Job Progress] ${job.progress}`); // Log progress to browser console

                if (job.status === 'completed') {
                    setJobStatus('completed');
                    if (pollInterval.current) {
                        clearInterval(pollInterval.current);
                        pollInterval.current = null;
                    }
                    await fetchState(job.project_name);
                } else if (job.status === 'failed') {
                    setJobStatus('failed');
                    setJobProgress(job.error || 'Unknown error');
                    if (pollInterval.current) clearInterval(pollInterval.current);
                }
            } catch (e) {
                console.error("Polling error", e);
            }
        }, 1000);
    }, []);

    // Actions
    const createProject = async () => {
        window.location.reload();
    };

    const uploadFilesActions = async (files: File[]) => {
        if (!projectName) return;

        const newFiles: SoundFile[] = files.map(f => ({
            id: f.name,
            file: f,
            name: f.name,
            status: 'uploading'
        }));
        setUploadedFiles(prev => [...prev, ...newFiles]);

        try {
            const uploadPromise = beatApi.upload(projectName, files);
            currentUploadPromise.current = uploadPromise;
            await uploadPromise;

            setUploadedFiles(prev => prev.map(f =>
                newFiles.some(nf => nf.id === f.id) ? { ...f, status: 'done' } : f
            ));
        } catch (e) {
            console.error(e);
            setUploadedFiles(prev => prev.map(f =>
                newFiles.some(nf => nf.id === f.id) ? { ...f, status: 'error' } : f
            ));
        } finally {
            currentUploadPromise.current = null;
        }
    };

    const generateInitial = async () => {
        if (!projectName) return;

        // Wait for pending upload if chained
        if (currentUploadPromise.current) {
            setJobStatus('running');
            setJobProgress('Finishing upload...');
            try {
                await currentUploadPromise.current;
            } catch (e) {
                console.error("Implicit upload failed", e);
                setJobStatus('failed');
                return;
            }
        }

        try {
            const res = await beatApi.generateInitial(projectName, config);
            if (res.ok && res.job_id) {
                startPolling(res.job_id);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const regenerate = async (fromStage: number, params?: Partial<PipelineConfig>) => {
        if (!projectName) return;
        try {
            const res = await beatApi.regenerate(projectName, fromStage, params);
            if (res.ok && res.job_id) {
                startPolling(res.job_id);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const updateConfigHandler = async (updates: Partial<PipelineConfig>) => {
        if (!projectName) return;
        setConfig(prev => ({ ...prev, ...updates }));
        await beatApi.updateConfig(projectName, updates);
    };

    try {
        if (isConnected) {
            // Check if active audio is available via some other call or just downloadUrl (done in components)
        }
    } catch { }

    const downloadUrl = (format: string = 'mp3') => {
        if (!projectName) return '';
        return beatApi.getDownloadUrl(projectName, format);
    };

    return (
        <ProjectContext.Provider value={{
            projectName,
            isConnected,
            jobStatus,
            jobProgress,
            config,
            uploadedFiles,
            grid,
            rolePools,
            createProject,
            uploadFiles: uploadFilesActions,
            generateInitial,
            regenerate,
            updateConfig: updateConfigHandler,
            downloadUrl
        }}>
            {children}
        </ProjectContext.Provider>
    );
};

export const useProject = () => {
    const ctx = useContext(ProjectContext);
    if (!ctx) throw new Error("useProject must be used within ProjectProvider");
    return ctx;
};
