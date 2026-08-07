import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, Badge, JsonViewer, EmptyState } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId } from '@/types';
import { ArrowLeft, Ban, Globe, Play, Loader2, Wrench } from 'lucide-react';

export default function ToolDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const tool = useWorkspace((s) => s.tools.find((t) => t.id === id));
  const agents = useWorkspace((s) => s.agents);

  const [query, setQuery] = useState('');
  const [trying, setTrying] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; status?: number; text?: string; error?: string } | null>(null);

  if (!tool) {
    return (
      <div>
        <PageHeader title="Tool" description="" />
        <EmptyState icon={<Wrench size={26} />} title="Tool not found" message="This tool id doesn't exist." />
        <Button className="mt-3" variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/tools')}>Back to Tools</Button>
      </div>
    );
  }

  const isHttpGet = tool.kind === 'http_api' && tool.http?.method === 'GET';

  const tryIt = async () => {
    if (!tool.http) return;
    setTrying(true);
    const def = {
      name: tool.name,
      kind: tool.kind,
      http: {
        method: tool.http.method,
        url_template: tool.http.url_template,
        query_params: tool.http.query_params ?? {},
        headers: tool.http.headers ?? {},
        auth_header: tool.http.auth_header ?? 'Authorization: Bearer {secret}',
      },
      auth_secret_ref: tool.http.auth_secret_ref ?? null,
    };
    const r = await api.tryTool(def, query);
    setTrying(false);
    setResult(r ?? { ok: false, error: 'Engine offline.' });
  };

  return (
    <div>
      <PageHeader
        title={tool.name}
        description={tool.description}
        badges={tool.kind === 'http_api' ? <Badge tone="accent"><Globe size={10} /> http {tool.http?.method}</Badge> : <Badge tone="muted">catalog</Badge>}
        action={<Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/tools')}>Back</Button>}
      />

      {tool.write_capable && (
        <div className="mb-4 rounded-card border border-err/40 bg-err/10 px-3 py-2 text-[12px] text-err">
          <Ban size={12} className="mr-1 inline" /> Write-capable — advisory-block. This tool can never be bound to an agent{tool.http ? ' (mutating HTTP method).' : '.'}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Definition</div>
          <div className="space-y-1 text-[12px]">
            <Row label="category">{tool.category}</Row>
            <Row label="permission ceiling"><Badge tone="info">{tool.permission_ceiling}</Badge></Row>
            <Row label="version"><span className="mono">{tool.version}</span></Row>
            <Row label="connector"><span className="mono text-[11px]">{tool.connector_id ?? '—'}</span></Row>
          </div>
          <div className="mt-3 mb-1 text-[12px] font-semibold text-text-hi">Schema</div>
          <JsonViewer data={tool.schema} maxHeight={160} />
        </Card>

        {tool.kind === 'http_api' && tool.http ? (
          <Card>
            <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-text-hi"><Globe size={14} /> HTTP endpoint</div>
            <div className="space-y-1 text-[12px]">
              <Row label="method"><span className="mono">{tool.http.method}</span></Row>
              <Row label="url"><span className="mono text-[11px] break-all text-right">{tool.http.url_template}</span></Row>
              <Row label="auth secret">{tool.http.auth_secret_ref ? <span className="mono text-[11px]">{tool.http.auth_secret_ref}</span> : <span className="text-text-low">none</span>}</Row>
            </div>
            {isHttpGet ? (
              <div className="mt-3">
                <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Try it (live GET)</div>
                <div className="flex gap-2">
                  <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && tryIt()} placeholder="query → fills {placeholders}" className="flex-1 rounded-control border border-border bg-canvas px-2.5 py-1.5 text-[12px] text-text-hi placeholder:text-text-low focus-ring" />
                  <Button variant="primary" size="sm" icon={trying ? <Loader2 size={13} className="animate-spin-slow" /> : <Play size={13} />} onClick={tryIt} disabled={trying}>Run</Button>
                </div>
                {result && (
                  <pre className="mt-2 max-h-56 overflow-auto rounded-control border border-border bg-canvas p-2 mono text-[11px] text-text-mid whitespace-pre-wrap">
                    {result.ok ? `status ${result.status}\n\n${result.text}` : `error: ${result.error}`}
                  </pre>
                )}
              </div>
            ) : (
              <div className="mt-3 rounded-control border border-warn/40 bg-warn/10 px-2.5 py-1.5 text-[11px] text-warn">
                Mutating method — advisory-block. Cannot be bound or tested live.
              </div>
            )}
          </Card>
        ) : (
          <Card>
            <div className="mb-2 text-[13px] font-semibold text-text-hi">Bound agents</div>
            {tool.used_by.length ? tool.used_by.map((aid) => {
              const a = agents.find((x) => agentId(x) === aid);
              return <button key={aid} onClick={() => navigate(`/agents/${aid}`)} className="block text-left text-[12px] text-accent hover:underline">{a?.config.identity.agent_name.value ?? aid}</button>;
            }) : <span className="text-[12px] text-text-low">Not bound to any agent.</span>}
          </Card>
        )}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/50 py-1 last:border-0">
      <span className="text-text-low">{label}</span>
      <span className="text-text-hi">{children}</span>
    </div>
  );
}
