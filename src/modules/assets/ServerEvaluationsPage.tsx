// Evaluation Center (server-backed, Increment E). Scorecards derive ONLY from
// real engine runs; skipped judge checks and excluded unreviewed cases are
// shown, never hidden.
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Play, Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, EmptyState, Modal } from '@/components/primitives';
import {
  agentsApi, apiErrorMessage, evalApi,
  type EvalPackRow, type EvalRunRow, type ServerAgent,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';
const AREA = 'min-h-[80px] w-full rounded-control border border-border bg-canvas px-2.5 py-2 mono text-[12px] text-text-hi outline-none focus:border-border-strong';

export default function ServerEvaluationsPage() {
  const [agents, setAgents] = useState<ServerAgent[]>([]);
  const [agentId, setAgentId] = useState('');
  const [packs, setPacks] = useState<EvalPackRow[]>([]);
  const [runs, setRuns] = useState<EvalRunRow[]>([]);
  const [openRun, setOpenRun] = useState<EvalRunRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [packOpen, setPackOpen] = useState(false);
  const [caseFor, setCaseFor] = useState<EvalPackRow | null>(null);

  useEffect(() => {
    agentsApi.list().then((rows) => {
      setAgents(rows);
      if (rows.length && !agentId) setAgentId(rows[0].id);
    }).catch((e) => setError(apiErrorMessage(e)));
  }, []);

  const load = useCallback(() => {
    if (!agentId) return;
    evalApi.packs(agentId).then(setPacks).catch((e) => setError(apiErrorMessage(e)));
    evalApi.runs(agentId).then(setRuns).catch(() => setRuns([]));
  }, [agentId]);
  useEffect(load, [load]);

  const run = async (pack: EvalPackRow) => {
    setBusy(true); setError(null);
    try { setOpenRun(await evalApi.runPack(pack.id)); load(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div>
      <PageHeader
        title="Evaluation Center"
        description="Cases run through the real engine (mode=evaluation, all governance controls on); scorecards gate promotion."
        action={<Button variant="new" icon={<Plus size={15} />} disabled={!agentId} onClick={() => setPackOpen(true)}>New pack</Button>}
      />
      <div className="mb-4 flex items-center gap-2">
        <span className="text-[12px] text-text-mid">Agent:</span>
        <select className="h-8 rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none"
          value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        {/* The other half of the admission dependency: a passing run here is
            what admits a production deployment, but deploying happens on the
            agent's own page. Say so, and link there. */}
        {agentId && (
          <span className="text-[11px] text-text-low">
            A passing run on the active workflow version admits production deployment —{' '}
            <Link to={`/agents/${agentId}`} className="text-accent hover:underline">
              deploy on the agent page →
            </Link>
          </span>
        )}
      </div>
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}

      {packs.length === 0 ? (
        <EmptyState title="No evaluation packs" message="Create a pack and add cases with expectations." />
      ) : (
        <div className="flex flex-col gap-3">
          {packs.map((p) => (
            <Card key={p.id}>
              <CardHeader
                title={<span className="flex items-center gap-2">{p.name}
                  <span className="text-[11px] text-text-low">threshold {p.threshold}</span></span>}
                subtitle={`${p.cases.length} cases`}
                action={<div className="flex gap-2">
                  <Button size="tiny" variant="subtle" onClick={() => setCaseFor(p)}>Add case</Button>
                  <Button size="tiny" variant="primary" icon={<Play size={12} />} disabled={busy || p.cases.length === 0}
                    onClick={() => run(p)}>{busy ? 'Running…' : 'Run'}</Button>
                </div>}
              />
              {p.cases.map((c) => (
                <div key={c.id} className="flex items-center justify-between border-t border-border py-1.5 text-[12px]">
                  <span className="text-text-mid">
                    <Badge tone="neutral">{c.category}</Badge> {c.name}
                    {c.review_status !== 'reviewed' && <Badge tone="warn">pending review — excluded</Badge>}
                  </span>
                  <span className="mono text-[10px] text-text-low">{Object.keys(c.expectations).join(', ')}</span>
                </div>
              ))}
            </Card>
          ))}
        </div>
      )}

      <Card className="mt-4">
        <CardHeader title="Evaluation history" subtitle="Real runs only." />
        {runs.length === 0 ? <div className="text-[12px] text-text-low">No evaluation runs yet.</div>
          : runs.map((r) => (
            <button key={r.id} onClick={() => evalApi.run(r.id).then(setOpenRun)}
              className="flex w-full items-center justify-between border-t border-border py-1.5 text-left hover:bg-canvas">
              <span className="flex items-center gap-2 text-[12px] text-text-mid">
                <Badge tone={r.scorecard.overall_passed ? 'ok' : 'err'}>
                  {r.scorecard.overall_passed ? 'PASSED' : 'FAILED'} · {r.scorecard.score}
                </Badge>
                {r.scorecard.cases_run}/{r.scorecard.cases_total} cases
              </span>
              <span className="text-[11px] text-text-low">{fmtDate(r.started_at)}</span>
            </button>
          ))}
      </Card>

      {openRun && <RunDetailModal run={openRun} onClose={() => setOpenRun(null)} />}
      <Modal open={packOpen} onClose={() => setPackOpen(false)} title="New evaluation pack" footer={null}>
        <PackForm agentId={agentId} onDone={() => { setPackOpen(false); load(); }} />
      </Modal>
      {caseFor && (
        <Modal open onClose={() => setCaseFor(null)} title={`Add case — ${caseFor.name}`} footer={null} width="max-w-2xl">
          <CaseForm pack={caseFor} onDone={() => { setCaseFor(null); load(); }} />
        </Modal>
      )}
    </div>
  );
}

function RunDetailModal({ run, onClose }: { run: EvalRunRow; onClose: () => void }) {
  const card = run.scorecard;
  return (
    <Modal open onClose={onClose} title="Scorecard" width="max-w-3xl" footer={null}>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className={`text-2xl font-semibold ${card.overall_passed ? 'text-ok' : 'text-red-400'}`}>{card.score}</span>
        <Badge tone={card.overall_passed ? 'ok' : 'err'}>{card.overall_passed ? 'PASSED' : 'FAILED'}</Badge>
        <span className="text-[12px] text-text-low">threshold {card.threshold}</span>
        {card.cases_excluded_pending_review > 0 && (
          <Badge tone="warn">{card.cases_excluded_pending_review} excluded (pending review)</Badge>
        )}
        {card.cases_not_evaluated > 0 && <Badge tone="warn">{card.cases_not_evaluated} not evaluated</Badge>}
      </div>
      <div className="mb-3 flex flex-wrap gap-2 text-[12px] text-text-mid">
        {Object.entries(card.categories ?? {}).map(([cat, v]) => (
          <span key={cat} className="rounded-control border border-border bg-canvas px-2 py-1">
            {titleCase(cat)}: {v.passed}✓ {v.failed}✕{v.not_evaluated ? ` ${v.not_evaluated}∅` : ''}
          </span>
        ))}
      </div>
      {(run.results ?? []).map((res) => (
        <Card key={res.case_id} className="mb-2">
          <CardHeader
            title={<span className="flex items-center gap-2">{res.case_name}
              <Badge tone={res.passed === true ? 'ok' : res.passed === false ? 'err' : 'muted'}>
                {res.passed === true ? 'pass' : res.passed === false ? 'fail' : 'not evaluated'}
              </Badge></span>}
            subtitle={res.run_id ? `workflow run ${res.run_id}` : undefined}
          />
          {res.checks.map((c, i) => (
            <div key={i} className="text-[12px]">
              <span className={c.ok === true ? 'text-ok' : c.ok === false ? 'text-red-400' : 'text-amber-400'}>
                {c.ok === true ? '✓' : c.ok === false ? '✕' : '∅'} {c.check}
              </span>{' '}
              <span className="text-text-low">{c.note}</span>
            </div>
          ))}
        </Card>
      ))}
    </Modal>
  );
}

function PackForm({ agentId, onDone }: { agentId: string; onDone: () => void }) {
  const [name, setName] = useState('');
  const [threshold, setThreshold] = useState(70);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setError(null);
    try { await evalApi.createPack(agentId, name, threshold); onDone(); }
    catch (e) { setError(apiErrorMessage(e)); }
  };
  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
        <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Pass threshold (0-100)</span>
        <input className={INPUT} type="number" min={0} max={100} value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))} /></label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end"><Button variant="primary" disabled={name.trim().length < 3} onClick={submit}>Create</Button></div>
    </div>
  );
}

