import InputMaterial from "../components/beat/InputMaterial";
import BeatCanvas from "../components/beat/BeatCanvas";
import ControlPanel from "../components/beat/ControlPanel";
import PlayPreview from "../components/beat/PlayPreview";
import GenerationPlaceholder from "../components/common/GenerationPlaceholder";
import { useProject } from "../context/ProjectContext";
import ConfirmModal from "../components/common/ConfirmModal";
import WaveformPreview from "../components/common/WaveformPreview";

export default function BeatStudioPage() {
    const { modalState, setModalState, uploadFiles, removeFile, jobStatus, grid } = useProject();

    // Local State for Generation Flow
    // Status logic:
    // - Idle: No grid (or fresh start), job not running.
    // - Generating: Job running.
    // - Completed: Job completed / Grid exists.

    // However, beat contexts 'jobStatus' tracks running/completed/failed.
    // We map that to our visual states.

    // Derived view state
    const isGenerating = jobStatus === 'running';
    const hasResult = !!grid || jobStatus === 'completed';
    // Note: ProjectContext sets jobStatus='completed' then refreshState() -> sets grid.

    // If we have a result AND we are not generating, show Canvas.
    // Otherwise show placeholder (either Idle or Generating).
    const showCanvas = hasResult && !isGenerating;

    // Sound Material Disabled?
    // Disabled during generation.
    const isMaterialDisabled = isGenerating;


    // Modal Handlers
    const closeModals = () => setModalState({ type: null });

    const handleConfirmPreview = async () => {
        if (modalState.type === 'PREVIEW' && modalState.data) {
            await uploadFiles([modalState.data]);
            closeModals();
        }
    };

    const handleConfirmDelete = async () => {
        if (modalState.type === 'DELETE' && modalState.data) {
            await removeFile(modalState.data);
            closeModals();
        }
    };

    return (
        <div className="flex h-screen bg-white font-sans text-gray-900 overflow-hidden">
            {/* 1. Left Sidebar (Sound Material) */}
            <div className="flex flex-col h-full border-r border-gray-200 shadow-xl z-20">
                <InputMaterial disabled={isMaterialDisabled} />
            </div>

            {/* Middle + Right Area Wrapper */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* Horizontal Content: Canvas + ControlPanel */}
                <div className="flex-1 flex overflow-hidden">

                    {showCanvas ? (
                        <>
                            {/* 2. Main (Beat Canvas) */}
                            <BeatCanvas />

                            {/* 3. Right Sidebar (Controls) */}
                            <ControlPanel />
                        </>
                    ) : (
                        <GenerationPlaceholder
                            status={isGenerating ? 'generating' : 'idle'}
                        />
                    )}

                </div>

                {/* 4. Bottom (Play Preview) - Only visible when we have a result? or always? 
                    User said "Before generate, only 'Start adding...'".
                    User said "After pipeline completed, then grid and all panels visible".
                    So hide PlayPreview if not complete.
                */}
                {showCanvas && <PlayPreview />}
            </div>

            {/* Global Modals rendered at Root Level to avoid Z-Index/Overflow clipping */}

            {/* 1. Delete Modal */}
            <ConfirmModal
                isOpen={modalState.type === 'DELETE'}
                title="Delete this sound?"
                onClose={closeModals}
                onConfirm={handleConfirmDelete}
                confirmText="Delete"
                confirmColor="bg-yellow-400"
            />

            {/* 2. Preview Modal */}
            <ConfirmModal
                isOpen={modalState.type === 'PREVIEW'}
                title="Use this sound?"
                onClose={closeModals}
                onConfirm={handleConfirmPreview}
                confirmText="Use"
                confirmColor="bg-yellow-400"
            >
                {modalState.type === 'PREVIEW' && modalState.data && (
                    <WaveformPreview file={modalState.data} />
                )}
            </ConfirmModal>
        </div>
    );
}
