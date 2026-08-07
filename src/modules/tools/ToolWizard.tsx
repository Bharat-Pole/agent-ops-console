import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button } from '@/components/primitives';
import { AssetWizard, type AssetPhase, type AssetPhaseProps } from '@/modules/assets/AssetWizard';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { audit } from '@/kernel/api';
import type { HttpMethod, HttpToolConfig, ToolAsset, ToolPermission } from '@/types';
import { Ban, Globe, Play, Loader2 } from 'lucide-react';

const PERMISSIONS: ToolPermission[] = ['read', 'summarize', 'draft', 'recommend', 'validate'];
const METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];

interface ToolDraft {
  name: string;
  description: string;
  category: string;
  permission: ToolPermission;
  kind: 'catalog' | 'http_api';
  // declared implementation for catalog tools (no name-guessing):
  // 'web_search' = live web search; 'none' = not connected (honest stub)
  capability: 'web_search' | 'none';
  method: HttpMethod;
  url_template: string;
  auth_secret_ref: string;
  auth_header: string;
  // simple key/val editing as text lines "k=v"
  headers_text: string;
}

const isWrite = (d: ToolDraft) => d.kind === 'http_api' && d.method !== 'GET';

function parseKv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const i = line.indexOf('=');
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

export default function ToolWizard() {
  const navigate = useNavigate();
  const nextId = useWorkspace((s) => s.nextId);
  const upsertTool = useWorkspace((s) => s.upsertTool);
  const [secretNames, setSecretNames] = useState<string[]>([]);

  useEffect(() => { api.engineHealth().then((h) => setSecretNames(h.secretNames)); }, []);

  const initial: ToolDraft = {
    name: '', description: '', category: 'general', permission: 'read',
    kind: 'catalog', capability: 'none', method: 'GET', url_template: '', auth_secret_ref: '',
    auth_header: 'Authorization: Bearer {secret}', headers_text: '',
  };

  const steps: AssetPhase<ToolDraft>[] = [
    {
      key: 'identity', label: 'Identity',
      validate: (d) => (!d.name.trim() ? 'Give the tool a name.' : null),
      render: ({ draft, patch }) => <IdentityPhase draft={draft} patch={patch} />,
    },
    {
      key: 'interface', label: 'Interface',
      validate: (d) => (d.kind === 'http_api' && !d.url_template.trim() ? 'HTTP tools need a URL template.' : null),
      render: (p) => <InterfacePhase {...p} secretNames={secretNames} />,
    },
    {
      key: 'test', label: 'Test',
      render: (p) => <TestPhase {...p} />,
    },
    {
      key: 'review', label: 'Review & Register',
      render: ({ draft }) => <ReviewPhase draft={draft} />,
    },
  ];

  const onRegister = (d: ToolDraft) => {
    const id = `tool-${nextId('t')}`;
    const http: HttpToolConfig | undefined = d.kind === 'http_api' ? {
      method: d.method,
      url_template: d.url_template.trim(),
      query_params: {},
      headers: parseKv(d.headers_text),
      body_template: null,
      auth_secret_ref: d.auth_secret_ref || null,
      auth_header: d.auth_header || 'Authorization: Bearer {secret}',
    } : undefined;
    const tool: ToolAsset = {
      id, version: 'v1', name: d.name.trim(), description: d.description.trim(),
      category: d.category.trim() || 'general', permission_ceiling: d.permission,
      write_capable: isWrite(d), connector_id: null,
      schema: { inputs: { query: 'string' }, outputs: { result: 'string' } },
      status: 'available', used_by: [], kind: d.kind, http,
      // declared implementation — the engine binds exactly this, no name-guessing
      capability: d.kind === 'http_api' ? 'http_api' : d.capability,
    };
    upsertTool(tool);
    audit('register_tool', 'tool', id, `Registered ${d.kind} tool "${d.name}"${http ? ` (${http.method})` : ''}.`);
    useWorkspace.getState().pushToast('ok', `Tool "${d.name}" registered.`);
    navigate(`/tools/${id}`);
  };

  return (
    <AssetWizard<ToolDraft>
      title="Register a Tool"
      description="Onboard a tool the console can bind to agents. HTTP tools run for real at run time."
      breadcrumb={[{ label: 'Tools', to: '/tools' }, { label: 'New' }]}
      steps={steps}
      initial={initial}
      registerLabel="Register tool"
      onRegister={onRegister}
    />
  );
}

