import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, Database, Loader2, Search, AlertCircle } from 'lucide-react';
import { Button } from '@/components/primitives';
import { cn } from '@/utils/cn';

interface SchemaColumn {
  column: string;
  type: string;
}

interface SchemaResponse {
  tables: Record<string, SchemaColumn[]>;
}

interface AskResponse {
  question: string;
  llm_provider: string;
  generated_sql: string;
  row_count: number;
  truncated: boolean;
  rows: Record<string, unknown>[];
}

interface ProviderStatus {
  configured: boolean;
  model: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  groq: 'Groq (Llama 3.3 70B)',
};

export function isStructuredSource(sourceType: string, mimeType: string | null): boolean {
  if (sourceType === 'database' || sourceType === 'bigquery') return true;
  if (sourceType === 'file' && mimeType) {
    return mimeType.toLowerCase().includes('csv') || mimeType.toLowerCase().includes('spreadsheetml');
  }
  return false;
}

export function QueryStructuredSourcePanel({ sourceId }: { sourceId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);

  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const [providers, setProviders] = useState<Record<string, ProviderStatus> | null>(null);
  const [llmProvider, setLlmProvider] = useState<string>('anthropic');

  useEffect(() => {
    if (!expanded || schema || schemaError) return;
    setLoadingSchema(true);
    fetch(`/v1/knowledge/sources/${sourceId}/schema`)
      .then(async (r) => {
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `Error ${r.status}`); }
        return r.json();
      })
      .then(setSchema)
      .catch((e: Error) => setSchemaError(e.message))
      .finally(() => setLoadingSchema(false));
  }, [expanded, schema, schemaError, sourceId]);

  useEffect(() => {
    if (!expanded || providers) return;
    fetch('/v1/knowledge/config')
      .then((r) => r.json())
      .then((cfg) => {
        const p = cfg.text_to_sql_providers as Record<string, ProviderStatus> | undefined;
        if (!p) return;
        setProviders(p);
        if (!p.anthropic?.configured && p.groq?.configured) setLlmProvider('groq');
      })
      .catch(() => {});
  }, [expanded, providers]);

  async function handleAsk() {
    if (!question.trim()) return;
    setAsking(true); setAskError(null); setAnswer(null);
    try {
      const res = await fetch(`/v1/knowledge/sources/${sourceId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim(), llm_provider: llmProvider }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
      setAnswer(data);
    } catch (e: unknown) {
      setAskError(e instanceof Error ? e.message : 'Failed to answer question');
    } finally {
      setAsking(false);
    }
  }

  const resultColumns = answer && answer.rows.length > 0 ? Object.keys(answer.rows[0]) : [];

  return (
    <div className="rounded-lg border border-border">
      <button
        className="flex w-full items-center gap-1.5 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-text-low hover:text-text-mid"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        <Database size={12} /> Query this source
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-border px-3 py-3">
          {/* Schema */}
          {loadingSchema && (
            <div className="flex items-center gap-2 text-[11px] text-text-low">
              <Loader2 size={12} className="animate-spin" /> Loading schema…
            </div>
          )}
          {schemaError && (
            <div className="flex items-start gap-1.5 rounded-md bg-err/10 px-2.5 py-1.5 text-[11px] text-err">
              <AlertCircle size={12} className="mt-0.5 shrink-0" /> {schemaError}
            </div>
          )}
          {schema && (
            <div className="max-h-[140px] space-y-2 overflow-y-auto rounded-md border border-border bg-raised p-2">
              {Object.entries(schema.tables).map(([table, cols]) => (
                <div key={table}>
                  <div className="mono text-[11px] font-semibold text-text-hi">{table}</div>
                  <div className="mono text-[10px] text-text-low">
                    {cols.map((c) => `${c.column} (${c.type})`).join(', ')}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Ask */}
          {providers && (
            <label className="block text-[11px] font-medium text-text-low">
              Model
              <select
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-raised px-2.5 py-1.5 text-[12px] text-text-hi focus:border-accent focus:outline-none"
              >
                {Object.entries(providers).map(([key, status]) => (
                  <option key={key} value={key}>
                    {PROVIDER_LABELS[key] || key}
                    {!status.configured ? ' — not configured' : ''}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="block text-[11px] font-medium text-text-low">
            Ask a question about this data
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What's the average resolution time for P1 incidents?"
              rows={2}
              className="mt-1 w-full rounded-md border border-border bg-raised px-2.5 py-1.5 text-[12px] text-text-hi placeholder:text-text-low focus:border-accent focus:outline-none resize-none"
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleAsk(); }}
            />
          </label>
          <Button size="sm" icon={<Search size={12} />} onClick={handleAsk} disabled={asking || !question.trim()}>
            {asking ? 'Generating & running SQL…' : 'Ask (⌘↵)'}
          </Button>

          {askError && (
            <div className="flex items-start gap-1.5 rounded-md bg-err/10 px-2.5 py-1.5 text-[11px] text-err">
              <AlertCircle size={12} className="mt-0.5 shrink-0" /> {askError}
            </div>
          )}

          {answer && (
            <div className="space-y-2">
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-low">
                  Generated SQL · {PROVIDER_LABELS[answer.llm_provider] || answer.llm_provider}
                </div>
                <pre className="mono overflow-x-auto rounded-md border border-border bg-raised px-2.5 py-1.5 text-[11px] text-text-mid">{answer.generated_sql}</pre>
              </div>
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-low">
                  {answer.row_count} row{answer.row_count !== 1 ? 's' : ''}{answer.truncated ? ' (truncated)' : ''}
                </div>
                {answer.rows.length === 0 ? (
                  <div className="text-[11px] text-text-low italic">No rows returned.</div>
                ) : (
                  <div className="max-h-[220px] overflow-auto rounded-md border border-border">
                    <table className="w-full text-[11px]">
                      <thead className="sticky top-0 bg-raised">
                        <tr>
                          {resultColumns.map((c) => (
                            <th key={c} className="mono border-b border-border px-2 py-1 text-left text-text-low">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {answer.rows.map((row, i) => (
                          <tr key={i} className={cn(i % 2 === 1 && 'bg-raised/40')}>
                            {resultColumns.map((c) => (
                              <td key={c} className="mono px-2 py-1 text-text-mid">{String(row[c] ?? '—')}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
