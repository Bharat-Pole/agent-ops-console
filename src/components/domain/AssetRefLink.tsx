import { useNavigate } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import { agentId } from '@/types';
import { Tooltip } from '@/components/primitives/Tooltip';
import { cn } from '@/utils/cn';

// Section 5.3 — AssetRefLink renders any asset URI as a monospace chip; clicking
// navigates to the owning module's detail view. Unresolvable refs render with a
// ⚠️ tooltip "asset not in catalog" — never crash.

interface Parsed {
  scheme: string;
  id: string;
  version: string | null;
}

function parseRef(ref: string): Parsed | null {
  const m = /^([a-z0-9]+):\/\/(.+)$/i.exec(ref);
  if (!m) return null;
  const scheme = m[1];
  const rest = m[2];
  const [idPart, version] = rest.split('@');
  return { scheme, id: idPart, version: version ?? null };
}

export function AssetRefLink({ refUri, className }: { refUri: string; className?: string }) {
  const navigate = useNavigate();
  const store = useWorkspace((s) => ({ prompts: s.prompts, tools: s.tools, sources: s.sources, knowledgeSources: s.knowledgeSources, agents: s.agents, models: s.models, connectors: s.connectors }));
  const parsed = parseRef(refUri);

  if (!parsed) {
    return <span className={cn('mono text-[11px] text-text-mid', className)}>{refUri}</span>;
  }

  let to: string | null = null;
  let resolvable = true;
  const shortId = parsed.id.split('/')[0];

  switch (parsed.scheme) {
    case 'prompts':
      to = `/prompts/${shortId}`;
      resolvable = store.prompts.some((p) => p.id === shortId);
      break;
    case 'tools':
      to = `/tools`;
      resolvable = store.tools.some((t) => t.id === shortId);
      break;
    case 'kb':
      to = `/knowledge`;
      // Checks both the real, DB-backed sources (Knowledge & RAG module) and
      // the legacy client-only demo `sources` seed array some pre-existing
      // seeded agents still reference — either counts as resolved.
      resolvable = store.knowledgeSources.some((s) => s.id === shortId) || store.sources.some((s) => s.id === shortId);
      break;
    case 'vector':
      to = `/knowledge`;
      resolvable = store.sources.some((s) => s.index_target.value === refUri) || true; // indexes tab lists all
      break;
    case 'a2a':
      to = `/a2a/${parsed.id}`;
      resolvable = store.agents.some((a) => agentId(a) === parsed.id);
      break;
    case 'policies':
      to = `/governance`;
      resolvable = true; // policies listed on the Matrix & Policies tab
      break;
    case 'mcp':
      to = `/tools?tab=mcp`;
      resolvable = store.connectors.some((c) => c.id === shortId);
      break;
    case 'vertex':
      // model_primary/model_fallback refs — resolve into the Model Repository
      // when catalogued there, otherwise fall back to display-only.
      resolvable = store.models.some((m) => m.id === refUri);
      to = resolvable ? '/models' : null;
      break;
    case 'gs':
    default:
      to = null; // external / storage — display only
      resolvable = true;
      break;
  }

  const chip = (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 mono text-[11px]',
        to ? 'border-accent/30 bg-accent/10 text-accent hover:bg-accent/20 cursor-pointer' : 'border-border bg-raised text-text-mid',
        !resolvable && 'border-warn/40 bg-warn/10 text-warn',
        className,
      )}
      onClick={to ? () => navigate(to!) : undefined}
    >
      {!resolvable && <AlertTriangle size={11} />}
      {refUri}
    </span>
  );

  if (!resolvable) {
    return <Tooltip content="asset not in catalog">{chip}</Tooltip>;
  }
  return chip;
}
