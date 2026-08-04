// Section 11 — Playground response mechanics. `refusal`/`tool_call` are still
// fully deterministic here (no LLM needed, no server round trip). For
// `grounded_answer`/`general_answer`, real retrieval (Phase 3, server-side
// cosine similarity over embedded knowledge chunks — see
// server/services/retrieval.ts) and real prose (Phase 2, Claude — see
// kernel/services.ts's chatWithAgent) both come from the server; this module
// only returns a minimal placeholder for those two kinds, used as a fallback
// if the server is unreachable or has no API key configured.

import type { AgentRecord, PromptAsset, ToolAsset } from '@/types';

// Resolves a `prompts://<id>@<version>` reference against the prompts store
// slice; returns the literal string unchanged if it isn't a prompts:// ref
// (some config fields hold literal text), or null if the ref doesn't resolve.
export function resolvePromptRef(ref: string | null | undefined, prompts: PromptAsset[]): string | null {
  if (!ref) return null;
  if (!ref.startsWith('prompts://')) return ref;
  const [id, version] = ref.slice('prompts://'.length).split('@');
  return prompts.find((p) => p.id === id && p.version === version)?.body ?? null;
}

export type MessageKind = 'refusal' | 'grounded_answer' | 'tool_call' | 'general_answer';

export interface RetrievalChunk {
  doc_id: string;
  source_id: string;
  text: string;
  score: number;
  passed: boolean;
}
export interface ToolCallBlock {
  tool_id: string;
  permission: string;
  result: string;
  requiresHitl: boolean;
}
export interface PlaygroundResponse {
  kind: MessageKind;
  text: string;
  citations: string[];
  retrieval: RetrievalChunk[];
  toolCalls: ToolCallBlock[];
  routing: string[];
  tokenCount: number;
  shapedBy: string[];
}

const WRITE_VERBS = ['send', 'approve', 'deploy', 'update', 'create', 'delete', 'close', 'assign', 'notify', 'post', 'execute', 'modify', 'file', 'submit', 'remove', 'email'];
const ADVISORY_FRAMES = ['draft', 'summarize', 'recommend', 'what', 'how', 'explain', 'show', 'list'];

// Decides refusal/grounded/tool_call/general. No longer pre-judges
// "groundable" by matching message words against KB *content* (that required
// `sources` data client-side and is what caused the old retrieval-scoring
// bug — real retrieval now always runs server-side for any question-shaped
// message when RAG is enabled, regardless of whether it happens to share
// vocabulary with a snippet). `isQuestion` is purely message-shape, no source
// data needed — it exists only to keep this ordered ahead of the tool_call
// check, since a loose tool-name substring match (e.g. "incident_reader" →
// "incident") would otherwise swallow plain questions like "summarize the
// latest incident" before they ever reached the grounded-answer path.
function classify(agent: AgentRecord, message: string, boundToolIds: string[]): MessageKind {
  const t = message.toLowerCase();
  // 1) write-verb (not in an advisory frame) → refusal
  const hasWrite = WRITE_VERBS.some((v) => new RegExp(`\\b${v}\\b`).test(t));
  const advisory = ADVISORY_FRAMES.some((f) => t.includes(f));
  if (hasWrite && !advisory) return 'refusal';
  // 2) question-shaped + RAG-enabled → attempt a real grounded answer
  const isQuestion = /\?$/.test(message.trim()) || /^(what|how|which|summarize|show|list|when|why|who|give|tell)\b/.test(t);
  if (agent.config.data.rag_enabled.value && isQuestion) return 'grounded_answer';
  // 3) tool-name / action mention → tool_call
  if (boundToolIds.some((id) => t.includes(id.split('_')[0]) || t.includes(id))) return 'tool_call';
  // 4) else general (still attempts a real answer server-side if RAG-enabled)
  return agent.config.data.rag_enabled.value ? 'grounded_answer' : 'general_answer';
}

export function generatePlaygroundResponse(
  agent: AgentRecord,
  tools: ToolAsset[],
  message: string,
): PlaygroundResponse {
  const cfg = agent.config;
  const isAdv = agent.capability_tier === 'advanced';
  const critical = agent.governance_path === 'critical';
  const boundToolIds = cfg.tooling.bound_tools.value.map((t) => t.replace('tools://', '').split('@')[0]);
  const boundTools = tools.filter((t) => boundToolIds.includes(t.id));

  const kind = classify(agent, message, boundToolIds);
  const routing: string[] = isAdv ? ['coordinator'] : [];

  if (kind === 'refusal') {
    return {
      kind, citations: [], retrieval: [], toolCalls: [], routing, tokenCount: 42,
      shapedBy: ['tool_permission=read (advisory-only)', 'safety_instructions'],
      text: "I'm advisory-only. I can draft this for you, but I can't send, update, delete, or otherwise act. Would you like a draft you can review and act on yourself?",
    };
  }

  if (kind === 'grounded_answer') {
    // Placeholder only — real retrieval + citations come back from the
    // server (see kernel/services.ts's chatWithAgent), which replaces all of
    // this except as a fallback if that call fails.
    if (isAdv) routing.push('research_assistant', 'synthesizer');
    return {
      kind, citations: [], retrieval: [], toolCalls: [], routing, tokenCount: 80,
      shapedBy: [`rag_enabled=true`, `retrieval_type=${cfg.data.retrieval_type.value}`, `top_k=${cfg.data.top_k.value ?? 5}`, `score_threshold=${cfg.data.score_threshold.value ?? 0.35}`],
      text: 'Retrieving relevant context and drafting a grounded answer…',
    };
  }

  if (kind === 'tool_call') {
    const tool = boundTools[0];
    if (isAdv) routing.push('log_analyzer');
    const toolCalls: ToolCallBlock[] = tool ? [{
      tool_id: tool.id,
      permission: tool.permission_ceiling,
      result: tool.result_fixtures?.[0] ?? '{"ok":true}',
      requiresHitl: critical,
    }] : [];
    return {
      kind, citations: [], retrieval: [], toolCalls, routing, tokenCount: 90,
      shapedBy: [`bound_tools`, critical ? 'runtime HITL per action (Critical path)' : 'advisory tool call'],
      text: tool ? `I queried ${tool.id} (${tool.permission_ceiling}). Here is what it returned:` : 'No read tool is bound to answer that.',
    };
  }

  // general
  return {
    kind, citations: [], retrieval: [], toolCalls: [], routing, tokenCount: 60,
    shapedBy: ['persona_role', 'system_prompt_ref'],
    text: `As the ${cfg.identity.use_case_category.value} ${agent.capability_tier === 'minimal' ? 'advisor' : 'assistant'}, here's my take: ${message.length > 3 ? 'that’s within my scope — ask me something specific about ' + cfg.identity.use_case_category.value + ' and I’ll ground it in my sources.' : 'how can I help?'}`,
  };
}
