import { useState } from 'react';
import type { Prov, Confidence } from '@/types';
import { VALUE_SOURCE_LABEL } from '@/types';
import { Tooltip } from '@/components/primitives/Tooltip';
import { Modal } from '@/components/primitives/Modal';
import { JsonViewer } from '@/components/primitives/JsonViewer';
import { cn } from '@/utils/cn';

// Section 3.3 — ProvenanceChip: tiny chip on any field row showing the value's
// origin as a letter code (U user · S system · D default · I inferred ·
// G generated), a confidence dot (green/amber/red), and gap_note on hover.
// Clicking opens the field's provenance envelope JSON.

// Derive the five legend letters from the envelope. Engine-generated values are
// value_source 'inferred' at low confidence (Section 7.5); 'inherited' shows H.
export function chipCode(p: Prov<unknown>): string {
  switch (p.value_source) {
    case 'user':
      return 'U';
    case 'system':
      return 'S';
    case 'default':
      return 'D';
    case 'inherited':
      return 'H';
    case 'inferred':
      return p.confidence === 'low' ? 'G' : 'I';
  }
}

function codeLabel(p: Prov<unknown>): string {
  if (p.value_source === 'inferred' && p.confidence === 'low') return 'Engine-generated';
  return VALUE_SOURCE_LABEL[p.value_source];
}

const DOT: Record<Confidence, string> = {
  high: 'bg-ok',
  medium: 'bg-warn',
  low: 'bg-err',
};

const CODE_CLS: Record<string, string> = {
  U: 'text-ok border-ok/30',
  S: 'text-accent border-accent/30',
  D: 'text-text-mid border-border',
  I: 'text-warn border-warn/30',
  G: 'text-err border-err/30',
  H: 'text-info border-info/30',
};

export function ProvenanceChip({ prov, field }: { prov: Prov<unknown>; field?: string }) {
  const [open, setOpen] = useState(false);
  const code = chipCode(prov);

  const tip = (
    <div className="space-y-0.5">
      <div>
        <b>{codeLabel(prov)}</b> · confidence {prov.confidence}
        {prov.verified_flag ? ' · verified' : ''}
      </div>
      {prov.gap_note && <div className="text-text-mid">{prov.gap_note}</div>}
      <div className="text-text-low">Click for provenance envelope</div>
    </div>
  );

  return (
    <>
      <Tooltip content={tip}>
        <button
          onClick={() => setOpen(true)}
          className={cn(
            'inline-flex items-center gap-1 rounded border px-1 py-0.5 text-[10px] font-semibold mono hover:bg-raised',
            CODE_CLS[code],
          )}
        >
          {code}
          <span className={cn('inline-block h-1.5 w-1.5 rounded-full', DOT[prov.confidence])} />
        </button>
      </Tooltip>
      <Modal open={open} onClose={() => setOpen(false)} title={`Provenance · ${field ?? 'field'}`} width="max-w-md">
        <JsonViewer data={prov} maxHeight={320} />
      </Modal>
    </>
  );
}
