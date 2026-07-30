import type {
  KnowledgeSource,
  PipelineRun,
  PipelineStage,
  Sensitivity,
  SourceApproval,
  RefreshCadence,
  Prov,
} from '@/types';
import { prov, PIPELINE_STAGE_NAMES } from '@/types';
import { AGENT, SOURCE } from './ids';
import { isoTs, daysFromToday } from './helpers';

const sp = <T,>(v: T, src: 'system' | 'inferred' | 'user' = 'system'): Prov<T> =>
  prov(v, src, src === 'inferred' ? { confidence: 'low', gap_note: 'Auto-generated. Confirm with data owner.' } : { confidence: 'high' });

// governance-critical sensitivity — confirmed sources are verified/high.
const sens = (v: Sensitivity, confirmed: boolean): Prov<Sensitivity> =>
  prov(v, 'inferred', {
    confidence: confirmed ? 'high' : 'medium',
    verified_flag: confirmed,
    gap_note: confirmed ? null : 'Confirm sensitivity with data owner.',
  });

// ---- Pipeline run builders ----
function completedRun(id: string, sourceId: string, startDate: string, items: number, trigger: 'manual' | 'scheduled'): PipelineRun {
  const stages: PipelineStage[] = PIPELINE_STAGE_NAMES.map((n, idx) => ({
    name: n,
    status: 'ready',
    started_at: isoTs(startDate, 2, idx * 3),
    duration_s: 8 + idx * 4,
    items: Math.round(items * (1 - idx * 0.02)),
  }));
  return { id, source_id: sourceId, stages, trigger, overall: 'ready', started_at: isoTs(startDate, 2, 0) };
}

function midflightRun(id: string, sourceId: string, startDate: string, items: number): PipelineRun {
  const stages: PipelineStage[] = PIPELINE_STAGE_NAMES.map((n, idx) => ({
    name: n,
    status: idx < 4 ? 'ready' : idx === 4 ? 'in_progress' : 'not_started',
    started_at: idx <= 4 ? isoTs(startDate, 2, idx * 3) : null,
    duration_s: idx < 4 ? 8 + idx * 4 : null,
    items: idx < 4 ? Math.round(items * (1 - idx * 0.02)) : null,
  }));
  return { id, source_id: sourceId, stages, trigger: 'scheduled', overall: 'in_progress', started_at: isoTs(startDate, 2, 0) };
}

// Section 12.2 — pipeline runs. capacity-reports (source #4) has one mid-flight run.
export const SEED_PIPELINE_RUNS: PipelineRun[] = [
  completedRun('run-incident-1', SOURCE.incidentDb, daysFromToday(-7), 4820, 'scheduled'),
  completedRun('run-incident-2', SOURCE.incidentDb, daysFromToday(-1), 4931, 'scheduled'),
  completedRun('run-hr-1', SOURCE.hrPolicies, daysFromToday(-14), 342, 'manual'),
  completedRun('run-contracts-1', SOURCE.contractsRepo, daysFromToday(-9), 1180, 'manual'),
  completedRun('run-capacity-1', SOURCE.capacityReports, daysFromToday(-8), 640, 'scheduled'),
  midflightRun('run-capacity-2', SOURCE.capacityReports, daysFromToday(0), 672),
  completedRun('run-churn-1', SOURCE.churnAnalytics, daysFromToday(-5), 2100, 'scheduled'),
  completedRun('run-regulatory-1', SOURCE.regulatoryFilings, daysFromToday(-11), 890, 'manual'),
];

