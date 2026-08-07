import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, Badge, EmptyState } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { fmtDateTime } from '@/utils/format';
import { ArrowLeft, Power, Activity, Loader2, Plug } from 'lucide-react';

export default function McpDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const c = useWorkspace((s) => s.connectors.find((x) => x.id === id));
  const jobs = useWorkspace((s) => s.jobs);
  const tools = useWorkspace((s) => s.tools);

  if (!c) {
    return (
      <div>
        <PageHeader title="MCP connector" description="" />
        <EmptyState icon={<Plug size={26} />} title="Connector not found" message="This connector id doesn't exist." />
        <Button className="mt-3" variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/mcp')}>Back to MCP Connectors</Button>
      </div>
    );
  }

  const checking = jobs.some((j) => j.kind === 'healthcheck' && j.entity_id === c.id && (j.status === 'processing' || j.status === 'queued'));

  return (
    <div>
      <PageHeader
        title={c.name}
        description={`${c.transport} · ${c.endpoint}`}
        badges={<Badge tone={c.status === 'connected' ? 'ok' : c.status === 'degraded' ? 'warn' : 'err'}>{c.status}</Badge>}
        action={<Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate('/mcp')}>Back</Button>}
      />
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Connector</div>
          <div className="space-y-1 text-[12px]">
            <Row label="transport">{c.transport}</Row>
            <Row label="endpoint"><span className="mono text-[11px] break-all text-right">{c.endpoint}</span></Row>
            <Row label="auth_mode">{c.auth_mode}</Row>
            <Row label="last healthcheck">{fmtDateTime(c.last_healthcheck)}</Row>
          </div>
          <div className="mt-3 flex gap-2">
            <Button variant="subtle" size="sm" icon={checking ? <Loader2 size={13} className="animate-spin-slow" /> : <Activity size={13} />} disabled={checking} onClick={() => api.healthcheck(c.id)}>Run healthcheck</Button>
            <Button variant={c.status === 'offline' ? 'primary' : 'outline'} size="sm" icon={<Power size={13} />} onClick={() => api.toggleConnectorOffline(c.id)}>{c.status === 'offline' ? 'Bring online' : 'Toggle offline'}</Button>
          </div>
        </Card>
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Tools provided</div>
          {c.tools_provided.length ? c.tools_provided.map((tn) => {
            const t = tools.find((x) => x.name === tn || x.id === tn);
            return (
              <button key={tn} onClick={() => t && navigate(`/tools/${t.id}`)} className="mb-1 block text-left text-[12px]">
                <span className="mono text-accent hover:underline">{tn}</span>
                {t?.write_capable && <Badge tone="err">write</Badge>}
              </button>
            );
          }) : <span className="text-[12px] text-text-low">No tools advertised.</span>}
        </Card>
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
