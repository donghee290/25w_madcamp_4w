import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

interface GenerationPlaceholderProps {
    status: 'idle' | 'generating';
}

const PIPELINE_STEPS = [
    "Loading audio files...",
    "Checking audio duration...",
    "Extracting drum elements...",
    "Separating percussive components...",
    "Detecting transients...",
    "Slicing audio into hits...",
    "Cleaning duplicate samples...",
    "Building master sample kit...",
    "Analyzing spectral features...",
    "Scoring rhythmic roles...",
    "Assigning musical roles...",
    "Organizing sound pools...",
    "Setting up tempo grid...",
    "Generating rhythm skeleton...",
    "Initializing AI generator...",
    "Synthesizing beat patterns...",
    "Refining groove structure...",
    "Mapping notes to timeline...",
    "Applying progressive layering...",
    "Finalizing event grid...",
    "Rendering preview beat...",
    "Exporting audio output..."
];

const GenerationPlaceholder: React.FC<GenerationPlaceholderProps> = ({ status }) => {
    const [currentText, setCurrentText] = useState(PIPELINE_STEPS[0]);

    useEffect(() => {
        if (status !== 'generating') return;

        // Choose random initially
        setCurrentText(PIPELINE_STEPS[Math.floor(Math.random() * PIPELINE_STEPS.length)]);

        const interval = setInterval(() => {
            const randomIndex = Math.floor(Math.random() * PIPELINE_STEPS.length);
            setCurrentText(PIPELINE_STEPS[randomIndex]);
        }, 3000);

        return () => clearInterval(interval);
    }, [status]);

    if (status === 'idle') {
        return (
            <div className="flex-1 flex items-center justify-center bg-white">
                <h2 className="text-3xl font-bold text-gray-300">
                    Start by adding your sounds.
                </h2>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col items-center justify-center bg-white space-y-6">
            <div className="relative">
                <div className="absolute inset-0 bg-yellow-400 rounded-full blur-xl opacity-20 animate-pulse"></div>
                <Loader2 className="w-16 h-16 text-yellow-500 animate-spin relative z-10" />
            </div>

            <div className="text-center space-y-2">
                <h3 className="text-2xl font-black text-gray-900">
                    Generating a groovy BEAT!
                </h3>
                <div className="h-8 flex items-center justify-center">
                    <p key={currentText} className="text-lg font-medium text-gray-500 animate-in fade-in slide-in-from-bottom-2 duration-300">
                        {currentText}
                    </p>
                </div>
            </div>
        </div>
    );
};

export default GenerationPlaceholder;
