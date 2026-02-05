import React, { useState } from 'react';
import { useProject } from '../../context/ProjectContext';
import { beatApi } from '../../api/beatApi';
import { Play, Pause } from 'lucide-react';
import type { RoleType } from '../../types/beatType';

const ROLE_COLORS: Record<RoleType, string> = {
    CORE: 'bg-orange-500',
    ACCENT: 'bg-yellow-400',
    MOTION: 'bg-blue-500',
    FILL: 'bg-purple-600',
    TEXTURE: 'bg-green-500',
};

const ORDERED_ROLES: RoleType[] = ['CORE', 'ACCENT', 'MOTION', 'FILL', 'TEXTURE'];

interface SoundMaterialProps {
    disabled?: boolean;
}

const SoundMaterial: React.FC<SoundMaterialProps> = ({ disabled = false }) => {
    const { rolePools, setRolePools, beatName } = useProject();
    const [playingFile, setPlayingFile] = useState<string | null>(null);
    const audioRef = React.useRef<HTMLAudioElement | null>(null);

    const handlePlay = (name: string) => {
        if (playingFile === name) {
            audioRef.current?.pause();
            setPlayingFile(null);
            return;
        }

        if (audioRef.current) {
            audioRef.current.pause();
        }

        // Construct URL for the preprocessed sample
        const url = beatApi.getSampleUrl(beatName, name);

        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => setPlayingFile(null);
        audio.play().catch(e => console.error("Play failed", e));
        setPlayingFile(name);
    };

    // Drag and Drop Handlers
    const handleDragStart = (e: React.DragEvent, name: string, fromRole: RoleType) => {
        if (disabled) return;
        e.dataTransfer.setData('soundName', name);
        e.dataTransfer.setData('fromRole', fromRole);
    };

    const handleDragOver = (e: React.DragEvent) => {
        if (disabled) return;
        e.preventDefault(); // allow drop
    };

    const handleDrop = (e: React.DragEvent, targetRole: RoleType) => {
        if (disabled) return;
        e.preventDefault();
        const soundName = e.dataTransfer.getData('soundName');
        const fromRole = e.dataTransfer.getData('fromRole') as RoleType;

        if (!soundName || !fromRole || !rolePools) return;

        if (fromRole === targetRole) return;

        const newPools = { ...rolePools };

        // Remove from old role
        if (newPools[fromRole]) {
            newPools[fromRole] = newPools[fromRole].filter(n => n !== soundName);
        }

        // Add to new role
        if (!newPools[targetRole]) newPools[targetRole] = [];
        if (!newPools[targetRole].includes(soundName)) {
            newPools[targetRole].push(soundName);
        }

        setRolePools(newPools);
    };

    if (!rolePools) return <div className="p-4">No roles assigned.</div>;

    // Helper to format name (remove extension)
    const formatName = (name: string) => name.replace(/\.[^/.]+$/, "");

    return (
        <div className={`w-80 bg-white border-r border-gray-200 flex flex-col h-full font-sans transition-opacity duration-300 ${disabled ? 'opacity-50 pointer-events-none select-none' : ''}`}>
            <div className="p-5 border-b border-gray-100">
                <h2 className="text-xl font-bold flex items-center gap-2">
                    Sound Material
                    {/* Info Icon if needed */}
                </h2>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {ORDERED_ROLES.map(role => (
                    <div
                        key={role}
                        className="space-y-2"
                        onDragOver={handleDragOver}
                        onDrop={(e) => handleDrop(e, role)}
                    >
                        {/* Role Header */}
                        <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-xs font-bold text-white uppercase ${ROLE_COLORS[role]}`}>
                                {role}
                            </span>
                        </div>

                        {/* Files List/Drop Zone */}
                        <div className={`min-h-[40px] space-y-2 rounded-lg transition-colors ${rolePools[role]?.length === 0 ? 'bg-gray-50 border-2 border-dashed border-gray-200 p-2 flex items-center justify-center' : ''}`}>
                            {rolePools[role]?.length === 0 ? (
                                <span className="text-xs text-gray-400 text-center">No suitable sound for this slot</span>
                            ) : (
                                rolePools[role]?.map(name => (
                                    <div
                                        key={name}
                                        draggable={!disabled}
                                        onDragStart={(e) => handleDragStart(e, name, role)}
                                        className={`bg-white border-2 border-gray-200 rounded-full pl-3 pr-2 py-1.5 flex items-center justify-between shadow-sm cursor-grab active:cursor-grabbing hover:border-gray-400 transition-all ${disabled ? 'cursor-default' : ''}`}
                                    >
                                        <span className="text-sm font-bold truncate max-w-[160px]" title={name}>{formatName(name)}</span>
                                        <button
                                            onClick={() => handlePlay(name)}
                                            className="ml-2 w-6 h-6 rounded-full flex items-center justify-center hover:bg-gray-100 text-black shadow-[1px_1px_0px_#000] border border-black text-[10px]"
                                        >
                                            {playingFile === name ? <Pause size={10} fill="currentColor" /> : <Play size={10} fill="currentColor" />}
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default SoundMaterial;
