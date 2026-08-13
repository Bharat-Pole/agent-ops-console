// MCP Connectors (server-backed). Discovery creates DRAFT tool entries only;
// diffs (new / changed / vanished) are the server's report, shown verbatim.
import { useCallback, useEffect, useState } from 'react';
import { Plus, RefreshCw, Radar } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, EmptyState, Modal } from '@/components/primitives';
import { apiErrorMessage, mcpApi, type ServerConnector } from '@/api/client';
import { fmtDate } from '@/utils/format';
import { useCreateParam } from '@/hooks/useCreateParam';

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerMcpPage() {
  const [connectors, setConnectors] = useState<ServerConnector[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  useCreateParam(setCreateOpen);   // left-nav "+ New" deep link
  const [report, setReport] = useState<{ name: string; text: string } | null>(null);

  const load = useCallback(() => {
    mcpApi.list().then(setConnectors).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const discover = async (c: ServerConnector) => {
    setError(null); setReport(null);
    try {
      const r = await mcpApi.discover(c.id);
      setReport({
        name: c.name,
        text: `${r.created_drafts.length} new draft tools · ${r.new_version_drafts.length} changed (new draft versions) · `
          + `${r.unchanged.length} unchanged · vanished: ${r.vanished.length ? r.vanished.join(', ') : 'none'}`,
      });
      load();
    } catch (e) { setError(apiErrorMessage(e)); }
  };

  const health = async (c: ServerConnector) => {
    setError(null);
    try { await mcpApi.health(c.id); load(); } catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <div>
      <PageHeader
        title="MCP Connectors"
        description="Discovery lists a server's tools into DRAFT registry entries — governance fields are never taken from the remote server."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>Register connector</Button>}
      />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
      {report && (
        <Card className="mb-3"><div className="text-[13px] text-text-mid"><b>{report.name}</b>: {report.text}</div></Card>
      )}
      {connectors === null ? (
        <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
      ) : connectors.length === 0 ? (
        <EmptyState title="No connectors registered" message="Register an MCP server endpoint to discover its tools." />
      ) : (
        <div className="flex flex-col gap-3">
          {connectors.map((c) => (
            <Card key={c.id}>
              <CardHeader
                title={<span className="flex items-center gap-2">{c.name}
                  <Badge tone={c.health.ok === true ? 'ok' : c.health.ok === false ? 'err' : 'muted'}>
                    {c.health.ok === true ? 'healthy' : c.health.ok === false ? 'unhealthy' : 'unchecked'}
                  </Badge>
                  {/* connector status is separate from health: a disabled connector
                      is skipped regardless of how healthy its last probe was */}
                  {c.status !== 'active' && <Badge tone="muted">{c.status}</Badge>}
                </span>}
                subtitle={<span className="mono text-[11px]">{c.endpoint} · {c.transport}</span>}
                action={<div className="flex gap-2">
                  <Button size="tiny" variant="subtle" icon={<Radar size={12} />} onClick={() => discover(c)}>Discover tools</Button>
                  <Button size="tiny" variant="ghost" icon={<RefreshCw size={12} />} onClick={() => health(c)}>Health</Button>
                </div>}
              />
              <div className="text-[12px] text-text-low">
                {c.health.last_checked ? `Last checked ${fmtDate(c.health.last_checked)} — ${c.health.note ?? ''}` : 'Never checked.'}
                {c.health.consecutive_failures > 0 && ` · ${c.health.consecutive_failures} consecutive failures`}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Register MCP connector"
        footer={null}>
        <RegisterForm onDone={() => { setCreateOpen(false); load(); }} />
      </Modal>
    </div>
  );
}

function RegisterForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [transport, setTransport] = useState('streamable_http');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true); setError(null);
    try { await mcpApi.create({ name, endpoint, transport }); onDone(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
        <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Endpoint URL</span>
        <input className={INPUT} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://mcp.example.com/mcp" />
        <span className="mt-1 block text-[11px] text-text-low">Private/loopback hosts are rejected unless allowlisted (SSRF guard).</span></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Transport</span>
        <select className={INPUT} value={transport} onChange={(e) => setTransport(e.target.value)}>
          <option value="streamable_http">streamable_http</option><option value="sse">sse</option>
        </select></label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end"><Button variant="primary" disabled={busy || !name || !endpoint} onClick={submit}>{busy ? 'Registering…' : 'Register'}</Button></div>
    </div>
  );
}
