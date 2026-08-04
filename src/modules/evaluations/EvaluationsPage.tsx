import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { DataTable, Badge, EmptyState, type Column } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { agentId, type EvaluationPack } from '@/types';
import { fmtDate } from '@/utils/format';
import { cn } from '@/utils/cn';

export default function EvaluationsPage() {
  const navigate = useNavigate();
  const packs = useWorkspace((s) => s.evalPacks);
  const agents = useWorkspace((s) => s.agents);
  const nameOf = (aid: string) => agents.find((a) => agentId(a) === aid)?.config.identity.agent_name.value ?? aid;

  const columns: Column<EvaluationPack>[] = [
    { key: 'agent', header: 'Agent', width: '26%', sortValue: (p) => nameOf(p.agent_id), render: (p) => <div><div className="font-medium text-text-hi">{nameOf(p.agent_id)}</div><div className="mono text-[10px] text-text-low">{p.id}</div></div> },
    { key: 'cases', header: 'Cases', render: (p) => <span className="text-text-mid">{p.cases.length} ({[...new Set(p.cases.map((c) => c.category))].length} categories)</span> },
    { key: 'score', header: 'Last score', align: 'right', sortValue: (p) => p.last_run?.score ?? -1, render: (p) => p.last_run ? <span className={cn('font-semibold', p.last_run.score >= 90 ? 'text-ok' : p.last_run.score >= 75 ? 'text-warn' : 'text-err')}>{p.last_run.score}</span> : <span className="text-text-low">—</span> },
    { key: 'run', header: 'Last run', align: 'right', sortValue: (p) => p.last_run?.date ?? '', render: (p) => <span className="text-text-low">{p.last_run ? fmtDate(p.last_run.date) : 'not run'}</span> },
    { key: 'safety', header: 'Safety', render: (p) => { const fail = p.cases.some((c) => c.category === 'safety_boundary' && c.last_result === 'fail'); return fail ? <Badge tone="err">safety fail</Badge> : <Badge tone="ok">ok</Badge>; } },
  ];

  return (
    <div>
      <PageHeader title="Evaluations" description="Auto-generated evaluation packs per agent — grounding, correctness, safety boundary, latency/cost, regression." />
      {packs.length === 0 ? (
        <EmptyState title="No eval packs" message="Packs are generated during onboarding (Phase 6)." />
      ) : (
        <DataTable columns={columns} rows={packs} rowKey={(p) => p.id} onRowClick={(p) => navigate(`/evaluations/${p.id}`)} searchText={(p) => `${nameOf(p.agent_id)} ${p.id}`} searchPlaceholder="Search eval packs…" initialSort={{ key: 'score', dir: 'asc' }} />
      )}
    </div>
  );
}
