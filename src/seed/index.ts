// Seed data assembly (Section 12). The store's reset() rehydrates from here so
// two "Reset demo" runs are identical. This is the demo's script — coherent
// stories, not filler.

import type {
  AgentRecord,
  PromptAsset,
  ToolAsset,
  McpConnector,
  KnowledgeSource,
  PipelineRun,
  EvaluationPack,
  ApprovalItem,
  AuditEvent,
  AgentTelemetry,
  ModelAsset,
  PolicyRule,
  PathDefinition,
  GovernanceException,
  AgentCard,
} from '@/types';
import { agentId } from '@/types';
import { SEED_AGENTS } from './agents';
import { SEED_PROMPTS } from './prompts';
import { SEED_TOOLS } from './tools';
import { SEED_CONNECTORS } from './connectors';
import { SEED_SOURCES, SEED_PIPELINE_RUNS } from './sources';
import { SEED_EVAL_PACKS } from './evals';
import { SEED_APPROVALS } from './approvals';
import { SEED_AUDIT } from './audit';
import { SEED_MODELS } from './models';
import { SEED_POLICY_RULES, SEED_PATH_DEFINITIONS, SEED_GOVERNANCE_EXCEPTIONS } from './governance';
import { generateTelemetry } from '@/kernel/telemetry';

export interface WorkspaceData {
  agents: AgentRecord[];
  prompts: PromptAsset[];
  tools: ToolAsset[];
  connectors: McpConnector[];
  sources: KnowledgeSource[];
  pipelineRuns: PipelineRun[];
  evalPacks: EvaluationPack[];
  approvals: ApprovalItem[];
  auditLog: AuditEvent[];
  telemetry: AgentTelemetry[];
  models: ModelAsset[];
  policyRules: PolicyRule[];
  pathDefinitions: PathDefinition[];
  governanceExceptions: GovernanceException[];
  a2aCards: AgentCard[];
}

export function createInitialWorkspace(): WorkspaceData {
  const agents = SEED_AGENTS.map((a) => structuredClone(a));
  const evalPacks = SEED_EVAL_PACKS.map((p) => structuredClone(p));

  // Map each agent to its pack's last score so telemetry eval-history converges.
  const packScoreByAgent: Record<string, number | null> = {};
  for (const a of agents) {
    const pack = evalPacks.find((p) => p.agent_id === agentId(a));
    packScoreByAgent[agentId(a)] = pack?.last_run?.score ?? null;
  }

  return {
    agents,
    prompts: SEED_PROMPTS.map((p) => structuredClone(p)),
    tools: SEED_TOOLS.map((t) => structuredClone(t)),
    connectors: SEED_CONNECTORS.map((c) => structuredClone(c)),
    sources: SEED_SOURCES.map((s) => structuredClone(s)),
    pipelineRuns: SEED_PIPELINE_RUNS.map((r) => structuredClone(r)),
    evalPacks,
    approvals: SEED_APPROVALS.map((a) => structuredClone(a)),
    auditLog: SEED_AUDIT.map((e) => structuredClone(e)),
    telemetry: generateTelemetry(agents, packScoreByAgent),
    models: SEED_MODELS.map((m) => structuredClone(m)),
    policyRules: SEED_POLICY_RULES.map((r) => structuredClone(r)),
    pathDefinitions: SEED_PATH_DEFINITIONS.map((p) => structuredClone(p)),
    governanceExceptions: SEED_GOVERNANCE_EXCEPTIONS.map((e) => structuredClone(e)),
    // No client-side generator — real cards are derived server-side from live
    // agent config (services/a2a.py) and arrive via hydrateFromServer(). Empty
    // until then is the honest pre-hydration state, same as `knowledgeSources`.
    a2aCards: [],
  };
}
