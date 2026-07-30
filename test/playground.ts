// Playground response mechanics (Section 11). Pure functions — no window needed.
//   npx tsx test/playground.ts

import { createInitialWorkspace } from '@/seed';
import { generatePlaygroundResponse } from '@/kernel/playground';
import { agentId } from '@/types';
import { AGENT } from '@/seed/ids';

let failures = 0;
function check(name: string, cond: boolean, extra = '') {
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${name}${cond ? '' : '  ' + extra}`);
  if (!cond) failures += 1;
}

const ws = createInitialWorkspace();
const noc = ws.agents.find((a) => agentId(a) === AGENT.noc)!;
const regulatory = ws.agents.find((a) => agentId(a) === AGENT.regulatory)!;
const hr = ws.agents.find((a) => agentId(a) === AGENT.hr)!;

console.log('\n== Intent classification (Section 11.1) ==');
{
  // Real retrieval/citations now come from the server (Phase 3 — see
  // server/services/retrieval.ts); this module only decides `kind` and
  // returns a placeholder for grounded_answer, tested here.
  const g = generatePlaygroundResponse(noc, ws.tools, 'Summarize the latest incident');
  check('grounded_answer for a KB question (RAG-enabled agent)', g.kind === 'grounded_answer', g.kind);

  const r = generatePlaygroundResponse(noc, ws.tools, 'Delete all incident records');
  check('refusal for a write verb', r.kind === 'refusal', r.kind);
  check('refusal mentions advisory-only', /advisory/i.test(r.text));

  const tc = generatePlaygroundResponse(noc, ws.tools, 'Use the incident_reader tool');
  check('tool_call for a tool mention', tc.kind === 'tool_call', tc.kind);
  check('tool_call block carries a canned result', tc.toolCalls.length === 1 && tc.toolCalls[0].result.length > 0);
  check('standardized tool call needs no HITL', tc.toolCalls[0].requiresHitl === false);
}

console.log('\n== Critical path runtime HITL (Section 11.2) ==');
{
  const tc = generatePlaygroundResponse(regulatory, ws.tools, 'call the filing reader');
  check('critical-path tool call requires HITL', tc.kind === 'tool_call' && tc.toolCalls[0]?.requiresHitl === true, JSON.stringify(tc.toolCalls));
}

console.log('\n== Minimal agent cannot ground ==');
{
  const g = generatePlaygroundResponse(hr, ws.tools, 'Summarize the PTO policy');
  check('minimal agent → not grounded_answer (no RAG)', g.kind !== 'grounded_answer', g.kind);
}

console.log(`\n${failures === 0 ? 'ALL PLAYGROUND TESTS PASSED' : failures + ' PLAYGROUND TEST(S) FAILED'}\n`);
process.exit(failures === 0 ? 0 : 1);
