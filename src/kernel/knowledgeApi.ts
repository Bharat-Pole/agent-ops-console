// Knowledge & RAG API client
// All calls go to /v1/knowledge/* on the FastAPI backend.
//
// NOTE: as of this revision, the Knowledge & RAG UI components (KnowledgePage,
// AddSourceModal, PipelineRunDetail, RetrievalTestPanel) still call fetch()
// inline rather than through this client — migrating them is tracked as
// follow-up cleanup, not done in this pass. This file is kept accurate to the
// real backend contract so it's ready to wire in without further changes.

import type {
  RealKnowledgeSource,
  RealPipelineRun,
  KnowledgeChunk,
  RetrievalResponse,
  KnowledgeConfig,
} from '@/types';

const BASE = '/v1/knowledge';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

interface SharedMeta {
  domain?: string;
  owner?: string;
  tags?: string;
  valid_until?: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

interface CreatedSource {
  source: RealKnowledgeSource;
  run_id: string;
}

// ── Sources ──────────────────────────────────────────────────────────────────

export async function listSources(): Promise<RealKnowledgeSource[]> {
  const data = await getJson<{ sources: RealKnowledgeSource[] }>(`${BASE}/sources`);
  return data.sources;
}

export async function getSource(
  id: string,
): Promise<{ source: RealKnowledgeSource; runs: RealPipelineRun[] }> {
  return getJson(`${BASE}/sources/${encodeURIComponent(id)}`);
}

export async function uploadFile(
  file: File,
  name: string,
  sensitivity: string,
  opts: SharedMeta & { ingestionMode?: 'hybrid' | 'vector' | 'sql' } = {},
): Promise<CreatedSource> {
  const form = new FormData();
  form.append('file', file);
  form.append('name', name);
  form.append('sensitivity', sensitivity);
  form.append('ingestion_mode', opts.ingestionMode ?? 'hybrid');
  form.append('domain', opts.domain ?? '');
  form.append('owner', opts.owner ?? '');
  form.append('tags', opts.tags ?? '');
  form.append('valid_until', opts.valid_until ?? '');
  form.append('chunk_size', String(opts.chunk_size ?? 800));
  form.append('chunk_overlap', String(opts.chunk_overlap ?? 100));

  const res = await fetch(`${BASE}/sources/upload`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function addUrlSource(url: string, name: string, sensitivity: string, meta: SharedMeta = {}): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/url`, { url, name, sensitivity, ...meta });
}

export async function addTextSource(text: string, name: string, sensitivity: string, meta: SharedMeta = {}): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/text`, { text, name, sensitivity, ...meta });
}

export async function addDatabaseSource(connectionUrl: string, query: string, name: string, sensitivity: string, meta: SharedMeta = {}): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/database`, { connection_url: connectionUrl, query, name, sensitivity, ...meta });
}

export async function addConfluenceSource(
  params: { baseUrl: string; email: string; apiToken: string; pageId?: string; spaceKey?: string; name?: string; sensitivity?: string } & SharedMeta,
): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/confluence`, {
    ...params,
    base_url: params.baseUrl, email: params.email, api_token: params.apiToken,
    page_id: params.pageId ?? '', space_key: params.spaceKey ?? '', name: params.name ?? '',
    sensitivity: params.sensitivity ?? 'internal',
  });
}

export async function addJiraSource(
  params: { baseUrl: string; email: string; apiToken: string; jql: string; name?: string; sensitivity?: string } & SharedMeta,
): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/jira`, {
    ...params,
    base_url: params.baseUrl, email: params.email, api_token: params.apiToken,
    jql: params.jql, name: params.name ?? '', sensitivity: params.sensitivity ?? 'internal',
  });
}

export async function addGithubSource(
  params: { repoOwner: string; repo: string; path?: string; branch?: string; token?: string; name?: string; sensitivity?: string } & SharedMeta,
): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/github`, {
    ...params,
    repo_owner: params.repoOwner, repo: params.repo, path: params.path ?? '', branch: params.branch ?? '',
    token: params.token ?? '', name: params.name ?? '', sensitivity: params.sensitivity ?? 'internal',
  });
}

