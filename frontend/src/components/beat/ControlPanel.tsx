import React from 'react';
import { useProject } from '../../context/ProjectContext';
import { Download, Settings, Sliders, Save } from 'lucide-react';

const ControlPanel = () => {
    const { config, updateConfig, regenerate, downloadUrl } = useProject();

    const handleBpmChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        updateConfig({ bpm: parseFloat(e.target.value) });
    };

    return (
        <div className="w-72 bg-white border-l border-gray-200 flex flex-col h-full shadow-xl z-20">
            {/* Header */}
            <div className="h-16 flex items-center px-6 border-b border-gray-100">
                <h2 className="text-lg font-bold flex items-center gap-2">
                    <Sliders className="w-4 h-4" />
                    Controls
                </h2>
            </div>

            {/* Settings List */}
            <div className="flex-1 overflow-y-auto p-6 space-y-8">
                {/* Tempo */}
                <div className="space-y-3">
                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Tempo</label>
                    <div className="flex items-center gap-3">
                        <div className="relative flex-1">
                            <input
                                type="number"
                                className="w-full border-2 border-gray-100 rounded-lg px-3 py-2 text-lg font-bold text-center focus:border-yellow-400 focus:outline-none transition-colors"
                                value={config.bpm}
                                onChange={handleBpmChange}
                                onBlur={() => regenerate(3, { bpm: config.bpm })}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-gray-400">BPM</span>
                        </div>
                    </div>
                </div>

                {/* Style (Ready only for now or dropdown later) */}
                <div className="space-y-3">
                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Style</label>
                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-100 font-medium text-gray-700 capitalize flex justify-between items-center">
                        {config.style}
                        <Settings className="w-4 h-4 text-gray-400 cursor-pointer hover:text-gray-600" />
                    </div>
                </div>

                {/* Divider */}
                <hr className="border-gray-100" />

                {/* Actions */}
                <div className="space-y-4">
                    <button className="w-full py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl font-bold text-sm transition-colors flex items-center justify-center gap-2">
                        <Save className="w-4 h-4" />
                        Save Project
                    </button> // Just a placeholder for now
                </div>
            </div>

            {/* Footer / Export */}
            <div className="p-6 border-t border-gray-100 bg-gray-50">
                <a
                    href={downloadUrl('mp3')}
                    download
                    className="w-full py-4 bg-black hover:bg-gray-800 text-white rounded-xl font-bold text-sm shadow-lg active:scale-[0.98] transition-all flex items-center justify-center gap-2"
                >
                    <Download className="w-4 h-4" />
                    Download Beat
                </a>
                <div className="text-center mt-3 text-[10px] text-gray-400 font-medium">
                    MP3 • WAV • FLAC
                </div>
            </div>
        </div>
    );
};

export default ControlPanel;
