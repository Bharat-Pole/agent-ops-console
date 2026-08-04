import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip as RTooltip, AreaChart, Area, CartesianGrid, Legend,
} from 'recharts';
import { Boxes, CheckCircle2, ClipboardList, DollarSign, Gauge, ArrowRight, AlertTriangle, Clock } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card } from '@/components/primitives';
import { GovernanceMatrix } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { agentId, isLive, type AgentRecord } from '@/types';
import { TIER_ORDER, FAST_PATH_WARN_DAYS, PERSONAS } from '@/kernel/constants';
import { cost30d, money, fmtDateTime, daysUntil, pointCost } from '@/utils/format';
import { cn } from '@/utils/cn';

const CHART_COLORS = ['var(--accent)', 'var(--info)', 'var(--ok)', 'var(--warn)', 'var(--risk-high)'];

function StatTile({ icon, label, value, sub, onClick, accent }: { icon: React.ReactNode; label: string; value: string; sub?: string; onClick: () => void; accent?: string }) {
  return (
    <button onClick={onClick} className="flex flex-col items-start rounded-card border border-border bg-surface p-4 text-left transition hover:border-border-strong hover:bg-raised">
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
  const { agents, approvals, telemetry, evalPacks, auditLog, connectors, pipelineRuns, persona } = useWorkspace((s) => ({
    agents: s.agents, approvals: s.approvals, telemetry: s.telemetry, evalPacks: s.evalPacks,
    auditLog: s.auditLog, connectors: s.connectors, pipelineRuns: s.pipelineRuns, persona: s.ui.persona,
  }));

  const liveCount = agents.filter(isLive).length;
  const pendingApprovals = approvals.filter((a) => a.status === 'pending');
  const monthlySpend = telemetry.reduce((acc, t) => acc + cost30d(t), 0);
  const scored = evalPacks.filter((p) => p.last_run);
  const avgScore = scored.length ? Math.round(scored.reduce((a, p) => a + (p.last_run?.score ?? 0), 0) / scored.length) : 0;

  // Tier distribution (stacked by lifecycle-live vs not)
  const tierDist = useMemo(
    () => TIER_ORDER.map((t) => {
      const of = agents.filter((a) => a.capability_tier === t);
      return { tier: t, live: of.filter(isLive).length, other: of.length - of.filter(isLive).length };
    }),
    [agents],
  );

  // Governance matrix counts
  const matrixCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const a of agents) {
      const k = `${a.capability_tier}:${a.config.lifecycle.risk_tier.value}`;
      m[k] = (m[k] ?? 0) + 1;
    }
    return m;
  }, [agents]);

  // Cost trend: 30-day stacked area, top 5 agents + other
  const { costData, topAgents } = useMemo(() => {
    const withCost = agents
      .map((a) => ({ a, cost: cost30d(telemetry.find((t) => t.agent_id === agentId(a))) }))
      .sort((x, y) => y.cost - x.cost);
    const top = withCost.slice(0, 5).map((x) => x.a);
    const topIds = new Set(top.map((a) => agentId(a)));
    const days = telemetry[0]?.series.map((p) => p.day) ?? [];
    const data = days.map((day, i) => {
      const row: Record<string, number | string> = { day: day.slice(5) };
      let other = 0;
      for (const t of telemetry) {
        const pt = t.series[i];
        if (!pt) continue;
        const c = Number(pointCost(pt).toFixed(3));
        if (topIds.has(t.agent_id)) {
          const name = agents.find((a) => agentId(a) === t.agent_id)!.config.identity.agent_name.value;
          row[name] = c;
        } else other += c;
      }
      row['Other'] = Number(other.toFixed(3));
      return row;
    });
    return { costData: data, topAgents: top };
  }, [agents, telemetry]);

  const attention = useMemo(() => buildAttention(persona, agents, pendingApprovals.length, connectors, pipelineRuns), [persona, agents, pendingApprovals.length, connectors, pipelineRuns]);

  return (
    <div>
      <PageHeader title="Home" description="What's running, what needs you, and what it's costing." />

      {/* Row 1 — stat tiles */}
      <div className="mb-4 grid grid-cols-5 gap-3">
        <StatTile icon={<Boxes size={16} />} label="Total agents" value={String(agents.length)} onClick={() => navigate('/agents')} accent="var(--accent)" />
        <StatTile icon={<CheckCircle2 size={16} />} label="Live (all tracks ✓)" value={String(liveCount)} sub={`${agents.length - liveCount} not live`} onClick={() => navigate('/agents?tab=&live=1')} accent="var(--ok)" />
        <StatTile icon={<ClipboardList size={16} />} label="Pending approvals" value={String(pendingApprovals.length)} onClick={() => navigate('/governance')} accent="var(--warn)" />
        <StatTile icon={<DollarSign size={16} />} label="Monthly token spend" value={money(monthlySpend)} onClick={() => navigate('/monitoring')} accent="var(--info)" />
        <StatTile icon={<Gauge size={16} />} label="Avg eval score" value={String(avgScore)} sub={`${scored.length} scored`} onClick={() => navigate('/evaluations')} accent="var(--ok)" />
      </div>

      {/* Row 2 */}
      <div className="mb-4 grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-text-hi">Needs your attention</div>
            <span className="text-[11px] text-text-low">as {PERSONAS[persona].label}</span>
          </div>
          {attention.length === 0 ? (
            <div className="py-6 text-center text-[12px] text-text-low">Nothing needs you right now.</div>
          ) : (
            <div className="space-y-1.5">
              {attention.map((it, i) => (
                <button key={i} onClick={() => navigate(it.to)} className="flex w-full items-center gap-2.5 rounded-control border border-border bg-raised/40 px-3 py-2 text-left hover:border-border-strong">
                  <span className={cn('shrink-0', it.tone)}>{it.icon}</span>
                  <span className="flex-1 text-[12px] text-text-hi">{it.label}</span>
                  <ArrowRight size={13} className="text-text-low" />
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-3 text-[13px] font-semibold text-text-hi">Tier & risk distribution</div>
          <div style={{ height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tierDist} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                <XAxis dataKey="tier" tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                <RTooltip contentStyle={tooltipStyle} cursor={{ fill: 'var(--bg-raised)' }} />
                <Bar dataKey="live" stackId="s" fill="var(--ok)" name="live" radius={[0, 0, 0, 0]} />
                <Bar dataKey="other" stackId="s" fill="var(--tier-minimal)" name="not live" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3">
            <GovernanceMatrix counts={matrixCounts} onCell={(t, r) => navigate(`/governance?tab=matrix&tier=${t}&risk=${r}`)} />
          </div>
        </Card>
      </div>

      {/* Row 3 — cost trend */}
      <Card className="mb-4">
        <div className="mb-3 text-[13px] font-semibold text-text-hi">Daily token cost — 30 days (top 5 + other)</div>
        <div style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={costData} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} interval={4} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
              <RTooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              {topAgents.map((a, i) => (
                <Area key={agentId(a)} type="monotone" dataKey={a.config.identity.agent_name.value} stackId="c" stroke={CHART_COLORS[i]} fill={CHART_COLORS[i]} fillOpacity={0.35} isAnimationActive={false} />
              ))}
              <Area type="monotone" dataKey="Other" stackId="c" stroke="var(--text-low)" fill="var(--text-low)" fillOpacity={0.2} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Row 4 — recent activity */}
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-semibold text-text-hi">Recent activity</div>
          <button onClick={() => navigate('/governance?tab=audit')} className="text-[11px] text-accent hover:underline">View audit log →</button>
        </div>
        <div className="space-y-1">
          {auditLog.slice().sort((a, b) => (a.at < b.at ? 1 : -1)).slice(0, 10).map((e) => (
            <div key={e.id} className="flex items-center gap-2 border-b border-border/50 py-1.5 text-[12px] last:border-0">
              <span className="mono text-[11px] text-accent w-36 shrink-0 truncate">{e.action}</span>
              <span className="flex-1 truncate text-text-mid">{e.detail}</span>
              <span className="shrink-0 text-[10px] text-text-low">{fmtDateTime(e.at)}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

const tooltipStyle = { background: 'var(--bg-raised)', border: '1px solid var(--border-strong)', borderRadius: 6, fontSize: 11, color: 'var(--text-hi)' };

interface AttentionItem { label: string; to: string; icon: React.ReactNode; tone: string }

function buildAttention(
  persona: string,
  agents: AgentRecord[],
  pendingCount: number,
  connectors: ReturnType<typeof useWorkspace.getState>['connectors'],
  pipelineRuns: ReturnType<typeof useWorkspace.getState>['pipelineRuns'],
): AttentionItem[] {
  const out: AttentionItem[] = [];
  const drafts = agents.filter((a) => a.config.lifecycle.lifecycle_status.value === 'draft');
  const nearExpiry = agents.filter((a) => { const d = daysUntil(a.fast_path_expiry_date); return d !== null && d <= FAST_PATH_WARN_DAYS; });
  const degraded = connectors.filter((c) => c.status !== 'connected');
  const runningPipelines = pipelineRuns.filter((r) => r.overall === 'in_progress');

  if (persona === 'governance_officer' && pendingCount > 0) out.push({ label: `${pendingCount} approval item(s) pending your decision`, to: '/governance', icon: <ClipboardList size={15} />, tone: 'text-warn' });
  if (persona === 'business_owner' && drafts.length > 0) out.push({ label: `${drafts.length} draft(s) in progress — resume onboarding`, to: '/onboarding', icon: <Clock size={15} />, tone: 'text-accent' });
  if (persona === 'platform_engineer') {
    if (degraded.length) out.push({ label: `${degraded.length} connector(s) degraded/offline`, to: '/tools', icon: <AlertTriangle size={15} />, tone: 'text-err' });
    if (runningPipelines.length) out.push({ label: `${runningPipelines.length} pipeline run(s) in progress`, to: '/knowledge', icon: <Clock size={15} />, tone: 'text-warn' });
  }
  // fast-path expiry warnings surface for everyone
  for (const a of nearExpiry) {
    const d = daysUntil(a.fast_path_expiry_date);
    out.push({ label: `${a.config.identity.agent_name.value}: fast-path expires in ${d} days`, to: `/agents/${agentId(a)}`, icon: <AlertTriangle size={15} />, tone: 'text-warn' });
  }
  return out;
}
