// Testing console (Increment D): same engine as everything else, mode=test.
// The trace table is the REAL run_steps — tokens, cost, policy decisions,
// citation checks — and pending HITL gates are decided right here.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Play, Workflow as WorkflowIcon } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, JsonViewer } from '@/components/primitives';
import {
  apiErrorMessage, runsApi, workflowsApi,
  type ServerRun, type ServerWorkflow,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

const RUN_TONE: Record<string, 'ok' | 'warn' | 'err' | 'neutral' | 'muted'> = {
  completed: 'ok', paused_hitl: 'warn', failed: 'err', running: 'neutral', cancelled: 'muted',
};
const STEP_TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted'> = {
  ok: 'ok', refused: 'warn', failed: 'err', paused: 'muted',
};

export default function RunConsolePage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<ServerWorkflow[]>([]);
  const [versionId, setVersionId] = useState<string>('');
  const [input, setInput] = useState('');
  const [run, setRun] = useState<ServerRun | null>(null);
  const [history, setHistory] = useState<ServerRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    workflowsApi.listForAgent(id).then(setWorkflows).catch(() => setWorkflows([]));
    runsApi.listForAgent(id).then(setHistory).catch(() => setHistory([]));
  }, [id]);
  useEffect(load, [load]);

  const runnable = useMemo(() => workflows.flatMap((w) =>
    w.versions.filter((v) => ['validated', 'approved', 'active'].includes(v.status))
      .map((v) => ({ label: `${w.name} v${v.version} (${v.status})`, id: v.id, active: v.status === 'active' }))),
    [workflows]);

  const start = async () => {
    setBusy(true); setError(null);
    try {
      setRun(await runsApi.start(id, input, versionId || undefined));
      load();
    } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const decide = async (hitlId: string, approve: boolean) => {
    if (!run) return;
    setBusy(true); setError(null);
    try { setRun(await runsApi.decideHitl(run.id, hitlId, approve)); load(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader
        title="Testing Console"
        description="Runs the real engine with every governance control active — the trace below is the actual run record."
        action={<div className="flex gap-2">
          <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate(`/agents/${id}`)}>Agent</Button>
          <Button variant="ghost" icon={<WorkflowIcon size={14} />} onClick={() => navigate(`/agents/${id}/workflows`)}>Builder</Button>
        </div>}
      />

      <Card className="mb-4">
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <select className="h-9 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none"
              value={versionId} onChange={(e) => setVersionId(e.target.value)}>
              <option value="">Active version (default)</option>
              {runnable.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
            <input
              className="h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong"
              placeholder="Ask the agent something…"
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && input.trim() && start()}
            />
            <Button variant="primary" icon={<Play size={14} />} disabled={busy || !input.trim()} onClick={start}>
              {busy ? 'Running…' : 'Run'}
            </Button>
          </div>
          {error && <div className="text-[12px] text-red-400">{error}</div>}
        </div>
      </Card>

      {run && (
        <Card className="mb-4">
          <CardHeader
            title={<span className="flex items-center gap-2">Run <Badge tone={RUN_TONE[run.status]}>{titleCase(run.status)}</Badge></span>}
            subtitle={<span className="mono text-[11px]">{run.id} · {run.mode}</span>}
          />
          {run.status === 'completed' && (
            <div className="mb-3 rounded-control border border-border bg-canvas p-3 text-[13px] text-text-hi whitespace-pre-wrap">
              {typeof run.output.final_output === 'string'
                ? run.output.final_output
                : JSON.stringify(run.output.final_output, null, 2)}
            </div>
          )}
          {run.error && <div className="mb-3 text-[13px] text-red-400">{run.error}</div>}

          {(run.hitl ?? []).filter((h) => h.status === 'pending').map((h) => (
            <div key={h.id} className="mb-3 rounded-control border border-amber-900/50 bg-canvas p-3">
              <div className="mb-1 text-[13px] text-amber-400">Human approval required at "{h.node_id}"</div>
              <div className="mb-2 text-[12px] text-text-mid">{h.payload.llm_output_preview}</div>
              <div className="flex gap-2">
                <Button size="tiny" variant="primary" disabled={busy} onClick={() => decide(h.id, true)}>Approve & resume</Button>
                <Button size="tiny" variant="danger" disabled={busy} onClick={() => decide(h.id, false)}>Deny</Button>
              </div>
            </div>
          ))}

          {(run.steps ?? []).length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead><tr className="text-left text-text-low">
                  <th className="py-1 pr-2 font-normal">#</th><th className="py-1 pr-2 font-normal">Node</th>
                  <th className="py-1 pr-2 font-normal">Type</th><th className="py-1 pr-2 font-normal">Status</th>
                  <th className="py-1 pr-2 font-normal">ms</th><th className="py-1 pr-2 font-normal">Tokens</th>
                  <th className="py-1 pr-2 font-normal">Cost</th><th className="py-1 font-normal">Detail</th>
                </tr></thead>
                <tbody>
                  {(run.steps ?? []).map((s) => (
                    <tr key={s.ord} className="border-t border-border align-top">
                      <td className="py-1 pr-2 text-text-low">{s.ord}</td>
                      <td className="mono py-1 pr-2 text-text-hi">{s.node_id}</td>
                      <td className="py-1 pr-2 text-text-mid">{s.node_type}</td>
                      <td className="py-1 pr-2"><Badge tone={STEP_TONE[s.status] ?? 'muted'}>{s.status}</Badge></td>
                      <td className="mono py-1 pr-2 text-text-mid">{s.duration_ms}</td>
                      <td className="mono py-1 pr-2 text-text-mid">{s.tokens_in + s.tokens_out || '—'}</td>
                      <td className="mono py-1 pr-2 text-text-mid">{s.cost ? `$${s.cost.toFixed(5)}` : '—'}</td>
                      <td className="py-1"><JsonViewer data={s.detail} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {run.totals && (
                <div className="mt-2 text-[11px] text-text-low">
                  Totals: {run.totals.tokens_in + run.totals.tokens_out} tokens · ${run.totals.cost.toFixed(5)} · {run.totals.duration_ms}ms
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      <Card>
        <CardHeader title="Run history" subtitle="Real runs only — an empty list means no runs have happened." />
        {history.length === 0 ? (
          <div className="text-[12px] text-text-low">No runs yet.</div>
        ) : history.map((r) => (
          <button key={r.id} onClick={() => runsApi.get(r.id).then(setRun)}
            className="flex w-full items-center justify-between rounded-control border-t border-border px-1 py-1.5 text-left hover:bg-canvas">
            <span className="text-[12px] text-text-mid">{r.input.text?.slice(0, 80)}</span>
            <span className="flex items-center gap-2 text-[11px] text-text-low">
              <Badge tone={RUN_TONE[r.status]}>{titleCase(r.status)}</Badge>{fmtDate(r.started_at)}
            </span>
          </button>
        ))}
      </Card>
    </div>
  );
}
