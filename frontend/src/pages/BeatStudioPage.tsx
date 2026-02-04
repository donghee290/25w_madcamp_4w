import SoundMaterial from "../components/beat/SoundMaterial";
import BeatCanvas from "../components/beat/BeatCanvas";
import ControlPanel from "../components/beat/ControlPanel";
import PlayPreview from "../components/beat/PlayPreview";
import { Music2 } from "lucide-react";

export default function BeatStudioPage() {
    return (
        <div className="flex h-screen bg-white font-sans text-gray-900 overflow-hidden">
            {/* 1. Left Sidebar (Sound Material) */}
            <div className="flex flex-col h-full border-r border-gray-200 shadow-xl z-20">
                {/* Logo Area */}
                <div className="h-16 flex items-center px-6 border-b border-gray-100 bg-white">
                    <Music2 className="w-6 h-6 mr-2 text-yellow-500 fill-yellow-500" />
                    <span className="text-xl font-black italic tracking-tight">SoundRoutine</span>
                </div>

                <SoundMaterial />
            </div>

            {/* Middle + Right Area Wrapper */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* Horizontal Content: Canvas + ControlPanel */}
                <div className="flex-1 flex overflow-hidden">
                    {/* 2. Main (Beat Canvas) */}
                    <BeatCanvas />

                    {/* 3. Right Sidebar (Controls) */}
                    <ControlPanel />
                </div>

                {/* 4. Bottom (Play Preview) */}
                <PlayPreview />
            </div>
        </div>
    );
}
