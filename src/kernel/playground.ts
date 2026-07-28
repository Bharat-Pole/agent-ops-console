// Section 11 — deterministic Playground & eval response mechanics. Responses are
// assembled from the agent's own config; no LLM. "An agent is data" pays off:
// change top_k or score_threshold via a config-change proposal and the retrieval
// trace here changes.

import type { AgentRecord, KnowledgeSource, ToolAsset } from '@/types';

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

// Deterministic pseudo-relevance in [0,1] from message + doc id.
function relevance(message: string, docId: string): number {
  const s = (message + '|' + docId).toLowerCase();
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  // bias upward a bit so a few chunks clear a 0.75 threshold
  return 0.55 + ((h >>> 0) % 1000) / 1000 * 0.45;
}

// 5-char stem so singular/plural (incident/incidents) match.
function stem(w: string): string {
  return w.slice(0, 5);
}

function classify(agent: AgentRecord, message: string, boundToolIds: string[], stems: Set<string>): MessageKind {
  const t = message.toLowerCase();
  const words = t.split(/\W+/).filter(Boolean);
  // 1) write-verb (not in an advisory frame) → refusal
  const hasWrite = WRITE_VERBS.some((v) => new RegExp(`\\b${v}\\b`).test(t));
  const advisory = ADVISORY_FRAMES.some((f) => t.includes(f));
  if (hasWrite && !advisory) return 'refusal';
  // 2) question containing a seeded KB keyword → grounded (needs RAG)
  const isQuestion = /\?$/.test(message.trim()) || /^(what|how|which|summarize|show|list|when|why|who|give|tell)\b/.test(t);
  if (agent.config.data.rag_enabled.value && isQuestion && words.some((w) => w.length >= 4 && stems.has(stem(w)))) return 'grounded_answer';
  // 3) tool-name / action mention → tool_call
  if (boundToolIds.some((id) => t.includes(id.split('_')[0]) || t.includes(id))) return 'tool_call';
  // 4) else general
  return 'general_answer';
}

export function generatePlaygroundResponse(
  agent: AgentRecord,
  sources: KnowledgeSource[],
  tools: ToolAsset[],
  message: string,
): PlaygroundResponse {
  const cfg = agent.config;
  const isAdv = agent.capability_tier === 'advanced';
  const critical = agent.governance_path === 'critical';
  const boundToolIds = cfg.tooling.bound_tools.value.map((t) => t.replace('tools://', '').split('@')[0]);
  const boundTools = tools.filter((t) => boundToolIds.includes(t.id));

  // agent's knowledge sources + a stem set from snippets/domain/source names
  const agentSources = sources.filter((s) => cfg.data.knowledge_source_refs.value.some((r) => r.includes(s.id)));
  const stems = new Set<string>();
  const addStem = (w: string) => { if (w.length >= 4) stems.add(stem(w)); };
  for (const s of agentSources) {
    for (const sn of s.snippets) for (const w of sn.text.toLowerCase().split(/\W+/)) addStem(w);
    for (const w of s.name.toLowerCase().split(/\W+/)) addStem(w);
  }
  for (const w of cfg.identity.use_case_category.value.toLowerCase().split(/\W+/)) addStem(w);
  for (const w of cfg.identity.objective.value.toLowerCase().split(/\W+/)) addStem(w);

  const kind = classify(agent, message, boundToolIds, stems);
  const threshold = cfg.data.score_threshold.value ?? 0.75;
  const topK = cfg.data.top_k.value ?? 5;
  const routing: string[] = isAdv ? ['coordinator'] : [];

  if (kind === 'refusal') {
    return {
      kind, citations: [], retrieval: [], toolCalls: [], routing, tokenCount: 42,
      shapedBy: ['tool_permission=read (advisory-only)', 'safety_instructions'],
      text: "I'm advisory-only. I can draft this for you, but I can't send, update, delete, or otherwise act. Would you like a draft you can review and act on yourself?",
    };
  }

  if (kind === 'grounded_answer') {
    // score all snippets, filter by threshold, take top_k
    const scored: RetrievalChunk[] = agentSources.flatMap((s) => s.snippets.map((sn) => {
      const score = Number(relevance(message, sn.doc_id).toFixed(2));
      return { doc_id: sn.doc_id, source_id: s.id, text: sn.text, score, passed: score >= threshold };
    })).sort((a, b) => b.score - a.score);
    const passed = scored.filter((c) => c.passed).slice(0, topK);
    const used = passed.slice(0, 3);
    const citations = used.map((c) => `[source: kb://${c.source_id} · ${c.doc_id}]`);
    if (isAdv) routing.push('research_assistant', 'synthesizer');
    const body = used.length
      ? used.map((c) => c.text).join(' ')
      : `No source cleared the score_threshold of ${threshold} — abstaining rather than answering ungrounded.`;
    return {
      kind, citations, retrieval: scored.slice(0, Math.max(topK, 5)), toolCalls: [], routing,
      tokenCount: 120 + used.length * 60,
      shapedBy: [`rag_enabled=true`, `retrieval_type=${cfg.data.retrieval_type.value}`, `top_k=${topK}`, `score_threshold=${threshold}`, `citation_rules=${cfg.prompt.citation_rules.value}`],
      text: used.length ? `${body}\n\n${citations.join('  ')}` : body,
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
