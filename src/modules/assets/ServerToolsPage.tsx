// Tool Registry (server-backed, Increment C). Write-class forcing, approval
// submission, and try-out verdicts all come from the backend verbatim.
import { useCallback, useEffect, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, DataTable, EmptyState, Modal, type Column } from '@/components/primitives';
import { apiErrorMessage, mcpApi, toolsApi, type ServerConnector, type ServerTool } from '@/api/client';
import { flattenSchema, isRenderableSchema } from '@/modules/assets/schemaView';
import { fmtDate, titleCase } from '@/utils/format';
import { useCreateParam } from '@/hooks/useCreateParam';

const STATUS_TONE: Record<string, 'ok' | 'accent' | 'warn' | 'neutral' | 'muted' | 'err'> = {
  draft: 'muted', pending_approval: 'warn', approved: 'ok', rejected: 'err', deprecated: 'muted',
};

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerToolsPage() {
  const [tools, setTools] = useState<ServerTool[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  useCreateParam(setCreateOpen);   // left-nav "+ New" deep link
  const [selected, setSelected] = useState<ServerTool | null>(null);

  const load = useCallback(() => {
    toolsApi.list().then(setTools).catch((e) => setError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const columns: Column<ServerTool>[] = [
    {
      key: 'name', header: 'Tool', width: '26%', sortValue: (t) => t.name.toLowerCase(),
      render: (t) => (
        <div className="flex flex-col">
          <span className="font-medium text-text-hi">{t.name}</span>
          <span className="mono text-[10px] text-text-low">{t.slug} · v{t.version}</span>
        </div>
      ),
    },
    {
      key: 'perm', header: 'Permission', sortValue: (t) => t.permission_type,
      render: (t) => (
        <span className="flex items-center gap-1.5">
          <Badge tone={t.is_write_class ? 'err' : 'neutral'}>{t.permission_type}</Badge>
          {t.is_write_class && <span className="text-[10px] text-text-low">write-class</span>}
        </span>
      ),
    },
    { key: 'impl', header: 'Implementation', render: (t) => <span className="mono text-[11px] text-text-mid">{t.implementation.kind}</span> },
    { key: 'risk', header: 'Risk', sortValue: (t) => t.risk_level, render: (t) => <span className="text-text-mid">{titleCase(t.risk_level)}</span> },
    { key: 'status', header: 'Status', sortValue: (t) => t.status, render: (t) => <Badge tone={STATUS_TONE[t.status]}>{titleCase(t.status)}</Badge> },
    { key: 'source', header: 'Source', render: (t) => <span className="text-text-low">{t.source}</span> },
    { key: 'updated', header: 'Updated', align: 'right', sortValue: (t) => t.updated_at, render: (t) => <span className="text-text-low">{fmtDate(t.updated_at)}</span> },
  ];

  return (
    <div>
      <PageHeader
        title="Tool Registry"
        description="Declared implementations only — write-class tools require dual sign-off and cannot be bound in this platform phase."
        action={
          <div className="flex gap-2">
            <Button variant="ghost" icon={<RefreshCw size={14} />} onClick={load}>Refresh</Button>
            <Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>New Tool</Button>
          </div>
        }
      />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
      {tools === null ? (
        <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
      ) : tools.length === 0 ? (
        <EmptyState title="No tools registered" message="Create one, or discover tools from an MCP connector." action={<Button variant="primary" onClick={() => setCreateOpen(true)}>New Tool</Button>} />
      ) : (
        <DataTable columns={columns} rows={tools} rowKey={(t) => t.id} onRowClick={setSelected}
          searchText={(t) => `${t.name} ${t.slug} ${t.permission_type}`} searchPlaceholder="Search tools…" />
      )}

      <CreateToolModal open={createOpen} onClose={() => setCreateOpen(false)} onDone={() => { setCreateOpen(false); load(); }} />
      {selected && <ToolDetailModal tool={selected} onClose={() => setSelected(null)} onChanged={load} />}
    </div>
  );
}

function CreateToolModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [permission, setPermission] = useState('read');
  const [implKind, setImplKind] = useState('none');
  const [baseUrl, setBaseUrl] = useState('');
  const [headers, setHeaders] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true); setError(null);
    let parsedHeaders: Record<string, string> = {};
    if (headers.trim()) {
      try { parsedHeaders = JSON.parse(headers); }
      catch { setError('Headers must be valid JSON'); setBusy(false); return; }
    }
    try {
      await toolsApi.create({
        name, description, permission_type: permission,
        implementation: implKind === 'http_api'
          ? { kind: 'http_api', config: { base_url: baseUrl, ...(Object.keys(parsedHeaders).length ? { headers: parsedHeaders } : {}) } }
          : { kind: implKind, config: {} },
      });
      onDone();
    } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="New tool (draft)"
      footer={<div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={busy || name.trim().length < 3} onClick={submit}>{busy ? 'Creating…' : 'Create draft'}</Button></div>}>
      <div className="flex flex-col gap-3">
        <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
          <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
        <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Description</span>
          <input className={INPUT} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Permission type</span>
          <select className={INPUT} value={permission} onChange={(e) => setPermission(e.target.value)}>
            {['read', 'summarize', 'draft', 'recommend', 'validate', 'create', 'update', 'approve', 'deploy'].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <span className="mt-1 block text-[11px] text-text-low">create/update/approve/deploy are write-class: HITL + dual sign-off forced; binding disabled this phase.</span></label>
        <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Implementation</span>
          <select className={INPUT} value={implKind} onChange={(e) => setImplKind(e.target.value)}>
            {['none', 'http_api', 'builtin:web_search'].map((k) => <option key={k} value={k}>{k}</option>)}
          </select></label>
        {implKind === 'http_api' && (
          <>
            <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Base URL</span>
              <input className={INPUT} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1/resource" /></label>
            <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Static headers (JSON, optional)</span>
              <textarea className="mono min-h-[54px] w-full rounded-control border border-border bg-canvas px-2.5 py-1.5 text-[11px] text-text-hi outline-none focus:border-border-strong"
                value={headers} onChange={(e) => setHeaders(e.target.value)}
                placeholder='{"User-Agent": "MyPlatform/0.1"}' />
              <span className="mt-1 block text-[11px] text-text-low">
                Some APIs reject requests without a User-Agent. Credentials go in the Secrets vault, not here.
              </span></label>
          </>
        )}
        {error && <div className="text-[12px] text-red-400">{error}</div>}
      </div>
    </Modal>
  );
}

/** Read-only contract view. Falls back to raw JSON whenever the simple
 *  flattener cannot faithfully model the schema. */
function SchemaView({ label, schema }: { label: string; schema: Record<string, unknown> }) {
  const [raw, setRaw] = useState(false);
  const renderable = isRenderableSchema(schema);
  const fields = renderable ? flattenSchema(schema) : [];
  const isEmpty = !schema || Object.keys(schema).length === 0;

  return (
    <div className="rounded-control border border-border bg-canvas p-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide text-text-low">{label}</span>
        {!isEmpty && (
          <button className="text-[10px] text-text-low hover:text-text-hi"
            onClick={() => setRaw((r) => !r)}>
            {raw ? 'structured' : 'raw JSON'}
          </button>
        )}
      </div>

      {isEmpty ? (
        <div className="text-[11px] text-text-low">Not declared.</div>
      ) : raw || !renderable ? (
        <>
          {!renderable && (
            <div className="mb-1 text-[10px] text-amber-400">
              Contains constructs this viewer does not model — showing raw JSON.
            </div>
          )}
          <pre className="max-h-48 overflow-auto text-[10px] text-text-mid">
            {JSON.stringify(schema, null, 2)}
          </pre>
        </>
      ) : fields.length === 0 ? (
        <div className="text-[11px] text-text-low">No fields declared.</div>
      ) : (
        <table className="w-full text-[11px]">
          <tbody>
            {fields.map((f) => (
              <tr key={f.path} className="border-t border-border align-top">
                <td className="mono py-0.5 pr-2 text-text-hi">
                  {f.path}
                  {f.required && <span className="ml-1 text-red-400" title="required">*</span>}
                </td>
                <td className="mono py-0.5 pr-2 text-text-low">{f.type}</td>
                <td className="py-0.5 text-text-mid">
                  {f.description}
                  {f.enumValues && (
                    <span className="ml-1 text-text-low">one of: {f.enumValues.join(', ')}</span>
                  )}
                  {f.defaultValue !== undefined && (
                    <span className="ml-1 text-text-low">default: {JSON.stringify(f.defaultValue)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ToolDetailModal({ tool, onClose, onChanged }: { tool: ServerTool; onClose: () => void; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [tryout, setTryout] = useState<string | null>(null);
  const [connector, setConnector] = useState<ServerConnector | null>(null);

  // provenance for MCP-discovered tools, joined from the existing connectors API
  useEffect(() => {
    if (!tool.mcp_connector_id) return;
    mcpApi.list()
      .then((rows) => setConnector(rows.find((c) => c.id === tool.mcp_connector_id) ?? null))
      .catch(() => setConnector(null));
  }, [tool.mcp_connector_id]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); onChanged(); onClose(); } catch (e) { setError(apiErrorMessage(e)); }
  };

  const runTryout = async () => {
    setError(null); setTryout(null);
    try {
      const r = await toolsApi.tryout(tool.id, {});
      setTryout(`HTTP ${r.status_code} · ${r.content_type ?? '?'}\n${r.body_preview}`);
    } catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <Modal open onClose={onClose} title={`${tool.name} · v${tool.version}`} width="max-w-2xl"
      footer={<div className="flex justify-between gap-2">
        <div className="flex gap-2">
          {tool.status === 'draft' && <Button variant="primary" onClick={() => act(() => toolsApi.submit(tool.id))}>Submit for approval</Button>}
          {tool.implementation.kind === 'http_api' && <Button variant="subtle" onClick={runTryout}>Try out (GET)</Button>}
          <Button variant="ghost" onClick={() => act(() => toolsApi.newVersion(tool.id))}>New version draft</Button>
        </div>
        <Button variant="ghost" onClick={onClose}>Close</Button>
      </div>}>
      <div className="flex flex-col gap-2 text-[13px] text-text-mid">
        <div><Badge tone={STATUS_TONE[tool.status]}>{titleCase(tool.status)}</Badge>{' '}
          <Badge tone={tool.is_write_class ? 'err' : 'neutral'}>{tool.permission_type}</Badge>{' '}
          <span className="mono text-[11px]">{tool.implementation.kind}</span></div>
        <div>{tool.description || 'No description.'}</div>
        <div className="text-[12px] text-text-low">
          HITL: {tool.human_approval_required ? 'required' : 'no'} · risk {tool.risk_level} · auth {tool.auth.method}
          {tool.auth.credential_ref ? ` (secret: ${tool.auth.credential_ref})` : ''}
        </div>
        {tool.mcp_connector_id && (
          <div className="rounded-control border border-border bg-canvas px-2 py-1 text-[11px] text-text-mid">
            Discovered from MCP connector{' '}
            <span className="text-text-hi">{connector?.name ?? tool.mcp_connector_id}</span>
            {connector && (
              <>
                {' · '}
                <Badge tone={connector.health.ok === true ? 'ok'
                  : connector.health.ok === false ? 'err' : 'muted'}>
                  {connector.health.ok === true ? 'healthy'
                    : connector.health.ok === false ? 'unhealthy' : 'unchecked'}
                </Badge>
              </>
            )}
            <span className="ml-1 text-text-low">
              — remote discovery never approves a tool; governance fields above are the platform's.
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 gap-2">
          <SchemaView label="Input schema" schema={tool.input_schema} />
          <SchemaView label="Output schema" schema={tool.output_schema} />
        </div>
        {tool.is_write_class && (
          <div className="rounded-control border border-amber-900/50 bg-canvas px-3 py-2 text-[12px] text-amber-400">
            Write-class: dual sign-off (Governance + Security) required to approve; binding to agents is disabled in the advisory-only base phase.
          </div>
        )}
        {tryout && <pre className="max-h-48 overflow-auto rounded-control border border-border bg-canvas p-2 text-[11px] text-text-mid">{tryout}</pre>}
        {error && <div className="text-[12px] text-red-400">{error}</div>}
      </div>
    </Modal>
  );
}
