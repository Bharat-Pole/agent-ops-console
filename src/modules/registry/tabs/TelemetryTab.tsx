import type { AgentRecord } from '@/types';
import { agentId } from '@/types';
import { Card, EmptyState } from '@/components/primitives';
import { Sparkline, ScoreRing } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { P95_TARGET_MS } from '@/kernel/constants';
import { compactNum, pointCost, latestP95, errorRate30d, requests30d } from '@/utils/format';
import { cn } from '@/utils/cn';

function Metric({ title, value, sub, children }: { title: string; value: string; sub?: string; children: React.ReactNode }) {
  return (
    <Card>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[11px] text-text-low">{title}</span>
        <span className="text-[15px] font-semibold text-text-hi">{value}</span>
      </div>
      {sub && <div className="mb-1 text-[10px] text-text-low">{sub}</div>}
      {children}
    </Card>
  );
}

export function TelemetryTab({ agent }: { agent: AgentRecord }) {
  const t = useWorkspace((s) => s.telemetry.find((x) => x.agent_id === agentId(agent)));
  if (!t) {
    return <EmptyState title="No telemetry" message="Telemetry accrues once the agent is provisioned and live." />;
  }

  const series = t.series.map((p) => ({ ...p, cost: Number(pointCost(p).toFixed(4)) }));
  const p95 = latestP95(t);
  const target = P95_TARGET_MS[agent.capability_tier];
  const p95Over = p95 > target;
  const errRate = errorRate30d(t);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <Metric title="Requests (30d)" value={compactNum(requests30d(t))}>
          <Sparkline data={series} dataKey="requests" label="requests" />
        </Metric>
        <Metric title="p95 latency" value={`${(p95 / 1000).toFixed(1)}s`} sub={`tier target ${(target / 1000).toFixed(0)}s`}>
          <Sparkline data={series} dataKey="p95_ms" color={p95Over ? 'var(--err)' : 'var(--ok)'} label="p95 ms" />
        </Metric>
        <Metric title="Token spend (30d)" value={`$${series.reduce((a, p) => a + p.cost, 0).toFixed(2)}`}>
          <Sparkline data={series} dataKey="cost" color="var(--info)" label="daily $" />
        </Metric>
        <Metric title="Error rate" value={`${(errRate * 100).toFixed(2)}%`}>
          <Sparkline data={series} dataKey="errors" color="var(--warn)" label="errors" />
        </Metric>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Tokens per day (in / out)</div>
          <Sparkline data={series} dataKey="tokens_in" height={90} label="tokens in" />
          <Sparkline data={series} dataKey="tokens_out" color="var(--info)" height={90} label="tokens out" />
        </Card>
        <Card className="flex flex-col items-center justify-center">
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Eval score history</div>
          <ScoreRing score={t.eval_score_history[t.eval_score_history.length - 1]?.score ?? 0} />
          <div className={cn('mt-2 text-[11px]', p95Over ? 'text-warn' : 'text-text-low')}>
            {t.eval_score_history.map((h) => h.score).join(' → ')}
          </div>
        </Card>
      </div>
    </div>
  );
}
