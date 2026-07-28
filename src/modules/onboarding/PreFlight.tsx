import { CheckCircle2, Clock, XCircle } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import { cn } from '@/utils/cn';

// Section 8.4 — Pre-Flight readiness gate. 7 hard 🔴 + 5 soft 🟡 = 12 rows; we keep
// the Blueprint's own heading "11 prerequisites (Plan Section 8)" verbatim (the
// off-by-one is in the source document and the POC — consistency with source wins,
// acceptance #5). Hard-blocker state derives from live kernel state (e.g., a
// connector marked offline in /tools genuinely turns check #4 red — Section 10 #1).

export type CheckState = 'ok' | 'pending' | 'fail';
export interface PreflightCheck {
  id: string;
  label: string;
  hard: boolean;
  state: CheckState;
}

export function usePreflight(): { checks: PreflightCheck[]; hardBlocked: boolean } {
  const connectors = useWorkspace((s) => s.connectors);
  const sources = useWorkspace((s) => s.sources);

  const anyOffline = connectors.some((c) => c.status === 'offline');
  const allSourcesApproved = sources.every((s) => s.source_approval.value === 'approved');

  const checks: PreflightCheck[] = [
    // ---- hard 🔴 (all must be green) ----
    { id: 'gcp', label: 'GCP project access', hard: true, state: 'ok' },
    { id: 'sources_reachable', label: 'Data sources reachable', hard: true, state: 'ok' },
    { id: 'secrets', label: 'Credentials in Secret Manager', hard: true, state: 'ok' },
    { id: 'mcp', label: 'MCP connectors available', hard: true, state: anyOffline ? 'fail' : 'ok' },
    { id: 'runtime', label: 'Runtime host & model gateway', hard: true, state: 'ok' },
    { id: 'vector', label: 'Vector store provisioned', hard: true, state: 'ok' },
    { id: 'model_endpoint', label: 'Model endpoint approved', hard: true, state: 'ok' },
    // ---- soft 🟡 (may proceed as pending) ----
    { id: 'owners', label: 'Owners named', hard: false, state: 'ok' },
    { id: 'risk', label: 'Risk pre-assessed', hard: false, state: 'pending' },
    { id: 'source_docs', label: 'Source docs approved', hard: false, state: allSourcesApproved ? 'ok' : 'pending' },
    { id: 'evidence', label: 'Evidence store set', hard: false, state: 'ok' },
    { id: 'cadence', label: 'Review cadence', hard: false, state: 'pending' },
  ];

  const hardBlocked = checks.some((c) => c.hard && c.state !== 'ok');
  return { checks, hardBlocked };
}

function Mark({ state }: { state: CheckState }) {
  if (state === 'ok') return <CheckCircle2 size={15} className="text-ok" />;
  if (state === 'pending') return <Clock size={15} className="text-warn" />;
  return <XCircle size={15} className="text-err" />;
}

export function PreflightList({ checks }: { checks: PreflightCheck[] }) {
  return (
    <ul className="space-y-1">
      {checks.map((c) => (
        <li key={c.id} className={cn('flex items-center gap-2.5 rounded-control border px-3 py-2 text-[13px]', c.state === 'fail' ? 'border-err/40 bg-err/10' : 'border-border bg-raised/30')}>
          <Mark state={c.state} />
          <span className="flex-1 text-text-hi">{c.label}</span>
          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-semibold', c.hard ? 'bg-err/15 text-err' : 'bg-warn/15 text-warn')}>
            {c.hard ? '🔴 hard blocker' : '🟡 soft blocker'}
          </span>
        </li>
      ))}
    </ul>
  );
}
