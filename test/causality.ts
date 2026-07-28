// Headless causality tests for the kernel services (Section 10 seams that don't
// require the async job queue). Shims `window` so setTimeout-based paths don't
// throw under tsx.  npx tsx test/causality.ts

/* eslint-disable @typescript-eslint/no-explicit-any */
(globalThis as any).window = globalThis;
// Run job setTimeout chains synchronously so job-based flows are testable headlessly.
(globalThis as any).setTimeout = (fn: () => void) => { fn(); return 0; };

import { useWorkspace, ws } from '@/kernel/store';
import { api } from '@/kernel/api';
import { agentId, isLive } from '@/types';
import { AGENT, PACK, SOURCE } from '@/seed/ids';
import { DEMO_TODAY } from '@/kernel/constants';

let failures = 0;
function check(name: string, cond: boolean, extra = '') {
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${name}${cond ? '' : '  ' + extra}`);
  if (!cond) failures += 1;
}

useWorkspace.getState().setPersona('governance_officer');

console.log('\n== Approval cascade (Churn: 1 of 2 pending → approve → approved) ==');
{
  const churnBefore = ws().agents.find((a) => agentId(a) === AGENT.churn)!;
  check('Churn starts registered', churnBefore.config.lifecycle.lifecycle_status.value === 'registered');
  check('Churn registry not yet ready', churnBefore.tracks.registry.status !== 'ready');
  api.decideApproval('appr-churn-risk', 'approved', 'ok');
  const churnAfter = ws().agents.find((a) => agentId(a) === AGENT.churn)!;
  check('final approval → lifecycle approved', churnAfter.config.lifecycle.lifecycle_status.value === 'approved', churnAfter.config.lifecycle.lifecycle_status.value);
  check('final approval → registry track ready', churnAfter.tracks.registry.status === 'ready');
  check('no pending approvals remain for Churn', ws().approvals.filter((a) => a.agent_id === AGENT.churn && a.status === 'pending').length === 0);
  const evt = ws().auditLog[0];
  check('audit event written for the approval', evt.action === 'approve' || ws().auditLog.some((e) => e.entity_id === AGENT.churn && e.action === 'approve'));
}

console.log('\n== Contract still blocked (committee pending) ==');
{
  const contract = ws().agents.find((a) => agentId(a) === AGENT.contract)!;
  check('Contract not live', !isLive(contract));
  check('Contract has a pending committee item', ws().approvals.some((a) => a.agent_id === AGENT.contract && a.status === 'pending'));
}

console.log('\n== Fast-path re-certify (HR: extend expiry +90 days) ==');
{
  api.recertify(AGENT.hr);
  const hr = ws().agents.find((a) => agentId(a) === AGENT.hr)!;
  const base = new Date(DEMO_TODAY + 'T00:00:00Z');
  base.setUTCDate(base.getUTCDate() + 90);
  check('HR expiry extended to DEMO_TODAY+90', hr.fast_path_expiry_date === base.toISOString().slice(0, 10), String(hr.fast_path_expiry_date));
}

console.log('\n== Suspend / retire (Governance Officer) ==');
{
  api.setLifecycle(AGENT.noc, 'suspended');
  check('NOC suspended', ws().agents.find((a) => agentId(a) === AGENT.noc)!.config.lifecycle.lifecycle_status.value === 'suspended');
}

console.log('\n== Advisory-only bind guard (acceptance #3) ==');
{
  const before = ws().auditLog.length;
  const okWrite = api.bindTool(AGENT.churn, 'slack_notifier');
  check('binding a write-capable tool is REJECTED', okWrite === false);
  check('rejection writes an audit event', ws().auditLog.some((e) => e.action === 'bind_rejected'));
  const churn = ws().agents.find((a) => agentId(a) === AGENT.churn)!;
  check('write tool never appears in bound_tools', !churn.config.tooling.bound_tools.value.join(',').includes('slack_notifier'));
  const okRead = api.bindTool(AGENT.churn, 'confluence_reader');
  check('binding a read-only tool succeeds', okRead === true);
  check('read tool appears in bound_tools', ws().agents.find((a) => agentId(a) === AGENT.churn)!.config.tooling.bound_tools.value.some((t) => t.includes('confluence_reader')));
  void before;
}

console.log('\n== Offline toggle → Pre-Flight hard blocker condition (Section 10 #1) ==');
{
  api.toggleConnectorOffline('jira');
  check('connector jira is offline', ws().connectors.find((c) => c.id === 'jira')!.status === 'offline');
  // usePreflight reads exactly this: any connector offline → hard blocker #4 red
  check('Pre-Flight would block (a connector is offline)', ws().connectors.some((c) => c.status === 'offline'));
  api.toggleConnectorOffline('jira'); // restore
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

  api.proposeConfigChange(AGENT.contract, 'data', 'score_threshold', 0.75);
  api.runEvaluation(PACK.contract);
  const p2 = ws().evalPacks.find((p) => p.id === PACK.contract)!;
  check('after fix, eval scores 94', p2.last_run?.score === 94, String(p2.last_run?.score));
  check('grounding cases now pass', p2.cases.filter((c) => c.category === 'grounding' && c.last_result === 'fail').length === 0);
  check('promotion now unlocked (≥ 90)', (p2.last_run?.score ?? 0) >= 90);
}

console.log('\n== Provision → tracks ready → LIVE (Churn, jobs run synchronously) ==');
{
  // Churn was approved earlier → Registry ready. Provision runtime+content → live.
  api.provision(AGENT.churn);
  const churn = ws().agents.find((a) => agentId(a) === AGENT.churn)!;
  check('runtime track ready after provision', churn.tracks.runtime.status === 'ready');
  check('content track ready after provision', churn.tracks.content.status === 'ready');
  check('agent is LIVE', isLive(churn));
  check('lifecycle flipped to live', churn.config.lifecycle.lifecycle_status.value === 'live');
}

console.log('\n== Pipeline refresh → Content ready → Demo Mode clears (Section 10 #3) ==');
{
  // Capacity agent ships with Content re-indexing in progress; enable Demo Mode.
  api.enableDemoMode(AGENT.capacity);
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
