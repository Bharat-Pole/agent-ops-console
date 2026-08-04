import { useState } from 'react';
import { ChevronRight, ChevronDown, Copy, Check } from 'lucide-react';
import { cn } from '@/utils/cn';

// Collapsible JSON viewer with a copy button (Section 2.3 — reinforces
// "an agent is data"). No external dependency.

function JsonNode({
  keyName,
  value,
  depth,
  defaultOpen,
}: {
  keyName?: string;
  value: unknown;
  depth: number;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(depth < 2 || defaultOpen);

  const isArray = Array.isArray(value);
  const isObject = value !== null && typeof value === 'object';

  if (!isObject) {
    return (
      <div className="leading-relaxed" style={{ paddingLeft: depth * 14 }}>
        {keyName !== undefined && <span className="text-info">"{keyName}"</span>}
        {keyName !== undefined && <span className="text-text-low">: </span>}
        <JsonScalar value={value} />
      </div>
    );
  }

  const entries = isArray
    ? (value as unknown[]).map((v, i) => [String(i), v] as const)
    : Object.entries(value as Record<string, unknown>);

  const open_br = isArray ? '[' : '{';
  const close_br = isArray ? ']' : '}';

  return (
    <div style={{ paddingLeft: depth === 0 ? 0 : 14 }}>
      <button
        className="inline-flex items-center gap-0.5 hover:bg-raised rounded px-0.5 -ml-0.5 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="text-text-low">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        {keyName !== undefined && <span className="text-info">"{keyName}"</span>}
        {keyName !== undefined && <span className="text-text-low">: </span>}
        <span className="text-text-mid">{open_br}</span>
        {!open && (
          <span className="text-text-low">
            {' '}
            {entries.length} {entries.length === 1 ? 'item' : 'items'} {close_br}
          </span>
        )}
      </button>
      {open && (
        <div>
          {entries.map(([k, v]) => (
            <JsonNode
              key={k}
              keyName={isArray ? undefined : k}
              value={v}
              depth={depth + 1}
              defaultOpen={false}
            />
          ))}
          <div className="text-text-mid" style={{ paddingLeft: (depth + 1) * 14 - 14 }}>
            {close_br}
          </div>
        </div>
      )}
    </div>
  );
}

function JsonScalar({ value }: { value: unknown }) {
  if (value === null) return <span className="text-text-low">null</span>;
  if (typeof value === 'string') return <span className="text-ok">"{value}"</span>;
  if (typeof value === 'number') return <span className="text-warn">{value}</span>;
  if (typeof value === 'boolean')
    return <span className="text-tier-advanced">{String(value)}</span>;
  return <span>{String(value)}</span>;
}

export function JsonViewer({
  data,
  className,
  maxHeight = 520,
}: {
  data: unknown;
  className?: string;
  maxHeight?: number;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard may be unavailable; ignore */
    }
  };

  return (
    <div className={cn('relative rounded-card border border-border bg-canvas', className)}>
      <button
        onClick={copy}
        className="absolute right-2 top-2 z-10 inline-flex items-center gap-1 rounded border border-border bg-raised px-2 py-1 text-[11px] text-text-mid hover:text-text-hi"
      >
        {copied ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      <div className="overflow-auto p-3 mono text-[12px]" style={{ maxHeight }}>
        <JsonNode value={data} depth={0} defaultOpen />
      </div>
    </div>
  );
}
