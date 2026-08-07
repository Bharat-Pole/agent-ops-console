// Monitoring & FinOps (server-backed, Increment F). Fed ONLY by real
// workflow_runs + run_steps — pre-traffic the page says "no traffic yet",
// with no seeded charts, ever.
import { useCallback, useEffect, useState } from 'react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Card, CardHeader, EmptyState } from '@/components/primitives';
import { useAuth } from '@/api/auth';
import {
  agentsApi, apiErrorMessage, telemetryApi,
  type AgentCostRow, type ServerAgent, type TelemetrySummary,
} from '@/api/client';

export default function ServerMonitoringPage() {
  const { me } = useAuth();
  const [agents, setAgents] = useState<ServerAgent[]>([]);
  const [agentId, setAgentId] = useState('');
  const [summary, setSummary] = useState<TelemetrySummary | null>(null);
  const [costs, setCosts] = useState<AgentCostRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [budgetInputs, setBudgetInputs] = useState<Record<string, string>>({});

  const isAdmin = (me?.roles ?? []).some((r) => r === 'platform_admin' || r === 'finops_admin');

  useEffect(() => {
    agentsApi.list().then(setAgents).catch(() => setAgents([]));
  }, []);

  const load = useCallback(() => {
    telemetryApi.summary(agentId || undefined).then(setSummary).catch((e) => setError(apiErrorMessage(e)));
    telemetryApi.costs().then(setCosts).catch(() => setCosts([]));
  }, [agentId]);
  useEffect(load, [load]);

  const setBudget = async (row: AgentCostRow) => {
    const value = Number(budgetInputs[row.agent_id]);
    if (!value || value <= 0) return;
    try { await telemetryApi.setBudget(row.agent_id, value); load(); }
    catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <div>
      <PageHeader title="Monitoring & FinOps" description="Real traces only — every number derives from run_steps." />
      <div className="mb-4 flex items-center gap-2">
        <span className="text-[12px] text-text-mid">Scope:</span>
        <select className="h-8 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none"
          value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          <option value="">All agents</option>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}

      {summary && summary.runs === 0 ? (
        <EmptyState title="No traffic yet" message={summary.note ?? 'Runs will appear here as they happen — nothing is simulated.'} />
      ) : summary ? (
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Stat label="Runs" value={String(summary.runs)} />
          <Stat label="Error rate" value={summary.error_rate == null ? '—' : `${(summary.error_rate * 100).toFixed(1)}%`} />
          <Stat label="Latency p50" value={`${summary.latency_ms?.p50 ?? 0}ms`} />
          <Stat label="Latency p95" value={`${summary.latency_ms?.p95 ?? 0}ms`} />
          <Stat label="Tokens" value={String((summary.tokens?.in ?? 0) + (summary.tokens?.out ?? 0))} />
          <Stat label="Cost" value={`$${(summary.cost_usd ?? 0).toFixed(4)}`} />
        </div>
      ) : null}

      {summary && summary.runs > 0 && (
        <div className="mb-4 flex flex-wrap gap-2 text-[12px]">
          {Object.entries(summary.by_status ?? {}).map(([s, n]) => (
            <Badge key={s} tone={s === 'completed' ? 'ok' : s === 'failed' ? 'err' : 'warn'}>{s}: {n}</Badge>
          ))}
          {Object.entries(summary.by_mode ?? {}).map(([m, n]) => (
            <Badge key={m} tone="neutral">{m}: {n}</Badge>
          ))}
          {summary.feedback && summary.feedback.count > 0 && (
            <Badge tone="accent">feedback +{summary.feedback.positive} / −{summary.feedback.negative}</Badge>
          )}
        </div>
      )}

      <Card>
        <CardHeader title="Cost by agent" subtitle="Tokens × catalog prices; month-to-date vs budget." />
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead><tr className="text-left text-text-low">
              <th className="py-1 pr-3 font-normal">Agent</th><th className="py-1 pr-3 font-normal">Cost center</th>
              <th className="py-1 pr-3 font-normal">Runs</th><th className="py-1 pr-3 font-normal">Total</th>
              <th className="py-1 pr-3 font-normal">MTD</th><th className="py-1 font-normal">Budget</th>
            </tr></thead>
            <tbody>
              {costs.map((row) => (
                <tr key={row.agent_id} className="border-t border-border">
                  <td className="py-1.5 pr-3 text-text-hi">{row.agent}</td>
                  <td className="py-1.5 pr-3 text-text-mid">{row.cost_center ?? '—'}</td>
                  <td className="mono py-1.5 pr-3 text-text-mid">{row.runs}</td>
                  <td className="mono py-1.5 pr-3 text-text-mid">${row.cost_usd.toFixed(4)}</td>
                  <td className="mono py-1.5 pr-3 text-text-mid">${row.mtd_cost_usd.toFixed(4)}</td>
                  <td className="py-1.5">
                    {row.budget ? (
                      <span className="flex items-center gap-2">
                        <Badge tone={row.budget.alert ? 'err' : 'ok'}>
                          ${row.mtd_cost_usd.toFixed(2)} / ${row.budget.monthly_usd}
                        </Badge>
                        {row.budget.alert && <span className="text-red-400">over budget</span>}
                      </span>
                    ) : isAdmin ? (
                      <span className="flex gap-1">
                        <input className="h-6 w-20 rounded border border-border bg-canvas px-1 text-[11px] text-text-hi outline-none"
                          placeholder="USD/mo" value={budgetInputs[row.agent_id] ?? ''}
                          onChange={(e) => setBudgetInputs((s) => ({ ...s, [row.agent_id]: e.target.value }))} />
                        <button className="text-[11px] text-text-mid hover:text-text-hi" onClick={() => setBudget(row)}>set</button>
                      </span>
                    ) : <span className="text-text-low">none</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card pad={false} className="p-3">
      <div className="text-[10px] uppercase tracking-wide text-text-low">{label}</div>
      <div className="mono mt-0.5 text-[18px] text-text-hi">{value}</div>
    </Card>
  );
}
