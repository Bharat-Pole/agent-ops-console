import { useEffect, useState } from 'react';
import { Modal, Button } from '@/components/primitives';
import { api } from '@/kernel/api';
import { diffLines } from './diff';
import { Loader2 } from 'lucide-react';

export function CompareVersionsDialog({
  open,
  onClose,
  promptId,
  versionA,
  versionB,
}: {
  open: boolean;
  onClose: () => void;
  promptId: string;
  versionA: string;
  versionB: string;
}) {
  const [busy, setBusy] = useState(true);
  const [result, setResult] = useState<{ a: { version: string; date: string; body: string }; b: { version: string; date: string; body: string } } | null>(null);

  useEffect(() => {
    if (!open) return;
    setBusy(true);
    setResult(null);
    void api.comparePromptVersions(promptId, versionA, versionB).then((r) => {
      setResult(r);
      setBusy(false);
    });
  }, [open, promptId, versionA, versionB]);

  const diff = result ? diffLines(result.a.body, result.b.body) : [];

  return (
    <Modal open={open} onClose={onClose} title={`Compare ${versionA} → ${versionB}`} width="max-w-2xl" footer={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      {busy ? (
        <div className="flex items-center justify-center gap-2 py-8 text-[13px] text-text-low"><Loader2 size={14} className="animate-spin-slow" /> Loading…</div>
      ) : !result ? (
        <div className="py-6 text-center text-[12px] text-text-low">Comparison unavailable.</div>
      ) : (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-control border border-border bg-canvas p-3 mono text-[12px]">
          {diff.map((d, i) => (
            <div
              key={i}
              className={
                d.type === 'add' ? 'bg-ok/15 text-ok' : d.type === 'del' ? 'bg-err/15 text-err line-through' : 'text-text-hi'
              }
            >
              {d.type === 'add' ? '+ ' : d.type === 'del' ? '- ' : '  '}{d.text || ' '}
            </div>
          ))}
        </pre>
      )}
    </Modal>
  );
}
