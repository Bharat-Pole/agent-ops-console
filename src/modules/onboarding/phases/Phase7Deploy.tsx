import { useNavigate } from 'react-router-dom';
import { Card, Button } from '@/components/primitives';
import { ThreeTrackSwimlanes } from '@/components/domain';
import type { PhaseProps } from '../WizardPage';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { isLive } from '@/types';
import { Rocket, PartyPopper, MessagesSquare, Activity, LayoutGrid, ArrowLeft } from 'lucide-react';

export function Phase7Deploy({ draft, goPhase }: PhaseProps) {
  const navigate = useNavigate();
  const agent = useWorkspace((s) => s.agents.find((a) => a.config.identity.agent_id.value === draft.agent_id));
  const jobs = useWorkspace((s) => s.jobs);

  if (!agent) {
    return <Card><div className="text-[13px] text-text-mid">Register the agent (Phase 3) first.</div><Button className="mt-3" variant="ghost" onClick={() => goPhase(3)}>← Back to Phase 3</Button></Card>;
  }

  const live = isLive(agent);
  const provisioning = jobs.some((j) => (j.kind === 'runtime_provision' || j.kind === 'content_index') && j.entity_id === draft.agent_id && (j.status === 'processing' || j.status === 'queued'));
  const notStarted = agent.tracks.runtime.status === 'not_started';

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-semibold text-text-hi">Phase 7 · Deploy / Monitor / Improve</div>
          <Button variant="primary" icon={<Rocket size={14} />} onClick={() => api.provision(draft.agent_id!)} disabled={provisioning || live || !notStarted}>
            {live ? 'Provisioned' : provisioning ? 'Provisioning…' : 'Provision runtime & index content'}
          </Button>
        </div>
        <ThreeTrackSwimlanes agent={agent} />
      </Card>

      {live && (
        <Card className="border-ok/50 bg-ok/5">
          <div className="flex items-center gap-3">
            <PartyPopper size={22} className="text-ok" />
            <div>
              <div className="text-[16px] font-semibold text-ok">AGENT IS LIVE</div>
              <div className="text-[12px] text-text-mid">All three tracks are green. Metadata alone runs nothing — this agent now executes.</div>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <Button variant="subtle" icon={<MessagesSquare size={14} />} onClick={() => navigate(`/playground/${draft.agent_id}`)}>Open in Playground</Button>
            <Button variant="subtle" icon={<Activity size={14} />} onClick={() => navigate('/monitoring')}>Monitoring</Button>
            <Button variant="subtle" icon={<LayoutGrid size={14} />} onClick={() => navigate(`/agents/${draft.agent_id}`)}>Registry</Button>
          </div>
        </Card>
      )}

      <div className="flex items-center gap-2">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => goPhase(6)}>Back</Button>
      </div>
    </div>
  );
}
