// Engine correctness tests (Section 7 / M4 acceptance). Verifies the two
// Appendix-A worked examples reproduce their documented OUTCOMES, plus the other
// seed agents' expected tiers, the scoring formula, override rules, capability
// floor, write flagging, and tier-override re-evaluation.
//   npx tsx test/engine.ts

import { synthesize, applyTierOverride } from '@/kernel/engine';
import type { Intent } from '@/kernel/engine';

let failures = 0;
function check(name: string, cond: boolean, extra = '') {
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${name}${cond ? '' : '  ' + extra}`);
  if (!cond) failures += 1;
}

// ---- Appendix A, Example 1: HR Policy Bot → Minimal, all signals 0 ----
console.log('\n== Worked Example 1 — HR Policy Bot ==');
{
  const intent: Intent = {
    objective: 'Answer employee questions about company HR policies and benefits in plain language.',
    intended_audience: 'All employees',
  };
  const r = synthesize(intent);
  const b = r.trace.stage2_classification.signal_breakdown;
  check('tier = minimal', r.capability_tier === 'minimal', r.capability_tier);
  check('all six signals unfired', (['S1', 'S2', 'S3', 'S4', 'S5', 'S6'] as const).every((s) => !b[s].fired));
  check('score_minimal = 20 wins', r.trace.stage2_classification.scores.minimal === 20);
  check('archetype = simple_advisor', r.archetype === 'simple_advisor', r.archetype);
  check('rag disabled', r.config.data.rag_enabled.value === false);
  check('risk = low', r.risk_tier === 'low', r.risk_tier);
}

// ---- Appendix A, Example 2: Incident Response Coordinator → Advanced ----
console.log('\n== Worked Example 2 — Incident Response Coordinator ==');
{
  const intent: Intent = {
    objective:
      'Coordinate a team of agents to triage major incidents: analyze logs from the incident database and ticketing system, assess customer impact, draft comms, and route notifications to the on-call NOC lead and Slack.',
    intended_audience: 'NOC responders',
    data_sources: ['incident_db', 'ticketing'],
    tools: ['incident_reader', 'log_reader', 'health_checker', 'jira_reader', 'slack_notifier', 'email_sender'],
  };
  const r = synthesize(intent);
  const cls = r.trace.stage2_classification;
  check('tier = advanced', r.capability_tier === 'advanced', r.capability_tier);
  check('S1,S2,S3,S4,S5 all fire', (['S1', 'S2', 'S3', 'S4', 'S5'] as const).every((s) => cls.signal_breakdown[s].fired));
  check('S6 fires (explicit multi-agent)', cls.signal_breakdown.S6.fired);
  check('advanced score beats others', cls.scores.advanced > cls.scores.standardized && cls.scores.advanced > cls.scores.minimal, JSON.stringify(cls.scores));
  check('4 sub-agents decomposed', r.trace.stage3_synthesis.sub_agents.length === 4, String(r.trace.stage3_synthesis.sub_agents.length));
  check('slack_notifier + email_sender FLAGGED', r.flagged_write_tools.includes('slack_notifier') && r.flagged_write_tools.includes('email_sender'));
  check('flagged tools NOT bound', (() => {
    const bound = r.config.tooling.bound_tools.value.join(',');
    return !bound.includes('slack_notifier') && !bound.includes('email_sender');
  })());
  check('risk_tier = high', r.risk_tier === 'high', r.risk_tier);
  check('orchestration = coordinator+subagents', r.config.orchestration.orchestration_type.value === 'coordinator+subagents');
}

// ---- NOC Summarizer → Standardized via capability floor (single system!) ----
console.log('\n== NOC Incident Summarizer — capability floor ==');
{
  const intent: Intent = {
    objective: 'Summarize weekly incident reports for the NOC team and flag critical ones, grounded in the incident database.',
    data_sources: ['incident_db'],
    tools: ['incident_reader'],
  };
  const r = synthesize(intent);
  const cls = r.trace.stage2_classification;
  check('tier = standardized', r.capability_tier === 'standardized', r.capability_tier);
  check('S1 fired (retrieval)', cls.signal_breakdown.S1.fired);
  check('S3 NOT fired (single system)', !cls.signal_breakdown.S3.fired, `systems=${r.trace.stage1_nlu.systems.join('|')}`);
  check('capability floor note present', cls.capability_floor_note !== null, String(cls.capability_floor_note));
  check('rag enabled', r.config.data.rag_enabled.value === true);
}

// ---- Formula & base-20 spot checks ----
console.log('\n== Formula / override spot checks ==');
{
  // ≥4 tools forces Advanced
  const r = synthesize({ objective: 'Answer questions using four helpers.', tools: ['a', 'b', 'c', 'd'] });
  check('≥4 tools → forced Advanced', r.capability_tier === 'advanced', r.capability_tier);
}
{
  // no S1/S2/S3 and no override → Minimal
  const r = synthesize({ objective: 'Answer a simple question.' });
  check('no S1/S2/S3 → Minimal', r.capability_tier === 'minimal', r.capability_tier);
}

// ---- Tier override re-evaluation (Section 7.7) ----
console.log('\n== Tier override ==');
{
  const intent: Intent = { objective: 'Summarize incident reports grounded in the incident database.', data_sources: ['incident_db'] };
  const up = applyTierOverride(intent, 'advanced');
  check('upward override accepted', up.accepted && up.result?.capability_tier === 'advanced');
  const down = applyTierOverride(intent, 'minimal');
  check('downward to Minimal refused (retrieval need)', !down.accepted, down.note);
}

console.log(`\n${failures === 0 ? 'ALL ENGINE TESTS PASSED' : failures + ' ENGINE TEST(S) FAILED'}\n`);
process.exit(failures === 0 ? 0 : 1);
