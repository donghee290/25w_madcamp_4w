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

const SoundMaterial = () => {
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
        const total = uploadedFiles.length + emptySlots;
        if (total > 1) {
            setEmptySlots(prev => Math.max(0, prev - 1));
        } else {
            setShowMinTooltip(true);
            setTimeout(() => setShowMinTooltip(false), 3000);
        }
    };

    const handleAddSlot = () => {
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
        setModalState({ type: 'DELETE', data: name });
    };

    // 2. Upload Flow (Preview)
    const initiateUpload = (files: File[]) => {
        if (files.length > 0) {
            setModalState({ type: 'PREVIEW', data: files[0] });
        }
    };


    return (
        <>
            <div className="w-80 bg-white border-r border-gray-200 flex flex-col h-full font-sans">
                <div className="p-5 border-b border-gray-100">
                    <div className="flex justify-between items-center mb-1">
                        <h2 className="text-xl font-bold flex items-center gap-2">
                            Sound Material
                        </h2>
                        <div className="relative">
                            <button
                                onClick={handleAddSlot}
                                className={`text-sm font-medium underline underline-offset-2 text-black hover:text-gray-700`}
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
                        {/* Minimum Slot Tooltip (Global relative to header or slot?) 
                            Actually, let's put it near the slot or just reuse global header tooltip area?
                            Let's put it here for simplicity sharing position relative to header? 
                            Or near the slot itself? 
                            The user asked for a tooltip.
                        */}
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
                        />
                    ))}

                    {/* Empty Slots */}
                    {Array.from({ length: emptySlots }).map((_, i) => (
                        <EmptySlot
                            key={`empty-${i}`}
                            onUpload={initiateUpload}
                            onClose={handleRemoveEmptySlot}
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
                            className="w-full border-2 border-black rounded-lg px-3 py-2 font-medium focus:outline-none focus:ring-2 focus:ring-yellow-400"
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
                    />
                </div>
            </div>
        </>
    );
};

// --- Sub Components ---

const FilledSlot = ({ file, rolePools, onRemove }: { file: any, rolePools: any, onRemove: () => void }) => {
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
        <div className="group relative bg-white border-2 border-black rounded-full px-4 py-2 flex items-center justify-between shadow-[2px_2px_0px_rgba(0,0,0,0.1)] hover:shadow-none hover:translate-x-[1px] hover:translate-y-[1px] transition-all">
            <div className="flex items-center gap-2 overflow-hidden flex-1">
                <span className="text-sm font-bold truncate text-gray-900" title={file.name}>
                    {file.name}
                </span>
            </div>

            <div className="flex items-center gap-2">
                {/* Roles */}
                <div className="flex gap-1">
                    {assignedRoles.map(role => (
                        <div key={role} className={`w-2 h-2 rounded-full ${ROLE_COLORS[role]}`} title={role} />
                    ))}
                </div>

                {/* Status / Remove */}
                {file.status === 'uploading' ? (
                    <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                ) : (
                    <button onClick={onRemove} className="text-gray-400 hover:text-black transition-colors">
                        <X className="w-4 h-4" />
                    </button>
                )}
            </div>
        </div>
    )
}

const EmptySlot = ({ onUpload, onClose }: { onUpload: (f: File[]) => void, onClose: () => void }) => {
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Recording State
    const [isRecording, setIsRecording] = useState(false);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            onUpload(Array.from(e.target.files));
            // Do NOT call onClose() here. 
            // The slot will be conceptually "filled" when the upload is confirmed and uploadedFiles changes.
            // If we close it now, it disappears while the popup is open, which is confusing.
        }
    };

    const toggleRecording = async () => {
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

                // Determine extension from mimeType
                let ext = 'webm';
                if (mimeType.includes('mp4')) ext = 'm4a';
                if (mimeType.includes('ogg')) ext = 'ogg';

                const file = new File([blob], `recording-${Date.now()}.${ext}`, { type: mimeType });

                // Instead of onUpload directly, we pass it up.
                // onUpload expects File[].
                onUpload([file]);
                // removed onClose();

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
        <div className="bg-white border-2 border-black rounded-lg p-2.5 flex items-center justify-between shadow-[2px_2px_0px_rgba(0,0,0,0.1)] group">
            <span className="text-sm text-gray-400 font-medium ml-2">Upload a sound.</span>

            <div className="flex items-center gap-2">
                <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className="hidden"
                    accept=".wav,.mp3,.m4a,.flac,.ogg,.webm"
                />
                <button
                    onClick={() => fileInputRef.current?.click()}
                    className="px-3 py-1.5 bg-gray-200 text-gray-600 text-xs font-bold rounded hover:bg-gray-300 transition-colors"
                >
                    Select
                </button>

                <button
                    onClick={toggleRecording}
                    className={`w-8 h-8 flex items-center justify-center rounded-full border-2 transition-all
                        ${isRecording
                            ? 'border-red-500 bg-red-50'
                            : 'border-gray-200 hover:border-red-400'
                        }
                    `}
                    title={isRecording ? "Stop Recording" : "Record Audio"}
                >
                    {isRecording ? (
                        <Square className="w-3 h-3 text-red-500 fill-current" />
                    ) : (
                        <Circle className="w-3 h-3 text-red-500 fill-current" />
                    )}
                </button>
                <button
                    onClick={onClose}
                    className="text-gray-300 hover:text-black transition-colors"
                    title="Remove Slot"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
        </div>
    )
}

const GenerateButton = ({ beatName, generateBeat, jobStatus, jobProgress, isConnected, hasFiles }: any) => {
    const isProcessing = jobStatus === 'running';
    const isDisabled = isProcessing || !isConnected || !hasFiles;

    const handleClick = () => {
        // Pass beat name override
        generateBeat(beatName);
    };

    return (
        <button
            disabled={isDisabled}
            onClick={handleClick}
            className={`w-full py-4 rounded-xl font-black text-base shadow-[4px_4px_0px_#000] border-2 border-black transition-all flex justify-center items-center gap-2 active:translate-x-[2px] active:translate-y-[2px] active:shadow-[2px_2px_0px_#000]
                ${isDisabled
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed border-gray-300 shadow-none'
                    : 'bg-yellow-400 hover:bg-yellow-300 text-black'
                }
            `}
        >
            {isProcessing ? (
                <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    {jobProgress || 'Processing...'}
                </>
            ) : (
                "Generate BEAT"
            )}
        </button>
    )
}

export default SoundMaterial;