export async function addServiceNowSource(
  params: { instanceUrl: string; table: string; username: string; password: string; query?: string; name?: string; sensitivity?: string } & SharedMeta,
): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/servicenow`, {
    ...params,
    instance_url: params.instanceUrl, table: params.table, username: params.username, password: params.password,
    query: params.query ?? '', name: params.name ?? '', sensitivity: params.sensitivity ?? 'internal',
  });
}

export async function addBigQuerySource(
  params: { serviceAccountJson: string; query: string; name?: string; sensitivity?: string } & SharedMeta,
): Promise<CreatedSource> {
  return postJson(`${BASE}/sources/bigquery`, {
    ...params,
    service_account_json: params.serviceAccountJson, query: params.query, name: params.name ?? '',
    sensitivity: params.sensitivity ?? 'internal',
  });
}

export async function testConnection(sourceType: string, config: Record<string, unknown>): Promise<{ ok: boolean; detail: string }> {
  return postJson(`${BASE}/sources/test-connection`, { source_type: sourceType, config });
}

export async function reindexSource(id: string, chunkSettings?: { chunk_size?: number; chunk_overlap?: number }): Promise<{ run_id: string }> {
  return postJson(`${BASE}/sources/${encodeURIComponent(id)}/reindex`, chunkSettings ?? {});
}

export async function deleteSource(id: string): Promise<void> {
  const res = await fetch(`${BASE}/sources/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

export async function updateSourceMetadata(id: string, meta: SharedMeta): Promise<RealKnowledgeSource> {
  const data = await fetch(`${BASE}/sources/${encodeURIComponent(id)}/metadata`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(meta),
  });
  if (!data.ok) throw new Error(`Metadata update failed: ${data.status}`);
  return (await data.json()).source;
}

export async function retireSource(id: string): Promise<RealKnowledgeSource> {
  const data = await postJson<{ source: RealKnowledgeSource }>(`${BASE}/sources/${encodeURIComponent(id)}/retire`, {});
  return data.source;
}

export async function reactivateSource(id: string): Promise<RealKnowledgeSource> {
  const data = await postJson<{ source: RealKnowledgeSource }>(`${BASE}/sources/${encodeURIComponent(id)}/reactivate`, {});
  return data.source;
}

// ── Chunks ───────────────────────────────────────────────────────────────────

export async function getChunks(
  sourceId: string,
  limit = 20,
): Promise<{ chunks: KnowledgeChunk[]; total: number }> {
  return getJson(`${BASE}/sources/${encodeURIComponent(sourceId)}/chunks?limit=${limit}`);
}

// ── Pipeline Runs ─────────────────────────────────────────────────────────────

export async function listPipelineRuns(): Promise<RealPipelineRun[]> {
  const data = await getJson<{ runs: RealPipelineRun[] }>(`${BASE}/pipeline-runs`);
  return data.runs;
}

export async function getPipelineRun(runId: string): Promise<RealPipelineRun> {
  const data = await getJson<{ run: RealPipelineRun }>(
    `${BASE}/pipeline-runs/${encodeURIComponent(runId)}`,
  );
  return data.run;
}

// ── Retrieval Test ────────────────────────────────────────────────────────────

export async function testRetrieval(
  query: string,
  sourceIds: string[],
  topK = 5,
  scoreThreshold = 0.0,
  rerankEnabled = true,
): Promise<RetrievalResponse> {
  return postJson(`${BASE}/retrieve`, {
    query,
    source_ids: sourceIds,
    top_k: topK,
    score_threshold: scoreThreshold,
    rerank_enabled: rerankEnabled,
  });
}

// ── Config / Health ───────────────────────────────────────────────────────────

export async function getConfig(): Promise<KnowledgeConfig> {
  return getJson(`${BASE}/config`);
}
