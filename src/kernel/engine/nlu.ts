// Stage 1 — Intake & Normalize (Section 7.1). Keyword/regex NLU over the
// objective extracts task_type, domain, data-source/tool mentions, audience,
// output format. Ported from the POC engine_stub with the same detection rules.

import type { Intent, NluResult } from './types';

const TASK_VERBS: [string, RegExp][] = [
  ['coordinate', /\b(coordinat|orchestrat)/],
  ['route', /\b(route|escalate|assign|hand[- ]?off|dispatch|notify)/],
  ['draft', /\b(draft|compose|write)\b/],
  ['analyze', /\b(analyze|assess|evaluate|investigate|research)/],
  ['summarize', /\b(summariz|summarise|digest|recap)/],
  ['answer', /\b(answer|respond|explain|help)\b/],
];

const DOMAINS: [string, RegExp][] = [
  ['HR', /\b(hr|human resources|employee|benefits|payroll|pto)\b/],
  ['network_ops', /\b(noc|incident|network|outage|capacity|routing|telemetry|fiber)\b/],
  ['finance', /\b(finance|financial|invoice|payment|revenue|billing)\b/],
  ['legal', /\b(legal|contract|clause|nda|msa|counsel)\b/],
  ['support', /\b(support|ticket|help ?desk|faq|technician|field)\b/],
  ['sales', /\b(sales|crm|churn|retention|account|pipeline)\b/],
  ['compliance', /\b(regulat|compliance|filing|fcc|puc|attestation)\b/],
];

// Canonical system *families* (word-boundary matched). Synonyms map to one
// family so a data source and its own reader tool count as ONE system, and
// "database"/"db" never double-count (which would falsely fire S3 for a
// single-source RAG bot like the NOC summarizer).
const SYSTEM_FAMILIES: [RegExp, string][] = [
  [/\bslack\b/, 'slack'],
  [/\bemail\b/, 'email'],
  [/\bjira\b/, 'ticketing'],
  [/\bservicenow\b/, 'ticketing'],
  [/\bzendesk\b/, 'ticketing'],
  [/\bticketing\b/, 'ticketing'],
  [/\bconfluence\b/, 'docs'],
  [/\bsharepoint\b/, 'docs'],
  [/\bgithub\b/, 'github'],
  [/\bsalesforce\b/, 'crm'],
  [/\bcrm\b/, 'crm'],
  [/\bdatabase\b/, 'database'],
  [/\bdb\b/, 'database'],
  [/\bs3\b/, 'storage'],
  [/\bgcs\b/, 'storage'],
  [/\bbigquery\b/, 'storage'],
];

function familiesIn(str: string, into: Set<string>): void {
  const s = str.toLowerCase().replace(/[_-]/g, ' ');
  for (const [re, fam] of SYSTEM_FAMILIES) if (re.test(s)) into.add(fam);
}

export const ACTION_VERBS = [
  'summarize', 'summarise', 'analyze', 'analyse', 'draft', 'check', 'notify', 'alert',
  'review', 'classify', 'extract', 'answer', 'route', 'assess', 'generate', 'compare',
  'flag', 'monitor', 'coordinate', 'triage', 'research', 'recommend', 'watch',
];

function firstMatch(text: string, table: [string, RegExp][], fallback: string): string {
  for (const [label, re] of table) if (re.test(text)) return label;
  return fallback;
}

export function countActionVerbs(text: string): string[] {
  const found = new Set<string>();
  for (const v of ACTION_VERBS) {
    if (new RegExp(`\\b${v}`).test(text)) {
      // normalize British/American spellings to one bucket per concept
      found.add(v.replace('summarise', 'summarize').replace('analyse', 'analyze'));
    }
  }
  return [...found];
}

export function detectSystems(text: string, dataSources: string[], tools: string[]): string[] {
  // Distinct backend *families* only. A data source and its own reader tool
  // ("incident_db" + "incident_reader") map to the same family → ONE system.
  const fams = new Set<string>();
  familiesIn(text, fams);
  for (const s of dataSources) familiesIn(s, fams);
  for (const t of tools) familiesIn(t, fams);
  return [...fams];
}

const RETRIEVAL_CUES = [
  'document', 'knowledge base', 'knowledge', 'based on', 'using data', 'grounded in',
  'retrieve', 'look up', 'search the', 'from the docs', 'cited', 'citation', 'repository',
  'reports', 'records', 'database',
];

export function firesRetrieval(text: string, dataSources: string[]): boolean {
  // A named data source is the strongest cue. Generic words like "policy" do NOT
  // fire this (keeps the HR-policy bot Minimal, worked Example 1).
  return dataSources.length > 0 || RETRIEVAL_CUES.some((c) => text.includes(c));
}

export function detectNlu(intent: Intent): NluResult {
  const text = (intent.objective || '').toLowerCase();
  const dataSources = intent.data_sources ?? [];
  const tools = intent.tools ?? [];

  const action_verbs = countActionVerbs(text);
  const systems = detectSystems(text, dataSources, tools);

  const outputFmt = /\bjson\b/.test(text) ? 'json' : /\b(report|summary|digest)\b/.test(text) ? 'report' : /\b(list|table)\b/.test(text) ? 'list' : null;

  const gaps: string[] = [];
  if (!intent.intended_audience && !/\bfor the\b/.test(text)) gaps.push('intended_audience');
  if (!intent.business_owner) gaps.push('business_owner');
  if (!intent.technical_owner) gaps.push('technical_owner');
  if (dataSources.length === 0 && firesRetrieval(text, [])) gaps.push('data_sources');

  return {
    task_type: firstMatch(text, TASK_VERBS, 'answer'),
    domain: firstMatch(text, DOMAINS, 'general'),
    data_source_mentions: dataSources,
    tool_mentions: tools,
    audience: intent.intended_audience ?? (/(for the [a-z ]+team)/.exec(text)?.[1] ?? null),
    output_format: outputFmt,
    action_verbs,
    systems,
    gaps,
  };
}
