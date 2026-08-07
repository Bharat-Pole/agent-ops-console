import { useState } from 'react';
import type { AgentRecord } from '@/types';
import { agentId } from '@/types';
import { Modal, Button, Badge } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';
import { SensitivityBadge } from '@/modules/knowledge/KnowledgePage';
import { Database, Loader2 } from 'lucide-react';

function parseSourceId(ref: string): string {
  return ref.replace('kb://', '').split('@')[0];
}

// Sensitivity-gated attach action for the agent's data.knowledge_source_refs
// field — mirrors how Tools & MCP binds a tool, but a confidential/restricted
// source creates a pending risk-officer approval instead of binding immediately
// (server-enforced in knowledge_binding.py; this modal just surfaces the result).
export function KnowledgeSourcePickerModal({ agent, open, onClose }: { agent: AgentRecord; open: boolean; onClose: () => void }) {
  const sources = useWorkspace((s) => s.knowledgeSources);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const boundIds = new Set((agent.config.data.knowledge_source_refs.value as string[] | null ?? []).map(parseSourceId));
  const available = sources.filter((s) => s.lifecycle === 'active' && s.status === 'ready' && !boundIds.has(s.id));

  async function attach(sourceId: string) {
    setPendingId(sourceId);
    await api.bindKnowledgeSource(agentId(agent), sourceId);
    setPendingId(null);
  }

  return (
    <Modal open={open} onClose={onClose} title="Attach a knowledge source" width="max-w-lg"
      footer={<Button variant="ghost" onClick={onClose}>Done</Button>}>
      <div className="max-h-[420px] space-y-1.5 overflow-y-auto">
        {available.length === 0 && (
          <div className="py-6 text-center text-[12px] text-text-low">
            No available sources — every active, ready source is already bound, or none exist yet on the Knowledge & RAG page.
          </div>
        )}
        {available.map((s) => (
          <div key={s.id} className="flex items-center gap-2.5 rounded-md border border-border px-3 py-2">
            <Database size={14} className="shrink-0 text-text-low" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] text-text-hi">{s.name}</div>
              <div className="truncate text-[11px] text-text-low">{s.domain ?? '—'} · {s.ingestion_mode}</div>
            </div>
            <SensitivityBadge s={s.sensitivity} />
            <Button size="sm" disabled={pendingId === s.id} onClick={() => attach(s.id)}>
              {pendingId === s.id ? <Loader2 size={12} className="animate-spin" /> : 'Attach'}
            </Button>
          </div>
        ))}
      </div>
      <div className="mt-3 border-t border-border pt-2 text-[11px] text-text-low">
        Confidential or restricted sources require risk-officer approval before they're usable — check{' '}
        <Badge tone="neutral">Governance → Approvals</Badge> for pending requests.
      </div>
    </Modal>
  );
}
