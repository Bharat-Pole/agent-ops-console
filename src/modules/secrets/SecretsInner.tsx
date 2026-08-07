import { useEffect, useState } from 'react';
import { Trash2, Plus, ArrowRightLeft, Loader2 } from 'lucide-react';
import { Button, Badge } from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { api } from '@/kernel/api';

// Engine-side secrets vault manager body (shared by the API Keys page and the
// Playground modal). The browser only ever sees NAMES; values are write-only.
export function SecretsInner({ onChanged }: { onChanged?: (names: string[]) => void }) {
  const geminiKey = useWorkspace((s) => s.ui.geminiKey);
  const setGeminiKey = useWorkspace((s) => s.setGeminiKey);
  const pushToast = useWorkspace((s) => s.pushToast);

  const [names, setNames] = useState<string[] | null>(null);
  const [newName, setNewName] = useState('');
  const [newValue, setNewValue] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const n = await api.listSecrets();
    setNames(n);
    if (n) onChanged?.(n);
  };

  useEffect(() => { void refresh(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, []);

  const save = async () => {
    const name = newName.trim();
    if (!name || !newValue.trim()) return;
    setBusy(true);
    const n = await api.putSecret(name, newValue.trim());
    setBusy(false);
    if (n) {
      setNames(n);
      onChanged?.(n);
      setNewName('');
      setNewValue(''); // write-only — cleared immediately
      pushToast('ok', `Secret "${name}" saved to the engine vault.`);
    }
  };

  const remove = async (name: string) => {
    const n = await api.deleteSecret(name);
    if (n) { setNames(n); onChanged?.(n); }
  };

  const migrate = async () => {
    if (!geminiKey) return;
    setBusy(true);
    const n = await api.putSecret('GEMINI_DEFAULT', geminiKey);
    setBusy(false);
    if (n) {
      setGeminiKey('');
      setNames(n);
      onChanged?.(n);
      pushToast('ok', 'Browser key moved to the vault as GEMINI_DEFAULT.');
    }
  };

  return (
    <div className="space-y-3 text-[12px] text-text-mid">
      <p>
        Named secrets live in <span className="mono">engine/.secrets.json</span> (gitignored). Agents
        reference them by name (model key + per-tool). Values are <b>write-only</b> from here — they
        never come back to the browser. <span className="mono">GEMINI_DEFAULT</span> is the fallback
        model key for agents without their own.
      </p>

      {geminiKey && (
        <div className="flex items-center justify-between gap-2 rounded-control border border-warn/40 bg-warn/10 px-3 py-2">
          <span className="text-warn">A legacy key is still stored in this browser.</span>
          <Button variant="primary" size="sm" icon={<ArrowRightLeft size={13} />} onClick={migrate} disabled={busy}>
            Move to vault as GEMINI_DEFAULT
          </Button>
        </div>
      )}

      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Stored secrets</div>
        {names === null ? (
          <div className="flex items-center gap-2 text-text-low"><Loader2 size={13} className="animate-spin-slow" /> loading… (engine offline?)</div>
        ) : names.length === 0 ? (
          <div className="text-text-low">No secrets yet — add GEMINI_DEFAULT below.</div>
        ) : (
          <div className="space-y-1">
            {names.map((n) => (
              <div key={n} className="flex items-center gap-2 rounded-control border border-border bg-raised/40 px-2.5 py-1.5">
                <span className="mono flex-1 text-text-hi">{n}</span>
                <Badge tone="ok">stored</Badge>
                <button onClick={() => remove(n)} className="text-text-low hover:text-err" title="Delete"><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase text-text-low">Add / update</div>
        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="NAME (e.g. GEMINI_DEFAULT)"
            className="w-48 rounded-control border border-border bg-canvas px-2.5 py-2 mono text-[12px] text-text-hi placeholder:text-text-low focus-ring"
          />
          <input
            type="password"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && save()}
            placeholder="secret value"
            className="flex-1 rounded-control border border-border bg-canvas px-2.5 py-2 mono text-[12px] text-text-hi placeholder:text-text-low focus-ring"
          />
          <Button variant="primary" size="sm" icon={busy ? <Loader2 size={13} className="animate-spin-slow" /> : <Plus size={13} />} onClick={save} disabled={busy || !newName.trim() || !newValue.trim()}>
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
