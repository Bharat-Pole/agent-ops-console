// Stage 2b — Architecture recommendation (Section 7, additive). Selects one of
// the generatable architecture shapes and builds the concrete graph the code
// generator (agent_forge) will render. This deterministic baseline is BOTH the
// offline fallback AND the validator that re-checks every LLM-supplied
// recommendation (source: 'llm') before it is trusted.

import type {
  Intent,
  NluResult,
  Classification,
  ArchitectureRecommendation,
  ArchitectureValidation,
} from './types';
import type {
  Architecture,
  GraphSpec,
  GraphNode,
  GraphEdge,
  SubAgent,
  OrchestrationType,
  OrchestrationPattern,
} from '@/types';
import { inferPattern, decomposeSubAgents } from './templates';

export const ARCHITECTURES: Architecture[] = ['single', 'sequential_pipeline', 'hub_and_spoke', 'graph'];

export const ARCHITECTURE_LABEL: Record<Architecture, string> = {
  single: 'Single agent',
  sequential_pipeline: 'Sequential pipeline',
  hub_and_spoke: 'Hub & spoke',
  graph: 'Graph (router)',
};

// Each architecture kind maps deterministically onto the canonical
// (orchestration_type × pattern) surface — no OrchestrationType enum churn.
const ARCH_MAP: Record<Architecture, { orchestration_type: OrchestrationType; pattern: OrchestrationPattern | null }> = {
  single: { orchestration_type: 'single', pattern: null },
  sequential_pipeline: { orchestration_type: 'coordinator+subagents', pattern: 'pipeline' },
  hub_and_spoke: { orchestration_type: 'coordinator+subagents', pattern: 'hub' },
  graph: { orchestration_type: 'router', pattern: null },
};

// Build the concrete renderable graph for a shape. `single` needs no graph.
export function synthesizeGraphSpec(kind: Architecture, subAgents: SubAgent[], rag: boolean): GraphSpec | null {
  switch (kind) {
    case 'single':
      return null;
    case 'sequential_pipeline': {
      const nodes: GraphNode[] = subAgents.map((s) => ({ id: s.name, kind: 'llm', label: s.role, sub_agent: s.name }));
      const edges: GraphEdge[] = [];
      for (let idx = 0; idx < nodes.length - 1; idx++) edges.push({ from: nodes[idx].id, to: nodes[idx + 1].id });
      return { nodes, edges };
    }
    case 'hub_and_spoke': {
      const hub: GraphNode = { id: 'coordinator', kind: 'route', label: 'Coordinator (routes + aggregates)' };
      const spokes: GraphNode[] = subAgents.map((s) => ({ id: s.name, kind: 'llm', label: s.role, sub_agent: s.name }));
      const edges: GraphEdge[] = [];
      for (const s of subAgents) {
        edges.push({ from: 'coordinator', to: s.name, when: `route:${s.name}` });
        edges.push({ from: s.name, to: 'coordinator' }); // return to coordinator for aggregation
      }
      return { nodes: [hub, ...spokes], edges };
    }
    case 'graph': {
      // canonical RAG DAG (retrieve → generate) when grounded; else router-over-tools.
      const nodes: GraphNode[] = rag
        ? [
            { id: 'retrieve', kind: 'retrieve', label: 'Retrieve grounding context' },
            { id: 'generate', kind: 'llm', label: 'Generate grounded answer' },
          ]
        : [
            { id: 'agent', kind: 'llm', label: 'Agent' },
            { id: 'tools', kind: 'tool', label: 'Advisory tools' },
          ];
      const edges: GraphEdge[] = rag
        ? [{ from: 'retrieve', to: 'generate' }]
        : [
            { from: 'agent', to: 'tools', when: 'tool_calls' },
            { from: 'tools', to: 'agent' },
          ];
      return { nodes, edges };
    }
    default:
      return null;
  }
}

// Deterministic shape selection from tier + intent signals. Richer than the old
// tier-only derivation: advanced splits into pipeline vs hub by ordering cues,
// and standardized (RAG) becomes an explicit retrieve→generate graph.
function pickKind(intent: Intent, cls: Classification): { kind: Architecture; rationale: string[] } {
  const rationale: string[] = [];
  const tier = cls.proposed_tier;

  if (tier === 'advanced') {
    if (inferPattern(intent.objective) === 'pipeline') {
      rationale.push('Advanced tier with sequential/staged language → sequential pipeline.');
      return { kind: 'sequential_pipeline', rationale };
    }
    rationale.push(`Advanced tier${cls.forced ? ' (multi-agent forced by S6 / ≥4 tools)' : ''} → hub & spoke coordinator.`);
    return { kind: 'hub_and_spoke', rationale };
  }

  if (tier !== 'minimal') {
    rationale.push('Retrieval-grounded (Standardized) → explicit retrieve→generate graph.');
    return { kind: 'graph', rationale };
  }

  rationale.push('Single skill, no retrieval or multi-agent signals → single agent.');
  return { kind: 'single', rationale };
}

// Assemble a full recommendation for a given kind (used by the baseline and by
// the override path so both go through the same decomposition + graph builder).
export function buildRecommendation(
  kind: Architecture,
  intent: Intent,
  nlu: NluResult,
  cls: Classification,
  source: 'llm' | 'deterministic',
  rationale: string[] = [],
): ArchitectureRecommendation {
  const map = ARCH_MAP[kind];
  const multiAgent = map.orchestration_type === 'coordinator+subagents';
  const subAgents = multiAgent ? decomposeSubAgents(intent, nlu) : [];
  const rag = cls.proposed_tier !== 'minimal';
  const graph = synthesizeGraphSpec(kind, subAgents, rag);
  // engine-inferred → medium; a hard-gated multi-agent shape is high confidence.
  const confidence: 'high' | 'medium' | 'low' = cls.forced && multiAgent ? 'high' : 'medium';
  return {
    architecture: kind,
    orchestration_type: map.orchestration_type,
    pattern: map.pattern,
    sub_agents: subAgents,
    graph,
    rationale,
    confidence,
    source,
  };
}