const EXPECT_TEMPLATE = `{
  "must_contain": ["expected phrase"],
  "must_cite": false,
  "must_refuse": false,
  "no_write": true,
  "latency_max_ms": 60000,
  "judge": {"criteria": "Answer follows the runbook order", "min_score": 4}
}`;

function CaseForm({ pack, onDone }: { pack: EvalPackRow; onDone: () => void }) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('golden');
  const [input, setInput] = useState('');
  const [expectations, setExpectations] = useState(EXPECT_TEMPLATE);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setError(null);
    let parsed: Record<string, unknown>;
    try { parsed = JSON.parse(expectations); }
    catch { setError('expectations must be valid JSON'); return; }
    try { await evalApi.addCase(pack.id, { name, category, input, expectations: parsed }); onDone(); }
    catch (e) { setError(apiErrorMessage(e)); }
  };
  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
        <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Category</span>
        <select className={INPUT} value={category} onChange={(e) => setCategory(e.target.value)}>
          {['golden', 'boundary', 'refusal', 'no_write', 'data_boundary', 'tool_call', 'regression', 'latency', 'cost', 'safety']
            .map((c) => <option key={c} value={c}>{c}</option>)}
        </select></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Input (what the agent is asked)</span>
        <textarea className={AREA} value={input} onChange={(e) => setInput(e.target.value)} /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Expectations (JSON — remove keys you don't need)</span>
        <textarea className={AREA} rows={8} value={expectations} onChange={(e) => setExpectations(e.target.value)} /></label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end"><Button variant="primary" disabled={!name || !input} onClick={submit}>Add case</Button></div>
    </div>
  );
}
