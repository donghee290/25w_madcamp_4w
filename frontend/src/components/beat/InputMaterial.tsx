import React, { useRef, useState, useEffect } from 'react';
import { useProject } from '../../context/ProjectContext';
import { X, Loader2, Square, Circle } from 'lucide-react';
import type { RoleType } from '../../types/beatType';

const ROLE_COLORS: Record<RoleType, string> = {
    CORE: 'bg-orange-500',
    ACCENT: 'bg-yellow-400',
    MOTION: 'bg-blue-500',
    FILL: 'bg-purple-600',
    TEXTURE: 'bg-green-500',
};

const MAX_SLOTS = 5;

interface InputMaterialProps {
    disabled?: boolean;
}

const InputMaterial: React.FC<InputMaterialProps> = ({ disabled = false }) => {
    const { uploadedFiles, rolePools, generateBeat, jobStatus, jobProgress, isConnected, setModalState } = useProject();

    // Dynamic Slots State
    const [emptySlots, setEmptySlots] = useState<number>(1);
    const [beatNameInput, setBeatNameInput] = useState<string>("Awesome Beat");
    const [showLimitTooltip, setShowLimitTooltip] = useState(false);

    const [showMinTooltip, setShowMinTooltip] = useState(false);
    const prevUploadedLength = useRef(uploadedFiles.length);

    // Sync: Adjust empty slots based on upload/delete
    useEffect(() => {
        if (uploadedFiles.length > prevUploadedLength.current) {
            // Uploaded: Consume an empty slot
            setEmptySlots(prev => Math.max(0, prev - 1));
        } else if (uploadedFiles.length < prevUploadedLength.current) {
            // Deleted: Free up an empty slot (replace the file)
            setEmptySlots(prev => prev + 1);
        }
        prevUploadedLength.current = uploadedFiles.length;
    }, [uploadedFiles.length]);

    // Handle Removing Empty Slot
    const handleRemoveEmptySlot = () => {
        if (disabled) return;
        const total = uploadedFiles.length + emptySlots;
        if (total > 1) {
            setEmptySlots(prev => Math.max(0, prev - 1));
        } else {
            setShowMinTooltip(true);
            setTimeout(() => setShowMinTooltip(false), 3000);
        }
    };

    const handleAddSlot = () => {
        if (disabled) return;
        if (uploadedFiles.length + emptySlots < MAX_SLOTS) {
            setEmptySlots(prev => prev + 1);
        } else {
            setShowLimitTooltip(true);
            setTimeout(() => setShowLimitTooltip(false), 3000);
        }
    };

    // --- Trigger Modals ---

    // 1. Delete Flow
    const initiateRemove = (name: string) => {
        if (disabled) return;
        setModalState({ type: 'DELETE', data: name });
    };

    // 2. Upload Flow (Preview)
    const initiateUpload = (files: File[]) => {
        if (disabled) return;
        if (files.length > 0) {
            setModalState({ type: 'PREVIEW', data: files[0] });
        }
    };


    return (
        <>
            <div className={`w-80 bg-white border-r border-gray-200 flex flex-col h-full font-sans transition-opacity duration-300 ${disabled ? 'opacity-50 pointer-events-none select-none' : ''}`}>
                <div className="p-5 border-b border-gray-100">
                    <div className="flex justify-between items-center mb-1">
                        <h2 className="text-xl font-bold flex items-center gap-2">
                            Input Material
                        </h2>
                        <div className="relative">
                            <button
                                onClick={handleAddSlot}
                                disabled={disabled}
                                className={`text-sm font-medium underline underline-offset-2 text-black hover:text-gray-700 disabled:text-gray-400 disabled:no-underline`}
                            >
                                New slot
                            </button>
                            {showLimitTooltip && (
                                <div className="absolute top-8 right-0 z-50 w-max bg-white border-2 border-black rounded-full px-4 py-2 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] animate-in fade-in zoom-in duration-200">
                                    <p className="text-sm font-bold text-black whitespace-nowrap">
                                        You can upload up to 5 audio files.
                                    </p>
                                </div>
                            )}
                        </div>
                        {/* Minimum Slot Tooltip */}
                        <div className="relative">
                            {showMinTooltip && (
                                <div className="absolute top-8 right-0 z-50 w-max bg-white border-2 border-black rounded-full px-4 py-2 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] animate-in fade-in zoom-in duration-200">
                                    <p className="text-sm font-bold text-black whitespace-nowrap">
                                        You need at least one audio file.
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                    <p className="text-xs text-gray-500 leading-relaxed mt-1">
                        Supported formats are m4a, mp3, wav, webm.<br />
                        You can upload up to 5 sounds.<br />
                        • One-shot sounds: 3+ recommended.<br />
                        • Long sounds: Automatically split.
                    </p>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {/* Uploaded Files (Filled Slots) */}
                    {uploadedFiles.map((file) => (
                        <FilledSlot
                            key={file.id}
                            file={file}
                            rolePools={rolePools}
                            onRemove={() => initiateRemove(file.name)}
                            disabled={disabled}
                        />
                    ))}

                    {/* Empty Slots */}
                    {Array.from({ length: emptySlots }).map((_, i) => (
                        <EmptySlot
                            key={`empty-${i}`}
                            onUpload={initiateUpload}
                            onClose={handleRemoveEmptySlot}
                            disabled={disabled}
                        />
                    ))}
                </div>

                <div className="p-5 bg-white border-t border-gray-100">
                    <div className="mb-4">
                        <label className="block text-lg font-bold mb-2">Beat Name</label>
                        <input
                            type="text"
                            value={beatNameInput}
                            onChange={(e) => setBeatNameInput(e.target.value)}
                            disabled={disabled}
                            className="w-full border-2 border-black rounded-lg px-3 py-2 font-medium focus:outline-none focus:ring-2 focus:ring-yellow-400 disabled:bg-gray-100 disabled:text-gray-400 disabled:border-gray-200"
                            placeholder="My Awesome Beat"
                        />
                    </div>

                    <GenerateButton
                        beatName={beatNameInput}
                        generateBeat={generateBeat}
                        jobStatus={jobStatus}
                        jobProgress={jobProgress}
                        isConnected={isConnected}
                        hasFiles={uploadedFiles.length > 0}
                        disabled={disabled}
                    />
                </div>
            </div>
        </>
    );
};

// --- Sub Components ---

const FilledSlot = ({ file, rolePools, onRemove, disabled }: { file: any, rolePools: any, onRemove: () => void, disabled: boolean }) => {
    const getAssignedRoles = (fileName: string): RoleType[] => {
        if (!rolePools) return [];
        const roles: RoleType[] = [];
        Object.entries(rolePools).forEach(([role, files]) => {
            if (Array.isArray(files) && files.some(f => typeof f === 'string' && f.includes(fileName))) {
                roles.push(role as RoleType);
            }
        });
        return roles;
    };

    const assignedRoles = getAssignedRoles(file.name);

    return (
        <div className={`group relative bg-white border-2 border-black rounded-full px-4 py-2 flex items-center justify-between shadow-[2px_2px_0px_rgba(0,0,0,0.1)] transition-all ${disabled ? 'border-gray-300 shadow-none' : 'hover:shadow-none hover:translate-x-[1px] hover:translate-y-[1px]'}`}>
            <div className="flex items-center gap-2 overflow-hidden flex-1">
                <span className={`text-sm font-bold truncate ${disabled ? 'text-gray-400' : 'text-gray-900'}`} title={file.name}>
                    {file.name}
                </span>
            </div>

            <div className="flex items-center gap-2">
                {/* Roles */}
                <div className="flex gap-1">
                    {assignedRoles.map(role => (
                        <div key={role} className={`w-2 h-2 rounded-full ${disabled ? 'bg-gray-300' : ROLE_COLORS[role]}`} title={role} />
                    ))}
                </div>

                {/* Status / Remove */}
                {file.status === 'uploading' ? (
                    <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                ) : (
                    <button onClick={onRemove} disabled={disabled} className={`transition-colors ${disabled ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:text-black'}`}>
                        <X className="w-4 h-4" />
                    </button>
                )}
            </div>
        </div>
    )
}

const EmptySlot = ({ onUpload, onClose, disabled }: { onUpload: (f: File[]) => void, onClose: () => void, disabled: boolean }) => {
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Recording State
    const [isRecording, setIsRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (disabled) return;
        if (e.target.files && e.target.files.length > 0) {
            onUpload(Array.from(e.target.files));
        }
    };

    const toggleRecording = async () => {
        if (disabled) return;
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            chunksRef.current = [];

            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            mediaRecorder.onstop = () => {
                const mimeType = mediaRecorderRef.current?.mimeType || 'audio/webm';
                const blob = new Blob(chunksRef.current, { type: mimeType });

                let ext = 'webm';
                if (mimeType.includes('mp4')) ext = 'm4a';
                if (mimeType.includes('ogg')) ext = 'ogg';

                const file = new File([blob], `recording-${Date.now()}.${ext}`, { type: mimeType });

                onUpload([file]);
                // Stop tracks
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            setIsRecording(true);
        } catch (e) {
            console.error("Mic error", e);
            alert("Could not access microphone.");
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    };

    return (
        <div className={`bg-white border-2 border-black rounded-lg p-2.5 flex items-center justify-between shadow-[2px_2px_0px_rgba(0,0,0,0.1)] group ${disabled ? 'border-gray-200 shadow-none' : ''}`}>
            <span className={`text-sm font-medium ml-2 ${disabled ? 'text-gray-300' : 'text-gray-400'}`}>Upload a sound.</span>

            <div className="flex items-center gap-2">
                <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className="hidden"
                    accept=".wav,.mp3,.m4a,.flac,.ogg,.webm"
                    disabled={disabled}
                />
                <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={disabled}
                    className={`px-3 py-1.5 text-xs font-bold rounded transition-colors ${disabled ? 'bg-gray-100 text-gray-300 cursor-not-allowed' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
                >
                    Select
                </button>

                <button
                    onClick={toggleRecording}
                    disabled={disabled}
                    className={`w-8 h-8 flex items-center justify-center rounded-full border-2 transition-all
                        ${disabled
                            ? 'border-gray-100 bg-gray-50 cursor-not-allowed'
                            : isRecording
                                ? 'border-red-500 bg-red-50'
                                : 'border-gray-200 hover:border-red-400'
                        }
                    `}
                    title={isRecording ? "Stop Recording" : "Record Audio"}
                >
                    {isRecording ? (
                        <Square className={`w-3 h-3 fill-current ${disabled ? 'text-gray-300' : 'text-red-500'}`} />
                    ) : (
                        <Circle className={`w-3 h-3 fill-current ${disabled ? 'text-gray-300' : 'text-red-500'}`} />
                    )}
                </button>
                <button
                    onClick={onClose}
                    disabled={disabled}
                    className={`transition-colors ${disabled ? 'text-gray-200 cursor-not-allowed' : 'text-gray-300 hover:text-black'}`}
                    title="Remove Slot"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
        </div>
    )
}

const GenerateButton = ({ beatName, generateBeat, jobStatus, isConnected, hasFiles, disabled }: any) => {
    // If disabled prop is true, we force disabled state regardless of jobStatus.
    // However, if jobStatus is 'running', it is also visually disabled by logic below.
    // The parent passes disabled=true when generating, so this aligns.

    const isProcessing = jobStatus === 'running';
    const isDisabled = disabled || isProcessing || !isConnected || !hasFiles;

    const handleClick = () => {
        generateBeat(beatName);
    };

    return (
        <button
            disabled={isDisabled}
            onClick={handleClick}
            className={`w-full py-4 rounded-xl font-black text-base border-2 transition-all flex justify-center items-center gap-2
                ${isDisabled
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed border-gray-300 shadow-none'
                    : 'bg-yellow-400 hover:bg-yellow-300 text-black border-black shadow-[4px_4px_0px_#000] active:translate-x-[2px] active:translate-y-[2px] active:shadow-[2px_2px_0px_#000]'
                }
            `}
        >
            "Generate BEAT"
        </button>
    )
}

export default InputMaterial;
