// Runtime smoke test for the seed data + kernel invariants. Run:
//   TSX_TSCONFIG_PATH=./tsconfig.app.json npx tsx test/smoke.ts
// Verifies seed loads without throwing, entity counts, provenance coverage,
// governance-path derivation, determinism, and the key demo-story facts.

import { createInitialWorkspace } from '@/seed';
import { SCHEMA_GROUPS } from '@/types';
import { agentId, isLive } from '@/types';
import type { Prov } from '@/types';
import { governancePathFor } from '@/kernel/constants';
import { AGENT } from '@/seed/ids';
import { SEED_DRAFTS } from '@/seed/drafts';

let failures = 0;
function check(name: string, cond: boolean, extra = '') {
  if (cond) {
    console.log(`  ok   ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${name} ${extra}`);
  }
}

const ws = createInitialWorkspace();

console.log('\n== Entity counts ==');
// Section 12.1 enumerates 9 — 8 registered agents + 1 in-flight wizard draft.
check('8 registered agents', ws.agents.length === 8, `got ${ws.agents.length}`);
check('1 onboarding draft (Vendor SLA Watcher)', SEED_DRAFTS.length === 1 && SEED_DRAFTS[0].name === 'Vendor SLA Watcher', `got ${SEED_DRAFTS.length}`);
check('draft is at Phase 3 (resume story)', SEED_DRAFTS[0].phase === 3);
check('draft synthesized to a tier', SEED_DRAFTS[0].synthesis !== null && SEED_DRAFTS[0].confirmedTier !== null);
check('8 prompts', ws.prompts.length === 8, `got ${ws.prompts.length}`);
check('12 tools', ws.tools.length === 12, `got ${ws.tools.length}`);
check('5 connectors', ws.connectors.length === 5, `got ${ws.connectors.length}`);
check('6 sources', ws.sources.length === 6, `got ${ws.sources.length}`);
check('8 eval packs', ws.evalPacks.length === 8, `got ${ws.evalPacks.length}`);
check('15 approvals', ws.approvals.length === 15, `got ${ws.approvals.length}`);
check('>=40 audit events', ws.auditLog.length >= 40, `got ${ws.auditLog.length}`);
check('telemetry for 8 non-draft agents', ws.telemetry.length === 8, `got ${ws.telemetry.length}`);

console.log('\n== Provenance coverage (every leaf carries an envelope) ==');
const codes = new Set<string>();
function chipCode(p: Prov<unknown>): string {
  switch (p.value_source) {
    case 'user': return 'U';
    case 'system': return 'S';
    case 'default': return 'D';
    case 'inherited': return 'H';
    case 'inferred': return p.confidence === 'low' ? 'G' : 'I';
  }
}
let leafCount = 0;
let missingEnvelope = 0;
for (const a of ws.agents) {
  const cfg = a.config as unknown as Record<string, Record<string, Prov<unknown>>>;
  for (const grp of SCHEMA_GROUPS) {
    const group = cfg[grp.key];
    for (const f of grp.fields) {
      leafCount += 1;
      const leaf = group[f];
      if (!leaf || typeof leaf !== 'object' || !('value_source' in leaf) || !('confidence' in leaf)) {
        missingEnvelope += 1;
      } else {
        codes.add(chipCode(leaf));
      }
    }
  }
}
check('every schema leaf has a provenance envelope', missingEnvelope === 0, `${missingEnvelope} missing of ${leafCount}`);
check('all five chip codes U/S/D/I/G present', ['U', 'S', 'D', 'I', 'G'].every((c) => codes.has(c)), `got ${[...codes].sort().join(',')}`);
check('13 groups per agent', SCHEMA_GROUPS.length === 13);

console.log('\n== Governance-path derivation matches the matrix ==');
for (const a of ws.agents) {
  if (a.config.lifecycle.lifecycle_status.value === 'draft') continue;
  const expected = governancePathFor(a.capability_tier, a.config.lifecycle.risk_tier.value);
  check(`${a.config.identity.agent_name.value}: path ${a.governance_path}`, a.governance_path === expected, `expected ${expected}`);
}

console.log('\n== Demo-story facts ==');
const hr = ws.agents.find((a) => agentId(a) === AGENT.hr)!;
check('HR bot is Minimal', hr.capability_tier === 'minimal');
check('HR bot: all signals 0', Object.values(hr.signal_breakdown).every((s) => !s.fired));
check('HR bot is LIVE (all tracks ready)', isLive(hr));
check('HR bot fast-path expiry in 6 days', hr.fast_path_expiry_date !== null);

