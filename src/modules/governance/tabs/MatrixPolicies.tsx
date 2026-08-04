import { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Card, Button, Badge } from '@/components/primitives';
import { GovernanceMatrix, AssetRefLink } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, type CapabilityTier, type RiskTier } from '@/types';
import { PATH_DEFS, GOVERNANCE_MATRIX, FAST_PATH_WARN_DAYS } from '@/kernel/constants';
import { daysUntil, fmtDate } from '@/utils/format';
import { RotateCcw, AlertTriangle } from 'lucide-react';
import { cn } from '@/utils/cn';

export function MatrixPolicies() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const agents = useWorkspace((s) => s.agents);
  const persona = useWorkspace((s) => s.ui.persona);
  const canRecert = persona === 'governance_officer';

  const [cell, setCell] = useState<{ tier: CapabilityTier; risk: RiskTier } | null>(() => {
    const t = params.get('tier') as CapabilityTier | null;
    const r = params.get('risk') as RiskTier | null;
    return t && r ? { tier: t, risk: r } : null;
  });

  const counts: Record<string, number> = {};
  for (const a of agents) {
    const k = `${a.capability_tier}:${a.config.lifecycle.risk_tier.value}`;
    counts[k] = (counts[k] ?? 0) + 1;
  }

  const cellAgents = cell ? agents.filter((a) => a.capability_tier === cell.tier && a.config.lifecycle.risk_tier.value === cell.risk) : [];

  // Unique policy assets referenced across agents.
  const policyMap = new Map<string, number>();
  for (const a of agents) {
    const refs = [...a.config.governance.policy_controls.value, a.config.prompt.citation_rules.value].filter(Boolean) as string[];
    for (const r of refs) if (r.startsWith('policies://')) policyMap.set(r, (policyMap.get(r) ?? 0) + 1);
  }

  const fastAgents = agents.filter((a) => a.fast_path_expiry_date);

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="space-y-4">
        <Card>
          <div className="mb-3 text-[13px] font-semibold text-text-hi">Governance matrix — click a cell</div>
          <GovernanceMatrix activeTier={cell?.tier} activeRisk={cell?.risk} counts={counts} onCell={(tier, risk) => setCell({ tier, risk })} />
          {cell && (
            <div className="mt-3">
              <div className="text-[12px] text-text-mid">
                <span className="capitalize">{cell.tier}</span> × <span className="capitalize">{cell.risk}</span> →{' '}
                <Badge tone="accent">{PATH_DEFS[GOVERNANCE_MATRIX[cell.tier][cell.risk]].label}</Badge>
              </div>
              <div className="mt-2 space-y-1">
                {cellAgents.length ? cellAgents.map((a) => (
                  <button key={agentId(a)} onClick={() => navigate(`/agents/${agentId(a)}`)} className="block w-full rounded border border-border bg-raised/40 px-2 py-1 text-left text-[12px] text-text-hi hover:border-border-strong">
                    {a.config.identity.agent_name.value}
                  </button>
                )) : <div className="text-[12px] text-text-low">No agents in this cell.</div>}
              </div>
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Path legend</div>
          <div className="space-y-1.5">
            {(['fast', 'standard', 'deep', 'critical'] as const).map((p) => (
              <div key={p} className="text-[12px]">
                <Badge tone={p === 'fast' ? 'ok' : p === 'standard' ? 'accent' : p === 'deep' ? 'warn' : 'err'}>{PATH_DEFS[p].label}</Badge>
                <span className="ml-2 text-text-low">{PATH_DEFS[p].desc}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Policy assets</div>
          <div className="space-y-1">
            {[...policyMap.entries()].map(([ref, n]) => (
              <div key={ref} className="flex items-center justify-between">
                <AssetRefLink refUri={ref} />
                <span className="text-[11px] text-text-low">{n} agent(s)</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="mb-2 text-[13px] font-semibold text-text-hi">Fast-path expiry</div>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase text-text-low">
                <th className="py-1.5">Agent</th><th className="py-1.5">Expires</th><th className="py-1.5 text-right">In</th><th></th>
              </tr>
            </thead>
            <tbody>
              {fastAgents.map((a) => {
                const d = daysUntil(a.fast_path_expiry_date);
                const near = d !== null && d <= FAST_PATH_WARN_DAYS;
                return (
                  <tr key={agentId(a)} className="border-b border-border/50 last:border-0">
                    <td className="py-1.5 text-text-hi">{a.config.identity.agent_name.value}</td>
                    <td className="py-1.5 text-text-mid">{fmtDate(a.fast_path_expiry_date)}</td>
                    <td className={cn('py-1.5 text-right', near ? 'text-warn font-medium' : 'text-text-mid')}>
                      {near && <AlertTriangle size={11} className="mr-1 inline" />}{d}d
                    </td>
                    <td className="py-1.5 text-right">
                      <Button variant="subtle" size="tiny" icon={<RotateCcw size={11} />} disabled={!canRecert} onClick={() => api.recertify(agentId(a))} title={canRecert ? '' : 'Governance Officer only'}>Re-certify</Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
