// Home dashboard — server-backed.
//
// This page previously read the in-browser kernel, which meant its headline
// numbers came from seeded demo data whenever "Reset demo" had been used. Every
// figure here now comes from a real endpoint, and anything the backend has no
// data for renders as an honest empty state rather than a zero dressed up as a
// measurement.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip as RTooltip, CartesianGrid,
} from 'recharts';
import { Boxes, CheckCircle2, ClipboardList, DollarSign, Gauge, ArrowRight, AlertTriangle } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Card, CardHeader, EmptyState } from '@/components/primitives';
import {
  agentsApi, approvalsApi, telemetryApi,
  type AgentCostRow, type ApprovalStep, type ServerAgent, type TelemetrySummary,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

function money(usd: number): string {
  return usd >= 1000 ? `$${(usd / 1000).toFixed(1)}k` : `$${usd.toFixed(2)}`;
}

function StatTile({
  icon, label, value, sub, onClick, accent,
}: {
  icon: React.ReactNode; label: string; value: string; sub?: string;
  onClick: () => void; accent?: string;
}) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-start rounded-card border border-border bg-surface p-4 text-left transition hover:border-border-strong hover:bg-raised"
    >
      <div className="mb-2 flex items-center gap-2 text-text-low">
        <span style={{ color: accent }}>{icon}</span>
        <span className="text-[11px]">{label}</span>
      </div>
      <div className="text-[24px] font-semibold text-text-hi">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-text-low">{sub}</div>}
    </button>
  );
}

export default function HomePage() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<ServerAgent[] | null>(null);
  const [approvals, setApprovals] = useState<ApprovalStep[]>([]);
  const [summary, setSummary] = useState<TelemetrySummary | null>(null);
  const [costs, setCosts] = useState<AgentCostRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    agentsApi.list().then(setAgents).catch(() => { setAgents([]); setError('could not load agents'); });
    // A viewer without the reviewer role sees an empty queue; that is a
    // permission outcome, not a failure, so it must not raise an error banner.
    approvalsApi.queue('pending').then(setApprovals).catch(() => setApprovals([]));
    telemetryApi.summary().then(setSummary).catch(() => setSummary(null));
    telemetryApi.costs().then(setCosts).catch(() => setCosts([]));
  }, []);
  useEffect(load, [load]);

  const production = (agents ?? []).filter((a) => a.lifecycle_status === 'production');
  const needsReview = (agents ?? []).filter((a) => a.lifecycle_status === 'needs_review');
  const runs = summary?.runs ?? 0;

  const costData = costs
    .filter((c) => c.cost_usd > 0)
    .sort((a, b) => b.cost_usd - a.cost_usd)
    .slice(0, 6)
    .map((c) => ({ name: c.agent, cost: Number(c.cost_usd.toFixed(4)) }));

  if (agents === null) {
    return <div className="p-6 text-[13px] text-text-low">Loading…</div>;
  }

  return (
    <div>
      <PageHeader
        title="Home"
        description="Live platform state. Figures come from real runs — no sample data."
      />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile
          icon={<Boxes size={16} />} label="Agents" value={String(agents.length)}
          onClick={() => navigate('/agents')} accent="var(--accent)"
        />
        <StatTile
          icon={<CheckCircle2 size={16} />} label="In production" value={String(production.length)}
          sub={`${agents.length - production.length} not in production`}
          onClick={() => navigate('/agents')} accent="var(--ok)"
        />
        <StatTile
          icon={<ClipboardList size={16} />} label="Pending approvals" value={String(approvals.length)}
          sub={approvals.length ? 'awaiting your roles' : undefined}
          onClick={() => navigate('/governance')} accent="var(--warn)"
        />
        <StatTile
          icon={<Gauge size={16} />} label="Runs recorded" value={String(runs)}
          sub={runs ? `${summary?.latency_ms?.p50 ?? 0}ms p50` : 'no traffic yet'}
          onClick={() => navigate('/monitoring')} accent="var(--info)"
        />
        <StatTile
          icon={<DollarSign size={16} />} label="Spend to date"
          value={runs ? money(summary?.cost_usd ?? 0) : '—'}
          sub={runs ? 'actuals, not forecast' : 'no runs to cost'}
          onClick={() => navigate('/monitoring')} accent="var(--info)"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader title="Cost by agent" subtitle="Actual token spend from recorded runs." />
          {costData.length === 0 ? (
            <EmptyState
              title="No cost recorded yet"
              message="Cost appears once agents have run. Nothing is estimated or projected."
            />
          ) : (
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={costData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-low)', fontSize: 10 }} />
                  <YAxis tick={{ fill: 'var(--text-low)', fontSize: 10 }} />
                  <RTooltip
                    contentStyle={{ background: 'var(--bg-raised)', border: '1px solid var(--border)', fontSize: 12 }}
                    formatter={(v: number) => [`$${v.toFixed(4)}`, 'cost']}
                  />
                  <Bar dataKey="cost" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Needs attention"
            subtitle="Agents the platform has flagged, and approvals waiting on you."
          />
          {needsReview.length === 0 && approvals.length === 0 ? (
            <EmptyState title="Nothing waiting" message="No agents need review and no approvals are pending." />
          ) : (
            <div className="flex flex-col gap-1.5">
              {needsReview.map((a) => (
                <button
                  key={a.id} onClick={() => navigate(`/agents/${a.id}`)}
                  className="flex items-center justify-between rounded-control border border-border bg-canvas px-2 py-1.5 text-left text-[12px] hover:border-border-strong"
                >
                  <span className="flex items-center gap-2 text-text-hi">
                    <AlertTriangle size={13} className="text-amber-400" />
                    {a.name}
                  </span>
                  <Badge tone="warn">needs review</Badge>
                </button>
              ))}
              {approvals.slice(0, 6).map((s) => (
                <button
                  key={s.id} onClick={() => navigate('/governance')}
                  className="flex items-center justify-between rounded-control border border-border bg-canvas px-2 py-1.5 text-left text-[12px] hover:border-border-strong"
                >
                  <span className="text-text-hi">
                    {titleCase(s.resource_type)} — {s.step}
                  </span>
                  <span className="flex items-center gap-2 text-[11px] text-text-low">
                    {fmtDate(s.requested_at)}<ArrowRight size={12} />
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
