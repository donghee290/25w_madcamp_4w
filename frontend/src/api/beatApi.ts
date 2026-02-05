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
        beat_title?: string;
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

// Assuming API_BASE is defined elsewhere, e.g., in a config file or environment variable
// For this refactor, we'll define it here for completeness.
const API_BASE = http.defaults.baseURL || ""; // Use the existing http client's base URL

type BeatConfig = ProjectState["config"]; // Assuming BeatConfig refers to the project's config structure

// Response Types
export interface BeatCreationResponse {
    ok: boolean;
    beat_name: string;
    error?: string;
}

export interface FileUploadResponse {
    ok: boolean;
    beat_name?: string;
    uploaded?: Array<{ name: string; size: number; saved_path: string }>;
    error?: string;
}

export interface JobResponse {
    ok: boolean;
    job_id: string;
    error?: string;
}

export interface BeatStateResponse {
    ok: boolean;
    state?: ProjectState;
    error?: string;
}

export interface JobCheckResponse {
    ok: boolean;
    job?: JobStatus;
    error?: string;
}

export const beatApi = {
    async createBeat(): Promise<BeatCreationResponse> {
        const res = await fetch(`${API_BASE}/api/beats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ beat_name: '' }) // let server autogen
        });
        if (!res.ok) throw new Error('Failed to create beat');
        return res.json();
    },

    async uploadFiles(beatName: string, files: File[]): Promise<FileUploadResponse> {
        const formData = new FormData();
        files.forEach(f => formData.append('audio', f));

        const res = await fetch(`${API_BASE}/api/beats/${beatName}/upload`, {
            method: 'POST',
            body: formData,
        });
        if (!res.ok) throw new Error('Upload failed');
        return res.json();
    },

    async deleteFile(beatName: string, filename: string): Promise<{ ok: boolean; error?: string }> {
        const res = await fetch(`${API_BASE}/api/beats/${beatName}/files/${filename}`, {
            method: 'DELETE',
        });
        if (!res.ok) throw new Error('Delete failed');
        return res.json();
    },

    async generateInitial(beatName: string, config: BeatConfig): Promise<JobResponse> {
        const res = await fetch(`${API_BASE}/api/beats/${beatName}/generate/initial`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (!res.ok) throw new Error('Initial generation failed');
        return res.json();
    },

    async getBeatState(beatName: string): Promise<BeatStateResponse> {
        const res = await fetch(`${API_BASE}/api/beats/${beatName}/state`);
        if (!res.ok) {
            if (res.status === 404) throw new Error('Beat not found');
            throw new Error('Failed to fetch state');
        }
        return res.json();
    },

    async updateConfig(beatName: string, config: Partial<BeatConfig>): Promise<{ ok: boolean; config?: BeatConfig }> {
        const res = await fetch(`${API_BASE}/api/beats/${beatName}/config`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (!res.ok) throw new Error('Failed to update config');
        return res.json();
    },

    async regenerate(beatName: string, fromStage: number, params?: any): Promise<JobResponse> {
        const res = await fetch(`${API_BASE}/api/beats/${beatName}/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from_stage: fromStage, params })
        });
        if (!res.ok) throw new Error('Regeneration failed');
        return res.json();
    },

    async saveRoles(beatName: string, roles: Record<RoleType, string[]>): Promise<{ ok: boolean; pools_path?: string; error?: string }> {
        const res = await fetch(`${API_BASE}/api/beats/${beatName}/roles`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roles })
        });
        if (!res.ok) throw new Error('Failed to save roles');
        return res.json();
    },

    async getJobStatus(jobId: string): Promise<JobCheckResponse> {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
        if (!res.ok) throw new Error('Failed to check job');
        return res.json();
    },

    // Legacy / Convenience
    getDownloadUrl(beatName: string, kind: string = 'mp3'): string {
        return `${API_BASE}/api/beats/${beatName}/download?kind=${kind}`;
    },

    getPreviewUrl(beatName: string): string {
        return `${API_BASE}/api/beats/${beatName}/preview`;
    },

    getSampleUrl(beatName: string, filename: string): string {
        return `${API_BASE}/api/beats/${beatName}/samples/${filename}`;
    }
};
