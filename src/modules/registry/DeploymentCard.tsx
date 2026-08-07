// Deployment panel (Increment F): immutable manifests, admission verdicts
// verbatim, keyed REST channel, rollback-as-new-record. API keys show their
// plaintext exactly once — the UI mirrors the server contract.
import { useCallback, useEffect, useState } from 'react';
import { Rocket, RotateCcw } from 'lucide-react';
import { Badge, Button, Card, CardHeader, Modal } from '@/components/primitives';
import {
  apiErrorMessage, deploymentsApi,
  type AccessGroupRow, type ServerDeployment,
} from '@/api/client';
import { fmtDate, titleCase } from '@/utils/format';

const STATUS_TONE: Record<string, 'ok' | 'muted' | 'warn'> = {
  active: 'ok', superseded: 'muted', rolled_back: 'warn',
};

export default function DeploymentCard({ agentId }: { agentId: string }) {
  const [deployments, setDeployments] = useState<ServerDeployment[]>([]);
  const [groups, setGroups] = useState<AccessGroupRow[]>([]);
  const [channel, setChannel] = useState('sandbox');
  const [groupId, setGroupId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);

  const load = useCallback(() => {
    deploymentsApi.list(agentId).then(setDeployments).catch(() => setDeployments([]));
    deploymentsApi.groups().then(setGroups).catch(() => setGroups([]));
  }, [agentId]);
  useEffect(load, [load]);

  const deploy = async () => {
    setBusy(true); setError(null);
    try {
      await deploymentsApi.deploy(agentId, { channel, access_group_id: groupId || null });
      load();
    } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const rollback = async (id: string) => {
    setError(null);
    try { await deploymentsApi.rollback(id); load(); } catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <Card>
      <CardHeader
        title="Deployments"
        subtitle="Immutable manifests; production channel requires full admission."
        action={<Button size="tiny" variant="ghost" onClick={() => setKeysOpen(true)}>Access keys</Button>}
      />
      <div className="flex flex-col gap-2">
        {deployments.map((d) => (
          <div key={d.id} className="rounded-control border border-border bg-canvas px-2 py-1.5">
            <div className="flex items-center justify-between text-[12px]">
              <span className="flex items-center gap-2 text-text-mid">
                <Badge tone={STATUS_TONE[d.status] ?? 'muted'}>{titleCase(d.status)}</Badge>
                <Badge tone={d.channel === 'production' ? 'accent' : 'neutral'}>{d.channel}</Badge>
                wf v{d.workflow_version}
              </span>
              <span className="flex items-center gap-2 text-[11px] text-text-low">
                {fmtDate(d.created_at)}
                {d.status !== 'active' && (
                  <button className="text-text-mid hover:text-text-hi" title="Rollback to this manifest"
                    onClick={() => rollback(d.id)}><RotateCcw size={12} /></button>
                )}
              </span>
            </div>
            {d.invoke_path && (
              <div className="mono mt-1 text-[10px] text-text-low">POST {d.invoke_path} (X-API-Key)</div>
            )}
          </div>
        ))}
        {deployments.length === 0 && <div className="text-[12px] text-text-low">Not deployed yet.</div>}

        <div className="mt-1 flex gap-2 border-t border-border pt-2">
          <select className="h-8 rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
            value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="sandbox">sandbox</option><option value="production">production</option>
          </select>
          <select className="h-8 w-full rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
            value={groupId} onChange={(e) => setGroupId(e.target.value)}>
            <option value="">no access group (uninvokable)</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <Button size="tiny" variant="primary" icon={<Rocket size={12} />} disabled={busy} onClick={deploy}>
            Deploy
          </Button>
        </div>
        {error && <div className="text-[12px] text-red-400">{error}</div>}
      </div>
      {keysOpen && <AccessKeysModal groups={groups} onClose={() => { setKeysOpen(false); load(); }} />}
    </Card>
  );
}

function AccessKeysModal({ groups, onClose }: { groups: AccessGroupRow[]; onClose: () => void }) {
  const [rows, setRows] = useState(groups);
  const [groupName, setGroupName] = useState('');
  const [keyNames, setKeyNames] = useState<Record<string, string>>({});
  const [minted, setMinted] = useState<{ prefix: string; api_key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = () => deploymentsApi.groups().then(setRows).catch(() => undefined);

  const createGroup = async () => {
    setError(null);
    try { await deploymentsApi.createGroup(groupName); setGroupName(''); reload(); }
    catch (e) { setError(apiErrorMessage(e)); }
  };
  const createKey = async (gid: string) => {
    setError(null);
    try {
      const k = await deploymentsApi.createKey(gid, keyNames[gid] || 'key');
      setMinted({ prefix: k.prefix, api_key: k.api_key });
      reload();
    } catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <Modal open onClose={onClose} title="Access groups & API keys" width="max-w-2xl" footer={null}>
      {minted && (
        <div className="mb-3 rounded-control border border-amber-900/50 bg-canvas p-3">
          <div className="mb-1 text-[12px] text-amber-400">Copy this key now — it is shown exactly once:</div>
          <code className="mono block break-all text-[12px] text-text-hi">{minted.api_key}</code>
        </div>
      )}
      {rows.map((g) => (
        <div key={g.id} className="mb-3 rounded-control border border-border p-2">
          <div className="mb-1 text-[13px] font-medium text-text-hi">{g.name}</div>
          {g.keys.map((k) => (
            <div key={k.id} className="flex items-center justify-between py-0.5 text-[12px] text-text-mid">
              <span className="mono">{k.prefix}… <span className="text-text-low">({k.name})</span>
                {k.revoked && <Badge tone="err">revoked</Badge>}</span>
              {!k.revoked && (
                <button className="text-text-low hover:text-red-400"
                  onClick={() => deploymentsApi.revokeKey(k.id).then(reload)}>revoke</button>
              )}
            </div>
          ))}
          <div className="mt-1 flex gap-2">
            <input className="h-7 w-full rounded-control border border-border bg-canvas px-2 text-[11px] text-text-hi outline-none"
              placeholder="key name" value={keyNames[g.id] ?? ''}
              onChange={(e) => setKeyNames((s) => ({ ...s, [g.id]: e.target.value }))} />
            <Button size="tiny" variant="subtle" onClick={() => createKey(g.id)}>Mint key</Button>
          </div>
        </div>
      ))}
      <div className="flex gap-2">
        <input className="h-8 w-full rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none"
          placeholder="new access group name" value={groupName} onChange={(e) => setGroupName(e.target.value)} />
        <Button size="tiny" variant="primary" disabled={groupName.trim().length < 3} onClick={createGroup}>
          Create group
        </Button>
      </div>
      {error && <div className="mt-2 text-[12px] text-red-400">{error}</div>}
    </Modal>
  );
}