function mkSource(args: {
  id: string;
  name: string;
  uri: string;
  parser: string;
  sensitivity: Sensitivity;
  confirmed: boolean;
  approval: SourceApproval;
  cadence: RefreshCadence;
  version: string;
  index: string;
  docs: number;
  sizeMb: number;
  used_by: string[];
  runs: string[];
  snippets: { doc_id: string; text: string }[];
}): KnowledgeSource {
  return {
    id: args.id,
    name: args.name,
    source_uri: sp(args.uri),
    parser: sp(args.parser, 'inferred'),
    source_chunking: sp('recursive/512-128', 'inferred'),
    embedding_model: sp('openai://text-embedding-3-small'),
    index_target: sp(args.index),
    sensitivity: sens(args.sensitivity, args.confirmed),
    source_approval: prov(args.approval, args.approval === 'approved' ? 'user' : 'inferred', {
      confidence: args.approval === 'approved' ? 'high' : 'low',
      verified_flag: args.approval === 'approved',
      gap_note: args.approval === 'approved' ? null : 'Awaiting data-owner approval.',
    }),
    refresh_cadence: sp(args.cadence, 'inferred'),
    source_version: sp(args.version),
    document_count: args.docs,
    index_size_mb: args.sizeMb,
    used_by: args.used_by,
    snippets: args.snippets,
    ingestion: args.runs,
  };
}

