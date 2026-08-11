import { useEffect, useMemo, useState } from 'react';
import { Search, ChevronDown, ChevronUp, Zap, Quote, History } from 'lucide-react';
import type { RealKnowledgeSource, RetrievalResult, RetrievalResponse, KnowledgeConfig } from '@/types';
import { Button, Badge } from '@/components/primitives';
import { cn } from '@/utils/cn';

interface RetrievalTestRun {
  id: string;
  query: string;
  source_ids: string[];
  top_k: number;
  score_threshold: number;
  rerank_enabled: boolean;
  result_count: number;
  passed_count: number;
  latency_ms: number;
  estimated_cost_usd: number | null;
  created_at: string;
}

interface Props {
  sources: RealKnowledgeSource[];
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.8 ? 'bg-ok/15 text-ok' :
    score >= 0.5 ? 'bg-warn/15 text-warn' :
    'bg-border/40 text-text-low';
  return (
    <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold tabular-nums', color)}>
      {pct}%
    </span>
  );
}

function ResultCard({ result, idx, sourceName }: { result: RetrievalResult; idx: number; sourceName: string }) {
  const [expanded, setExpanded] = useState(idx < 2);
  const citation = `[${sourceName}, chunk #${result.chunk_index}]`;
  return (
    <div className={cn(
      'rounded-lg border transition-all',
      result.passed ? 'border-border bg-surface' : 'border-border/50 bg-surface/50 opacity-70',
    )}>
      <button
        className="flex w-full items-start gap-3 px-3 py-2.5 text-left"
        onClick={() => setExpanded((x) => !x)}
      >
        <span className="mt-0.5 shrink-0 text-[11px] font-bold text-text-low">#{idx + 1}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <ScoreBadge score={result.score} />
            <span className="mono text-[10px] text-text-low truncate">{citation}</span>
            {!result.passed && (
              <span className="text-[10px] text-err">below threshold</span>
            )}
          </div>
          {!expanded && (
            <p className="mt-1 text-[12px] text-text-mid line-clamp-2">{result.text}</p>
          )}
        </div>
        {expanded ? (
          <ChevronUp size={13} className="mt-0.5 shrink-0 text-text-low" />
        ) : (
          <ChevronDown size={13} className="mt-0.5 shrink-0 text-text-low" />
        )}
      </button>
      {expanded && (
        <div className="border-t border-border px-3 py-2 space-y-2">
          <p className="text-[12px] leading-relaxed text-text-mid whitespace-pre-wrap">{result.text}</p>
          <div className="flex items-center gap-1.5 text-[11px] text-accent">
            <Quote size={11} className="shrink-0" />
            <span className="mono">{citation}</span>
          </div>
          {(result.vector_score !== undefined || result.rerank_score !== undefined) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-text-low">
              {result.vector_score !== undefined && <span>vector: <span className="mono text-text-mid">{result.vector_score.toFixed(4)}</span></span>}
              {result.rerank_score !== undefined && <span>rerank: <span className="mono text-text-mid">{result.rerank_score.toFixed(4)}</span></span>}
              {result.matched_terms && result.matched_terms.length > 0 && (
                <span>matched terms: <span className="mono text-text-mid">{result.matched_terms.join(', ')}</span></span>
              )}
            </div>
          )}
          <div className="text-[10px] text-text-low">
            doc: <span className="mono">{result.doc_id}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function RetrievalTestPanel({ sources }: Props) {
  const readySources = useMemo(
    () => sources.filter((s) => s.status === 'ready' && s.lifecycle === 'active'),
    [sources],
  );

  const [query, setQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.0);
  const [rerankEnabled, setRerankEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<RetrievalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<KnowledgeConfig | null>(null);

  const [domainFilter, setDomainFilter] = useState('all');
  const [ownerFilter, setOwnerFilter] = useState('all');
  const [sensitivityFilter, setSensitivityFilter] = useState('all');
  const [recentRuns, setRecentRuns] = useState<RetrievalTestRun[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    fetch('/v1/knowledge/config').then((r) => r.json()).then(setConfig).catch(() => {});
  }, []);

  const loadRecentRuns = () => {
    fetch('/v1/knowledge/retrieval-test-runs')
      .then((r) => r.json())
      .then((d) => setRecentRuns(d.runs ?? []))
      .catch(() => {});
  };

  const domains = useMemo(() => Array.from(new Set(readySources.map((s) => s.domain).filter((d): d is string => !!d))).sort(), [readySources]);
  const owners = useMemo(() => Array.from(new Set(readySources.map((s) => s.owner).filter((o): o is string => !!o))).sort(), [readySources]);
  const sensitivities = useMemo(() => Array.from(new Set(readySources.map((s) => s.sensitivity))).sort(), [readySources]);

  const filteredSources = useMemo(() => readySources.filter((s) =>
    (domainFilter === 'all' || s.domain === domainFilter) &&
    (ownerFilter === 'all' || s.owner === ownerFilter) &&
    (sensitivityFilter === 'all' || s.sensitivity === sensitivityFilter),
  ), [readySources, domainFilter, ownerFilter, sensitivityFilter]);

  const sourceNameById = useMemo(() => Object.fromEntries(sources.map((s) => [s.id, s.name])), [sources]);

  // A 1536-dim OpenAI vector and a 384-dim BGE vector can't be searched together —
  // once one source is checked, lock the picker to its provider rather than letting
  // the user build an invalid selection and find out after clicking Search.
  const activeProvider = useMemo(() => {
    const first = selectedIds.map((id) => sources.find((s) => s.id === id)).find(Boolean);
    return first?.embedding_provider ?? null;
  }, [selectedIds, sources]);

  function toggleSource(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function handleSearch() {
    if (!query.trim()) return;
    if (selectedIds.length === 0) { setError('Select at least one source to search.'); return; }
    setLoading(true); setError(null); setResponse(null);
    try {
      const res = await fetch('/v1/knowledge/retrieve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          source_ids: selectedIds,
          top_k: topK,
          score_threshold: threshold,
          rerank_enabled: rerankEnabled,
        }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Error ${res.status}`);
      }
      const data: RetrievalResponse = await res.json();
      setResponse(data);
      loadRecentRuns();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }

  const results = response?.results ?? null;
  const passed = results?.filter((r) => r.passed) ?? [];
  const failed = results?.filter((r) => !r.passed) ?? [];

  return (
    <div className="grid grid-cols-[300px_1fr] gap-4 h-full">
      {/* Left panel — query controls */}
      <div className="space-y-4 overflow-y-auto rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap size={14} className="text-accent" />
            <span className="text-[12px] font-semibold text-text-hi">Retrieval Test</span>
          </div>
        </div>

        {/* Query */}
        <label className="block text-[11px] font-medium text-text-low">
          Query
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="What does the refund policy say?"
            rows={4}
            className="mt-1 w-full rounded-md border border-border bg-raised px-2.5 py-2 text-[12px] text-text-hi placeholder:text-text-low focus:border-accent focus:outline-none resize-none"
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSearch(); }}
          />
        </label>

        {/* Feature Toggles */}
        <div className="rounded-lg border border-border bg-raised p-2.5 space-y-2">
          <div className="text-[11px] font-semibold text-text-hi">Pipeline Feature Toggles</div>
          <label className="flex cursor-pointer items-center justify-between">
            <span className="text-[11px] text-text-mid">2-Stage Hybrid Reranker</span>
            <input
              type="checkbox"
              checked={rerankEnabled}
              onChange={(e) => setRerankEnabled(e.target.checked)}
              className="accent-accent h-4 w-4 rounded"
            />
          </label>
        </div>

        {/* Real pipeline configuration — read-only, sourced from the backend */}
        {config && (
          <div className="rounded-lg border border-border bg-raised p-2.5 space-y-1 text-[11px]">
            <div className="font-semibold text-text-hi">Pipeline Configuration</div>
            <div className="flex justify-between text-text-low"><span>OpenAI model</span><span className="mono text-text-mid">{config.embedding_model}</span></div>
            <div className="flex justify-between text-text-low"><span>Local model</span><span className="mono text-text-mid">{config.local_embedding_model}</span></div>
            <div className="flex justify-between text-text-low"><span>Vector store</span><span className="text-text-mid text-right">{config.vector_store}</span></div>
            <div className="flex justify-between text-text-low"><span>Reranker</span><span className="text-text-mid text-right">{config.reranker}</span></div>
            {!config.embeddings_configured && (
              <div className="pt-1 text-warn">OpenAI: OPENAI_API_KEY not configured.</div>
            )}
            {!config.local_embeddings_available && (
              <div className="pt-1 text-warn">Local: sentence-transformers not installed on the server.</div>
            )}
          </div>
        )}

        {/* Metadata filters — real filter over real tag data, computed client-side */}
        {(domains.length > 0 || owners.length > 0 || sensitivities.length > 1) && (
          <div className="space-y-1.5">
            <div className="text-[11px] font-medium text-text-low">Filter sources by</div>
            <div className="flex flex-wrap gap-1.5">
              {domains.length > 0 && (
                <select value={domainFilter} onChange={(e) => setDomainFilter(e.target.value)}
                  className="rounded-md border border-border bg-raised px-2 py-1 text-[11px] text-text-hi focus:border-accent focus:outline-none">
                  <option value="all">All domains</option>
                  {domains.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              )}
              {owners.length > 0 && (
                <select value={ownerFilter} onChange={(e) => setOwnerFilter(e.target.value)}
                  className="rounded-md border border-border bg-raised px-2 py-1 text-[11px] text-text-hi focus:border-accent focus:outline-none">
                  <option value="all">All owners</option>
                  {owners.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              )}
              {sensitivities.length > 1 && (
                <select value={sensitivityFilter} onChange={(e) => setSensitivityFilter(e.target.value)}
                  className="rounded-md border border-border bg-raised px-2 py-1 text-[11px] text-text-hi focus:border-accent focus:outline-none">
                  <option value="all">All sensitivities</option>
                  {sensitivities.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
            </div>
          </div>
        )}

        {/* Source selection */}
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px] font-medium text-text-low">
            <span>Sources to search</span>
            {activeProvider && (
              <span className="text-[10px] text-text-low">
                locked to {activeProvider === 'local_bge_small' ? 'Local (BGE)' : 'OpenAI'}
              </span>
            )}
          </div>
          {filteredSources.length === 0 ? (
            <div className="text-[11px] text-text-low italic">
              {readySources.length === 0 ? 'No ready sources yet' : 'No sources match the selected filters'}
            </div>
          ) : (
            <div className="space-y-1 max-h-[180px] overflow-y-auto">
              {filteredSources.map((src) => {
                const disabled = activeProvider !== null && src.embedding_provider !== activeProvider;
                return (
                  <label key={src.id}
                    title={disabled ? `This source uses ${src.embedding_provider === 'local_bge_small' ? 'Local (BGE)' : 'OpenAI'} embeddings — deselect the other provider's sources first.` : undefined}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5',
                      disabled ? 'cursor-not-allowed opacity-40' : 'cursor-pointer hover:bg-raised',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(src.id)}
                      onChange={() => toggleSource(src.id)}
                      disabled={disabled}
                      className="accent-accent"
                    />
                    <span className="flex-1 min-w-0 text-[12px] text-text-hi truncate">{src.name}</span>
                    <span className="shrink-0 text-[9px] text-text-low">{src.embedding_provider === 'local_bge_small' ? 'BGE' : 'OpenAI'}</span>
                    <span className="shrink-0 text-[10px] text-text-low">{src.chunk_count} chunks</span>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        {/* Top-K */}
        <label className="block text-[11px] font-medium text-text-low">
          Top-K results: <span className="text-text-hi font-semibold">{topK}</span>
          <input type="range" min={1} max={20} value={topK} onChange={(e) => setTopK(Number(e.target.value))}
            className="mt-1 w-full accent-accent" />
        </label>

        {/* Threshold */}
        <label className="block text-[11px] font-medium text-text-low">
          Score threshold: <span className="text-text-hi font-semibold">{threshold.toFixed(2)}</span>
          <input type="range" min={0} max={1} step={0.05} value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="mt-1 w-full accent-accent" />
        </label>

        <Button size="sm" className="w-full" onClick={handleSearch} disabled={loading || !query.trim()}
          icon={<Search size={13} />}>
          {loading ? 'Searching…' : 'Search (⌘↵)'}
        </Button>

        {error && (
          <div className="rounded-md border border-err/30 bg-err/10 px-3 py-2 text-[11px] text-err">{error}</div>
        )}

        {/* Recent tests — real, persisted (Blueprint 3.3 "retrieval test results") */}
        <div>
          <button
            className="flex items-center gap-1 text-[11px] font-medium text-text-low hover:text-text-mid"
            onClick={() => (showHistory ? setShowHistory(false) : (loadRecentRuns(), setShowHistory(true)))}
          >
            <History size={11} /> Recent tests {showHistory ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
          {showHistory && (
            <div className="mt-1.5 space-y-1 max-h-[160px] overflow-y-auto">
              {recentRuns.length === 0 ? (
                <div className="text-[11px] text-text-low italic">No test runs yet.</div>
              ) : recentRuns.map((r) => (
                <div key={r.id} className="rounded-md border border-border bg-raised px-2 py-1.5 text-[11px]">
                  <div className="truncate text-text-hi" title={r.query}>{r.query}</div>
                  <div className="mt-0.5 flex justify-between text-[10px] text-text-low">
                    <span>{r.passed_count}/{r.result_count} passed</span>
                    <span>{r.latency_ms.toFixed(0)}ms</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right panel — results */}
      <div className="overflow-y-auto">
        {results === null && !loading && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-text-low">
            <Search size={28} className="opacity-30" />
            <p className="text-[13px]">Run a query to test your knowledge sources</p>
          </div>
        )}

        {loading && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-text-low">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-accent" />
            <p className="text-[12px]">Searching…</p>
          </div>
        )}

        {results !== null && response && !loading && (
          <div className="space-y-2">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[12px] font-semibold text-text-hi">
                {results.length} results
              </span>
              <div className="flex items-center gap-3 text-[11px] text-text-low">
                <span><span className="font-semibold text-ok">{passed.length}</span> passed threshold</span>
                {failed.length > 0 && <span><span className="font-semibold text-text-low">{failed.length}</span> below threshold</span>}
                <Badge tone="info">{response.latency_ms.toFixed(0)} ms</Badge>
                <Badge tone="neutral">{response.embedding_provider === 'local_bge_small' ? 'Local (BGE)' : 'OpenAI'}</Badge>
                {response.estimated_cost_usd !== null && (
                  <Badge tone="neutral">${response.estimated_cost_usd.toFixed(6)}</Badge>
                )}
              </div>
            </div>

            {results.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-10 text-text-low">
                <Search size={22} className="opacity-40" />
                <p className="text-[12px]">No results — try a different query or lower the threshold</p>
              </div>
            ) : (
              <div className="space-y-2">
                {results.map((r, i) => (
                  <ResultCard key={`${r.source_id}-${r.chunk_index}`} result={r} idx={i}
                    sourceName={sourceNameById[r.source_id] ?? r.source_id} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