const inc = ws.agents.find((a) => agentId(a) === AGENT.incident)!;
check('Incident Coordinator is Advanced', inc.capability_tier === 'advanced');
check('Incident: S1..S5 all fire', (['S1', 'S2', 'S3', 'S4', 'S5'] as const).every((s) => inc.signal_breakdown[s].fired));
check('Incident: 4 sub-agents', inc.config.orchestration.sub_agents.value.length === 4);
check('Incident: risk_tier=high', inc.config.lifecycle.risk_tier.value === 'high');
check('Incident: slack_notifier + email_sender flagged, not bound', (() => {
  const bound = inc.config.tooling.bound_tools.value.join(',');
  const flagged = inc.review_card?.flagged_write_tools ?? [];
  return !bound.includes('slack_notifier') && !bound.includes('email_sender') && flagged.includes('slack_notifier') && flagged.includes('email_sender');
})());
check('Incident NOT live (provisioning)', !isLive(inc));

const contract = ws.agents.find((a) => agentId(a) === AGENT.contract)!;
const contractPack = ws.evalPacks.find((p) => p.agent_id === AGENT.contract)!;
check('Contract eval score 82', contractPack.last_run?.score === 82);
check('Contract score_threshold mis-set to 0.95', contract.config.data.score_threshold.value === 0.95);
check('Contract: 2 grounding cases fail', contractPack.cases.filter((c) => c.category === 'grounding' && c.last_result === 'fail').length === 2);

check('no write-capable tool is bound to ANY agent', (() => {
  const writeTools = new Set(ws.tools.filter((t) => t.write_capable).map((t) => t.id));
  for (const a of ws.agents) {
    for (const b of a.config.tooling.bound_tools.value) {
      const id = b.replace('tools://', '').split('@')[0];
      if (writeTools.has(id)) return false;
    }
  }
  return true;
})());

console.log('\n== Derived-value helpers (Home/Registry aggregations) ==');
{
  const { cost30d, tokens30d, requests30d, latestP95, errorRate30d, daysUntil } = await import('@/utils/format');
  let allFinite = true;
  let totalCost = 0;
  for (const t of ws.telemetry) {
    const c = cost30d(t);
    totalCost += c;
    if (![c, tokens30d(t), requests30d(t), latestP95(t), errorRate30d(t)].every((x) => Number.isFinite(x) && x >= 0)) allFinite = false;
  }
  check('all telemetry aggregations finite & non-negative', allFinite);
  // cost is now real (services/monitoring.py: real tokens x real per-model
  // pricing from the Model Repository) — this headless test has no running
  // server, so it only ever sees kernel/telemetry.ts's brief pre-hydration
  // placeholder, which correctly reports cost 0 rather than fabricating a
  // number. Real non-zero cost is covered by curl/browser verification
  // against a live backend instead (see FinOps module verification).
  check('monthly spend is the honest pre-hydration 0 (real cost verified live)', totalCost === 0, `got ${totalCost}`);
  check('NOC is highest-traffic agent', (() => {
    const byReq = ws.telemetry.map((t) => ({ id: t.agent_id, r: requests30d(t) })).sort((a, b) => b.r - a.r);
    return byReq[0].id === AGENT.noc;
  })());
  check('HR fast-path expiry is 6 days out', daysUntil(ws.agents.find((a) => agentId(a) === AGENT.hr)!.fast_path_expiry_date) === 6);
  check('Incident Coordinator has a day-22 telemetry spike', (() => {
    const t = ws.telemetry.find((x) => x.agent_id === AGENT.incident)!;
    const errs = t.series.map((p) => p.errors);
    const avg = errs.reduce((a, b) => a + b, 0) / errs.length;
    return errs[22] > avg * 2;
  })());
}

console.log('\n== Determinism (two builds identical) ==');
const ws2 = createInitialWorkspace();
check('telemetry identical across two builds', JSON.stringify(ws.telemetry) === JSON.stringify(ws2.telemetry));
check('eval packs identical across two builds', JSON.stringify(ws.evalPacks) === JSON.stringify(ws2.evalPacks));

console.log(`\n${failures === 0 ? 'ALL SMOKE CHECKS PASSED' : failures + ' CHECK(S) FAILED'}\n`);
process.exit(failures === 0 ? 0 : 1);
