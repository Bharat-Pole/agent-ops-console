// Real Knowledge & RAG types — backed by the backend DB (not seed data).
// These are separate from the old Prov-wrapped KnowledgeSource in assets.ts
// which is kept for backward compatibility with the existing seed/agent config.

export type KnowledgeSourceStatus = 'pending' | 'indexing' | 'ready' | 'error';
export type KnowledgeSourceType =
  | 'file' | 'url' | 'text' | 'database'
  | 'confluence' | 'jira' | 'github' | 'servicenow' | 'bigquery';
export type KnowledgeSensitivity = 'public' | 'internal' | 'confidential' | 'restricted';
export type KnowledgeLifecycle = 'active' | 'retired';
export type EmbeddingProvider = 'openai' | 'local_bge_small';

export interface RealKnowledgeSource {
  id: string;
  name: string;
  source_type: KnowledgeSourceType;
  mime_type: string | null;
  uri: string;
  status: KnowledgeSourceStatus;
  sensitivity: KnowledgeSensitivity;
  ingestion_mode: 'hybrid' | 'vector' | 'sql';
  chunk_count: number;
  size_bytes: number;
  error_msg: string | null;
  domain: string | null;
  owner: string | null;
  tags: string[];
  valid_until: string | null;
  lifecycle: KnowledgeLifecycle;
  last_queried_at: string | null;
  chunk_size: number;
  chunk_overlap: number;
  connector_config_masked: string | null;
  embedding_provider: EmbeddingProvider;
  has_raw_text: boolean;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeConfig {
  embeddings_configured: boolean;
  embedding_model: string;
  embedding_dimension: number;
  vector_store: string;
  reranker: string;
  cost_per_1k_tokens_usd: number | null;
  local_embeddings_available: boolean;
  local_embedding_model: string;
  local_embedding_dimension: number;
  text_to_sql_providers: {
    anthropic: { configured: boolean; model: string };
    groq: { configured: boolean; model: string };
  };
}

export type TextToSqlProvider = 'anthropic' | 'groq';

export type PipelineRunStatus = 'running' | 'success' | 'error';
export type PipelineStageStatus = 'pending' | 'running' | 'done' | 'error';
export type PipelineStageName = 'fetch' | 'parse' | 'chunk' | 'embed' | 'store' | 'finalize';

export interface RealPipelineStage {
  id: string;
  run_id: string;
  stage_name: PipelineStageName;
  status: PipelineStageStatus;
  items_total: number;
  items_done: number;
  error_msg: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface RealPipelineRun {
  id: string;
  source_id: string;
  trigger: 'manual' | 'api' | 'schedule';
  status: PipelineRunStatus;
  chunks_created: number;
  error_msg: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  stages?: RealPipelineStage[];
}

export interface KnowledgeChunk {
  id: string;
  doc_id: string;
  chunk_index: number;
  text: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface RetrievalResult {
  doc_id: string;
  source_id: string;
  text: string;
  chunk_index: number;
  score: number;
  passed: boolean;
  vector_score?: number;
  rerank_score?: number;
  matched_terms?: string[];
}

export interface RetrievalResponse {
  results: RetrievalResult[];
  query: string;
  rerank_enabled: boolean;
  latency_ms: number;
  query_tokens: number | null;
  estimated_cost_usd: number | null;
  embedding_provider: EmbeddingProvider;
}
