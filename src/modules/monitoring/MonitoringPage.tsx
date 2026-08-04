import { useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip as RTooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from 'recharts';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Card, Badge, EmptyState, type TabItem } from '@/components/primitives';
import { MiniTrackPills, Sparkline } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { agentId, type AgentRecord } from '@/types';
import { P95_TARGET_MS } from '@/kernel/constants';
import { cost30d, requests30d, latestP95, errorRate30d, pointCost, money, compactNum } from '@/utils/format';
import { TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react';
import { cn } from '@/utils/cn';

const CHART_COLORS = ['var(--accent)', 'var(--info)', 'var(--ok)', 'var(--warn)', 'var(--risk-high)'];
const tooltipStyle = { background: 'var(--bg-raised)', border: '1px solid var(--border-strong)', borderRadius: 6, fontSize: 11, color: 'var(--text-hi)' };

export default function MonitoringPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'health';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });
  return (
    <div>
      <PageHeader title="Monitoring & FinOps" description="Per-agent health and 30-day usage & cost, from the seeded telemetry generator." />
      <Tabs items={[{ key: 'health', label: 'Health' }, { key: 'cost', label: 'Usage & Cost' }] as TabItem[]} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'health' ? <HealthTab /> : <CostTab />}
    </div>
  );
}

