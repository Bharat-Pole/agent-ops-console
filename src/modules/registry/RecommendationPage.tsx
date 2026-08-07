// Design recommendation review (Increment B). Server truth, verbatim:
// verification badges come from the basis-overlap machinery, contradictions
// are shown — never auto-resolved — and LLM failures render as the labeled
// deterministic baseline, not as fabricated content. Per-item accept/reject
// only; there is no bulk accept, by design.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Sparkles } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, EmptyState, JsonViewer } from '@/components/primitives';
import {
  agentsApi, apiErrorMessage, recommendationApi,
  type ItemState, type Recommendation, type RecommendationItem, type ServerAgent,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

const VERIFICATION_TONE = {
  grounded: 'ok',
  unverified: 'warn',
  deterministic: 'neutral',
} as const;

const VERIFICATION_LABEL = {
  grounded: 'grounded in intent',
  unverified: 'unverified — review carefully',
  deterministic: 'rule-derived (deterministic)',
} as const;

export default function RecommendationPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<ServerAgent | null>(null);
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    agentsApi.get(id).then(setAgent).catch(() => setAgent(null));
    recommendationApi.get(id)
      .then((r) => { setRec(r); setMissing(false); setError(null); })
      .catch((e) => {
        setRec(null);
        if ((e as { status?: number }).status === 404) setMissing(true);
        else setError(apiErrorMessage(e));
      });
  }, [id]);
  useEffect(load, [load]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      setRec(await recommendationApi.generate(id));
      setMissing(false);
    } catch (e) {
      setError(apiErrorMessage(e)); // e.g. 409 no submitted intent, 403 role
    } finally {
      setBusy(false);
    }
  };

  const decide = async (itemId: string, state: ItemState) => {
    try {
      const r = await recommendationApi.setItemState(id, itemId, state);
      setRec((prev) => (prev ? { ...prev, item_states: r.item_states } : prev));
    } catch (e) {
      setError(apiErrorMessage(e));
    }
  };

  return (
    <div>
      <PageHeader
        title={`Design recommendation — ${agent?.name ?? '…'}`}
        description="Grounded in the submitted intent; every claim is verified mechanically and decided per item."
        action={
          <div className="flex gap-2">
            <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate(`/agents/${id}`)}>
              Back to agent
            </Button>
            <Button variant="new" icon={rec ? <RefreshCw size={14} /> : <Sparkles size={14} />} disabled={busy} onClick={generate}>
              {busy ? 'Generating…' : rec ? 'Regenerate (new version)' : 'Generate'}
            </Button>
          </div>
        }
      />

      {error && (
        <Card className="mb-4 border-red-900/50">
          <div className="text-[13px] text-red-400">{error}</div>
        </Card>
      )}

      {missing && !rec ? (
        <EmptyState
          title="No recommendation yet"
          message="Generate one from the submitted intent. If the LLM provider is unavailable, the deterministic baseline is produced and labeled as such — manual configuration always remains open."
          action={<Button variant="primary" disabled={busy} onClick={generate}>{busy ? 'Generating…' : 'Generate now'}</Button>}
        />
      ) : rec ? (
        <>
          {/* engine banner — honest about what produced this */}
          <Card className="mb-4">
            <div className="flex flex-wrap items-center gap-3 text-[12px] text-text-mid">
              <Badge tone={rec.engine === 'llm+deterministic' ? 'accent' : 'neutral'}>{rec.engine}</Badge>
              {rec.model_id && <span className="mono">{rec.model_id}</span>}
              {rec.prompt_version && <span className="mono text-text-low">{rec.prompt_version}</span>}
              <span className="text-text-low">{fmtDate(rec.created_at)}</span>
              {rec.validation.llm_error && (
                <span className="text-amber-400">
                  LLM attempt failed ({rec.validation.llm_error}) — showing the labeled deterministic baseline.
                </span>
              )}
            </div>
            {rec.summary && <div className="mt-2 text-[13px] text-text-mid">{rec.summary}</div>}
          </Card>

          {(rec.validation.contradictions?.length ?? 0) > 0 && (
            <Card className="mb-4 border-amber-900/50">
              <CardHeader title="Contradictions — reviewer must resolve" subtitle="Deterministic signals are never silently overridden." />
              {rec.validation.contradictions!.map((c, i) => (
                <div key={i} className="text-[13px] text-amber-400">
                  {c.field}: LLM says <b>{c.llm}</b>, deterministic analysis says <b>{c.deterministic}</b>. {c.note}
                </div>
              ))}
            </Card>
          )}

          <div className="flex flex-col gap-3">
            {rec.items.map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                state={rec.item_states[item.id] ?? 'pending'}
                onDecide={(s) => decide(item.id, s)}
              />
            ))}
          </div>

          {(rec.missing_information.length > 0 || rec.clarifying_questions.length > 0) && (
            <Card className="mt-4">
              <CardHeader title="Declared gaps" subtitle="What the engine says it does NOT know — not what it guessed." />
              {rec.missing_information.map((m, i) => (
                <div key={`m${i}`} className="text-[13px] text-text-mid">• {m}</div>
              ))}
              {rec.clarifying_questions.map((q, i) => (
                <div key={`q${i}`} className="text-[13px] text-text-mid">? {q}</div>
              ))}
            </Card>
          )}

          {(rec.validation.closed_world_demotions?.length ?? 0) > 0 && (
            <Card className="mt-4">
              <CardHeader
                title="Closed-world demotions"
                subtitle="References that do not resolve in the registries were demoted to described needs."
              />
              {rec.validation.closed_world_demotions!.map((d, i) => (
                <div key={i} className="text-[13px] text-text-mid">
                  <span className="mono">{d.ref}</span> ({d.kind} {d.item}) — {d.note}
                </div>
              ))}
            </Card>
          )}
        </>
      ) : !missing && !error ? (
        <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
      ) : null}
    </div>
  );
}