// Section 12.2 — Knowledge sources (6). Each has full 5.12 config + 4–6 snippets.
export const SEED_SOURCES: KnowledgeSource[] = [
  mkSource({
    id: SOURCE.incidentDb,
    name: 'Incident DB (prod)',
    uri: 'gs://brightspeed-noc/incident-db/',
    parser: 'document_ai',
    sensitivity: 'internal',
    confirmed: true,
    approval: 'approved',
    cadence: 'daily',
    version: 'v3',
    index: 'vector://alloydb-incidents',
    docs: 4931,
    sizeMb: 512,
    used_by: [AGENT.noc, AGENT.incident],
    runs: ['run-incident-2', 'run-incident-1'],
    snippets: [
      { doc_id: 'INC-2026-0142', text: 'Core-routing outage in us-central; MTTR 47m; root cause BGP route flap after config push.' },
      { doc_id: 'INC-2026-0151', text: 'DNS-edge degradation; elevated p95 to 9.4s; mitigated by failover to secondary resolver.' },
      { doc_id: 'INC-2026-0163', text: 'Critical: fiber cut midwest backbone; 2h partial outage; escalated to on-call NOC lead.' },
      { doc_id: 'INC-2026-0177', text: 'Recurring transient packet loss on edge-7; flagged for capacity review.' },
      { doc_id: 'INC-2026-0181', text: 'Weekly summary: 23 incidents, 3 critical, mean MTTR 61m, down 12% WoW.' },
    ],
  }),
  mkSource({
    id: SOURCE.hrPolicies,
    name: 'HR Policies',
    uri: 'gs://brightspeed-hr/policies/',
    parser: 'native',
    sensitivity: 'internal',
    confirmed: true,
    approval: 'approved',
    cadence: 'monthly',
    version: 'v2',
    index: 'vector://alloydb-hr',
    docs: 342,
    sizeMb: 44,
    used_by: [AGENT.hr],
    runs: ['run-hr-1'],
    snippets: [
      { doc_id: 'HR-PTO-2026', text: 'Full-time employees accrue 15 days PTO annually, rising to 20 after 3 years.' },
      { doc_id: 'HR-REMOTE-2026', text: 'Hybrid policy: minimum 2 days on-site per week for role bands 4+.' },
      { doc_id: 'HR-PARENTAL-2026', text: 'Parental leave: 12 weeks paid for primary caregivers.' },
      { doc_id: 'HR-EXPENSE-2026', text: 'Expense reimbursement requires manager approval for amounts over $250.' },
    ],
  }),
  mkSource({
    id: SOURCE.contractsRepo,
    name: 'Contracts Repository',
    uri: 'gs://brightspeed-legal/contracts/',
    parser: 'document_ai',
    sensitivity: 'confidential',
    confirmed: true,
    approval: 'approved',
    cadence: 'weekly',
    version: 'v1',
    index: 'vector://alloydb-contracts',
    docs: 1180,
    sizeMb: 220,
    used_by: [AGENT.contract],
    runs: ['run-contracts-1'],
    snippets: [
      { doc_id: 'MSA-ACME-2025', text: 'Limitation of liability capped at 12 months of fees paid.' },
      { doc_id: 'MSA-GLOBEX-2025', text: 'Auto-renewal clause: 60-day notice required to prevent renewal.' },
      { doc_id: 'SLA-INITECH-2026', text: 'Uptime SLA 99.95%; service credits tiered at 99.9/99.5/99.0.' },
      { doc_id: 'NDA-UMBRELLA-2026', text: 'Confidentiality survives 3 years post-termination.' },
    ],
  }),
  mkSource({
    id: SOURCE.capacityReports,
    name: 'Capacity Reports',
    uri: 'gs://brightspeed-noc/capacity/',
    parser: 'native',
    sensitivity: 'internal',
    confirmed: true,
    approval: 'approved',
    cadence: 'weekly',
    version: 'v2',
    index: 'vector://alloydb-capacity',
    docs: 672,
    sizeMb: 96,
    used_by: [AGENT.capacity],
    runs: ['run-capacity-2', 'run-capacity-1'],
    snippets: [
      { doc_id: 'CAP-MIDWEST-Q2', text: 'Midwest utilization 81%; projected headroom 7 months at current growth.' },
      { doc_id: 'CAP-NE-Q2', text: 'Northeast metro rings nearing 90% peak; recommend augmentation in Q3.' },
      { doc_id: 'CAP-WEST-Q2', text: 'West region stable at 63%; no near-term action.' },
      { doc_id: 'CAP-FORECAST-2026', text: 'Company-wide traffic CAGR 18%; capex plan aligned to top-5 congested regions.' },
    ],
  }),
  mkSource({
    id: SOURCE.churnAnalytics,
    name: 'Churn Analytics',
    uri: 'gs://brightspeed-sales/churn/',
    parser: 'native',
    sensitivity: 'confidential',
    confirmed: true,
    approval: 'approved',
    cadence: 'weekly',
    version: 'v1',
    index: 'vector://alloydb-churn',
    docs: 2100,
    sizeMb: 180,
    used_by: [AGENT.churn],
    runs: ['run-churn-1'],
    snippets: [
      { doc_id: 'CHURN-ENT-NE', text: 'Enterprise NE: 14 accounts at risk; top driver support latency.' },
      { doc_id: 'CHURN-SMB-2026', text: 'SMB churn 4.2% monthly; price sensitivity leading indicator.' },
      { doc_id: 'CHURN-SAVE-PLAYS', text: 'Save plays with proactive outreach reduce churn 22%.' },
      { doc_id: 'CHURN-NPS-LINK', text: 'Accounts with NPS < 20 churn at 3.1x baseline.' },
    ],
  }),
  mkSource({
    id: SOURCE.regulatoryFilings,
    name: 'Regulatory Filings',
    uri: 'gs://brightspeed-compliance/filings/',
    parser: 'document_ai',
    sensitivity: 'restricted',
    confirmed: true,
    approval: 'approved',
    cadence: 'monthly',
    version: 'v1',
    index: 'vector://alloydb-filings',
    docs: 890,
    sizeMb: 150,
    used_by: [AGENT.regulatory],
    runs: ['run-regulatory-1'],
    snippets: [
      { doc_id: 'FCC-477-2026', text: 'Form 477 broadband deployment data due 2026-09-01.' },
      { doc_id: 'STATE-PUC-TX', text: 'Texas PUC annual service-quality report filing window opens Aug 15.' },
      { doc_id: 'CPNI-2026', text: 'CPNI annual certification must be filed with the FCC by March 1.' },
      { doc_id: 'CROSS-BORDER-2026', text: 'Cross-border data transfer attestation required for EU subprocessors.' },
    ],
  }),
];
