// Secrets vault (server-backed): names + timestamps ONLY. Values are
// write-only — the API never returns them, so neither can this page.
import { useCallback, useEffect, useState } from 'react';
import { KeyRound, Trash2 } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Button, Card, CardHeader, EmptyState } from '@/components/primitives';
import { apiErrorMessage, secretsApi, type SecretMeta } from '@/api/client';
import { fmtDate } from '@/utils/format';

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerSecretsPage() {
  const [secrets, setSecrets] = useState<SecretMeta[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    secretsApi.list().then(setSecrets).catch((e) => { setSecrets([]); setError(apiErrorMessage(e)); });
  }, []);
  useEffect(load, [load]);

  const put = async () => {
    setBusy(true); setError(null);
    try { await secretsApi.put(name.trim(), value); setName(''); setValue(''); load(); }
    catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const remove = async (n: string) => {
    setError(null);
    try { await secretsApi.remove(n); load(); } catch (e) { setError(apiErrorMessage(e)); }
  };

  return (
    <div>
      <PageHeader title="Secrets Vault" description="Encrypted at rest; values never leave the server. Tools and connectors reference secrets by name." />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}
          {secrets === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
            : secrets.length === 0 ? <EmptyState title="No secrets stored" message="Add credentials that tools and MCP connectors will reference by name." />
            : (
              <div className="flex flex-col gap-2">
                {secrets.map((s) => (
                  <div key={s.name} className="flex items-center justify-between rounded-control border border-border bg-surface px-3 py-2">
                    <span className="flex items-center gap-2 text-[13px] text-text-hi"><KeyRound size={13} className="text-text-low" /><span className="mono">{s.name}</span></span>
                    <span className="flex items-center gap-3 text-[11px] text-text-low">
                      rotated {fmtDate(s.updated_at)}
                      <button className="rounded p-1 text-text-mid hover:bg-raised hover:text-red-400" title="Delete (platform admin)" onClick={() => remove(s.name)}><Trash2 size={13} /></button>
                    </span>
                  </div>
                ))}
              </div>
            )}
        </div>
        <Card>
          <CardHeader title="Add / rotate secret" subtitle="Writing an existing name rotates its value." />
          <div className="flex flex-col gap-3">
            <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
              <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} placeholder="svc.ticketing.api_key" /></label>
            <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Value (write-only)</span>
              <input className={INPUT} type="password" value={value} onChange={(e) => setValue(e.target.value)} /></label>
            <Button variant="primary" disabled={busy || !name || !value} onClick={put}>{busy ? 'Saving…' : 'Save'}</Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
