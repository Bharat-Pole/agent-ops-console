import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import { Tabs, Badge, type TabItem } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { ApprovalsQueue } from './tabs/ApprovalsQueue';
import { MatrixPolicies } from './tabs/MatrixPolicies';
import { AuditLog } from './tabs/AuditLog';

export default function GovernancePage() {
  const [params, setParams] = useSearchParams();
  const pending = useWorkspace((s) => s.approvals.filter((a) => a.status === 'pending').length);
  const auditCount = useWorkspace((s) => s.auditLog.length);
  const persona = useWorkspace((s) => s.ui.persona);

  const tab = params.get('tab') ?? 'queue';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });

  const tabs: TabItem[] = [
    { key: 'queue', label: 'Approvals Queue', count: pending },
    { key: 'matrix', label: 'Matrix & Policies' },
    { key: 'audit', label: 'Audit Log', count: auditCount },
  ];

  return (
    <div>
      <PageHeader
        title="Approvals & Gates"
        description="Work the approvals queue, the capability × risk matrix, and the append-only audit log."
        badges={<Badge tone={persona === 'governance_officer' ? 'ok' : 'muted'}>{persona === 'governance_officer' ? 'can approve' : 'view-only for this persona'}</Badge>}
      />
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'queue' && <ApprovalsQueue />}
      {tab === 'matrix' && <MatrixPolicies />}
      {tab === 'audit' && <AuditLog />}
    </div>
  );
}
