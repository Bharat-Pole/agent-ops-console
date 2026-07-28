import { useNavigate } from 'react-router-dom';
import { Download } from 'lucide-react';
import { Button, DataTable, type Column, type FilterDef } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import type { AuditEvent } from '@/types';
import { fmtDateTime } from '@/utils/format';

export function AuditLog() {
  const navigate = useNavigate();
  const auditLog = useWorkspace((s) => s.auditLog);
  const sorted = [...auditLog].sort((a, b) => (a.at < b.at ? 1 : -1));

  const actions = [...new Set(auditLog.map((e) => e.action))].sort();
  const types = [...new Set(auditLog.map((e) => e.entity_type))].sort();

  const linkFor = (e: AuditEvent) =>
    e.entity_type === 'agent' ? `/agents/${e.entity_id}` : e.entity_type === 'prompt' ? `/prompts/${e.entity_id}` : e.entity_type === 'source' ? '/knowledge' : e.entity_type === 'connector' ? '/tools' : e.entity_type === 'approval' ? '/governance' : null;

  const columns: Column<AuditEvent>[] = [
    { key: 'at', header: 'Time', width: '150px', sortValue: (e) => e.at, render: (e) => <span className="text-text-low">{fmtDateTime(e.at)}</span> },
    { key: 'persona', header: 'Persona', sortValue: (e) => e.actor_persona, render: (e) => <span className="text-text-mid">{e.actor_persona}</span> },
    { key: 'action', header: 'Action', sortValue: (e) => e.action, render: (e) => <span className="mono text-[11px] text-accent">{e.action}</span> },
    {
      key: 'entity', header: 'Entity', render: (e) => {
        const to = linkFor(e);
        return to ? (
          <button onClick={(ev) => { ev.stopPropagation(); navigate(to); }} className="mono text-[11px] text-text-hi hover:text-accent">{e.entity_type}:{e.entity_id.length > 20 ? e.entity_id.slice(0, 20) + '…' : e.entity_id}</button>
        ) : <span className="mono text-[11px] text-text-mid">{e.entity_type}</span>;
      },
    },
    { key: 'detail', header: 'Detail', render: (e) => <span className="text-text-mid">{e.detail}</span> },
  ];

  const filters: FilterDef<AuditEvent>[] = [
    { key: 'action', label: 'Action', options: actions.map((a) => ({ value: a, label: a })), predicate: (e, v) => e.action === v },
    { key: 'type', label: 'Type', options: types.map((t) => ({ value: t, label: t })), predicate: (e, v) => e.entity_type === v },
  ];

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(sorted, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'audit-log.json'; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  return (
    <DataTable
      columns={columns}
      rows={sorted}
      rowKey={(e) => e.id}
      searchText={(e) => `${e.action} ${e.detail} ${e.actor_persona} ${e.entity_id}`}
      searchPlaceholder="Search audit log…"
      filters={filters}
      toolbarRight={<Button variant="subtle" size="sm" icon={<Download size={13} />} onClick={exportJson}>Export JSON</Button>}
      initialSort={{ key: 'at', dir: 'desc' }}
    />
  );
}
