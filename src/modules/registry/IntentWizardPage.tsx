// Intent capture wizard (Increment B): 6 field groups, auto-saved to the
// server draft, frozen to an immutable version on submit. All validation
// verdicts (errors, warnings, PII flags) come from the server and are shown
// verbatim — the UI is a view of policy, not the policy.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Send } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader } from '@/components/primitives';
import {
  agentsApi, apiErrorMessage, intentApi,
  type IntentPayload, type PiiFlag, type ServerAgent,
} from '@/api/client';
import { cn } from '@/utils/cn';

const STEPS = [
  { key: 'identity_purpose', label: 'Identity & Purpose' },
  { key: 'trigger_contract', label: 'Trigger & Contract' },
  { key: 'data_rules', label: 'Data & Rules' },
  { key: 'tools_interaction', label: 'Tools & Interaction' },
  { key: 'risk_governance', label: 'Risk & Governance' },
  { key: 'volume_evidence', label: 'Volume & Evidence' },
] as const;

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';
const AREA = 'min-h-[64px] w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi outline-none focus:border-border-strong';
const SELECT = 'h-9 w-full rounded-control border border-border bg-canvas px-2 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function IntentWizardPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<ServerAgent | null>(null);
  const [payload, setPayload] = useState<IntentPayload>({});
  const [step, setStep] = useState(0);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<{ version: number; warnings: string[]; pii_flags: PiiFlag[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const saveTimer = useRef<number | null>(null);
  const payloadRef = useRef(payload);
  payloadRef.current = payload;

  useEffect(() => {
    agentsApi.get(id).then(setAgent).catch(() => setAgent(null));
    intentApi.getDraft(id).then((d) => setPayload(d.payload ?? {})).catch(() => undefined);
  }, [id]);

  const save = useCallback(async () => {
    try {
      const r = await intentApi.saveDraft(id, payloadRef.current);
      setSavedAt(r.updated_at);
      setSaveError(null);
    } catch (e) {
      setSaveError(apiErrorMessage(e));
    }
  }, [id]);

  // debounced auto-save on every change
  const update = useCallback(<G extends keyof IntentPayload>(group: G, patch: Partial<NonNullable<IntentPayload[G]>>) => {
    setPayload((p) => ({ ...p, [group]: { ...(p[group] ?? {}), ...patch } }));
    setSubmitted(null);
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => void save(), 800);
  }, [save]);

  useEffect(() => () => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
  }, []);

  const submit = async () => {
    setBusy(true);
    setSubmitError(null);
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    try {
      await save(); // flush the draft first
      const r = await intentApi.submit(id);
      setSubmitted({ version: r.version, warnings: r.warnings, pii_flags: r.pii_flags });
    } catch (e) {
      setSubmitError(apiErrorMessage(e)); // server validation errors, verbatim
    } finally {
      setBusy(false);
    }
  };

  const g = <G extends keyof IntentPayload>(group: G): NonNullable<IntentPayload[G]> =>
    (payload[group] ?? {}) as NonNullable<IntentPayload[G]>;

  const toolCount = (g('tools_interaction').tools_required ?? []).length;
  const channel = g('risk_governance').deployment_channel ?? 'sandbox';

  return (
    <div>
      <PageHeader
        title={`Intent — ${agent?.name ?? '…'}`}
        description="Describe what this agent should do. Submitting freezes an immutable version for governance."
        action={
          <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate(`/agents/${id}`)}>
            Back to agent
          </Button>
        }
      />

      {/* step chips */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {STEPS.map((s, i) => (
          <button
            key={s.key}
            onClick={() => setStep(i)}
            className={cn(
              'rounded-control border px-2.5 py-1 text-[12px]',
              i === step
                ? 'border-border-strong bg-surface text-text-hi'
                : 'border-border bg-canvas text-text-mid hover:text-text-hi',
            )}
          >
            {i + 1}. {s.label}
          </button>
        ))}
        <span className="ml-auto self-center text-[11px] text-text-low">
          {saveError ? `Auto-save failed: ${saveError}` : savedAt ? `Draft saved ${new Date(savedAt).toLocaleTimeString()}` : 'Not saved yet'}
        </span>
      </div>

      <Card>
        <CardHeader title={STEPS[step].label} />
        {step === 0 && (
          <div className="flex flex-col gap-3">
            <Field label="Objective — what should this agent do? (required)">
              <textarea className={AREA} value={g('identity_purpose').objective ?? ''}
                onChange={(e) => update('identity_purpose', { objective: e.target.value })}
                placeholder="e.g. Summarize weekly network incident reports for the NOC team, with citations to the source tickets." />
            </Field>
            <Field label="Business function / domain">
              <input className={INPUT} value={g('identity_purpose').business_function ?? ''}
                onChange={(e) => update('identity_purpose', { business_function: e.target.value })} />
            </Field>
            <Field label="Target users">
              <input className={INPUT} value={g('identity_purpose').target_users ?? ''}
                onChange={(e) => update('identity_purpose', { target_users: e.target.value })} />
            </Field>
            <Field label="Success criteria">
              <textarea className={AREA} value={g('identity_purpose').success_criteria ?? ''}
                onChange={(e) => update('identity_purpose', { success_criteria: e.target.value })} />
            </Field>
          </div>
        )}

        {step === 1 && (
          <div className="flex flex-col gap-3">
            <Field label="Trigger type">
              <select className={SELECT} value={g('trigger_contract').trigger_type ?? 'user_message'}
                onChange={(e) => update('trigger_contract', { trigger_type: e.target.value })}>
                {['user_message', 'api_call', 'scheduled', 'event'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Input description">
              <textarea className={AREA} value={g('trigger_contract').input_description ?? ''}
                onChange={(e) => update('trigger_contract', { input_description: e.target.value })} />
            </Field>
            <Field label="Output description">
              <textarea className={AREA} value={g('trigger_contract').output_description ?? ''}
                onChange={(e) => update('trigger_contract', { output_description: e.target.value })} />
            </Field>
            <Field label="Output format">
              <select className={SELECT} value={g('trigger_contract').output_format ?? 'text'}
                onChange={(e) => update('trigger_contract', { output_format: e.target.value })}>
                {['text', 'structured_json', 'action_summary'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
          </div>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-3">
            <Field label="Data sources (one per line)">
              <textarea className={AREA} value={(g('data_rules').data_sources ?? []).join('\n')}
                onChange={(e) => update('data_rules', { data_sources: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })}
                placeholder={'incident_db\nnetwork_runbooks'} />
            </Field>
            <Field label="Data sensitivity">
              <select className={SELECT} value={g('data_rules').data_sensitivity ?? 'internal'}
                onChange={(e) => update('data_rules', { data_sensitivity: e.target.value })}>
                {['public', 'internal', 'confidential', 'restricted'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Business rules the agent must follow">
              <textarea className={AREA} value={g('data_rules').business_rules ?? ''}
                onChange={(e) => update('data_rules', { business_rules: e.target.value })} />
            </Field>
            <Field label="Knowledge freshness">
              <select className={SELECT} value={g('data_rules').knowledge_freshness ?? 'static'}
                onChange={(e) => update('data_rules', { knowledge_freshness: e.target.value })}>
                {['static', 'periodic', 'live'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col gap-3">
            <ToolsEditor
              tools={g('tools_interaction').tools_required ?? []}
              onChange={(tools_required) => update('tools_interaction', { tools_required })}
            />
            {toolCount > 0 && (
              <label className="flex items-center gap-2 text-[13px] text-text-mid">
                <input type="checkbox" checked={g('tools_interaction').mcp_connectors_required ?? false}
                  onChange={(e) => update('tools_interaction', { mcp_connectors_required: e.target.checked })} />
                MCP connectors required for these tools
              </label>
            )}
            <Field label="Interaction style">
              <select className={SELECT} value={g('tools_interaction').interaction_style ?? 'single_turn'}
                onChange={(e) => update('tools_interaction', { interaction_style: e.target.value })}>
                {['single_turn', 'conversational'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="External systems touched (one per line)">
              <textarea className={AREA} value={(g('tools_interaction').external_systems ?? []).join('\n')}
                onChange={(e) => update('tools_interaction', { external_systems: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })} />
            </Field>
          </div>
        )}

        {step === 4 && (
          <div className="flex flex-col gap-3">
            <Field label="Risk tier (self-assessed — the platform cross-checks this)">
              <select className={SELECT} value={g('risk_governance').risk_tier ?? ''}
                onChange={(e) => update('risk_governance', { risk_tier: e.target.value || undefined })}>
                <option value="">not set</option>
                {['low', 'medium', 'high', 'restricted'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Human approval requirement">
              <select className={SELECT} value={g('risk_governance').human_approval_requirement ?? 'none'}
                onChange={(e) => update('risk_governance', { human_approval_requirement: e.target.value })}>
                {['none', 'pre_action', 'post_action', 'continuous'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <label className="flex items-center gap-2 text-[13px] text-text-mid">
              <input type="checkbox" checked={g('risk_governance').write_actions_expected ?? false}
                onChange={(e) => update('risk_governance', { write_actions_expected: e.target.checked })} />
              Write actions expected (advisory-only is enforced in this platform phase)
            </label>
            <Field label="Compliance notes">
              <textarea className={AREA} value={g('risk_governance').compliance_notes ?? ''}
                onChange={(e) => update('risk_governance', { compliance_notes: e.target.value })} />
            </Field>
            <Field label="Deployment channel">
              <select className={SELECT} value={channel}
                onChange={(e) => update('risk_governance', { deployment_channel: e.target.value })}>
                {['sandbox', 'internal_chat', 'rest_api'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
          </div>
        )}

        {step === 5 && (
          <div className="flex flex-col gap-3">
            <Field label={`Expected volume per day${channel !== 'sandbox' ? ' (required for non-sandbox channels)' : ''}`}>
              <input className={INPUT} type="number" min={0}
                value={g('volume_evidence').expected_volume_per_day ?? ''}
                onChange={(e) => update('volume_evidence', { expected_volume_per_day: e.target.value === '' ? null : Number(e.target.value) })} />
            </Field>
            <Field label="Latency target">
              <select className={SELECT} value={g('volume_evidence').latency_target ?? 'interactive'}
                onChange={(e) => update('volume_evidence', { latency_target: e.target.value })}>
                {['interactive', 'batch'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field label="Evidence requirement">
              <select className={SELECT} value={g('volume_evidence').evidence_requirement ?? 'standard'}
                onChange={(e) => update('volume_evidence', { evidence_requirement: e.target.value })}>
                {['basic', 'standard', 'full'].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
          </div>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
          <div className="flex gap-2">
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Previous</Button>
            <Button variant="ghost" disabled={step === STEPS.length - 1} onClick={() => setStep(step + 1)}>Next</Button>
          </div>
          <Button variant="primary" icon={<Send size={14} />} disabled={busy} onClick={submit}>
            {busy ? 'Submitting…' : agent?.current_intent_version ? `Submit as v${agent.current_intent_version + 1}` : 'Submit intent'}
          </Button>
        </div>
      </Card>

      {submitError && (
        <Card className="mt-4 border-red-900/50">
          <CardHeader title="Submission blocked by validation" subtitle="Server verdict, verbatim." />
          <div className="text-[13px] text-red-400">{submitError}</div>
        </Card>
      )}

      {submitted && (
        <Card className="mt-4">
          <CardHeader
            title={`Intent v${submitted.version} submitted`}
            subtitle="Frozen as an immutable document; the draft stays editable for the next version."
            action={
              <Link to={`/agents/${id}/recommendation`}>
                <Button variant="new">Generate design recommendation</Button>
              </Link>
            }
          />
          {submitted.warnings.length > 0 && (
            <div className="mb-2">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-text-low">Warnings (non-blocking)</div>
              {submitted.warnings.map((w, i) => (
                <div key={i} className="text-[12px] text-amber-400">• {w}</div>
              ))}
            </div>
          )}
          {submitted.pii_flags.length > 0 && (
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wide text-text-low">
                PII flags (heuristic detector — flag-only, nothing was redacted)
              </div>
              {submitted.pii_flags.map((f, i) => (
                <div key={i} className="text-[12px] text-text-mid">
                  <Badge tone="warn">{f.kind}</Badge>{' '}
                  <span className="mono">{f.path}</span> — {f.count}× (e.g. {f.preview})
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] text-text-mid">{label}</span>
      {children}
    </label>
  );
}

function ToolsEditor({
  tools, onChange,
}: {
  tools: { name: string; purpose: string; system?: string }[];
  onChange: (tools: { name: string; purpose: string; system?: string }[]) => void;
}) {
  return (
    <div>
      <div className="mb-1 text-[12px] text-text-mid">
        Tools needed (described needs — the registry is populated in the Asset Studio)
      </div>
      <div className="flex flex-col gap-2">
        {tools.map((t, i) => (
          <div key={i} className="flex gap-2">
            <input className={INPUT} placeholder="tool name" value={t.name}
              onChange={(e) => onChange(tools.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <input className={INPUT} placeholder="purpose" value={t.purpose}
              onChange={(e) => onChange(tools.map((x, j) => (j === i ? { ...x, purpose: e.target.value } : x)))} />
            <Button variant="ghost" onClick={() => onChange(tools.filter((_, j) => j !== i))}>Remove</Button>
          </div>
        ))}
        <div>
          <Button variant="subtle" onClick={() => onChange([...tools, { name: '', purpose: '' }])}>Add tool need</Button>
        </div>
      </div>
    </div>
  );
}
