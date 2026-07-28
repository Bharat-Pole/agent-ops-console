import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/utils/cn';

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  width = 'w-[560px]',
}: {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[90]">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'absolute right-0 top-0 h-full max-w-[92vw] bg-surface border-l border-border-strong shadow-2xl flex flex-col animate-fade-in',
          width,
        )}
      >
        <div className="flex items-start justify-between border-b border-border px-4 py-3">
          <div>
            {title && <div className="text-[14px] font-semibold text-text-hi">{title}</div>}
            {subtitle && <div className="text-xs text-text-low mt-0.5">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="text-text-low hover:text-text-hi mt-0.5">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}
