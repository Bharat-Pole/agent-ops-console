import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/utils/cn';

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 'max-w-lg',
}: {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
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
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'relative w-full rounded-card border border-border-strong bg-surface shadow-2xl animate-fade-in',
          width,
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="text-[14px] font-semibold text-text-hi">{title}</div>
            <button onClick={onClose} className="text-text-low hover:text-text-hi">
              <X size={16} />
            </button>
          </div>
        )}
        <div className="p-4">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
