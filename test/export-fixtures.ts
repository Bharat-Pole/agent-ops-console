// Phase 0 — serialize the three seed AgentRecords to JSON fixtures for agent_forge.
// These are the EXACT shape the console's JSON-tab "Export config" produces.
//   npx tsx test/export-fixtures.ts
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { SEED_AGENTS } from '@/seed/agents';
import { AGENT } from '@/seed/ids';
import { agentId } from '@/types';

const outDir = 'engine/agent_forge/tests/fixtures';
mkdirSync(outDir, { recursive: true });

// one representative per topology: single / coordinator+subagents / RAG(dag)
const want: Record<string, string> = {
  [AGENT.hr]: 'hr_policy_bot.json',
  [AGENT.incident]: 'incident_response_coordinator.json',
  [AGENT.noc]: 'noc_incident_summarizer.json',
};

let n = 0;
for (const a of SEED_AGENTS) {
  const id = agentId(a);
  const file = want[id];
  if (file) {
    writeFileSync(join(outDir, file), JSON.stringify(a, null, 2) + '\n');
    console.log(
      `wrote ${file}  [tier=${a.capability_tier}, orch=${a.config.orchestration.orchestration_type.value}, ` +
        `rag=${a.config.data.rag_enabled.value}, subagents=${a.config.orchestration.sub_agents.value.length}, ` +
        `flagged=${a.review_card?.flagged_write_tools.join('|') ?? '(review_card null)'}]`,
    );
    n++;
  }
}
console.log(`\nexported ${n}/3 fixtures to ${outDir}`);
if (n !== 3) process.exit(1);
