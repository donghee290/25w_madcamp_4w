import React from 'react';
import { X } from 'lucide-react';

interface ConfirmModalProps {
    isOpen: boolean;
    title: string;
    onClose: () => void;
    onConfirm: () => void;
    confirmText?: string;
    children?: React.ReactNode;
    confirmColor?: string; // e.g., 'bg-yellow-400', 'bg-red-500'
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({
    isOpen,
    title,
    onClose,
    onConfirm,
    confirmText = "Confirm",
    children,
    confirmColor = "bg-yellow-400"
}) => {
    if (!isOpen) return null;
    return (
        <div className="fixed top-0 left-0 w-full h-full z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm" >
            <div className="bg-white rounded-2xl p-6 w-[320px] shadow-2xl relative animate-in fade-in zoom-in duration-200">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-400 hover:text-black transition-colors"
                >
                    <X className="w-5 h-5" />
                </button>

                <h3 className="text-xl font-bold text-center mb-6 mt-2">
                    {title}
                </h3>

                {children && <div className="mb-6">{children}</div>}

                <div className="flex gap-3">
                    <button
                        onClick={onClose}
                        className="flex-1 py-3 rounded-xl border-2 border-black font-bold hover:bg-gray-50 transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onConfirm}
                        className={`flex-1 py-3 rounded-xl border-2 border-black font-bold text-black transition-transform active:scale-95 ${confirmColor}`}
                    >
                        {confirmText}
                    </button>
                </div>
            </div>
        </div >
    );
};

export default ConfirmModal;