const inputCls = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring';

function IdentityPhase({ draft, patch }: { draft: ToolDraft; patch: (u: Partial<ToolDraft>) => void }) {
  return (
    <div className="space-y-3">
      <Field label="Name"><input className={inputCls} value={draft.name} onChange={(e) => patch({ name: e.target.value })} placeholder="e.g. weather_lookup" /></Field>
      <Field label="Description"><input className={inputCls} value={draft.description} onChange={(e) => patch({ description: e.target.value })} placeholder="What does this tool do?" /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Category"><input className={inputCls} value={draft.category} onChange={(e) => patch({ category: e.target.value })} /></Field>
        <Field label="Permission ceiling (advisory)">
          <select className={inputCls} value={draft.permission} onChange={(e) => patch({ permission: e.target.value as ToolPermission })}>
            {PERMISSIONS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
      </div>
    </div>
  );
}

function InterfacePhase({ draft, patch, secretNames }: AssetPhaseProps<ToolDraft> & { secretNames: string[] }) {
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {(['catalog', 'http_api'] as const).map((k) => (
          <button key={k} onClick={() => patch({ kind: k })} className={`rounded-control border px-3 py-2 text-left ${draft.kind === k ? 'border-accent bg-accent/10' : 'border-border hover:border-border-strong'}`}>
            <div className={`text-[12px] font-semibold ${draft.kind === k ? 'text-accent' : 'text-text-hi'}`}>{k === 'catalog' ? 'Built-in capability' : 'HTTP API (real call)'}</div>
            <div className="text-[10px] text-text-low">{k === 'catalog' ? 'Pick a real implementation below (or none)' : 'Engine calls the endpoint live'}</div>
          </button>
        ))}
      </div>
      {draft.kind === 'catalog' && (
        <Field label="Implementation (declared — the engine binds exactly this)">
          <div className="flex gap-2">
            {([
              { id: 'web_search' as const, label: 'Web search (live)', blurb: 'Real web search at run time — keyless. No name-guessing.' },
              { id: 'none' as const, label: 'Not connected', blurb: 'No real integration — the agent will say so honestly.' },
            ]).map((c) => (
              <button key={c.id} onClick={() => patch({ capability: c.id })} className={`rounded-control border px-3 py-2 text-left ${draft.capability === c.id ? 'border-accent bg-accent/10' : 'border-border hover:border-border-strong'}`}>
                <div className={`text-[12px] font-semibold ${draft.capability === c.id ? 'text-accent' : 'text-text-hi'}`}>{c.label}</div>
                <div className="text-[10px] text-text-low">{c.blurb}</div>
              </button>
            ))}
          </div>
        </Field>
      )}

      {draft.kind === 'http_api' && (
        <div className="space-y-3 rounded-control border border-border bg-raised/30 p-3">
          <div className="grid grid-cols-[120px_1fr] gap-3">
            <Field label="Method">
              <select className={inputCls} value={draft.method} onChange={(e) => patch({ method: e.target.value as HttpMethod })}>
                {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="URL template ({param} filled from the query)">
              <input className={inputCls} value={draft.url_template} onChange={(e) => patch({ url_template: e.target.value })} placeholder="https://api.example.com/v1/search?q={query}" />
            </Field>
          </div>
          <Field label="Headers (one k=v per line; no secret values)">
            <textarea className={inputCls} rows={2} value={draft.headers_text} onChange={(e) => patch({ headers_text: e.target.value })} placeholder="Accept=application/json" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Auth secret (vault name)">
              <select className={inputCls} value={draft.auth_secret_ref} onChange={(e) => patch({ auth_secret_ref: e.target.value })}>
                <option value="">(none)</option>
                {secretNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </Field>
            <Field label="Auth header ({secret} injected engine-side)">
              <input className={inputCls} value={draft.auth_header} onChange={(e) => patch({ auth_header: e.target.value })} />
            </Field>
          </div>
          {isWrite(draft) ? (
            <div className="rounded-control border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err"><Ban size={12} className="mr-1 inline" /> {draft.method} is a mutating method → write-capable. This tool will be catalogued but <b>never bindable</b> (advisory-only).</div>
          ) : (
            <div className="rounded-control border border-ok/30 bg-ok/10 px-3 py-2 text-[12px] text-ok">GET → read-only → advisory-bindable and testable live.</div>
          )}
          {secretNames.length === 0 && <div className="text-[11px] text-warn">No vault secrets found — add one on the API Keys page if this endpoint needs auth.</div>}
        </div>
      )}
    </div>
  );
}

function TestPhase({ draft }: AssetPhaseProps<ToolDraft>) {
  const [query, setQuery] = useState('');
  const [trying, setTrying] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; status?: number; text?: string; error?: string } | null>(null);

  if (draft.kind !== 'http_api') {
    return <div className="text-[12px] text-text-mid">Catalog tool — nothing to call live. The Playground renders a simulated result from its fixtures.</div>;
  }
  if (isWrite(draft)) {
    return <div className="rounded-control border border-warn/40 bg-warn/10 px-3 py-2 text-[12px] text-warn">Mutating method — advisory-block. Cannot be tested live or bound to an agent.</div>;
  }

  const tryIt = async () => {
    setTrying(true);
    const def = {
      name: draft.name, kind: 'http_api',
      http: { method: draft.method, url_template: draft.url_template, query_params: {}, headers: parseKv(draft.headers_text), auth_header: draft.auth_header },
      auth_secret_ref: draft.auth_secret_ref || null,
    };
    const r = await api.tryTool(def, query);
    setTrying(false);
    setResult(r ?? { ok: false, error: 'Engine offline.' });
  };

  return (
    <div className="space-y-2">
      <div className="text-[12px] text-text-mid">Live GET against your endpoint (auth injected engine-side from the vault).</div>
      <div className="flex gap-2">
        <input className={inputCls} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && tryIt()} placeholder="query → fills {placeholders}" />
        <Button variant="primary" size="sm" icon={trying ? <Loader2 size={13} className="animate-spin-slow" /> : <Play size={13} />} onClick={tryIt} disabled={trying}>Run</Button>
      </div>
      {result && (
        <pre className="max-h-56 overflow-auto rounded-control border border-border bg-canvas p-2 mono text-[11px] text-text-mid whitespace-pre-wrap">
          {result.ok ? `status ${result.status}\n\n${result.text}` : `error: ${result.error}`}
        </pre>
      )}
    </div>
  );
}

