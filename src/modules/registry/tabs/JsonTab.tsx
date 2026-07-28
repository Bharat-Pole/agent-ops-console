import type { AgentRecord } from '@/types';
import { agentId } from '@/types';
import { Button, JsonViewer } from '@/components/primitives';
import { Download } from 'lucide-react';

// Section 9.2 #7 — full canonical record with provenance envelopes; [Export config].
export function JsonTab({ agent }: { agent: AgentRecord }) {
  const exportConfig = () => {
    const blob = new Blob([JSON.stringify(agent, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${agentId(agent)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[13px] text-text-mid">Full canonical record — an agent is data.</div>
        <Button variant="subtle" size="sm" icon={<Download size={14} />} onClick={exportConfig}>Export config</Button>
      </div>
      <JsonViewer data={agent} maxHeight={680} />
    </div>
  );
}
