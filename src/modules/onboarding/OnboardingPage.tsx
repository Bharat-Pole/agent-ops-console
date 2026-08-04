import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Plus, Rocket } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Card, Button, Badge, TierBadge, EmptyState } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { newDraft } from '@/kernel/wizard';
import { nowIso } from '@/kernel/api';
import { usePreflight } from './PreFlight';
import { fmtDate } from '@/utils/format';
import { CheckCircle2, AlertTriangle } from 'lucide-react';

const PHASE_NAMES = ['Capture Intent', 'Create Work Package', 'Register', 'Configure Workflow', 'Add Governance Gates', 'Evaluate & Approve', 'Deploy / Monitor / Improve'];

export default function OnboardingPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const drafts = useWorkspace((s) => s.drafts);
  const addDraft = useWorkspace((s) => s.addDraft);
  const nextId = useWorkspace((s) => s.nextId);
  const { checks, hardBlocked } = usePreflight();

  const startNew = () => {
    const id = nextId('draft');
    addDraft(newDraft(id, nowIso()));
    navigate(`/onboarding/${id}/phase/pre`);
  };

  // "+ New → New Agent" and the registry CTA pass ?new=1.
  useEffect(() => {
    if (params.get('new') === '1') {
      params.delete('new');
      setParams(params, { replace: true });
      startNew();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hardOk = checks.filter((c) => c.hard && c.state === 'ok').length;
  const hardTotal = checks.filter((c) => c.hard).length;

  return (
    <div>
      <PageHeader
        title="Onboarding"
        description="One process, any agent. The seven-phase lifecycle never changes; only which settings are filled changes."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={startNew}>Start new onboarding</Button>}
      />

      {/* Pre-Flight status strip */}
      <Card className={hardBlocked ? 'mb-4 border-err/40' : 'mb-4 border-ok/40'}>
        <div className="flex items-center gap-2">
          {hardBlocked ? <AlertTriangle size={16} className="text-err" /> : <CheckCircle2 size={16} className="text-ok" />}
          <div className="flex-1">
            <div className="text-[13px] font-semibold text-text-hi">Pre-Flight readiness</div>
            <div className="text-[12px] text-text-low">
              {hardOk}/{hardTotal} hard blockers green.{' '}
              {hardBlocked ? 'Resolve all 🔴 items before onboarding can start.' : 'All 🔴 clear — onboarding can start.'}
            </div>
          </div>
          <div className="flex gap-1">
            {checks.map((c) => (
              <span key={c.id} title={c.label} className={`h-2.5 w-2.5 rounded-full ${c.state === 'ok' ? 'bg-ok' : c.state === 'fail' ? 'bg-err' : 'bg-warn'}`} />
            ))}
          </div>
        </div>
      </Card>

      {/* Drafts table */}
      <Card pad={false}>
        <div className="border-b border-border px-4 py-2.5 text-[13px] font-semibold text-text-hi">Drafts in progress</div>
        {drafts.length === 0 ? (
          <div className="p-4">
            <EmptyState icon={<Rocket size={26} />} title="No drafts" message="Start a new onboarding to create your first agent." action={<Button variant="primary" onClick={startNew}>Start new onboarding</Button>} />
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wide text-text-low">
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Phase reached</th>
                <th className="px-4 py-2">Tier proposal</th>
                <th className="px-4 py-2">Updated</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d) => (
                <tr key={d.id} className="border-b border-border/60 last:border-0 hover:bg-raised">
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-text-hi">{d.name}</div>
                    <div className="mono text-[10px] text-text-low">{d.id}</div>
                  </td>
                  <td className="px-4 py-2.5 text-text-mid">
                    <Badge tone="neutral">Phase {d.maxPhaseReached}</Badge> {PHASE_NAMES[d.maxPhaseReached - 1]}
                  </td>
                  <td className="px-4 py-2.5">{d.confirmedTier ? <TierBadge tier={d.confirmedTier} /> : <span className="text-text-low">—</span>}</td>
                  <td className="px-4 py-2.5 text-text-low">{fmtDate(d.updated_at)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <Button variant="subtle" size="sm" onClick={() => navigate(`/onboarding/${d.id}/phase/${d.phase}`)}>Resume →</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
