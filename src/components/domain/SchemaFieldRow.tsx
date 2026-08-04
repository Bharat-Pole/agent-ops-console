import { Pencil } from 'lucide-react';
import type { Prov } from '@/types';
import { ProvenanceChip } from './ProvenanceChip';
import { AssetRefLink } from './AssetRefLink';
import { GOVERNANCE_CRITICAL_FIELDS } from '@/types';
import { cn } from '@/utils/cn';

const URI_RE = /^[a-z0-9]+:\/\//i;

function ValueView({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-text-low">—</span>;
  }
  if (typeof value === 'boolean') {
    return (
      <span className={cn('mono text-[12px]', value ? 'text-ok' : 'text-text-mid')}>{String(value)}</span>
    );
  }
  if (typeof value === 'number') {
    return <span className="mono text-[12px] text-text-hi">{value}</span>;
  }
  if (typeof value === 'string') {
    if (URI_RE.test(value)) return <AssetRefLink refUri={value} />;
    return <span className="text-text-hi">{value}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-text-low">[] empty</span>;
    if (value.every((v) => typeof v === 'string')) {
      return (
        <span className="flex flex-wrap gap-1">
          {value.map((v, i) =>
            URI_RE.test(v as string) ? (
              <AssetRefLink key={i} refUri={v as string} />
            ) : (
              <span key={i} className="rounded bg-raised px-1.5 py-0.5 text-[11px] text-text-mid">
                {v as string}
              </span>
            ),
          )}
        </span>
      );
    }
    // array of objects (e.g., sub_agents, hitl gates)
    return (
      <span className="flex flex-col gap-0.5">
        {value.map((v, i) => (
          <span key={i} className="mono text-[11px] text-text-mid">
            {summarizeObject(v)}
          </span>
        ))}
      </span>
    );
  }
  if (typeof value === 'object') {
    return <span className="mono text-[11px] text-text-mid">{summarizeObject(value)}</span>;
  }
  return <span className="text-text-hi">{String(value)}</span>;
}

function summarizeObject(v: unknown): string {
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    if ('name' in o && 'role' in o) return `${o.name} — ${String(o.role).slice(0, 60)}`;
    if ('placement' in o) return `${o.placement}: ${o.trigger}`;
    const keys = Object.keys(o);
    return `{ ${keys.slice(0, 4).join(', ')}${keys.length > 4 ? '…' : ''} }`;
  }
  return String(v);
}

// Section 9.2 #2 — every field is a SchemaFieldRow: label (verbatim field name,
// mono), value, ProvenanceChip.
export function SchemaFieldRow({ field, prov, onEdit }: { field: string; prov: Prov<unknown>; onEdit?: () => void }) {
  const critical = GOVERNANCE_CRITICAL_FIELDS.has(field);
  return (
    <div className="group flex items-start gap-3 border-b border-border/50 py-1.5 last:border-0">
      <div className="flex w-56 shrink-0 items-center gap-1.5">
        <span className="mono text-[12px] text-text-mid">{field}</span>
        {critical && (
          <span className="rounded bg-warn/15 px-1 text-[9px] font-semibold text-warn" title="governance-critical field">
            GOV
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1 text-[12px]">
        <ValueView value={prov.value} />
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {onEdit && (
          <button onClick={onEdit} title="Propose change" className="text-text-low opacity-0 transition group-hover:opacity-100 hover:text-accent">
            <Pencil size={12} />
          </button>
        )}
        <ProvenanceChip prov={prov} field={field} />
      </div>
    </div>
  );
}
