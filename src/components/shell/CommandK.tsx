import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, LayoutGrid, FileText, Wrench, Database } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import { agentId, agentName } from '@/types';
import { cn } from '@/utils/cn';

interface Hit {
  kind: 'agent' | 'prompt' | 'tool' | 'source';
  id: string;
  name: string;
  sub: string;
  to: string;
}

// Section 3.1 — global search (Cmd+K) searching agents/prompts/tools/sources by name.
export function CommandK({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('');
  const [idx, setIdx] = useState(0);
  const navigate = useNavigate();
  const { agents, prompts, tools, sources } = useWorkspace((s) => ({
    agents: s.agents,
    prompts: s.prompts,
    tools: s.tools,
    sources: s.sources,
  }));

  const hits = useMemo<Hit[]>(() => {
    const all: Hit[] = [
      ...agents.map((a) => ({
        kind: 'agent' as const,
        id: agentId(a),
        name: agentName(a),
        sub: `Agent · ${a.capability_tier}`,
        to: `/agents/${agentId(a)}`,
      })),
      ...prompts.map((p) => ({
        kind: 'prompt' as const,
        id: p.id,
        name: p.name,
        sub: `Prompt · ${p.kind}`,
        to: `/prompts/${p.id}`,
      })),
      ...tools.map((t) => ({
        kind: 'tool' as const,
        id: t.id,
        name: t.name,
        sub: `Tool · ${t.category}`,
        to: `/tools`,
      })),
      ...sources.map((s) => ({
        kind: 'source' as const,
        id: s.id,
        name: s.name,
        sub: `Knowledge source`,
        to: `/knowledge`,
      })),
    ];
    if (!q.trim()) return all.slice(0, 8);
    const needle = q.toLowerCase();
    return all.filter((h) => h.name.toLowerCase().includes(needle) || h.id.toLowerCase().includes(needle)).slice(0, 12);
  }, [agents, prompts, tools, sources, q]);

  useEffect(() => {
    if (open) {
      setQ('');
      setIdx(0);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setIdx((i) => Math.min(i + 1, hits.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && hits[idx]) {
        navigate(hits[idx].to);
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, hits, idx, navigate, onClose]);

  if (!open) return null;

  const ICON = { agent: LayoutGrid, prompt: FileText, tool: Wrench, source: Database };

  return (
    <div className="fixed inset-0 z-[150] flex items-start justify-center p-4 pt-[12vh]">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-xl overflow-hidden rounded-card border border-border-strong bg-surface shadow-2xl animate-fade-in">
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search size={16} className="text-text-low" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setIdx(0);
            }}
            placeholder="Search agents, prompts, tools, sources…"
            className="h-11 flex-1 bg-transparent text-[14px] text-text-hi placeholder:text-text-low outline-none"
          />
          <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] mono text-text-low">esc</kbd>
        </div>
        <div className="max-h-80 overflow-auto py-1">
          {hits.length === 0 && (
            <div className="px-4 py-8 text-center text-[13px] text-text-low">No matches.</div>
          )}
          {hits.map((h, i) => {
            const Icon = ICON[h.kind];
            return (
              <button
                key={`${h.kind}-${h.id}`}
                onMouseEnter={() => setIdx(i)}
                onClick={() => {
                  navigate(h.to);
                  onClose();
                }}
                className={cn(
                  'flex w-full items-center gap-3 px-3 py-2 text-left',
                  i === idx ? 'bg-raised' : 'hover:bg-raised/60',
                )}
              >
                <Icon size={15} className="text-text-mid" />
                <span className="flex-1">
                  <span className="block text-[13px] text-text-hi">{h.name}</span>
                  <span className="block text-[11px] text-text-low">{h.sub}</span>
                </span>
                <span className="mono text-[10px] text-text-low">{h.id}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
