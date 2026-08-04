import { useEffect } from 'react';
import { CheckCircle2, Info, AlertTriangle, XCircle, X } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import type { ToastKind } from '@/kernel/store';
import { cn } from '@/utils/cn';

const ICON: Record<ToastKind, React.ReactNode> = {
  ok: <CheckCircle2 size={15} className="text-ok" />,
  info: <Info size={15} className="text-accent" />,
  warn: <AlertTriangle size={15} className="text-warn" />,
  err: <XCircle size={15} className="text-err" />,
};

function ToastRow({ id, kind, message }: { id: string; kind: ToastKind; message: string }) {
  const dismiss = useWorkspace((s) => s.dismissToast);
  useEffect(() => {
    const t = window.setTimeout(() => dismiss(id), 4200);
    return () => window.clearTimeout(t);
  }, [id, dismiss]);
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-card border border-border-strong bg-raised px-3 py-2.5 shadow-2xl animate-fade-in',
      )}
    >
      <span className="mt-0.5">{ICON[kind]}</span>
      <span className="flex-1 text-[13px] text-text-hi">{message}</span>
      <button onClick={() => dismiss(id)} className="text-text-low hover:text-text-hi">
        <X size={14} />
      </button>
    </div>
  );
}

export function Toaster() {
  const toasts = useWorkspace((s) => s.ui.toasts);
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[200] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastRow id={t.id} kind={t.kind} message={t.message} />
        </div>
      ))}
    </div>
  );
}
