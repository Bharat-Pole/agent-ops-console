import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Badge, EmptyState, TierBadge, Button } from '@/components/primitives';
import { AssetRefLink } from '@/components/domain';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive } from '@/types';
import { deriveWorkflowSteps, type WorkflowStep } from '@/kernel/workflow';
import {
  LogIn,
  Database,
  Table2,
  FileText,
  Cpu,
  Wrench,
  Network,
  Share2,
  UserCheck,
  ShieldCheck,
  ClipboardCheck,
  AlignLeft,
  Rocket,
  MessagesSquare,
} from 'lucide-react';
import { cn } from '@/utils/cn';

const STEP_ICON: Record<WorkflowStep['kind'], typeof LogIn> = {
  intake: LogIn,
  rag: Database,
  structured_query: Table2,
  prompt: FileText,
  llm: Cpu,
  tool_call: Wrench,
  orchestration: Network,
  a2a: Share2,
  human_approval: UserCheck,
  guardrail: ShieldCheck,
  evaluation: ClipboardCheck,
  output_format: AlignLeft,
  deployment: Rocket,
};

export default function BuilderPage() {
  const { agentId: paramId } = useParams();
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const selected = agents.find((a) => agentId(a) === paramId) ?? null;

  return (
    <div>
      <PageHeader
        title="Workflow & Agent Builder"
        description="Every agent's request pipeline, derived from its own config — not a separate diagram to keep in sync. Step order is fixed runtime semantics; toggle the flags a step depends on and the Configuration tab, Playground, and this view all move together."
      />
      <div className="grid grid-cols-[220px_1fr] gap-4" style={{ minHeight: 560 }}>
        <Card pad={false} className="overflow-hidden">
          <div className="border-b border-border px-3 py-2 text-[12px] font-semibold text-text-hi">Agents</div>
          <div className="max-h-[620px] overflow-auto p-2">
            {agents.map((a) => {
              const live = isLive(a);
              const active = agentId(a) === paramId;
              return (
                <button
                  key={agentId(a)}
                  onClick={() => navigate(`/builder/${agentId(a)}`)}
                  className={cn('mb-1 w-full rounded-control border px-2.5 py-2 text-left', active ? 'border-accent bg-accent/10' : 'border-transparent hover:bg-raised')}
                >
                  <div className="flex items-center gap-1.5">
                    <span className={cn('h-2 w-2 rounded-full', live ? 'bg-ok' : 'bg-border-strong')} />
                    <span className="flex-1 truncate text-[12px] text-text-hi">{a.config.identity.agent_name.value}</span>
                  </div>
                  <div className="mt-0.5"><TierBadge tier={a.capability_tier} /></div>
                </button>
              );
            })}
          </div>
        </Card>

        {!selected ? (
          <Card className="flex items-center justify-center">
            <EmptyState icon={<Network size={26} />} title="Pick an agent" message="Choose an agent to see its request pipeline as a sequence of steps." />
          </Card>
        ) : (
          <Pipeline agentIdStr={agentId(selected)} />
        )}
      </div>
    </div>
  );
}

function Pipeline({ agentIdStr }: { agentIdStr: string }) {
  const navigate = useNavigate();
  const agent = useWorkspace((s) => s.agents.find((a) => agentId(a) === agentIdStr))!;
  const steps = deriveWorkflowSteps(agent);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold text-text-hi">{agent.config.identity.agent_name.value}</span>
          <TierBadge tier={agent.capability_tier} />
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate(`/agents/${agentIdStr}?tab=configuration`)}>Full config</Button>
          <Button variant="primary" size="sm" icon={<MessagesSquare size={13} />} onClick={() => navigate(`/playground/${agentIdStr}`)}>Test in Playground</Button>
        </div>
      </div>

      <div className="space-y-0">
        {steps.map((step, i) => {
          const Icon = STEP_ICON[step.kind];
          const dimmed = step.optional && !step.enabled;
          return (
            <div key={step.kind} className="relative flex gap-3 pb-3">
              {i < steps.length - 1 && <span className="absolute left-[15px] top-8 bottom-0 w-px bg-border" />}
              <div className={cn('z-10 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border', dimmed ? 'border-border bg-canvas text-text-low' : 'border-accent/40 bg-accent/10 text-accent')}>
                <Icon size={14} />
              </div>
              <Card className={cn('flex-1', dimmed && 'opacity-60')}>
                <div className="mb-1 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-text-hi">{step.label}</span>
                    {step.optional && <Badge tone={step.enabled ? 'ok' : 'neutral'}>{step.enabled ? 'active' : 'skipped'}</Badge>}
                    {step.badges.map((b) => <Badge key={b} tone="info">{b}</Badge>)}
                  </div>
                  {step.toggleField && (
                    <Button
                      variant="subtle"
                      size="tiny"
                      onClick={() => api.proposeConfigChange(agentIdStr, step.toggleField!.groupKey, step.toggleField!.field, !step.enabled)}
                    >
                      {step.enabled ? 'Disable' : 'Enable'}
                    </Button>
                  )}
                </div>
                <p className="text-[12px] text-text-mid">{step.detail}</p>
                {step.assetRefs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {step.assetRefs.map((ref) => <AssetRefLink key={ref} refUri={ref} />)}
                  </div>
                )}
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}
