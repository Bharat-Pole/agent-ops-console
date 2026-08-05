import { useState } from 'react';
import type { AgentRecord, Prov } from '@/types';
import { SCHEMA_GROUPS, agentId } from '@/types';
import { Card, Modal, Button, Badge } from '@/components/primitives';
import { SchemaFieldRow } from '@/components/domain';
import { api } from '@/kernel/api';
import { GOVERNANCE_CRITICAL_FIELDS } from '@/types';
import { ChevronDown, ChevronRight, Info, Plus } from 'lucide-react';
import { KnowledgeSourcePickerModal } from '../components/KnowledgeSourcePickerModal';

interface Editing { groupKey: string; field: string; value: unknown }

// Section 9.2 #2 — the 13 schema groups as collapsible sections; every field a
// SchemaFieldRow with a ProvenanceChip. Read-only except through "Propose change",
// which creates an audit event (+ an approval for governance-critical fields).
export function ConfigurationTab({ agent }: { agent: AgentRecord }) {
  const [open, setOpen] = useState<Record<string, boolean>>(() => Object.fromEntries(SCHEMA_GROUPS.map((g, i) => [g.key, i < 3])));
  const [editing, setEditing] = useState<Editing | null>(null);
  const [attachingSource, setAttachingSource] = useState(false);
  const cfg = agent.config as unknown as Record<string, Record<string, Prov<unknown>>>;

  const isEditable = (v: unknown) => v === null || ['string', 'number', 'boolean'].includes(typeof v);

  const save = () => {
    if (!editing) return;
    let val: unknown = editing.value;
    // coerce numeric strings back to numbers when the original was numeric
    const orig = cfg[editing.groupKey][editing.field].value;
    if (typeof orig === 'number') val = Number(editing.value);
    if (typeof orig === 'boolean') val = editing.value === 'true' || editing.value === true;
    api.proposeConfigChange(agentId(agent), editing.groupKey, editing.field, val);
    setEditing(null);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-card border border-border bg-surface px-3 py-2 text-[12px] text-text-mid">
        <Info size={14} className="text-accent" />
        Read-only. Hover a field and click the pencil to <b>Propose change</b> — governance-critical fields create a new approval.
      </div>
      {SCHEMA_GROUPS.map((g) => {
        const group = cfg[g.key];
        const isOpen = open[g.key];
        return (
          <Card key={g.key} pad={false}>
            <button onClick={() => setOpen((o) => ({ ...o, [g.key]: !o[g.key] }))} className="flex w-full items-center gap-2 px-3 py-2.5 text-left">
              {isOpen ? <ChevronDown size={14} className="text-text-low" /> : <ChevronRight size={14} className="text-text-low" />}
              <span className="text-[13px] font-semibold text-text-hi">{g.label}</span>
              <span className="text-[11px] text-text-low">{g.fields.length} fields</span>
            </button>
            {isOpen && (
              <div className="border-t border-border px-3 py-1">
                {g.fields.map((f) => (
                  <SchemaFieldRow key={f} field={f} prov={group[f]} onEdit={isEditable(group[f].value) ? () => setEditing({ groupKey: g.key, field: f, value: group[f].value }) : undefined} />
                ))}
                {g.key === 'data' && (
                  <div className="flex justify-end py-1.5">
                    <Button size="sm" variant="ghost" icon={<Plus size={12} />} onClick={() => setAttachingSource(true)}>
                      Attach source
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Card>
        );
      })}

      <Modal open={!!editing} onClose={() => setEditing(null)} title={<span className="mono">{editing?.field}</span>} width="max-w-md"
        footer={<><Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" onClick={save}>Propose change</Button></>}>
        {editing && (
          <div className="space-y-2">
            {GOVERNANCE_CRITICAL_FIELDS.has(editing.field) && <Badge tone="warn">governance-critical — creates a new approval</Badge>}
            <div className="text-[12px] text-text-low">New value</div>
            <input autoFocus value={String(editing.value ?? '')} onChange={(e) => setEditing({ ...editing, value: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && save()} className="w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi focus-ring" />
          </div>
        )}
      </Modal>

      <KnowledgeSourcePickerModal agent={agent} open={attachingSource} onClose={() => setAttachingSource(false)} />
    </div>
  );
}
