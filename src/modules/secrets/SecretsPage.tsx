import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Badge } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { agentId } from '@/types';
import { KeyRound } from 'lucide-react';
import { SecretsInner } from './SecretsInner';

export default function SecretsPage() {
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const tools = useWorkspace((s) => s.tools);
  const [names, setNames] = useState<string[]>([]);

  // Build: secret name → [{agent, use}] by scanning agents' tooling.secret_refs
  // (key 'model' = LLM key; other keys = per-tool) plus each bound HTTP tool's
  // auth_secret_ref. Names only — never values.
  const refMap = new Map<string, { agent: string; agentId: string; use: string }[]>();
  const add = (secret: string, agentName: string, aid: string, use: string) => {
    if (!secret) return;
    const arr = refMap.get(secret) ?? [];
    arr.push({ agent: agentName, agentId: aid, use });
    refMap.set(secret, arr);
  };
  for (const a of agents) {
    const aid = agentId(a);
    const nm = a.config.identity.agent_name.value;
    const refs = (a.config.tooling.secret_refs?.value ?? {}) as Record<string, string>;
    for (const [k, secret] of Object.entries(refs)) add(secret, nm, aid, k === 'model' ? 'model key' : `tool: ${k}`);
    // bound HTTP tools with their own auth secret
    for (const ref of a.config.tooling.bound_tools.value) {
      const id = ref.replace('tools://', '').split('@')[0];
      const t = tools.find((x) => x.id === id || x.name === id);
      if (t?.http?.auth_secret_ref) add(t.http.auth_secret_ref, nm, aid, `tool auth: ${t.name}`);
    }
  }

  return (
    <div>
      <PageHeader
        title="API Keys"
        description="The engine-side secrets vault. Manage named secrets and see which agents/tools reference each one. Values are stored engine-side and never shown here."
        badges={<Badge tone="ok"><KeyRound size={10} /> {names.length} stored</Badge>}
      />
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Vault</div>
          <SecretsInner onChanged={setNames} />
        </Card>
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">References</div>
          <div className="text-[12px] text-text-mid mb-2">Who uses each secret (deleting a referenced secret will break those runs).</div>
          {names.length === 0 ? (
            <div className="text-[12px] text-text-low">No secrets stored.</div>
          ) : (
            <div className="space-y-2">
              {names.map((n) => {
                const refs = refMap.get(n) ?? [];
                return (
                  <div key={n} className="rounded-control border border-border bg-raised/30 p-2.5">
                    <div className="mb-1 flex items-center gap-2">
                      <span className="mono text-[12px] text-text-hi">{n}</span>
                      <Badge tone={refs.length ? 'accent' : 'muted'}>{refs.length} ref{refs.length === 1 ? '' : 's'}</Badge>
                    </div>
                    {refs.length === 0 ? (
                      <div className="text-[11px] text-text-low">Unreferenced — safe to delete.</div>
                    ) : (
                      refs.map((r, i) => (
                        <button key={i} onClick={() => navigate(`/agents/${r.agentId}`)} className="block text-left text-[11px] text-accent hover:underline">
                          {r.agent} <span className="text-text-low">· {r.use}</span>
                        </button>
                      ))
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