function ItemCard({
  item, state, onDecide,
}: {
  item: RecommendationItem;
  state: ItemState;
  onDecide: (s: ItemState) => void;
}) {
  const flow = item.kind === 'flow' ? item.detail.flow : undefined;
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {item.title}
            <Badge tone={VERIFICATION_TONE[item.verification]}>{VERIFICATION_LABEL[item.verification]}</Badge>
            {typeof item.overlap === 'number' && item.verification !== 'deterministic' && (
              <span className="mono text-[10px] text-text-low">overlap {(item.overlap * 100).toFixed(0)}%</span>
            )}
            {item.state === 'described_need' && <Badge tone="muted">described need</Badge>}
          </span>
        }
        subtitle={item.note}
        action={
          <div className="flex gap-1">
            <Button size="tiny" variant={state === 'accepted' ? 'primary' : 'ghost'} onClick={() => onDecide('accepted')}>
              Accept
            </Button>
            <Button size="tiny" variant={state === 'rejected' ? 'danger' : 'ghost'} onClick={() => onDecide('rejected')}>
              Reject
            </Button>
            {state !== 'pending' && (
              <Button size="tiny" variant="ghost" onClick={() => onDecide('pending')}>Reset</Button>
            )}
          </div>
        }
      />
      {item.basis && (
        <div className="mb-2 rounded-control border border-border bg-canvas px-3 py-2 text-[12px] text-text-mid">
          <span className="text-text-low">Basis: </span>{item.basis}
        </div>
      )}
      {flow ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-text-low">
                <th className="py-1 pr-3 font-normal">Node</th>
                <th className="py-1 pr-3 font-normal">Type</th>
                <th className="py-1 font-normal">Label</th>
              </tr>
            </thead>
            <tbody>
              {flow.nodes.map((n) => (
                <tr key={n.id} className="border-t border-border">
                  <td className="mono py-1 pr-3 text-text-hi">{n.id}</td>
                  <td className="py-1 pr-3"><Badge tone={n.type === 'guardrail' ? 'warn' : 'neutral'}>{titleCase(n.type)}</Badge></td>
                  <td className="py-1 text-text-mid">{n.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-[11px] text-text-low">
            {flow.edges.map((e, i) => (
              <span key={i} className="mono mr-3">{e.from} → {e.to}{e.when ? ` [${e.when}]` : ''}</span>
            ))}
          </div>
        </div>
      ) : (
        <JsonViewer data={item.detail} />
      )}
    </Card>
  );
}
