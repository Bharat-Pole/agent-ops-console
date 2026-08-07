import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, Badge } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { type McpConnector } from '@/types';
import { fmtDateTime } from '@/utils/format';
import { Radio, Power, Activity, Loader2, Plus } from 'lucide-react';
import { cn } from '@/utils/cn';

export default function McpPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const connectors = useWorkspace((s) => s.connectors);
  const jobs = useWorkspace((s) => s.jobs);

  useEffect(() => {
    if (params.get('new') === '1') {
      params.delete('new');
      setParams(params, { replace: true });
      navigate('/mcp/new');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dot = (status: McpConnector['status']) => status === 'connected' ? 'bg-ok' : status === 'degraded' ? 'bg-warn' : 'bg-err';

  return (
    <div>
      <PageHeader
        title="MCP Connectors"
        description="Model Context Protocol servers that provide tools. An offline connector turns Pre-Flight hard blocker #4 red."
        action={<Button variant="new" icon={<Plus size={14} />} onClick={() => navigate('/mcp/new')}>Register MCP connector</Button>}
      />
      <div className="grid grid-cols-2 gap-4">
        {connectors.map((c) => {
          const checking = jobs.some((j) => j.kind === 'healthcheck' && j.entity_id === c.id && (j.status === 'processing' || j.status === 'queued'));
          return (
            <Card key={c.id}>
              <div className="mb-2 flex items-center justify-between">
                <button onClick={() => navigate(`/mcp/${c.id}`)} className="flex items-center gap-2 text-left">
                  <span className={cn('h-2.5 w-2.5 rounded-full', dot(c.status))} />
                  <span className="text-[14px] font-semibold text-text-hi hover:text-accent">{c.name}</span>
                  <Badge tone={c.status === 'connected' ? 'ok' : c.status === 'degraded' ? 'warn' : 'err'}>{c.status}</Badge>
                </button>
                <Radio size={14} className="text-text-low" />
              </div>
              <div className="space-y-1 text-[12px]">
                <div className="flex justify-between"><span className="text-text-low">transport</span><span className="text-text-hi">{c.transport}</span></div>
                <div className="flex justify-between"><span className="text-text-low">endpoint</span><span className="mono text-[11px] text-text-mid truncate max-w-[60%]">{c.endpoint}</span></div>
                <div className="flex justify-between"><span className="text-text-low">auth_mode</span><span className="text-text-hi">{c.auth_mode}</span></div>
                <div className="flex justify-between"><span className="text-text-low">tools provided</span><span className="mono text-[11px] text-text-mid">{c.tools_provided.join(', ')}</span></div>
                <div className="flex justify-between"><span className="text-text-low">last healthcheck</span><span className="text-text-mid">{fmtDateTime(c.last_healthcheck)}</span></div>
              </div>
              <div className="mt-3 flex gap-2">
                <Button variant="subtle" size="sm" icon={checking ? <Loader2 size={13} className="animate-spin-slow" /> : <Activity size={13} />} disabled={checking} onClick={() => api.healthcheck(c.id)}>Run healthcheck</Button>
                <Button variant={c.status === 'offline' ? 'primary' : 'outline'} size="sm" icon={<Power size={13} />} onClick={() => api.toggleConnectorOffline(c.id)}>{c.status === 'offline' ? 'Bring online' : 'Toggle offline'}</Button>
              </div>
              {c.status === 'offline' && <div className="mt-2 text-[11px] text-err">Offline → Pre-Flight hard blocker #4 (MCP connectors available) is now red.</div>}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
