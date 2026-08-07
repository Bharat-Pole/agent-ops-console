import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip as RTooltip, CartesianGrid, ReferenceLine } from 'recharts';
import { PageHeader } from '@/components/shell/PageHeader';
import { Breadcrumbs } from '@/components/shell/Breadcrumbs';
import { Card, Button, Badge, EmptyState } from '@/components/primitives';
import { ScoreRing } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, type EvalCategory } from '@/types';
import { DEEP_EVAL_PASS_SCORE } from '@/kernel/constants';
import { titleCase, fmtDate } from '@/utils/format';
import { Play, Loader2, Wrench, AlertTriangle, Plus, FileDown, RotateCcw } from 'lucide-react';
import { cn } from '@/utils/cn';

const CATS: EvalCategory[] = ['grounding', 'correctness', 'safety_boundary', 'latency_cost', 'regression'];

export default function EvalDetailPage() {
  const { packId } = useParams();
  const navigate = useNavigate();
  const pack = useWorkspace((s) => s.evalPacks.find((p) => p.id === packId));
  const agent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === pack?.agent_id));
  const telemetry = useWorkspace((s) => s.telemetry.find((t) => t.agent_id === pack?.agent_id));
  const jobs = useWorkspace((s) => s.jobs);
  const upsertPack = useWorkspace((s) => s.upsertEvalPack);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ category: 'correctness' as EvalCategory, input: '', expected: '' });
  const [regenerating, setRegenerating] = useState(false);

  if (!pack) return <div><Breadcrumbs items={[{ label: 'Evaluations', to: '/evaluations' }, { label: packId ?? 'pack' }]} /><EmptyState title="Pack not found" action={<Button variant="primary" onClick={() => navigate('/evaluations')}>Back</Button>} /></div>;

  const running = jobs.some((j) => j.kind === 'evaluation_run' && j.entity_id === pack.id && (j.status === 'processing' || j.status === 'queued'));
  const score = pack.last_run?.score ?? null;
  const thresholdBroken = agent && (agent.config.data.score_threshold.value ?? 0) > 0.9 && pack.cases.some((c) => c.category === 'grounding' && c.last_result === 'fail');

  const fixThreshold = async () => {
    if (!agent) return;
    await api.proposeConfigChange(agentId(agent), 'data', 'score_threshold', 0.35);
    void api.runEvaluation(pack.id);
  };

  const addCase = () => {
    if (!form.input.trim()) return;
    upsertPack({ ...pack, cases: [...pack.cases, { test_id: `${pack.id}-custom-${pack.cases.length + 1}`, category: form.category, input: form.input, expected_output: form.expected, evaluation_method: 'manual', pass_threshold: 'rubric', last_result: null }] });
    setForm({ category: 'correctness', input: '', expected: '' });
    setAdding(false);
  };

  const historyData = (telemetry?.eval_score_history ?? []).map((h) => ({ date: h.date.slice(5), score: h.score }));

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Evaluations', to: '/evaluations' }, { label: agent?.config.identity.agent_name.value ?? pack.id }]} />
      <PageHeader title={`${agent?.config.identity.agent_name.value ?? 'Evaluation'} — eval pack`} description={pack.id}
        action={
          <div className="flex gap-2">
            <Button variant="outline" icon={<FileDown size={14} />} onClick={() => void api.downloadEvidencePack(pack.id)}>Evidence pack</Button>
            <Button variant="primary" icon={running ? <Loader2 size={14} className="animate-spin-slow" /> : <Play size={14} />} disabled={running} onClick={() => void api.runEvaluation(pack.id)}>{running ? 'Running…' : 'Run all'}</Button>
          </div>
        } />

      {thresholdBroken && (
        <Card className="mb-4 border-warn/40">
          <div className="flex items-center gap-3">
            <AlertTriangle size={18} className="text-warn" />
            <div className="flex-1 text-[12px]">
              <div className="font-medium text-text-hi">Two grounding cases fail — score_threshold is {agent!.config.data.score_threshold.value} (too strict)</div>
              <div className="text-text-low">Deep-path promotion is locked below {DEEP_EVAL_PASS_SCORE}. Fix the threshold and re-run.</div>
            </div>
            <Button variant="primary" size="sm" icon={<Wrench size={13} />} onClick={() => void fixThreshold()}>Fix score_threshold → 0.35 & re-run</Button>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-4">
          <Card className="flex flex-col items-center">
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Last run</div>
            {score !== null ? <ScoreRing score={score} /> : <div className="py-4 text-[12px] text-text-low">not run</div>}
            {pack.last_run && <div className="mt-2 text-[11px] text-text-low">{fmtDate(pack.last_run.date)}</div>}
          </Card>
          <Card>
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Category breakdown</div>
            {CATS.map((cat) => {
              const cs = pack.cases.filter((c) => c.category === cat);
              if (!cs.length) return null;
              const passed = cs.filter((c) => c.last_result === 'pass').length;
              const pct = cs.length ? (passed / cs.length) * 100 : 0;
              return (
                <div key={cat} className="mb-1.5">
                  <div className="flex justify-between text-[11px]"><span className="text-text-mid">{titleCase(cat)}</span><span className="text-text-low">{passed}/{cs.length}</span></div>
                  <div className="h-1.5 rounded-full bg-canvas"><div className={cn('h-full rounded-full', pct === 100 ? 'bg-ok' : pct > 0 ? 'bg-warn' : 'bg-err')} style={{ width: `${pct}%` }} /></div>
                </div>
              );
            })}
          </Card>
          {historyData.length > 0 && (
            <Card>
              <div className="mb-2 text-[13px] font-semibold text-text-hi">Run history</div>
              <div style={{ height: 120 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={historyData} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 9, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
                    <YAxis domain={[50, 100]} tick={{ fontSize: 9, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
                    <RTooltip contentStyle={{ background: 'var(--bg-raised)', border: '1px solid var(--border-strong)', borderRadius: 6, fontSize: 11 }} />
                    <ReferenceLine y={DEEP_EVAL_PASS_SCORE} stroke="var(--ok)" strokeDasharray="4 2" />
                    <Line type="monotone" dataKey="score" stroke="var(--accent)" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          )}
        </div>

        <div className="col-span-2 space-y-4">
          <Card pad={false}>
            <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
              <span className="text-[13px] font-semibold text-text-hi">Cases ({pack.cases.length})</span>
              <div className="flex gap-2">
                <Button
                  variant="ghost" size="sm"
                  icon={regenerating ? <Loader2 size={13} className="animate-spin-slow" /> : <RotateCcw size={13} />}
                  disabled={regenerating}
                  onClick={async () => { setRegenerating(true); await api.regenerateEvalPack(pack.id); setRegenerating(false); }}
                  title="Rebuild these cases from the agent's current objective and bound source"
                >
                  {regenerating ? 'Regenerating…' : 'Regenerate cases'}
                </Button>
                <Button variant="subtle" size="sm" icon={<Plus size={13} />} onClick={() => setAdding((v) => !v)}>Add custom case</Button>
              </div>
            </div>
            {adding && (
              <div className="space-y-2 border-b border-border bg-raised/30 p-3">
                <div className="flex gap-2">
                  <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as EvalCategory })} className="rounded-control border border-border bg-canvas px-2 py-1.5 text-[12px] text-text-hi">
                    {CATS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <input value={form.input} onChange={(e) => setForm({ ...form, input: e.target.value })} placeholder="input" className="flex-1 rounded-control border border-border bg-canvas px-2 py-1.5 text-[12px] text-text-hi" />
                </div>
                <input value={form.expected} onChange={(e) => setForm({ ...form, expected: e.target.value })} placeholder="expected output" className="w-full rounded-control border border-border bg-canvas px-2 py-1.5 text-[12px] text-text-hi" />
                <Button variant="primary" size="sm" onClick={addCase}>Add</Button>
              </div>
            )}
            <div className="divide-y divide-border/50">
              {CATS.map((cat) => {
                const cs = pack.cases.filter((c) => c.category === cat);
                if (!cs.length) return null;
                return (
                  <div key={cat} className="px-3 py-2">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-low">{titleCase(cat)}</div>
                    {cs.map((c) => (
                      <div key={c.test_id} className={cn('flex items-start gap-2 py-1', cat === 'safety_boundary' && c.last_result === 'fail' && '-mx-1 rounded bg-err/10 px-1')}>
                        <Badge tone={c.last_result === 'pass' ? 'ok' : c.last_result === 'fail' ? 'err' : 'muted'}>{c.last_result ?? 'not run'}</Badge>
                        <div className="min-w-0 flex-1 text-[12px]">
                          <div className="text-text-hi">{c.input}</div>
                          <div className="text-[11px] text-text-low">{c.evaluation_method} · {c.pass_threshold} → {c.expected_output}</div>
                        </div>
                        <Button variant="ghost" size="tiny" icon={<Play size={10} />} disabled={running} onClick={() => void api.runEvaluation(pack.id)}>Run</Button>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
