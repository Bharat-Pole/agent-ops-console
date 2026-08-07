import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/primitives';
import { AssetWizard, type AssetPhase } from '@/modules/assets/AssetWizard';
import { useWorkspace } from '@/kernel/store';
import { api, audit, nowIso } from '@/kernel/api';
import type { McpAuthMode, McpConnector, McpTransport } from '@/types';

const TRANSPORTS: McpTransport[] = ['sse', 'stdio', 'http'];
const AUTH_MODES: McpAuthMode[] = ['secret_manager', 'oauth', 'none'];

interface McpDraft {
  name: string;
  transport: McpTransport;
  endpoint: string;
  auth_mode: McpAuthMode;
  auth_secret_ref: string;
  tools_text: string; // comma/newline separated tool names
}

const inputCls = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring';

export default function McpWizard() {
  const navigate = useNavigate();
  const nextId = useWorkspace((s) => s.nextId);
  const upsertConnector = useWorkspace((s) => s.upsertConnector);
  const [secretNames, setSecretNames] = useState<string[]>([]);
  useEffect(() => { api.engineHealth().then((h) => setSecretNames(h.secretNames)); }, []);

  const initial: McpDraft = { name: '', transport: 'sse', endpoint: '', auth_mode: 'secret_manager', auth_secret_ref: '', tools_text: '' };

  const steps: AssetPhase<McpDraft>[] = [
    {
      key: 'identity', label: 'Identity',
      validate: (d) => (!d.name.trim() ? 'Name the connector.' : !d.endpoint.trim() ? 'Endpoint is required.' : null),
      render: ({ draft, patch }) => (
        <div className="space-y-3">
          <Field label="Name"><input className={inputCls} value={draft.name} onChange={(e) => patch({ name: e.target.value })} placeholder="e.g. gcp-ticketing" /></Field>
          <div className="grid grid-cols-[140px_1fr] gap-3">
            <Field label="Transport">
              <select className={inputCls} value={draft.transport} onChange={(e) => patch({ transport: e.target.value as McpTransport })}>
                {TRANSPORTS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Endpoint"><input className={inputCls} value={draft.endpoint} onChange={(e) => patch({ endpoint: e.target.value })} placeholder="sse://mcp.example.com/…" /></Field>
          </div>
        </div>
      ),
    },
    {
      key: 'auth', label: 'Auth',
      render: ({ draft, patch }) => (
        <div className="space-y-3">
          <Field label="Auth mode">
            <select className={inputCls} value={draft.auth_mode} onChange={(e) => patch({ auth_mode: e.target.value as McpAuthMode })}>
              {AUTH_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>
          {draft.auth_mode === 'secret_manager' && (
            <Field label="Vault secret (name)">
              <select className={inputCls} value={draft.auth_secret_ref} onChange={(e) => patch({ auth_secret_ref: e.target.value })}>
                <option value="">(none)</option>
                {secretNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </Field>
          )}
        </div>
      ),
    },
    {
      key: 'discover', label: 'Discover',
      render: ({ draft, patch }) => (
        <div className="space-y-3">
          <div className="text-[12px] text-text-mid">List the tools this connector provides (one per line). A real healthcheck runs after registration.</div>
          <Field label="Tools provided"><textarea className={inputCls} rows={4} value={draft.tools_text} onChange={(e) => patch({ tools_text: e.target.value })} placeholder={'incident_reader\nticket_updater'} /></Field>
        </div>
      ),
    },
    {
      key: 'review', label: 'Review & Register',
      render: ({ draft }) => (
        <div className="space-y-2 text-[12px]">
          <Row label="name"><span className="mono text-text-hi">{draft.name}</span></Row>
          <Row label="transport">{draft.transport}</Row>
          <Row label="endpoint"><span className="mono text-[11px] break-all text-right">{draft.endpoint}</span></Row>
          <Row label="auth_mode"><Badge tone="info">{draft.auth_mode}</Badge></Row>
          <Row label="tools">{toolList(draft.tools_text).join(', ') || '—'}</Row>
        </div>
      ),
    },
  ];

  const onRegister = (d: McpDraft) => {
    const id = `mcp-${nextId('mcp')}`;
    const c: McpConnector = {
      id, name: d.name.trim(), transport: d.transport, endpoint: d.endpoint.trim(),
      auth_mode: d.auth_mode, status: 'connected', tools_provided: toolList(d.tools_text),
      last_healthcheck: nowIso(),
    };
    upsertConnector(c);
    audit('register_connector', 'connector', id, `Registered MCP connector "${d.name}" (${d.transport}).`);
    useWorkspace.getState().pushToast('ok', `Connector "${d.name}" registered.`);
    navigate(`/mcp/${id}`);
  };

  return (
    <AssetWizard<McpDraft>
      title="Register an MCP Connector"
      description="Onboard a Model Context Protocol server and the tools it provides."
      breadcrumb={[{ label: 'MCP Connectors', to: '/mcp' }, { label: 'New' }]}
      steps={steps}
      initial={initial}
      registerLabel="Register connector"
      onRegister={onRegister}
    />
  );
}

function toolList(text: string): string[] {
  return text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block"><div className="mb-1 text-[11px] font-semibold uppercase text-text-low">{label}</div>{children}</label>;
}
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1 last:border-0"><span className="text-text-low">{label}</span><span className="text-text-hi">{children}</span></div>;
}
