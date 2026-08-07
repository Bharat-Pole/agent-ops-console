import type { AgentTelemetry, TelemetryPoint } from '@/types';
import { DEMO_TODAY } from '@/kernel/constants';

export function money(n: number): string {
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}k`;
  if (n >= 100) return `$${n.toFixed(0)}`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(2)}`;
}

export function compactNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

// Real cost (services/monitoring.py) — real tokens that day priced at the
// real per-model rate from the Model Repository, computed server-side since
// a day can mix models (e.g. a chat call + an eval judge call) at different rates.
export function pointCost(p: TelemetryPoint): number {
  return p.cost;
}

export function cost30d(t: AgentTelemetry | undefined): number {
  if (!t) return 0;
  return t.series.reduce((acc, p) => acc + pointCost(p), 0);
}

export function tokens30d(t: AgentTelemetry | undefined): number {
  if (!t) return 0;
  return t.series.reduce((acc, p) => acc + p.tokens_in + p.tokens_out, 0);
}

export function requests30d(t: AgentTelemetry | undefined): number {
  if (!t) return 0;
  return t.series.reduce((acc, p) => acc + p.requests, 0);
}

export function latestP95(t: AgentTelemetry | undefined): number {
  if (!t || t.series.length === 0) return 0;
  return t.series[t.series.length - 1].p95_ms;
}

export function errorRate30d(t: AgentTelemetry | undefined): number {
  if (!t) return 0;
  const req = requests30d(t);
  const err = t.series.reduce((acc, p) => acc + p.errors, 0);
  return req === 0 ? 0 : err / req;
}

// Human date formatting off ISO strings (deterministic; no locale surprises).
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso.length <= 10 ? iso + 'T00:00:00Z' : iso);
  if (isNaN(d.getTime())) return '—';
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${hh}:${mm}`;
}

// Days until a date, relative to the fixed DEMO_TODAY.
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date((iso.length <= 10 ? iso : iso.slice(0, 10)) + 'T00:00:00Z').getTime();
  const today = new Date(DEMO_TODAY + 'T00:00:00Z').getTime();
  return Math.round((target - today) / 86400000);
}

export function relTime(iso: string | null | undefined): string {
  const d = daysUntil(iso);
  if (d === null) return '—';
  if (d === 0) return 'today';
  if (d > 0) return `in ${d}d`;
  return `${-d}d ago`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
}
