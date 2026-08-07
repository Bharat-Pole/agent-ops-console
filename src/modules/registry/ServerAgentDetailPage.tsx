// Server agent detail (Increment A): the control record, lifecycle transition
// panel, and the REAL audit trail. Policy lives server-side — this page offers
// the actions and renders the server's allow/deny verdicts verbatim.
//
// Strangler note: ids that the backend doesn't know (404) fall back to the
// legacy kernel detail page, so pre-existing demo links keep working until
// every module is rewired.
import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowRight, FileText, Play, Sparkles, Workflow as WorkflowIcon } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, ComboBox, EmptyState, JsonViewer, type ComboOption } from '@/components/primitives';
import {
  agentsApi, auditApi, ApiError, apiErrorMessage, bindingsApi, knowledgeApi, modelsApi,
  promptsApi, ragApi, toolsApi, SERVER_LIFECYCLE,
  type AssetBindingRow, type AuditRow, type ServerAgent, type ServerLifecycleStatus,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';
import LegacyAgentDetailPage from './AgentDetailPage';
import DeploymentCard from './DeploymentCard';
import { SERVER_LIFECYCLE_TONE } from './ServerRegistryPage';

export default function ServerAgentDetailPage() {
  const { id = '' } = useParams();
  const [agent, setAgent] = useState<ServerAgent | null>(null);
  const [audit, setAudit] = useState<AuditRow[] | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoadError(null);
    agentsApi.get(id).then((a) => {
      setAgent(a);
      auditApi.forResource('agent', a.id).then(setAudit).catch(() => setAudit(null));
    }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
      else setLoadError(apiErrorMessage(e));
    });
  }, [id]);
  useEffect(load, [load]);

  if (notFound) return <LegacyAgentDetailPage />; // kernel-era id — legacy view
  if (loadError) {
    return (
      <EmptyState
        title="Could not load agent"
        message={loadError}
        action={<Button variant="primary" onClick={load}>Retry</Button>}
      />
    );
  }
  if (!agent) return <div className="py-16 text-center text-[13px] text-text-low">Loading agent…</div>;

  const risk = agent.confirmed_risk_tier ?? agent.draft_risk_tier;

  return (
    <div>
      <PageHeader
        title={agent.name}
        description={agent.description || 'No description.'}
        action={<Badge tone={SERVER_LIFECYCLE_TONE[agent.lifecycle_status]}>{titleCase(agent.lifecycle_status)}</Badge>}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Control record" />
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px]">
            <Field label="Slug" mono value={agent.slug} />
            <Field label="Intent type" value={titleCase(agent.intent_type)} />
            <Field
              label="Risk tier"
              value={risk ? `${titleCase(risk)}${agent.confirmed_risk_tier ? '' : ' (draft)'}` : '—'}
            />
            <Field
              label="Intent document"
              value={agent.current_intent_version ? `v${agent.current_intent_version}` : 'none submitted'}
            />
            <Field label="Business owner" value={agent.business_owner ?? '—'} />
            <Field label="Technical owner" value={agent.technical_owner ?? '—'} />
            <Field label="Governance owner" value={agent.governance_owner ?? '—'} />
            <Field label="Cost center" value={agent.cost_center ?? '—'} />
            <Field label="Created" value={fmtDate(agent.created_at)} />
            <Field label="Updated" value={fmtDate(agent.updated_at)} />
          </dl>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader
              title="Design journey"
              subtitle={agent.current_intent_version
                ? `Intent v${agent.current_intent_version} submitted.`
                : 'No intent submitted yet — start there.'}
            />
            <div className="flex flex-col gap-2">
              <Link to={`/agents/${agent.id}/intent`}>
                <Button variant="subtle" icon={<FileText size={14} />} className="w-full">
                  {agent.current_intent_version ? 'Edit intent draft (next version)' : 'Capture intent'}
                </Button>
              </Link>
              <Link to={`/agents/${agent.id}/recommendation`}>
                <Button
                  variant="subtle"
                  icon={<Sparkles size={14} />}
                  className="w-full"
                  disabled={!agent.current_intent_version}
                  title={agent.current_intent_version ? undefined : 'Submit an intent first'}
                >
                  Design recommendation
                </Button>
              </Link>
              <Link to={`/agents/${agent.id}/workflows`}>
                <Button variant="subtle" icon={<WorkflowIcon size={14} />} className="w-full">
                  Workflow builder
                </Button>
              </Link>
              <Link to={`/agents/${agent.id}/console`}>
                <Button variant="subtle" icon={<Play size={14} />} className="w-full">
                  Testing console
                </Button>
              </Link>
            </div>
          </Card>

          <TransitionPanel agent={agent} onChanged={load} />
          <DeploymentCard agentId={agent.id} />
          <BindingsCard agentId={agent.id} />
        </div>
      </div>

      <div className="mt-4">
        <Card>
          <CardHeader title="Audit trail" subtitle="Append-only; actor derived from the server session." />
          {audit === null ? (
            <div className="text-[12px] text-text-low">Audit trail unavailable.</div>
          ) : audit.length === 0 ? (
            <div className="text-[12px] text-text-low">No audit entries yet.</div>
          ) : (
            <div className="flex flex-col gap-2">
              {audit.map((row) => (
                <div key={row.id} className="rounded-control border border-border bg-canvas px-3 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="mono text-[12px] text-text-hi">{row.action}</span>
                    <span className="text-[11px] text-text-low">{fmtDate(row.at)}</span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-text-mid">{row.actor}</div>
                  {Object.keys(row.detail).length > 0 && (
                    <div className="mt-1">
                      <JsonViewer data={row.detail} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-text-low">{label}</dt>
      <dd className={mono ? 'mono text-text-mid' : 'text-text-mid'}>{value}</dd>
    </>
  );
}

function BindingsCard({ agentId }: { agentId: string }) {
  const [bindings, setBindings] = useState<AssetBindingRow[] | null>(null);
  const [assetType, setAssetType] = useState('tool');
  const [assetRef, setAssetRef] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [options, setOptions] = useState<Record<string, ComboOption[]>>({});

  const load = useCallback(() => {
    bindingsApi.list(agentId).then(setBindings).catch(() => setBindings([]));
  }, [agentId]);
  useEffect(load, [load]);

  // one fetch per registry so every asset type is pickable, not typed
  useEffect(() => {
    Promise.allSettled([
      toolsApi.list(), promptsApi.list(), knowledgeApi.list(), ragApi.list(), modelsApi.list(),
    ]).then(([tools, prompts, knowledge, rag, models]) => {
      setOptions({
        tool: tools.status === 'fulfilled'
          ? tools.value.filter((t) => t.status === 'approved' && !t.is_write_class)
              .map((t) => ({ value: t.slug, hint: t.permission_type }))
          : [],
        prompt: prompts.status === 'fulfilled'
          ? prompts.value.map((p) => ({ value: p.slug, hint: p.prompt_type })) : [],
        knowledge: knowledge.status === 'fulfilled'
          ? knowledge.value.map((k) => ({ value: k.id, label: k.name, hint: `${k.chunk_count} chunks` })) : [],
        rag: rag.status === 'fulfilled'
          ? rag.value.map((r) => ({ value: r.name, hint: `${r.source_ids.length} sources` })) : [],
        model: models.status === 'fulfilled'
          ? models.value.filter((m) => m.status === 'active').map((m) => ({ value: m.model_ref, hint: m.kind })) : [],
      });
    });
  }, []);

  const bind = async () => {
    setError(null);
    try {
      await bindingsApi.bind(agentId, { asset_type: assetType, asset_ref: assetRef.trim() });
      setAssetRef('');
      load();
    } catch (e) {
      setError(apiErrorMessage(e)); // incl. the write-class bind DENY, verbatim
    }
  };

  return (
    <Card>
      <CardHeader title="Asset bindings" subtitle="Refs resolve fresh (latest approved); deployments snapshot exact versions." />
      <div className="flex flex-col gap-2">
        {(bindings ?? []).map((b) => (
          <div key={b.id} className="flex items-center justify-between rounded-control border border-border bg-canvas px-2 py-1.5 text-[12px]">
            <span className="text-text-mid"><Badge tone="neutral">{b.asset_type}</Badge> <span className="mono">{b.asset_ref}</span></span>
            <button className="text-text-low hover:text-red-400" onClick={() => bindingsApi.unbind(agentId, b.id).then(load)}>unbind</button>
          </div>
        ))}
        {bindings !== null && bindings.length === 0 && (
          <div className="text-[12px] text-text-low">Nothing bound yet.</div>
        )}
        <div className="mt-1 flex gap-2">
          <select
            className="h-8 rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
            value={assetType}
            onChange={(e) => { setAssetType(e.target.value); setAssetRef(''); }}
          >
            {['tool', 'prompt', 'knowledge', 'rag', 'model'].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <ComboBox
            className="w-full"
            value={assetRef}
            options={options[assetType] ?? []}
            emptyHint={`no ${assetType} assets available yet`}
            onChange={setAssetRef}
          />
          <Button size="tiny" variant="subtle" disabled={!assetRef.trim()} onClick={bind}>Bind</Button>
        </div>
        {error && <div className="text-[12px] text-red-400">{error}</div>}
      </div>
    </Card>
  );
}

function TransitionPanel({ agent, onChanged }: { agent: ServerAgent; onChanged: () => void }) {
  const [to, setTo] = useState<ServerLifecycleStatus | ''>('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!to) return;
    setBusy(true);
    setError(null);
    try {
      await agentsApi.transition(agent.id, to, note.trim() || undefined);
      setTo('');
      setNote('');
      onChanged(); // re-fetch record + audit — the DENYs land there too
    } catch (e) {
      setError(apiErrorMessage(e)); // PolicyService reasons, verbatim
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="Lifecycle transition" />
      <div className="flex flex-col gap-3">
        <div className="text-[12px] text-text-mid">
          Current: <Badge tone={SERVER_LIFECYCLE_TONE[agent.lifecycle_status]}>{titleCase(agent.lifecycle_status)}</Badge>
        </div>
        <label className="block">
          <span className="mb-1 block text-[12px] text-text-mid">Transition to</span>
          <select
            className="h-9 w-full rounded-control border border-border bg-canvas px-2 text-[13px] text-text-hi outline-none focus:border-border-strong"
            value={to}
            onChange={(e) => setTo(e.target.value as ServerLifecycleStatus | '')}
          >
            <option value="">Select target status…</option>
            {SERVER_LIFECYCLE.filter((s) => s !== agent.lifecycle_status).map((s) => (
              <option key={s} value={s}>{titleCase(s)}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-[12px] text-text-mid">Note (optional)</span>
          <input
            className="h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        {error && <div className="text-[12px] text-red-400">{error}</div>}
        <Button variant="primary" icon={<ArrowRight size={14} />} disabled={busy || !to} onClick={submit}>
          {busy ? 'Applying…' : 'Apply transition'}
        </Button>
        <div className="text-[11px] text-text-low">
          Allowed transitions are enforced server-side per role; denials are audited and shown here.
        </div>
      </div>
    </Card>
  );
}