export function deriveBaselineArchitecture(intent: Intent, nlu: NluResult, cls: Classification): ArchitectureRecommendation {
  const { kind, rationale } = pickKind(intent, cls);
  return buildRecommendation(kind, intent, nlu, cls, 'deterministic', rationale);
}

// The raw shape an LLM recommender returns (mirrors the service JSON contract).
export interface LlmArchitectureProposal {
  architecture: Architecture;
  graph?: GraphSpec | null;
  rationale?: string[];
  confidence?: 'high' | 'medium' | 'low';
}

// Turn an LLM proposal into a validated, source:'llm' recommendation. Prefers the
// LLM-supplied graph when it passes validation; otherwise rebuilds the graph
// deterministically for the chosen kind. Returns null if the kind itself is
// illegal (e.g. single when a hard gate forces multi-agent) → caller falls back
// to the deterministic baseline.
export function recommendationFromLlm(
  intent: Intent,
  nlu: NluResult,
  cls: Classification,
  boundTools: string[],
  llm: LlmArchitectureProposal,
): ArchitectureRecommendation | null {
  if (!ARCHITECTURES.includes(llm.architecture)) return null;
  const rationale = llm.rationale?.length ? llm.rationale : [`LLM recommended ${llm.architecture}.`];
  const base = buildRecommendation(llm.architecture, intent, nlu, cls, 'llm', rationale);
  const withConf: ArchitectureRecommendation = { ...base, confidence: llm.confidence ?? base.confidence };

  // 1) trust the LLM's own graph if it validates
  if (llm.graph) {
    const candidate: ArchitectureRecommendation = { ...withConf, graph: llm.graph };
    if (validateArchitecture(candidate, cls, boundTools).ok) return candidate;
  }
  // 2) else use the deterministic graph for the kind
  return validateArchitecture(withConf, cls, boundTools).ok ? withConf : null;
}

function validateGraph(graph: GraphSpec): string[] {
  const v: string[] = [];
  if (graph.nodes.length === 0) {
    v.push('Graph has no nodes.');
    return v;
  }
  const ids = new Set<string>();
  for (const n of graph.nodes) {
    if (ids.has(n.id)) v.push(`Duplicate graph node id "${n.id}".`);
    ids.add(n.id);
  }
  for (const e of graph.edges) {
    if (!ids.has(e.from)) v.push(`Edge references missing node "${e.from}".`);
    if (!ids.has(e.to)) v.push(`Edge references missing node "${e.to}".`);
  }
  // Entry is nodes[0] (the generator always emits entry-first). Every other node
  // must be reachable from it — this handles cyclic hub/router shapes correctly.
  const adj = new Map<string, string[]>();
  for (const n of graph.nodes) adj.set(n.id, []);
  for (const e of graph.edges) if (ids.has(e.from) && ids.has(e.to)) adj.get(e.from)!.push(e.to);
  const seen = new Set<string>();
  const stack = [graph.nodes[0].id];
  while (stack.length) {
    const id = stack.pop()!;
    if (seen.has(id)) continue;
    seen.add(id);
    for (const nb of adj.get(id) ?? []) stack.push(nb);
  }
  for (const n of graph.nodes) {
    if (!seen.has(n.id)) v.push(`Node "${n.id}" is unreachable from entry "${graph.nodes[0].id}".`);
  }
  return v;
}

// Guardrail: every recommendation (LLM or user override) is re-checked here.
// Enforces the subset, the hard gates, advisory-only tool rules, and graph
// renderability. `boundTools` is the advisory bound-tool set (tools://…).
export function validateArchitecture(
  rec: ArchitectureRecommendation,
  cls: Classification,
  boundTools: string[],
): ArchitectureValidation {
  const violations: string[] = [];

  if (!ARCHITECTURES.includes(rec.architecture)) {
    violations.push(`Unknown architecture "${rec.architecture}" (not in the generatable subset).`);
  } else {
    const map = ARCH_MAP[rec.architecture];
    if (rec.orchestration_type !== map.orchestration_type) {
      violations.push(`orchestration_type "${rec.orchestration_type}" does not match architecture "${rec.architecture}".`);
    }
  }

  // Hard gate: an explicit multi-agent / ≥4-tool intent cannot collapse to single.
  if (cls.forced && rec.architecture === 'single') {
    violations.push('Explicit multi-agent (S6) or ≥4 tools forces a multi-agent architecture; "single" is not allowed.');
  }

  // Advisory-only: sub-agent tools ≤3 and drawn only from the advisory bound set.
  const allowed = new Set(boundTools);
  for (const sa of rec.sub_agents) {
    if (sa.tools.length > 3) violations.push(`Sub-agent "${sa.name}" binds ${sa.tools.length} tools (>3).`);
    for (const t of sa.tools) {
      if (!allowed.has(t)) violations.push(`Sub-agent "${sa.name}" binds non-advisory/unknown tool "${t}".`);
    }
  }

  if (rec.graph) violations.push(...validateGraph(rec.graph));

  return { ok: violations.length === 0, violations };
}
