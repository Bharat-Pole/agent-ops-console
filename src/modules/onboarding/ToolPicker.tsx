import { useMemo, useState } from 'react';
import { X, Ban, AlertTriangle, Clock } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import { Badge } from '@/components/primitives';
import { cn } from '@/utils/cn';
import type { ToolStatus, ToolAsset } from '@/types';

// Catalog-backed replacement for TagInput on the Tools field. The tool the user
// names here is what the synthesis engine binds, and each tool drags in exactly
// one MCP connector (a fixed FK on the tool row — a lookup, never a choice), so
// this is the first point in the wizard where the agent's MCP dependencies are
// actually decided. Free text made that decision invisible and untypo-able.
//
// Free entry is still allowed — a tool may legitimately not be catalogued yet —
// but an unrecognised name renders with a "not in catalog" warning instead of
// looking identical to a real one. A governance console should *show* the
// problem, not silently prevent the input.
//
// write_capable tools are selectable on purpose. They are advisory-blocked at
// synthesis and again server-side in tool_binding.py; letting the user pick one
// and watch it get dropped is the governance story made legible.
//
// Unapproved tools are shown the same way (Phase 3.2 / R8). They stay
// selectable for the same reason — but the badge is what makes it an *informed*
// choice rather than a surprise at the Register step, where the server strips
// the ref and the toast explains after the fact. Note the two states are
// independent of `status`: a tool can be `available` (its connector is healthy)
// and still unbindable (nobody has approved it).

const dot = (status: ToolStatus) =>
  status === 'available' ? 'bg-ok' : status === 'degraded' ? 'bg-warn' : 'bg-err';

// Mirrors the server's guard order in bound_tools_guard.sanitize_bound_tools():
// write-capability first, so approval never reads as an override for it.
const unbindable = (t: ToolAsset): 'write' | 'pending' | 'rejected' | null =>
  t.write_capable ? 'write' : t.approval_state === 'approved' ? null : t.approval_state;

export function ToolPicker({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const tools = useWorkspace((s) => s.tools);
  const connectors = useWorkspace((s) => s.connectors);
  const [draft, setDraft] = useState('');
  const [open, setOpen] = useState(false);

  const connectorName = (id: string | null) => connectors.find((c) => c.id === id)?.name ?? id;

  const suggestions = useMemo(() => {
    const q = draft.trim().toLowerCase();
    return tools
      .filter((t) => !value.includes(t.id))
      .filter((t) => !q || t.id.toLowerCase().includes(q) || t.category.toLowerCase().includes(q))
      .slice(0, 6);
  }, [tools, value, draft]);

  const add = (id: string) => {
    const t = id.trim().replace(/,$/, '');
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft('');
    setOpen(false);
  };

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-1 rounded-control border border-border bg-canvas px-2 py-1.5 focus-within:border-border-strong">
        {value.map((id) => {
          const t = tools.find((x) => x.id === id);
          const blocked = t ? unbindable(t) : null;
          return (
            <span
              key={id}
              className={cn(
                'inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[12px]',
                !t ? 'border-warn/40 bg-warn/10 text-warn'
                  : blocked === 'write' ? 'border-err/40 bg-err/10 text-text-hi'
                  : blocked ? 'border-warn/40 bg-warn/10 text-text-hi'
                  : 'border-border bg-raised text-text-hi',
              )}
            >
              {t && <span className={cn('h-1.5 w-1.5 rounded-full', dot(t.status))} />}
              <span className="mono">{id}</span>
              {!t ? (
                <span className="inline-flex items-center gap-0.5 text-[10px]"><AlertTriangle size={9} /> not in catalog</span>
              ) : blocked === 'write' ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] text-err"><Ban size={9} /> write</span>
              ) : blocked ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] text-warn"><Clock size={9} /> {blocked}</span>
              ) : (
                <span className="text-[10px] text-text-low">{t.connector_id ? connectorName(t.connector_id) : 'local'}</span>
              )}
              <button onClick={() => onChange(value.filter((x) => x !== id))} className="text-text-low hover:text-err"><X size={11} /></button>
            </span>
          );
        })}
        <input
          value={draft}
          onChange={(e) => { setDraft(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault();
              // Enter takes the single remaining suggestion, else the raw text.
              add(suggestions.length === 1 ? suggestions[0].id : draft);
            } else if (e.key === 'Escape') setOpen(false);
            else if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1));
          }}
          // Delay so a click on a suggestion lands before the list unmounts.
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          placeholder={value.length ? '' : placeholder}
          className="min-w-[140px] flex-1 bg-transparent py-0.5 text-[13px] text-text-hi placeholder:text-text-low outline-none"
        />
      </div>

      {open && suggestions.length > 0 && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-control border border-border-strong bg-raised shadow-lg">
          {suggestions.map((t) => (
            <button
              key={t.id}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => add(t.id)}
              className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[12px] hover:bg-canvas"
            >
              <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dot(t.status))} />
              <span className="mono flex-1 truncate text-text-hi">{t.id}</span>
              {unbindable(t) === 'write' ? (
                <Badge tone="err"><Ban size={9} /> WRITE — advisory-block</Badge>
              ) : unbindable(t) ? (
                <Badge tone="warn"><Clock size={9} /> {t.approval_state} — not bindable yet</Badge>
              ) : (
                <>
                  <span className="text-[10px] text-text-low">{t.permission_ceiling}</span>
                  <Badge tone={t.connector_id ? 'info' : 'muted'}>
                    {t.connector_id ? connectorName(t.connector_id) : 'local — no MCP'}
                  </Badge>
                </>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
