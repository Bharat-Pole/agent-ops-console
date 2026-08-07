import { useState } from 'react';
import { Download, FileCode, FolderTree, AlertTriangle } from 'lucide-react';
import { Modal, Button, Badge, Tabs, type TabItem } from '@/components/primitives';
import { api, type EngineGenerateResponse } from '@/kernel/api';
import { cn } from '@/utils/cn';

// Shows the agent_forge output: topology, build blockers, the generated file tree,
// and a code preview of key files, with a Download button for the runnable zip.
export function ProjectPreview({
  open,
  onClose,
  result,
}: {
  open: boolean;
  onClose: () => void;
  result: EngineGenerateResponse | null;
}) {
  const previewPaths = result ? Object.keys(result.preview).sort() : [];
  const [active, setActive] = useState<string>('');
  const activePath = active && previewPaths.includes(active) ? active : previewPaths[0] ?? '';

  if (!result) return null;

  const b = result.blockers as Record<string, unknown>;
  const hardBlockers = b.has_hard_blockers === true;
  const activeBlockers = Object.entries(b).filter(
    ([k, v]) => k !== 'has_hard_blockers' && Array.isArray(v) ? (v as unknown[]).length > 0 : v === true && k !== 'has_hard_blockers',
  );

  const tabs: TabItem[] = previewPaths.map((p) => ({ key: p, label: p.split('/').pop() ?? p }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      width="max-w-4xl"
      title={
        <span className="flex items-center gap-2">
          <FileCode size={16} /> Generated project
          <Badge tone="accent">{result.topology}</Badge>
          <span className="text-[11px] font-normal text-text-low">{result.file_tree.length} files</span>
        </span>
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          <Button variant="primary" icon={<Download size={14} />} onClick={() => api.downloadArtifact(result.artifact_b64, result.filename)}>
            Download {result.filename}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {activeBlockers.length > 0 && (
          <div className={cn('rounded-control border px-3 py-2 text-[12px]', hardBlockers ? 'border-err/40 bg-err/10 text-err' : 'border-warn/40 bg-warn/10 text-warn')}>
            <div className="flex items-center gap-1.5 font-medium"><AlertTriangle size={13} /> Build blockers</div>
            <ul className="mt-1 list-disc pl-5">
              {activeBlockers.map(([k, v]) => (
                <li key={k}><span className="mono">{k}</span>: {Array.isArray(v) ? (v as string[]).join(', ') : String(v)}</li>
              ))}
            </ul>
            <div className="mt-1 text-text-low">Write-capable tools are never bound regardless.</div>
          </div>
        )}

        <div className="grid grid-cols-[220px_1fr] gap-3" style={{ minHeight: 340 }}>
          {/* file tree */}
          <div className="rounded-control border border-border bg-canvas p-2 overflow-auto" style={{ maxHeight: 420 }}>
            <div className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase text-text-low"><FolderTree size={11} /> files</div>
            {result.file_tree.map((p) => (
              <div key={p} className={cn('truncate px-1 py-0.5 text-[11px] mono', previewPaths.includes(p) ? 'text-accent cursor-pointer hover:bg-raised' : 'text-text-low')} onClick={() => previewPaths.includes(p) && setActive(p)} title={p}>
                {p}
              </div>
            ))}
          </div>

          {/* code preview */}
          <div className="min-w-0 rounded-control border border-border bg-canvas">
            <Tabs items={tabs} active={activePath} onChange={setActive} className="px-2" />
            <pre className="max-h-[380px] overflow-auto p-3 mono text-[11px] leading-relaxed text-text-hi whitespace-pre">
              {result.preview[activePath] ?? ''}
            </pre>
          </div>
        </div>
      </div>
    </Modal>
  );
}
