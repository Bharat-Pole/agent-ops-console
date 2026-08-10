// Model catalog (server-backed). Each entry carries its own vault credential,
// so keys rotate without a restart and different teams can run on different
// keys. Secret NAMES are shown; values never leave the server.
import { useCallback, useEffect, useState } from 'react';
import { KeyRound, Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import {
  Badge, Button, Card, CardHeader, ComboBox, EmptyState, Modal, type ComboOption,
} from '@/components/primitives';
import { apiErrorMessage, modelsApi, secretsApi, type SecretMeta, type ServerModel } from '@/api/client';

const INPUT = 'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function ServerModelsPage() {
  const [models, setModels] = useState<ServerModel[] | null>(null);
  const [secrets, setSecrets] = useState<ComboOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ServerModel | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(() => {
    modelsApi.list().then(setModels).catch((e) => setError(apiErrorMessage(e)));
    secretsApi.list()
      .then((rows: SecretMeta[]) => setSecrets(rows.map((s) => ({ value: s.name }))))
      .catch(() => setSecrets([]));  // non-vault roles simply see no options
  }, []);
  useEffect(load, [load]);

  return (
    <div>
      <PageHeader
        title="Model Catalog"
        description="Providers, costs, risk limits, and the vault secret each model authenticates with."
        action={<Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>Add model</Button>}
      />
      {error && <div className="mb-3 text-[13px] text-red-400">{error}</div>}

      {models === null ? <div className="py-16 text-center text-[13px] text-text-low">Loading…</div>
        : models.length === 0 ? <EmptyState title="No models in the catalog" message="Seed the platform or add one." />
        : (
          <div className="flex flex-col gap-3">
            {models.map((m) => (
              <Card key={m.id}>
                <CardHeader
                  title={<span className="flex flex-wrap items-center gap-2">{m.display_name}
                    <span className="mono text-[11px] text-text-low">{m.model_ref}</span>
                    <Badge tone="neutral">{m.kind}</Badge>
                    <Badge tone={m.status === 'active' ? 'ok' : 'muted'}>{m.status}</Badge></span>}
                  subtitle={`${m.provider} · in $${m.cost_per_1k_in}/1k · out $${m.cost_per_1k_out}/1k · max risk ${m.max_risk_tier}`}
                  action={<Button size="tiny" variant="ghost" onClick={() => setEditing(m)}>Edit</Button>}
                />
                <div className="flex items-center gap-2 text-[12px]">
                  <KeyRound size={12} className="text-text-low" />
                  {m.credential_ref ? (
                    <span className="text-text-mid">vault secret <span className="mono">{m.credential_ref}</span></span>
                  ) : (
                    <span className="text-amber-400">
                      no vault credential — falls back to PLATFORM_GEMINI_API_KEY (restart required to change)
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}

      {(createOpen || editing) && (
        <Modal open onClose={() => { setCreateOpen(false); setEditing(null); }}
          title={editing ? `Edit ${editing.display_name}` : 'Add model'} footer={null} width="max-w-lg">
          <ModelForm
            model={editing}
            secrets={secrets}
            onDone={() => { setCreateOpen(false); setEditing(null); load(); }}
          />
        </Modal>
      )}
    </div>
  );
}

function ModelForm({
  model, secrets, onDone,
}: {
  model: ServerModel | null;
  secrets: ComboOption[];
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    provider: model?.provider ?? 'gemini',
    model_ref: model?.model_ref ?? '',
    kind: model?.kind ?? 'llm',
    display_name: model?.display_name ?? '',
    cost_per_1k_in: model?.cost_per_1k_in ?? 0,
    cost_per_1k_out: model?.cost_per_1k_out ?? 0,
    max_risk_tier: model?.max_risk_tier ?? 'high',
    status: model?.status ?? 'active',
    credential_ref: model?.credential_ref ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));

  const submit = async () => {
    setBusy(true); setError(null);
    const body = { ...form, credential_ref: form.credential_ref.trim() || null };
    try {
      if (model) await modelsApi.update(model.id, body);
      else await modelsApi.create(body);
      onDone();
    } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Display name</span>
        <input className={INPUT} value={form.display_name} onChange={(e) => set({ display_name: e.target.value })} /></label>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Model ref (provider's id)</span>
        <input className={INPUT} value={form.model_ref} onChange={(e) => set({ model_ref: e.target.value })}
          disabled={Boolean(model)} placeholder="gemini-flash-latest" /></label>
      <div className="flex gap-2">
        <label className="block flex-1"><span className="mb-1 block text-[12px] text-text-mid">Provider</span>
          <input className={INPUT} value={form.provider} onChange={(e) => set({ provider: e.target.value })} /></label>
        <label className="block flex-1"><span className="mb-1 block text-[12px] text-text-mid">Kind</span>
          <select className={INPUT} value={form.kind} onChange={(e) => set({ kind: e.target.value })}>
            {['llm', 'embedding', 'judge'].map((k) => <option key={k} value={k}>{k}</option>)}
          </select></label>
      </div>
      <div className="flex gap-2">
        <label className="block flex-1"><span className="mb-1 block text-[12px] text-text-mid">Cost / 1k in</span>
          <input className={INPUT} type="number" step="0.0001" value={form.cost_per_1k_in}
            onChange={(e) => set({ cost_per_1k_in: Number(e.target.value) })} /></label>
        <label className="block flex-1"><span className="mb-1 block text-[12px] text-text-mid">Cost / 1k out</span>
          <input className={INPUT} type="number" step="0.0001" value={form.cost_per_1k_out}
            onChange={(e) => set({ cost_per_1k_out: Number(e.target.value) })} /></label>
      </div>
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">API key (vault secret name)</span>
        <ComboBox value={form.credential_ref} options={secrets}
          emptyHint="no secrets yet — add one under Secrets first"
          onChange={(v) => set({ credential_ref: v })} />
        <span className="mt-1 block text-[11px] text-text-low">
          Leave blank to use PLATFORM_GEMINI_API_KEY. Naming a secret lets you rotate the key
          without restarting, and lets different models use different keys.
        </span></label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end">
        <Button variant="primary" disabled={busy || !form.display_name || !form.model_ref} onClick={submit}>
          {busy ? 'Saving…' : model ? 'Save' : 'Add model'}
        </Button>
      </div>
    </div>
  );
}
