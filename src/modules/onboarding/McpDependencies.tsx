import { useEffect, useState } from 'react';
import { Loader2, AlertTriangle, ServerOff } from 'lucide-react';
import { Card, Badge } from '@/components/primitives';
import { api } from '@/kernel/api';
import type { AgentConnectorsResponse } from '@/kernel/services';
import type { McpStatus } from '@/types';
import { cn } from '@/utils/cn';

// The agent's MCP dependency set, resolved server-side (see backend
// services/connector_resolution.py). This is the screen that answers "which MCP
// servers does this agent actually need?" — a question the app could previously
// only imply, never state.
//
// Real backend call, so it uses a local loading boolean, not kernel/jobs.ts.
//
// Same data as ROADMAP Phase 6's MCP Gateway view, at one-agent altitude.

const dot = (status: McpStatus) =>
  status === 'connected' ? 'bg-ok' : status === 'degraded' ? 'bg-warn' : 'bg-err';

const tone = (status: McpStatus) =>
  status === 'connected' ? 'ok' : status === 'degraded' ? 'warn' : 'err';

export function McpDependencies({ agentIdStr }: { agentIdStr: string }) {
  const [data, setData] = useState<AgentConnectorsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.listAgentConnectors(agentIdStr).then((res) => {
      if (!alive) return;
      setData(res);
      setLoading(false);
    });
    return () => { alive = false; };
  }, [agentIdStr]);

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[13px] font-semibold text-text-hi">MCP dependencies</div>
        {data && (
          <span className="text-[11px] text-text-low">
            {data.connectors.length === 0
              ? 'no MCP servers required'
              : `needs ${data.connectors.length} MCP server${data.connectors.length === 1 ? '' : 's'}`}
          </span>
        )}
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-2 text-[12px] text-text-mid">
          <Loader2 size={14} className="animate-spin-slow text-accent" /> Resolving connectors…
        </div>
      )}

      {!loading && !data && (
        <div className="py-2 text-[12px] text-text-low">Could not resolve connectors — is the backend running?</div>
      )}

      {!loading && data && (
        <div className="space-y-1">
          {data.connectors.map((c) => (
            <div key={c.id} className="flex items-center gap-2 rounded border border-border px-2 py-1.5 text-[12px]">
              <span className={cn('h-2 w-2 shrink-0 rounded-full', dot(c.status))} />
              <span className="flex-1 text-text-hi">{c.name}</span>
              <span className="mono text-[11px] text-text-low">{c.tools.join(', ')}</span>
              <Badge tone={tone(c.status)}>{c.status}</Badge>
            </div>
          ))}

          {/* A tool with connector_id = NULL is local — it needs no MCP server
              at all. Never rendered as a nameless connector. */}
          {data.local_tools.length > 0 && (
            <div className="flex items-center gap-2 rounded border border-dashed border-border px-2 py-1.5 text-[12px] text-text-low">
              <span className="flex-1">
                {data.local_tools.length} local tool{data.local_tools.length === 1 ? '' : 's'} need no connector
              </span>
              <span className="mono text-[11px]">{data.local_tools.join(', ')}</span>
            </div>
          )}

          {data.connectors.length === 0 && data.local_tools.length === 0 && (
            <div className="py-1 text-[12px] text-text-low">No tools bound — this agent reaches no external system.</div>
          )}

          {data.unknown_tools.length > 0 && (
            <div className="mt-1 flex items-start gap-1.5 text-[11px] text-warn">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              <span>Bound but no longer in the catalog: <span className="mono">{data.unknown_tools.join(', ')}</span></span>
            </div>
          )}

          {/* Health warns here and at bind time; it only *blocks* at Pre-Flight,
              which is now scoped to exactly these connectors. */}
          {data.offline.length > 0 && (
            <div className="mt-1 flex items-start gap-1.5 text-[11px] text-err">
              <ServerOff size={12} className="mt-0.5 shrink-0" />
              <span>{data.offline.join(', ')} offline — Pre-Flight hard blocker #4 is red for this agent.</span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
