// Agent Registry — the first console page served by the REAL backend
// (Increment A strangler start). Rows are server state verbatim; there is no
// kernel/demo data on this page.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, RefreshCw } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import {
  Badge, Button, DataTable, EmptyState, Modal,
  type Column, type FilterDef,
} from '@/components/primitives';
import { useAuth } from '@/api/auth';
import {
  agentsApi, apiErrorMessage, SERVER_LIFECYCLE,
  type ServerAgent, type ServerLifecycleStatus,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

export const SERVER_LIFECYCLE_TONE: Record<ServerLifecycleStatus, 'ok' | 'accent' | 'warn' | 'neutral' | 'muted' | 'err'> = {
  draft: 'muted',
  sandbox: 'neutral',
  candidate: 'warn',
  approved_prototype: 'accent',
  production_candidate: 'warn',
  production: 'ok',
  needs_review: 'err',
  deprecated: 'muted',
  retired: 'muted',
};

const CREATE_ROLES = new Set(['agent_creator', 'agent_owner', 'platform_admin']);

export default function ServerRegistryPage() {
  const navigate = useNavigate();
  const { me } = useAuth();
  const [agents, setAgents] = useState<ServerAgent[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(() => {
    setLoadError(null);
    agentsApi.list().then(setAgents).catch((e) => setLoadError(apiErrorMessage(e)));
  }, []);
  useEffect(load, [load]);

  const canCreate = useMemo(
    () => (me?.roles ?? []).some((r) => CREATE_ROLES.has(r)),
    [me],
  );

  const columns: Column<ServerAgent>[] = [
    {
      key: 'name',
      header: 'Name',
      width: '28%',
      sortValue: (a) => a.name.toLowerCase(),
      render: (a) => (
        <div className="flex flex-col">
          <span className="font-medium text-text-hi">{a.name}</span>
          <span className="mono text-[10px] text-text-low">{a.slug}</span>
        </div>
      ),
    },
    {
      key: 'lifecycle',
      header: 'Lifecycle',
      sortValue: (a) => a.lifecycle_status,
      render: (a) => (
        <Badge tone={SERVER_LIFECYCLE_TONE[a.lifecycle_status]}>{titleCase(a.lifecycle_status)}</Badge>
      ),
    },
    {
      key: 'risk',
      header: 'Risk',
      sortValue: (a) => a.confirmed_risk_tier ?? a.draft_risk_tier ?? '',
      render: (a) => {
        const risk = a.confirmed_risk_tier ?? a.draft_risk_tier;
        return risk ? (
          <span className="text-text-mid">
            {titleCase(risk)}
            {!a.confirmed_risk_tier && <span className="text-text-low"> (draft)</span>}
          </span>
        ) : (
          <span className="text-text-low">—</span>
        );
      },
    },
    {
      key: 'intent',
      header: 'Intent',
      sortValue: (a) => a.current_intent_version ?? 0,
      render: (a) =>
        a.current_intent_version ? (
          <span className="mono text-text-mid">v{a.current_intent_version}</span>
        ) : (
          <span className="text-text-low">none</span>
        ),
    },
    {
      key: 'owner',
      header: 'Business owner',
      sortValue: (a) => a.business_owner ?? '',
      render: (a) => <span className="text-text-mid">{a.business_owner ?? '—'}</span>,
    },
    {
      key: 'updated',
      header: 'Updated',
      align: 'right',
      sortValue: (a) => a.updated_at,
      render: (a) => <span className="text-text-low">{fmtDate(a.updated_at)}</span>,
    },
  ];

  const filters: FilterDef<ServerAgent>[] = [
    {
      key: 'lifecycle',
      label: 'Lifecycle',
      options: SERVER_LIFECYCLE.map((l) => ({ value: l, label: titleCase(l) })),
      predicate: (a, v) => a.lifecycle_status === v,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Agent Registry"
        description="The system of record — served live from the platform backend."
        action={
          <div className="flex items-center gap-2">
            <Button variant="ghost" icon={<RefreshCw size={14} />} onClick={load}>
              Refresh
            </Button>
            <Button
              variant="new"
              icon={<Plus size={15} />}
              disabled={!canCreate}
              title={canCreate ? undefined : 'Requires agent_creator, agent_owner or platform_admin'}
              onClick={() => setCreateOpen(true)}
            >
              New Agent
            </Button>
          </div>
        }
      />

      {loadError ? (
        <EmptyState
          title="Could not load the registry"
          message={loadError}
          action={<Button variant="primary" onClick={load}>Retry</Button>}
        />
      ) : agents === null ? (
        <div className="py-16 text-center text-[13px] text-text-low">Loading registry…</div>
      ) : agents.length === 0 ? (
        <EmptyState
          title="No agents in the registry yet"
          message="Create the first control record — intent capture and design recommendation attach to it next."
          action={
            canCreate ? (
              <Button variant="primary" onClick={() => setCreateOpen(true)}>New Agent</Button>
            ) : undefined
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={agents}
          rowKey={(a) => a.id}
          onRowClick={(a) => navigate(`/agents/${a.id}`)}
          searchText={(a) => `${a.name} ${a.slug} ${a.business_owner ?? ''}`}
          searchPlaceholder="Search agents…"
          filters={filters}
          initialSort={{ key: 'updated', dir: 'desc' }}
        />
      )}

      <CreateAgentModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(a) => {
          setCreateOpen(false);
          navigate(`/agents/${a.id}`);
        }}
      />
    </div>
  );
}

function CreateAgentModal({
  open, onClose, onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (a: ServerAgent) => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onCreated(await agentsApi.create(name.trim(), description.trim()));
      setName('');
      setDescription('');
    } catch (e) {
      setError(apiErrorMessage(e)); // server verdict verbatim (409 dup, 403 role, 422 name)
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New agent control record"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={busy || name.trim().length < 3} onClick={submit}>
            {busy ? 'Creating…' : 'Create'}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <label className="block">
          <span className="mb-1 block text-[12px] text-text-mid">Name</span>
          <input
            className="h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Billing Dispute Triage"
            autoFocus
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-[12px] text-text-mid">Description</span>
          <textarea
            className="min-h-[72px] w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi outline-none focus:border-border-strong"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this agent is for (one or two sentences)."
          />
        </label>
        {error && <div className="text-[12px] text-red-400">{error}</div>}
      </div>
    </Modal>
  );
}
