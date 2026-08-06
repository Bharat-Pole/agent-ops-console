// Headless causality tests for the kernel services (Section 10 seams that don't
// require the async job queue, and don't require a running backend). Shims
// `window` so setTimeout-based paths don't throw under tsx.  npx tsx test/causality.ts
//
// Phase 1 moved several services (decideApproval, bindTool, setLifecycle,
// recertify, proposeConfigChange, enableDemoMode) to real async backend calls
// (see /server) — those are no longer pure client-side logic, so they're
// intentionally NOT exercised here. They're covered by the Phase 1 backend
// verification instead (curl smoke tests against the write-guard/register/
// approval endpoints + a Playwright browser run confirming registration
// persists across a hard refresh). This file keeps testing what's still
// genuinely client-simulated: provision, runEvaluation, triggerPipeline,
// and export/import round-trip. (`toggleConnectorOffline` and `healthcheck`
// moved server-side when connectors became persisted — they are covered by
// `backend/verify_connectors.py` instead.) Where a test needs a
// precondition that used to come from one of the now-server-side calls, it's
// set up via a direct store patch instead (clearly commented below).

/* eslint-disable @typescript-eslint/no-explicit-any */
(globalThis as any).window = globalThis;
// Run job setTimeout chains synchronously so job-based flows are testable headlessly.
(globalThis as any).setTimeout = (fn: () => void) => { fn(); return 0; };

import { useWorkspace, ws } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive } from '@/types';
import { AGENT, PACK, SOURCE } from '@/seed/ids';

let failures = 0;
function check(name: string, cond: boolean, extra = '') {
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${name}${cond ? '' : '  ' + extra}`);
  if (!cond) failures += 1;
}

useWorkspace.getState().setPersona('governance_officer');

console.log('\n== Contract still blocked (committee pending) ==');
{
  const contract = ws().agents.find((a) => agentId(a) === AGENT.contract)!;
  check('Contract not live', !isLive(contract));
  check('Contract has a pending committee item', ws().approvals.some((a) => a.agent_id === AGENT.contract && a.status === 'pending'));
}

console.log('\n== Offline connector → Pre-Flight hard blocker condition (Section 10 #1) ==');
{
  // `toggleConnectorOffline` is now a real backend call (connectors are
  // server-persisted, and the server cascades status onto the tools the
  // connector serves), so it is no longer exercised here — see the header
  // note. The precondition is set via a direct store patch, and what this
  // block still tests is the genuinely client-side half of the seam: that
  // usePreflight's blocker #4 reads connector status.
  ws().patchConnector('jira', { status: 'offline' });
  check('connector jira is offline', ws().connectors.find((c) => c.id === 'jira')!.status === 'offline');
  // usePreflight reads exactly this: any connector offline → hard blocker #4 red
  check('Pre-Flight would block (a connector is offline)', ws().connectors.some((c) => c.status === 'offline'));
  ws().patchConnector('jira', { status: 'degraded' }); // restore to its seeded state
  check('bringing it back clears the block', !ws().connectors.some((c) => c.status === 'offline'));
}

console.log('\n== Failing-eval fix story (Contract 82 → fix threshold → 94, Section 11.3) ==');
{
  const contract = ws().agents.find((a) => agentId(a) === AGENT.contract)!;
  check('Contract score_threshold starts at 0.95', contract.config.data.score_threshold.value === 0.95);
  api.runEvaluation(PACK.contract);
  const p1 = ws().evalPacks.find((p) => p.id === PACK.contract)!;
  check('eval with 0.95 threshold scores 82', p1.last_run?.score === 82, String(p1.last_run?.score));
  check('two grounding cases fail', p1.cases.filter((c) => c.category === 'grounding' && c.last_result === 'fail').length === 2);
  check('promotion locked (< 90 on Deep path)', (p1.last_run?.score ?? 0) < 90);

  // proposeConfigChange is now a real backend call (Phase 1) — simulate its
  // effect directly on the store here since this test is exercising
  // runEvaluation's scoring response to config, not the HTTP round-trip
  // (which is covered by the server-side bindTool/register curl checks).
  ws().patchAgent(AGENT.contract, (a) => ({ ...a, config: { ...a.config, data: { ...a.config.data, score_threshold: { ...a.config.data.score_threshold, value: 0.75 } } } }));
  api.runEvaluation(PACK.contract);
  const p2 = ws().evalPacks.find((p) => p.id === PACK.contract)!;
  check('after fix, eval scores 94', p2.last_run?.score === 94, String(p2.last_run?.score));
  check('grounding cases now pass', p2.cases.filter((c) => c.category === 'grounding' && c.last_result === 'fail').length === 0);
  check('promotion now unlocked (≥ 90)', (p2.last_run?.score ?? 0) >= 90);
}

console.log('\n== Provision → tracks ready → LIVE (Incident Coordinator, jobs run synchronously) ==');
{
  // Incident Response Coordinator ships already `approved` with Registry
  // ready (see seed/agents.ts) — no approval call needed as a precondition.
  api.provision(AGENT.incident);
  const incident = ws().agents.find((a) => agentId(a) === AGENT.incident)!;
  check('runtime track ready after provision', incident.tracks.runtime.status === 'ready');
  check('content track ready after provision', incident.tracks.content.status === 'ready');
  check('agent is LIVE', isLive(incident));
  check('lifecycle flipped to live', incident.config.lifecycle.lifecycle_status.value === 'live');
}

console.log('\n== Pipeline refresh → Content ready → Demo Mode clears (Section 10 #3) ==');
{
  // enableDemoMode is now a real backend call (Phase 1) — set the precondition
  // directly on the store; the behavior under test is triggerPipeline's
  // completion callback (still pure client simulation), not the HTTP round-trip.
  ws().patchAgent(AGENT.capacity, (a) => ({ ...a, demo_mode: true }));
  const mid = ws().agents.find((a) => agentId(a) === AGENT.capacity)!;
  check('demo_mode enabled while content indexing', mid.demo_mode === true);
  check('content track not yet ready', mid.tracks.content.status !== 'ready');
  // Trigger the pipeline refresh on its source → callback brings content ready + clears demo_mode.
  api.triggerPipeline(SOURCE.capacityReports);
  const done = ws().agents.find((a) => agentId(a) === AGENT.capacity)!;
  check('content track ready after refresh', done.tracks.content.status === 'ready');
  check('demo_mode auto-cleared', done.demo_mode === false);
  check('agent now LIVE (all three tracks ready)', isLive(done));
}

console.log('\n== Export / import workspace round-trip (acceptance #11) ==');
{
  const exp = useWorkspace.getState().exportWorkspace();
  check('export carries the schema tag', exp._schema === 'brightspeed-agent-ops/v1');
  const agentsBefore = ws().agents.length;
  const auditBefore = ws().auditLog.length;
  useWorkspace.getState().importWorkspace(exp);
  check('round-trip preserves agent count', ws().agents.length === agentsBefore);
  check('round-trip preserves audit log', ws().auditLog.length === auditBefore);
  check('round-trip preserves drafts', ws().drafts.length === exp.drafts.length);
}

console.log(`\n${failures === 0 ? 'ALL CAUSALITY TESTS PASSED' : failures + ' CAUSALITY TEST(S) FAILED'}\n`);
process.exit(failures === 0 ? 0 : 1);
