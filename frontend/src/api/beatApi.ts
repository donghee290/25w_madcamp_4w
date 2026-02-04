import { http } from "./http";
import type { BeatGrid, RoleType } from "../types/beatType";

export interface ProjectState {
    created_at?: string;
    uploads_dir?: string;
    config: {
        bpm: number;
        style: string;
        seed: number;
        progressive: boolean;
        repeat_full: number;
        export_format?: "wav" | "mp3" | "flac" | "ogg" | "m4a";
        [key: string]: any;
    };
    latest_s1_dir?: string;
    latest_pools_json?: string;
    latest_grid_json?: string;
    latest_skeleton_json?: string;
    latest_transformer_json?: string;
    latest_event_grid_json?: string;
    latest_editor_json?: string;
    latest_audio_path?: string;
    latest_export_format?: string;
    latest_mp3?: string;
    latest_wav?: string;
    updated_at?: number;

    // Injected Content
    grid_content?: BeatGrid;
    pools_content?: Record<RoleType, string[]>;
}

export interface JobStatus {
    job_id: string;
    project_name: string;
    status: "running" | "completed" | "failed";
    progress: string;
    result?: any;
    error?: string;
    created_at: number;
}

export const beatApi = {
    // 1. Create Project
    create: async (projectName?: string) => {
        const res = await http.post("/api/projects", { project_name: projectName });
        return res.data; // { ok: true, project_name: "..." }
    },

    // 2. Upload Files
    upload: async (projectName: string, files: File[]) => {
        const formData = new FormData();
        files.forEach((f) => formData.append("audio", f));

        // Header 'Content-Type': 'multipart/form-data' is handled automatically by axios when passing FormData
        const res = await http.post(`/api/projects/${projectName}/upload`, formData, {
            headers: { "Content-Type": "multipart/form-data" },
        });
        return res.data;
    },

    // 3. Initial Generation (Full Pipeline)
    generateInitial: async (projectName: string, params?: any) => {
        // params: { bpm, style, seed, export_format, ... }
        const res = await http.post(`/api/projects/${projectName}/generate/initial`, params);
        return res.data; // { ok: true, job_id: "..." }
    },

    // 4. Get Project State
    getState: async (projectName: string) => {
        const res = await http.get<{ ok: boolean; state: ProjectState }>(
            `/api/projects/${projectName}/state`
        );
        return res.data.state;
    },

    // 5. Update Configuration
    updateConfig: async (projectName: string, config: Partial<ProjectState["config"]>) => {
        const res = await http.patch(`/api/projects/${projectName}/config`, config);
        return res.data; // { ok: true, config: ... }
    },

    // 6. Regenerate (Partial)
    regenerate: async (projectName: string, fromStage: number, params?: any) => {
        const res = await http.post(`/api/projects/${projectName}/regenerate`, {
            from_stage: fromStage,
            params,
        });
        return res.data; // { ok: true, job_id: "..." }
    },

    // 7. Poll Job Status
    getJobStatus: async (jobId: string) => {
        const res = await http.get<{ ok: boolean; job: JobStatus }>(`/api/jobs/${jobId}`);
        return res.data.job;
    },

    // 8. Download URL helper
    getDownloadUrl: (projectName: string, kind: string = "mp3") => {
        const baseURL = http.defaults.baseURL || "";
        // Note: 'kind' matches the requested format (wav, mp3, flac, etc.)
        return `${baseURL}/api/projects/${projectName}/download?kind=${kind}`;
    },
};
