import React, { useRef } from 'react';
import { useProject } from '../../context/ProjectContext';
import { Upload, X, Music, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import type { RoleType } from '../../types/beatType';

const ROLE_COLORS: Record<RoleType, string> = {
    CORE: 'bg-orange-500',
    ACCENT: 'bg-yellow-400',
    MOTION: 'bg-blue-500',
    FILL: 'bg-purple-600',
    TEXTURE: 'bg-green-500',
};

const SoundMaterial = () => {
    const { uploadedFiles, uploadFiles, rolePools } = useProject();
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            uploadFiles(Array.from(e.target.files));
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const getAssignedRoles = (fileName: string): RoleType[] => {
        if (!rolePools) return [];
        const roles: RoleType[] = [];
        Object.entries(rolePools).forEach(([role, files]) => {
            if (files.some(f => f.includes(fileName))) {
                roles.push(role as RoleType);
            }
        });
        return roles;
    };

    return (
        <div className="w-80 bg-white border-r border-gray-200 flex flex-col h-full">
            <div className="p-4 border-b border-gray-100">
                <div className="flex justify-between items-center mb-1">
                    <h2 className="text-lg font-bold flex items-center gap-2">
                        Sound Material
                    </h2>
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        className="text-xs text-blue-600 hover:underline font-medium"
                    >
                        New slot
                    </button>
                </div>
                <p className="text-xs text-gray-500 leading-tight">
                    Supported formats: m4a, mp3, wav.<br />
                    Upload up to 5 sounds recommended.
                </p>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {uploadedFiles.map((file) => {
                    const assignedRoles = getAssignedRoles(file.name);

                    return (
                        <div key={file.id} className="group relative bg-white border border-gray-200 rounded-lg p-3 shadow-sm hover:border-blue-400 transition-all">
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2 overflow-hidden">
                                    <div className="p-1.5 bg-gray-100 rounded-md">
                                        {file.status === 'uploading' ? (
                                            <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                                        ) : (
                                            <Music className="w-4 h-4 text-gray-600" />
                                        )}
                                    </div>
                                    <span className="text-sm font-medium truncate text-gray-700 max-w-[140px]" title={file.name}>
                                        {file.name}
                                    </span>
                                </div>

                                {file.status === 'done' && <CheckCircle className="w-4 h-4 text-green-500" />}
                                {file.status === 'error' && <AlertCircle className="w-4 h-4 text-red-500" />}
                                {file.status === 'idle' && <button className="text-gray-300 hover:text-red-500"><X className="w-4 h-4" /></button>}
                            </div>

                            <div className="flex flex-wrap gap-1 mt-1">
                                {assignedRoles.length > 0 ? (
                                    assignedRoles.map(role => (
                                        <span key={role} className={`text-[10px] px-1.5 py-0.5 rounded text-white font-bold ${ROLE_COLORS[role]}`}>
                                            {role}
                                        </span>
                                    ))
                                ) : (
                                    file.status === 'done' && !rolePools && (
                                        <span className="text-[10px] text-gray-400 italic">Ready to process</span>
                                    )
                                )}
                            </div>
                        </div>
                    );
                })}

                <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-gray-200 rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer hover:bg-gray-50 hover:border-gray-300 transition-colors h-24"
                >
                    <Upload className="w-6 h-6 text-gray-400 mb-1" />
                    <span className="text-xs text-gray-500 font-medium">Click to upload sounds</span>
                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleFileChange}
                        className="hidden"
                        multiple
                        accept=".wav,.mp3,.m4a,.flac,.ogg"
                    />
                </div>
            </div>

            <div className="p-4 border-t border-gray-100">
                <GenerateButton />
            </div>
        </div>
    );
};

const GenerateButton = () => {
    const { generateInitial, jobStatus, jobProgress, isConnected } = useProject();

    const isProcessing = jobStatus === 'running';

    return (
        <button
            disabled={isProcessing || !isConnected}
            onClick={generateInitial}
            className={`w-full py-3 rounded-lg font-bold text-sm shadow-sm transition-all flex justify-center items-center gap-2
                ${isProcessing
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-yellow-400 hover:bg-yellow-300 text-black active:scale-[0.98]'
                }
            `}
        >
            {isProcessing ? (
                <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {jobProgress || 'Processing...'}
                </>
            ) : (
                "Generate BEAT"
            )}
        </button>
    )
}

export default SoundMaterial;