function ReviewPhase({ draft }: { draft: ToolDraft }) {
  return (
    <div className="space-y-2 text-[12px]">
      <Row label="name"><span className="mono text-text-hi">{draft.name}</span></Row>
      <Row label="kind">{draft.kind === 'http_api' ? <Badge tone="accent"><Globe size={10} /> http {draft.method}</Badge> : <Badge tone="muted">catalog</Badge>}</Row>
      <Row label="permission"><Badge tone="info">{draft.permission}</Badge></Row>
      {draft.kind === 'http_api' && <Row label="url"><span className="mono text-[11px] break-all text-right">{draft.url_template}</span></Row>}
      {draft.kind === 'http_api' && draft.auth_secret_ref && <Row label="auth secret"><span className="mono text-[11px]">{draft.auth_secret_ref}</span></Row>}
      <Row label="write-capable">{isWrite(draft) ? <Badge tone="err"><Ban size={10} /> yes — advisory-block</Badge> : <span className="text-ok">no (bindable)</span>}</Row>
      {isWrite(draft) && <div className="rounded-control border border-err/40 bg-err/10 px-3 py-2 text-err">This tool cannot be bound to agents (mutating HTTP method). It is catalogued for visibility only.</div>}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">{label}</div>{children}</label>;
}
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1 last:border-0"><span className="text-text-low">{label}</span><span className="text-text-hi">{children}</span></div>;
}