function HealthTab() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const telemetry = useWorkspace((s) => s.telemetry);

  const rows = useMemo(() => {
    const withT = agents.map((a) => ({ a, t: telemetry.find((x) => x.agent_id === agentId(a)) })).filter((r) => r.t);
    return withT.map((r) => {
      const target = P95_TARGET_MS[r.a.capability_tier];
      const p95 = latestP95(r.t);
      const err = errorRate30d(r.t);
      const degraded = p95 > target || err > 0.02;
      return { ...r, target, p95, err, degraded };
    }).sort((x, y) => Number(y.degraded) - Number(x.degraded));
  }, [agents, telemetry]);

  if (rows.length === 0) return <EmptyState icon={<Activity size={26} />} title="No telemetry yet" message="Telemetry accrues once agents are provisioned and live." />;

  // Platform aggregate
  const platReq = rows.reduce((a, r) => a + requests30d(r.t), 0);
  const platErr = rows.reduce((a, r) => a + errorRate30d(r.t) * requests30d(r.t), 0) / (platReq || 1);

  return (
    <Card pad={false}>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border text-left text-[10px] uppercase tracking-wide text-text-low">
            <th className="px-3 py-2">Agent</th><th className="px-3 py-2">Requests/day (30d)</th><th className="px-3 py-2 text-right">p95 vs target</th><th className="px-3 py-2 text-right">Error rate</th><th className="px-3 py-2">Tracks</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-border bg-raised/40">
            <td className="px-3 py-2 font-semibold text-text-hi">Platform (all agents)</td>
            <td className="px-3 py-2 text-text-mid">{compactNum(platReq)} total</td>
            <td className="px-3 py-2 text-right text-text-mid">—</td>
            <td className="px-3 py-2 text-right text-text-mid">{(platErr * 100).toFixed(2)}%</td>
            <td className="px-3 py-2">—</td>
          </tr>
          {rows.map(({ a, t, target, p95, err, degraded }) => (
            <tr key={agentId(a)} onClick={() => navigate(`/agents/${agentId(a)}?tab=telemetry`)} className={cn('border-b border-border/50 cursor-pointer hover:bg-raised', degraded && 'bg-err/5')}>
              <td className="px-3 py-2">
                <div className="font-medium text-text-hi">{a.config.identity.agent_name.value}</div>
                {degraded && <Badge tone="err">degraded</Badge>}
              </td>
              <td className="px-3 py-2" style={{ width: 200 }}><Sparkline data={t!.series.map((p) => ({ ...p }))} dataKey="requests" label="req/day" /></td>
              <td className={cn('px-3 py-2 text-right mono', p95 > target ? 'text-err' : 'text-ok')}>{(p95 / 1000).toFixed(1)}s / {(target / 1000).toFixed(0)}s</td>
              <td className={cn('px-3 py-2 text-right mono', err > 0.02 ? 'text-warn' : 'text-text-mid')}>{(err * 100).toFixed(2)}%</td>
              <td className="px-3 py-2"><MiniTrackPills agent={a} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function CostTab() {
  const agents = useWorkspace((s) => s.agents);
  const telemetry = useWorkspace((s) => s.telemetry);

  const withCost = useMemo(() => agents.map((a) => ({ a, t: telemetry.find((x) => x.agent_id === agentId(a)) })).filter((r) => r.t).map((r) => ({ ...r, cost: cost30d(r.t) })).sort((x, y) => y.cost - x.cost), [agents, telemetry]);
  const top = withCost.slice(0, 5);
  const topIds = new Set(top.map((r) => agentId(r.a)));

  // stacked daily tokens by agent (top 5 + other)
  const days = telemetry[0]?.series.map((p) => p.day) ?? [];
  const tokenData = days.map((day, i) => {
    const row: Record<string, number | string> = { day: day.slice(5) };
    let other = 0;
    for (const t of telemetry) { const p = t.series[i]; if (!p) continue; const tk = p.tokens_in + p.tokens_out; if (topIds.has(t.agent_id)) row[agents.find((a) => agentId(a) === t.agent_id)!.config.identity.agent_name.value] = tk; else other += tk; }
    row['Other'] = other;
    return row;
  });

  // cost by cost_label (pie)
  const byLabel = new Map<string, number>();
  for (const r of withCost) { const label = r.a.config.observability.cost_label.value; byLabel.set(label, (byLabel.get(label) ?? 0) + r.cost); }
  const pieData = [...byLabel.entries()].map(([name, value]) => ({ name, value: Number(value.toFixed(2)) }));

  const monthly = withCost.reduce((a, r) => a + r.cost, 0);

  const trend = (r: (typeof withCost)[number]) => {
    const s = r.t!.series;
    const recent = s.slice(-7).reduce((a, p) => a + pointCost(p), 0);
    const prior = s.slice(-14, -7).reduce((a, p) => a + pointCost(p), 0);
    return recent - prior;
  };

  const budgetOf = (a: AgentRecord) => (a.capability_tier === 'advanced' ? 40 : a.capability_tier === 'standardized' ? 20 : 5);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Card><div className="text-[11px] text-text-low">Monthly token spend</div><div className="text-[22px] font-semibold text-text-hi">{money(monthly)}</div></Card>
        <Card><div className="text-[11px] text-text-low">30-day projection</div><div className="text-[22px] font-semibold text-text-hi">{money(monthly)}</div><div className="text-[11px] text-text-low">≈ next month</div></Card>
        <Card><div className="text-[11px] text-text-low">Agents reporting</div><div className="text-[22px] font-semibold text-text-hi">{withCost.length}</div></Card>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Daily tokens by agent (top 5 + other)</div>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={tokenData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} interval={4} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} tickFormatter={(v) => compactNum(Number(v))} />
                <RTooltip contentStyle={tooltipStyle} formatter={(v) => compactNum(Number(v))} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                {top.map((r, i) => <Area key={agentId(r.a)} type="monotone" dataKey={r.a.config.identity.agent_name.value} stackId="t" stroke={CHART_COLORS[i]} fill={CHART_COLORS[i]} fillOpacity={0.35} isAnimationActive={false} />)}
                <Area type="monotone" dataKey="Other" stackId="t" stroke="var(--text-low)" fill="var(--text-low)" fillOpacity={0.2} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Cost by cost_label</div>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="45%" outerRadius={70} innerRadius={38}>
                  {pieData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
                <RTooltip contentStyle={tooltipStyle} formatter={(v) => money(Number(v))} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card pad={false}>
        <div className="border-b border-border px-3 py-2.5 text-[13px] font-semibold text-text-hi">Cost per agent (30d)</div>
        <table className="w-full text-[13px]">
          <thead><tr className="border-b border-border text-left text-[10px] uppercase text-text-low"><th className="px-3 py-2">Agent</th><th className="px-3 py-2">cost_label</th><th className="px-3 py-2 text-right">Tokens in</th><th className="px-3 py-2 text-right">Tokens out</th><th className="px-3 py-2 text-right">$ (30d)</th><th className="px-3 py-2 text-right">Trend</th><th className="px-3 py-2 text-right">Budget</th></tr></thead>
          <tbody>
            {withCost.map((r) => {
              const tin = r.t!.series.reduce((a, p) => a + p.tokens_in, 0);
              const tout = r.t!.series.reduce((a, p) => a + p.tokens_out, 0);
              const tr = trend(r);
              const budget = budgetOf(r.a);
              const over = r.cost > budget;
              return (
                <tr key={agentId(r.a)} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-2 text-text-hi">{r.a.config.identity.agent_name.value}</td>
                  <td className="px-3 py-2 text-text-mid">{r.a.config.observability.cost_label.value}</td>
                  <td className="px-3 py-2 text-right mono text-text-mid">{compactNum(tin)}</td>
                  <td className="px-3 py-2 text-right mono text-text-mid">{compactNum(tout)}</td>
                  <td className="px-3 py-2 text-right mono text-text-hi">{money(r.cost)}</td>
                  <td className="px-3 py-2 text-right">{tr > 0.01 ? <TrendingUp size={14} className="inline text-warn" /> : tr < -0.01 ? <TrendingDown size={14} className="inline text-ok" /> : <Minus size={14} className="inline text-text-low" />}</td>
                  <td className="px-3 py-2 text-right"><Badge tone={over ? 'err' : 'ok'}>{over ? 'over' : 'under'}</Badge></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
