import { useCallback, useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/shell/PageHeader';
import {
  Tabs, Button, Badge, EmptyState, Drawer, DataTable,
  type TabItem, type Column, type FilterDef,
} from '@/components/primitives';
import { useWorkspace } from '@/kernel/store';
import { agentId } from '@/types';
import type { RealKnowledgeSource, RealPipelineRun, KnowledgeChunk, KnowledgeConfig } from '@/types';
import {
  Plus, Database, Loader2, CheckCircle2, XCircle, Clock,
  RefreshCw, Trash2, ChevronDown, ChevronUp, AlertCircle, Archive, ArchiveRestore,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { AddSourceModal } from './components/AddSourceModal';
import { PipelineRunDetail } from './components/PipelineRunDetail';
import { RetrievalTestPanel } from './components/RetrievalTestPanel';
import { QueryStructuredSourcePanel, isStructuredSource } from './components/QueryStructuredSourcePanel';

const ZERO_USAGE_THRESHOLD_DAYS = 14;

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtBytes(b: number): string {
  if (b === 0) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function daysSince(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 86_400_000;
}

function fmtRelative(iso: string): string {
  const days = Math.floor(daysSince(iso));
  if (days <= 0) return 'today';
  if (days === 1) return '1 day ago';
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? '1 month ago' : `${months} months ago`;
}

function UsageLabel({ source }: { source: RealKnowledgeSource }) {
  if (source.last_queried_at) {
    return <span className="text-text-mid">Queried {fmtRelative(source.last_queried_at)}</span>;
  }
  const stale = daysSince(source.created_at) >= ZERO_USAGE_THRESHOLD_DAYS;
  return stale
    ? <Badge tone="warn">Never queried</Badge>
    : <span className="text-text-low">Not queried yet</span>;
}

function FreshnessNote({ source }: { source: RealKnowledgeSource }) {
  if (!source.valid_until) return null;
  const isStale = new Date(source.valid_until).getTime() < Date.now();
  return isStale
    ? <Badge tone="warn">Stale since {fmtDate(source.valid_until)}</Badge>
    : <span className="text-[11px] text-text-low">Valid until {fmtDate(source.valid_until)}</span>;
}

function StatusBadge({ status }: { status: RealKnowledgeSource['status'] }) {
  const config = {
    ready:    { tone: 'ok'     as const, label: 'Ready',    icon: <CheckCircle2 size={11} /> },
    indexing: { tone: 'warn'   as const, label: 'Indexing', icon: <Loader2 size={11} className="animate-spin" /> },
    pending:  { tone: 'neutral'as const, label: 'Pending',  icon: <Clock size={11} /> },
    error:    { tone: 'err'    as const, label: 'Error',    icon: <XCircle size={11} /> },
  }[status];

  return (
    <Badge tone={config.tone}>
      <span className="flex items-center gap-1">{config.icon} {config.label}</span>
    </Badge>
  );
}

export function SensitivityBadge({ s }: { s: string }) {
  const tone =
    s === 'restricted' ? 'err' :
    s === 'confidential' ? 'warn' :
    s === 'public' ? 'ok' : 'neutral';
  return <Badge tone={tone as 'err' | 'warn' | 'ok' | 'neutral'}>{s}</Badge>;
}

function EmbeddingProviderBadge({ provider }: { provider: RealKnowledgeSource['embedding_provider'] }) {
  return provider === 'local_bge_small'
    ? <Badge tone="info">Local (BGE)</Badge>
    : <Badge tone="neutral">OpenAI</Badge>;
}

function TypeIcon({ type }: { type: RealKnowledgeSource['source_type'] }) {
  const icons: Record<string, string> = {
    file: '📄', url: '🌐', text: '📝', database: '🗄️',
    confluence: '🧩', jira: '🎫', github: '🐙', servicenow: '🛠️', bigquery: '📊',
  };
  return <span className="text-[14px]">{icons[type] ?? '📦'}</span>;
}


// ── Source Drawer ─────────────────────────────────────────────────────────────

function SourceDrawer({
  source,
  onClose,
  onReindex,
  onDelete,
  onRetire,
  onReactivate,
  activeRunId,
}: {
  source: RealKnowledgeSource | null;
  onClose: () => void;
  onReindex: (id: string) => void;
  onDelete: (id: string) => void;
  onRetire: (id: string) => void;
  onReactivate: (id: string) => void;
  activeRunId?: string;
}) {
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [runs, setRuns] = useState<RealPipelineRun[]>([]);
  const [showChunks, setShowChunks] = useState(false);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const navigate = useNavigate();
  const agents = useWorkspace((s) => s.agents);
  const approvals = useWorkspace((s) => s.approvals);

  useEffect(() => {
    if (!source) { setChunks([]); setRuns([]); setShowChunks(false); setConfirmDelete(false); return; }
    // Load run history
    fetch(`/v1/knowledge/sources/${source.id}`)
      .then((r) => r.json())
      .then((d) => setRuns(d.runs ?? []))
      .catch(() => {});
  }, [source?.id]);

  async function loadChunks() {
    if (!source) return;
    setLoadingChunks(true);
    try {
      const res = await fetch(`/v1/knowledge/sources/${source.id}/chunks`);
      const d = await res.json();
      setChunks(d.chunks ?? []);
    } finally {
      setLoadingChunks(false);
      setShowChunks(true);
    }
  }

  if (!source) return null;

  return (
    <Drawer
      open={!!source}
      onClose={onClose}
      title={source.name}
      subtitle={`${source.chunk_count} chunks · ${fmtBytes(source.size_bytes)} · ${source.source_type}`}
    >
      <div className="space-y-5">
        {/* Meta */}
        <div className="rounded-lg border border-border bg-bg-raised px-3 py-2 space-y-1.5 text-[12px]">
          {[
            { label: 'Status', value: <StatusBadge status={source.status} /> },
            { label: 'Lifecycle', value: <Badge tone={source.lifecycle === 'retired' ? 'neutral' : 'ok'}>{source.lifecycle}</Badge> },
            { label: 'Sensitivity', value: <SensitivityBadge s={source.sensitivity} /> },
            { label: 'Domain', value: source.domain ?? <span className="text-text-low">—</span> },
            { label: 'Owner', value: source.owner ?? <span className="text-text-low">—</span> },
            { label: 'Tags', value: source.tags.length ? source.tags.join(', ') : <span className="text-text-low">—</span> },
            { label: 'Freshness', value: source.valid_until ? <FreshnessNote source={source} /> : <span className="text-text-low">No expiry set</span> },
            { label: 'Usage', value: <UsageLabel source={source} /> },
            { label: 'URI', value: <span className="mono text-text-mid break-all">{source.uri}</span> },
            { label: 'Chunks', value: source.chunk_count.toLocaleString() },
            { label: 'Chunking', value: <span className="mono">{source.chunk_size}/{source.chunk_overlap}</span> },
            { label: 'Embedding', value: <EmbeddingProviderBadge provider={source.embedding_provider} /> },
            { label: 'Size', value: fmtBytes(source.size_bytes) },
            { label: 'Created', value: fmtDate(source.created_at) },
            { label: 'Updated', value: fmtDate(source.updated_at) },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-start justify-between gap-4">
              <span className="text-text-low">{label}</span>
              <span className="text-text-hi text-right">{value}</span>
            </div>
          ))}
          {source.error_msg && (
            <div className="mt-1 flex items-start gap-1.5 text-err">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span className="text-[11px]">{source.error_msg}</span>
            </div>
          )}
        </div>

        {/* Bound agents — the blueprint's "Source usage map", mirrors ToolsPage's used_by rendering */}
        <div>
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-low">Bound Agents</div>
          {source.used_by.length ? (
            <div className="space-y-0.5">
              {source.used_by.map((aid) => {
                const a = agents.find((x) => agentId(x) === aid);
                return (
                  <button key={aid} onClick={() => navigate(`/agents/${aid}`)} className="block text-left text-[12px] text-accent hover:underline">
                    {a?.config.identity.agent_name.value ?? aid}
                  </button>
                );
              })}
            </div>
          ) : (
            <span className="text-[12px] text-text-low">Not bound to any agent.</span>
          )}
          {approvals
            .filter((ap) => ap.step === 'data_source' && ap.status === 'pending' && ap.target_ref === `kb://${source.id}`)
            .map((ap) => (
              <div key={ap.id} className="mt-1.5 flex items-center gap-1.5 rounded-md bg-warn/10 px-2 py-1 text-[11px] text-warn">
                <Clock size={11} /> Pending approval to bind to {agents.find((x) => agentId(x) === ap.agent_id)?.config.identity.agent_name.value ?? ap.agent_id}
              </div>
            ))}
        </div>

        {/* Active pipeline run */}
        {activeRunId && (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-low">
              Active Run
            </div>
            <PipelineRunDetail runId={activeRunId} live />
          </div>
        )}

        {/* Run history */}
        {runs.filter((r) => r.id !== activeRunId).length > 0 && (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-low">Run History</div>
            <div className="space-y-2">
              {runs.filter((r) => r.id !== activeRunId).slice(0, 3).map((r) => (
                <div key={r.id} className="rounded-lg border border-border p-2">
                  <PipelineRunDetail runId={r.id} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Query this source — schema browser + ask-my-data for structured sources */}
        {source.status === 'ready' && isStructuredSource(source.source_type, source.mime_type) && (
          <QueryStructuredSourcePanel sourceId={source.id} />
        )}

        {/* Chunk preview */}
        {source.status === 'ready' && (
          <div>
            <button
              className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-text-low hover:text-text-mid"
              onClick={() => (showChunks ? setShowChunks(false) : loadChunks())}
            >
              {showChunks ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Chunk Preview ({source.chunk_count} total)
            </button>
            {loadingChunks && <div className="text-[11px] text-text-low">Loading…</div>}
            {showChunks && (
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {chunks.slice(0, 10).map((c) => (
                  <div key={c.id} className="rounded-md border border-border bg-surface px-3 py-2">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="mono text-[10px] text-text-low">chunk #{c.chunk_index}</span>
                      <span className="text-[10px] text-text-low">{c.text.length} chars</span>
                    </div>
                    <p className="text-[12px] text-text-mid line-clamp-3">{c.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2 pt-1 border-t border-border">
          <Button variant="subtle" size="sm" icon={<RefreshCw size={12} />}
            onClick={() => onReindex(source.id)}
            disabled={source.status === 'indexing' || source.status === 'pending'}
          >
            Re-index
          </Button>
          {source.lifecycle === 'active' ? (
            <Button variant="subtle" size="sm" icon={<Archive size={12} />} onClick={() => onRetire(source.id)}>
              Retire (hide from Retrieval Test)
            </Button>
          ) : (
            <Button variant="subtle" size="sm" icon={<ArchiveRestore size={12} />} onClick={() => onReactivate(source.id)}>
              Reactivate
            </Button>
          )}
          {!confirmDelete ? (
            <Button variant="ghost" size="sm" icon={<Trash2 size={12} />}
              className="text-err hover:bg-err/10"
              onClick={() => setConfirmDelete(true)}
            >
              Delete source
            </Button>
          ) : (
            <div className="rounded-md border border-err/30 bg-err/10 p-2 space-y-2">
              <p className="text-[12px] text-err">This permanently deletes all {source.chunk_count} chunks. Continue?</p>
              <div className="flex gap-2">
                <Button size="sm" className="flex-1 bg-err hover:bg-err/80 text-white border-0"
                  onClick={() => { onDelete(source.id); onClose(); }}>
                  Yes, delete
                </Button>
                <Button variant="ghost" size="sm" className="flex-1" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
}

// ── Sources Tab ───────────────────────────────────────────────────────────────

function SourcesTab() {
  const sources = useWorkspace((s) => s.knowledgeSources);
  const upsert = useWorkspace((s) => s.upsertRealSource);
  const remove = useWorkspace((s) => s.removeRealSource);

  const [showAdd, setShowAdd] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Derive from the live store (not a snapshot) so retire/reactivate/re-index reflect
  // immediately in an already-open drawer instead of showing stale data.
  const selected = selectedId ? sources.find((s) => s.id === selectedId) ?? null : null;
  const [activeRunIds, setActiveRunIds] = useState<Record<string, string>>({});

  // Refresh all sources to pick up status changes
  const refreshSources = useCallback(async () => {
    try {
      const res = await fetch('/v1/knowledge/sources');
      if (!res.ok) return;
      const d = await res.json();
      for (const s of (d.sources ?? [])) upsert(s);
    } catch { /* network */ }
  }, [upsert]);

  // Poll while any source is indexing/pending
  useEffect(() => {
    const indexing = sources.some((s) => s.status === 'indexing' || s.status === 'pending');
    if (!indexing) return;
    const t = setInterval(refreshSources, 3000);
    return () => clearInterval(t);
  }, [sources, refreshSources]);

  function handleCreated(sourceId: string, runId: string) {
    setActiveRunIds((prev) => ({ ...prev, [sourceId]: runId }));
    refreshSources();
  }

  async function handleReindex(id: string) {
    try {
      const res = await fetch(`/v1/knowledge/sources/${id}/reindex`, { method: 'POST' });
      if (!res.ok) return;
      const d = await res.json();
      setActiveRunIds((prev) => ({ ...prev, [id]: d.run_id }));
      refreshSources();
    } catch { /* */ }
  }

  async function handleDelete(id: string) {
    try {
      await fetch(`/v1/knowledge/sources/${id}`, { method: 'DELETE' });
      remove(id);
    } catch { /* */ }
  }

  async function handleRetire(id: string) {
    try {
      const res = await fetch(`/v1/knowledge/sources/${id}/retire`, { method: 'POST' });
      if (!res.ok) return;
      const d = await res.json();
      upsert(d.source);
    } catch { /* */ }
  }

  async function handleReactivate(id: string) {
    try {
      const res = await fetch(`/v1/knowledge/sources/${id}/reactivate`, { method: 'POST' });
      if (!res.ok) return;
      const d = await res.json();
      upsert(d.source);
    } catch { /* */ }
  }

  const domainOptions = Array.from(new Set(sources.map((s) => s.domain).filter((d): d is string => !!d)))
    .sort().map((d) => ({ value: d, label: d }));
  const ownerOptions = Array.from(new Set(sources.map((s) => s.owner).filter((o): o is string => !!o)))
    .sort().map((o) => ({ value: o, label: o }));

  const columns: Column<RealKnowledgeSource>[] = [
    {
      key: 'name', header: 'Name', width: '26%', sortValue: (s) => s.name,
      render: (s) => (
        <div className="flex items-center gap-2 min-w-0">
          <TypeIcon type={s.source_type} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-text-hi truncate">{s.name}</span>
              {s.lifecycle === 'retired' && <Badge tone="neutral">retired</Badge>}
            </div>
            <span className="mono text-[11px] text-text-low truncate block max-w-[320px]">{s.uri}</span>
          </div>
        </div>
      ),
    },
    { key: 'domain', header: 'Domain', sortValue: (s) => s.domain ?? '', render: (s) => s.domain ?? <span className="text-text-low">—</span> },
    { key: 'owner', header: 'Owner', sortValue: (s) => s.owner ?? '', render: (s) => s.owner ?? <span className="text-text-low">—</span> },
    { key: 'sensitivity', header: 'Sensitivity', sortValue: (s) => s.sensitivity, render: (s) => <SensitivityBadge s={s.sensitivity} /> },
    { key: 'embedding', header: 'Embedding', sortValue: (s) => s.embedding_provider, render: (s) => <EmbeddingProviderBadge provider={s.embedding_provider} /> },
    { key: 'status', header: 'Status', sortValue: (s) => s.status, render: (s) => <StatusBadge status={s.status} /> },
    { key: 'chunks', header: 'Chunks', align: 'right', sortValue: (s) => s.chunk_count, render: (s) => s.chunk_count.toLocaleString() },
    { key: 'usage', header: 'Usage', sortValue: (s) => s.last_queried_at ?? '', render: (s) => <UsageLabel source={s} /> },
    { key: 'updated', header: 'Updated', sortValue: (s) => s.updated_at, render: (s) => fmtDate(s.updated_at) },
  ];

  const filters: FilterDef<RealKnowledgeSource>[] = [
    { key: 'status', label: 'Status', options: [
      { value: 'ready', label: 'Ready' }, { value: 'indexing', label: 'Indexing' },
      { value: 'pending', label: 'Pending' }, { value: 'error', label: 'Error' },
    ], predicate: (s, v) => s.status === v },
    { key: 'lifecycle', label: 'Lifecycle', options: [
      { value: 'active', label: 'Active' }, { value: 'retired', label: 'Retired' },
    ], predicate: (s, v) => s.lifecycle === v },
    { key: 'sensitivity', label: 'Sensitivity', options: [
      { value: 'public', label: 'public' }, { value: 'internal', label: 'internal' },
      { value: 'confidential', label: 'confidential' }, { value: 'restricted', label: 'restricted' },
    ], predicate: (s, v) => s.sensitivity === v },
    { key: 'embedding_provider', label: 'Embedding', options: [
      { value: 'openai', label: 'OpenAI' }, { value: 'local_bge_small', label: 'Local (BGE)' },
    ], predicate: (s, v) => s.embedding_provider === v },
  ];
  if (domainOptions.length) {
    filters.push({ key: 'domain', label: 'Domain', options: domainOptions, predicate: (s, v) => s.domain === v });
  }
  if (ownerOptions.length) {
    filters.push({ key: 'owner', label: 'Owner', options: ownerOptions, predicate: (s, v) => s.owner === v });
  }

  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[12px] text-text-low">
          {sources.length} source{sources.length !== 1 ? 's' : ''} · documents are parsed, chunked, and embedded into pgvector
        </p>
        <Button size="sm" icon={<Plus size={13} />} onClick={() => setShowAdd(true)}>
          Add Source
        </Button>
      </div>

      {sources.length === 0 ? (
        <EmptyState
          icon={<Database size={28} />}
          title="No knowledge sources"
          message="Upload a PDF, DOCX, or paste text to create a grounded knowledge base for your agents."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={sources}
          rowKey={(s) => s.id}
          onRowClick={(s) => setSelectedId(s.id)}
          searchText={(s) => `${s.name} ${s.domain ?? ''} ${s.owner ?? ''} ${s.uri}`}
          searchPlaceholder="Search sources…"
          filters={filters}
          initialSort={{ key: 'updated', dir: 'desc' }}
        />
      )}

      <AddSourceModal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onCreated={handleCreated}
      />

      <SourceDrawer
        source={selected}
        onClose={() => setSelectedId(null)}
        onReindex={handleReindex}
        onDelete={handleDelete}
        onRetire={handleRetire}
        onReactivate={handleReactivate}
        activeRunId={selected ? activeRunIds[selected.id] : undefined}
      />
    </>
  );
}

// ── Pipelines Tab ─────────────────────────────────────────────────────────────

function PipelinesTab() {
  const sources = useWorkspace((s) => s.knowledgeSources);
  const [runs, setRuns] = useState<RealPipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetch('/v1/knowledge/pipeline-runs')
      .then((r) => r.json())
      .then((d) => setRuns(d.runs ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-text-low py-8 justify-center">
        <Loader2 size={16} className="animate-spin" /> Loading runs…
      </div>
    );
  }

  if (runs.length === 0) {
    return <EmptyState icon={<Database size={26} />} title="No pipeline runs" message="Add a source to trigger the first ingestion pipeline." />;
  }

  const sourceMap = Object.fromEntries(sources.map((s) => [s.id, s.name]));

  return (
    <div className="space-y-2">
      {runs.map((run) => {
        const isExpanded = expandedId === run.id;
        return (
          <div key={run.id} className="rounded-xl border border-border bg-surface overflow-hidden">
            <button
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-bg-raised transition-colors"
              onClick={() => setExpandedId(isExpanded ? null : run.id)}
            >
              <span className={cn(
                'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold',
                run.status === 'success' ? 'bg-ok/15 text-ok' :
                run.status === 'error' ? 'bg-err/15 text-err' : 'bg-warn/15 text-warn',
              )}>
                {run.status}
              </span>
              <span className="flex-1 text-[13px] font-medium text-text-hi">
                {sourceMap[run.source_id] ?? run.source_id}
              </span>
              <span className="text-[11px] text-text-low">{fmtDate(run.started_at)}</span>
              {run.chunks_created > 0 && (
                <span className="text-[11px] text-text-low">{run.chunks_created} chunks</span>
              )}
              {isExpanded ? <ChevronUp size={13} className="text-text-low" /> : <ChevronDown size={13} className="text-text-low" />}
            </button>
            {isExpanded && (
              <div className="border-t border-border px-4 py-3">
                <PipelineRunDetail runId={run.id} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') ?? 'sources';
  const setTab = (t: string) => setParams((p) => { p.set('tab', t); return p; });
  const sources = useWorkspace((s) => s.knowledgeSources);
  const upsert = useWorkspace((s) => s.upsertRealSource);
  const [config, setConfig] = useState<KnowledgeConfig | null>(null);

  // Load sources if not already bootstrapped
  useEffect(() => {
    if (sources.length > 0) return;
    fetch('/v1/knowledge/sources')
      .then((r) => r.json())
      .then((d) => { for (const s of (d.sources ?? [])) upsert(s); })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch('/v1/knowledge/config')
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => {});
  }, []);

  const readySources = sources.filter((s) => s.status === 'ready' && s.lifecycle === 'active');

  const tabs: TabItem[] = [
    { key: 'sources', label: 'Sources', count: sources.length },
    { key: 'pipelines', label: 'Pipelines' },
    { key: 'test', label: 'Retrieval Test', count: readySources.length },
  ];

  return (
    <div className={cn('flex flex-col', tab === 'test' ? 'h-[calc(100vh-120px)]' : '')}>
      <PageHeader
        title="Knowledge & RAG"
        description="Upload documents, trigger ingestion pipelines, and test vector retrieval — all backed by pgvector."
      />
      {config && !config.embeddings_configured && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[12px] text-warn">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>
            Embeddings are not configured (<span className="mono">OPENAI_API_KEY</span> missing on the backend).
            Uploads will fail at the embed stage and Retrieval Test will not run until this is set.
          </span>
        </div>
      )}
      <Tabs items={tabs} active={tab} onChange={setTab} className="mb-4" />
      {tab === 'sources' && <SourcesTab />}
      {tab === 'pipelines' && <PipelinesTab />}
      {tab === 'test' && <RetrievalTestPanel sources={sources} />}
    </div>
  );
}
