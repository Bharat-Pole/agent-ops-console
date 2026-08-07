// Stage 2b — architecture recommendation tests (deterministic baseline +
// validator + override), over the three seed fixtures.
//   npx tsx test/architecture.ts

import { synthesize, validateArchitecture, applyArchitectureOverride, applyLlmRecommendation, synthesizeGraphSpec } from '@/kernel/engine';
import type { Intent } from '@/kernel/engine';

let failures = 0;
function check(name: string, cond: boolean, extra = '') {
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${name}${cond ? '' : '  ' + extra}`);
  if (!cond) failures += 1;
}

const HR: Intent = {
  objective: 'Answer employee questions about company HR policies and benefits in plain language.',
  intended_audience: 'All employees',
};
const INCIDENT: Intent = {
  objective:
    'Coordinate a team of agents to triage major incidents: analyze logs from the incident database and ticketing system, assess customer impact, draft comms, and route notifications to the on-call NOC lead and Slack.',
  intended_audience: 'NOC responders',
  data_sources: ['incident_db', 'ticketing'],
  tools: ['incident_reader', 'log_reader', 'health_checker', 'jira_reader', 'slack_notifier', 'email_sender'],
};
const NOC: Intent = {
  objective: 'Summarize weekly incident reports for the NOC team and flag critical ones, grounded in the incident database.',
  data_sources: ['incident_db'],
  tools: ['incident_reader'],
};

// ---- HR Policy Bot → single (no graph) ----
console.log('\n== HR Policy Bot → single ==');
{
  const r = synthesize(HR);
  const a = r.trace.stage2b_architecture;
  check('architecture = single', r.architecture === 'single', r.architecture);
  check('orchestration_type = single', a.orchestration_type === 'single', a.orchestration_type);
  check('graph is null', a.graph === null);
  check('config graph leaf null', r.config.orchestration.graph.value === null);
  check('baseline validates', validateArchitecture(a, r.trace.stage2_classification, r.config.tooling.bound_tools.value).ok);
}

// ---- Incident Response Coordinator → hub_and_spoke (4 spokes + coordinator) ----
console.log('\n== Incident Response Coordinator → hub_and_spoke ==');
{
  const r = synthesize(INCIDENT);
  const a = r.trace.stage2b_architecture;
  check('architecture = hub_and_spoke', r.architecture === 'hub_and_spoke', r.architecture);
  check('orchestration_type = coordinator+subagents', a.orchestration_type === 'coordinator+subagents', a.orchestration_type);
  check('pattern = hub', a.pattern === 'hub', String(a.pattern));
  check('graph present', a.graph !== null);
  check('graph has coordinator + 4 spokes (5 nodes)', a.graph?.nodes.length === 5, String(a.graph?.nodes.length));
  check('coordinator node is a route hub', !!a.graph?.nodes.find((n) => n.id === 'coordinator' && n.kind === 'route'));
  check('confidence high (forced multi-agent)', a.confidence === 'high', a.confidence);
  check('baseline validates', validateArchitecture(a, r.trace.stage2_classification, r.config.tooling.bound_tools.value).ok);
}

// ---- NOC Summarizer → graph (retrieve → generate) ----
console.log('\n== NOC Summarizer → graph ==');
{
  const r = synthesize(NOC);
  const a = r.trace.stage2b_architecture;
  check('architecture = graph', r.architecture === 'graph', r.architecture);
  check('orchestration_type = router', a.orchestration_type === 'router', a.orchestration_type);
  check('graph is retrieve → generate', a.graph?.nodes.map((n) => n.id).join(',') === 'retrieve,generate', JSON.stringify(a.graph?.nodes));
  check('baseline validates', validateArchitecture(a, r.trace.stage2_classification, r.config.tooling.bound_tools.value).ok);
}

// ---- validator rejects non-advisory sub-agent tools ----
console.log('\n== validator: advisory guardrail ==');
{
  const r = synthesize(INCIDENT);
  const cls = r.trace.stage2_classification;
  const bad = {
    ...r.trace.stage2b_architecture,
    sub_agents: [{ name: 'x', role: '', prompt_hint: '', tools: ['tools://evil_writer@v1'] }],
  };
  const v = validateArchitecture(bad, cls, r.config.tooling.bound_tools.value);
  check('unknown/write sub-agent tool rejected', !v.ok, v.violations.join('; '));
}

// ---- overrides ----
console.log('\n== architecture override ==');
{
  const refuse = applyArchitectureOverride(INCIDENT, 'single');
  check('single refused when multi-agent forced', !refuse.accepted, refuse.note);

  const ok = applyArchitectureOverride(HR, 'graph');
  check('HR → graph override accepted', ok.accepted && ok.result?.architecture === 'graph', ok.note);
}

// ---- LLM-first apply (applyLlmRecommendation) ----
console.log('\n== applyLlmRecommendation (LLM-first) ==');
{
  // valid LLM pick for the incident coordinator → accepted, source llm, graph rebuilt
  const ok = applyLlmRecommendation(INCIDENT, { architecture: 'hub_and_spoke', rationale: ['LLM: independent specialists'], confidence: 'high' });
  check('valid LLM pick accepted', ok.accepted && ok.result?.architecture === 'hub_and_spoke', ok.note);
  check('recommendation tagged source=llm', ok.result?.trace.stage2b_architecture.source === 'llm');
  check('graph rebuilt (coordinator + 4 spokes)', ok.result?.trace.stage2b_architecture.graph?.nodes.length === 5);

  // hard gate: LLM picks single for a forced multi-agent intent → rejected
  const bad = applyLlmRecommendation(INCIDENT, { architecture: 'single' });
  check('LLM single rejected when forced', !bad.accepted, bad.note);

  // unknown architecture → rejected
  const unknown = applyLlmRecommendation(HR, { architecture: 'blackboard' as never });
  check('unknown architecture rejected', !unknown.accepted, unknown.note);

  // LLM supplies a broken graph → falls back to the deterministic graph, still accepted
  const brokenGraph = applyLlmRecommendation(NOC, {
    architecture: 'graph',
    graph: { nodes: [{ id: 'a', kind: 'llm' }], edges: [{ from: 'a', to: 'ghost' }] },
  });
  check('broken LLM graph → deterministic fallback accepted', brokenGraph.accepted && brokenGraph.result?.architecture === 'graph', brokenGraph.note);
  check('fallback graph is retrieve→generate', brokenGraph.result?.trace.stage2b_architecture.graph?.nodes.map((n) => n.id).join(',') === 'retrieve,generate');
}

// ---- graph regeneration used by updateOrchestration (pattern → kind) ----
console.log('\n== synthesizeGraphSpec (orchestration edit) ==');
{
  const subs = [
    { name: 'research', role: '', prompt_hint: '', tools: [] },
    { name: 'draft', role: '', prompt_hint: '', tools: [] },
    { name: 'review', role: '', prompt_hint: '', tools: [] },
  ];
  const pipe = synthesizeGraphSpec('sequential_pipeline', subs, false);
  check('pipeline graph chains stages in order', pipe?.nodes.map((n) => n.id).join(',') === 'research,draft,review');
  check('pipeline has 2 edges (linear)', pipe?.edges.length === 2 && pipe?.edges[0].from === 'research' && pipe?.edges[0].to === 'draft');

  const hub = synthesizeGraphSpec('hub_and_spoke', subs, false);
  check('hub graph has coordinator + 3 spokes', hub?.nodes.length === 4 && hub?.nodes[0].id === 'coordinator');
  check('single graph is null', synthesizeGraphSpec('single', [], false) === null);
}

// ---- determinism ----
console.log('\n== determinism ==');
{
  const a1 = JSON.stringify(synthesize(INCIDENT).trace.stage2b_architecture);
  const a2 = JSON.stringify(synthesize(INCIDENT).trace.stage2b_architecture);
  check('recommendation is byte-identical across runs', a1 === a2);
}

console.log(`\n${failures === 0 ? 'ALL ARCHITECTURE TESTS PASSED' : failures + ' ARCHITECTURE TEST(S) FAILED'}\n`);
process.exit(failures === 0 ? 0 : 1);
