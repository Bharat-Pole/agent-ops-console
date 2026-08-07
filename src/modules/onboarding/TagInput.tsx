import { useState } from 'react';
import { X } from 'lucide-react';

interface Suggestion {
  value: string;
  label: string;
}

function normalize(s: string | Suggestion): Suggestion {
  return typeof s === 'string' ? { value: s, label: s } : s;
}

export function TagInput({
  value,
  onChange,
  placeholder,
  suggestions,
  labelFor,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  // Known ids (e.g. real knowledge source / tool ids) shown as a dropdown
  // while typing — picking one adds its `value` as a tag (same as typing +
  // Enter), while the dropdown and the resulting chip show `label`. Plain
  // strings are shorthand for { value: s, label: s }.
  suggestions?: (string | Suggestion)[];
  // Resolves an already-added tag's real id to a display label — needed when
  // the stored value (e.g. a real "ks-<uuid>" source id) isn't human-readable.
  labelFor?: (id: string) => string;
}) {
  const [draft, setDraft] = useState('');
  const [open, setOpen] = useState(false);

  const addValue = (t: string) => {
    const cleaned = t.trim().replace(/,$/, '');
    if (cleaned && !value.includes(cleaned)) onChange([...value, cleaned]);
    setDraft('');
    setOpen(false);
  };
  const add = () => addValue(draft);

  const matches = suggestions
    ? suggestions
        .map(normalize)
        .filter((s) => !value.includes(s.value))
        .filter((s) => !draft.trim() || s.label.toLowerCase().includes(draft.trim().toLowerCase()))
        .slice(0, 6)
    : [];

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-1 rounded-control border border-border bg-canvas px-2 py-1.5 focus-within:border-border-strong">
        {value.map((t) => (
          <span key={t} className="inline-flex items-center gap-1 rounded bg-raised px-1.5 py-0.5 text-[12px] text-text-hi">
            {labelFor ? labelFor(t) : t}
            <button onClick={() => onChange(value.filter((x) => x !== t))} className="text-text-low hover:text-err"><X size={11} /></button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => { setDraft(e.target.value); setOpen(true); }}
          onFocus={() => { if (suggestions) setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); }
            else if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1));
            else if (e.key === 'Escape') setOpen(false);
          }}
          onBlur={add}
          placeholder={value.length ? '' : placeholder}
          className="min-w-[120px] flex-1 bg-transparent py-0.5 text-[13px] text-text-hi placeholder:text-text-low outline-none"
        />
      </div>
      {open && matches.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-40 overflow-auto rounded-control border border-border bg-raised shadow-lg">
          {matches.map((s) => (
            <button
              key={s.value}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); addValue(s.value); }}
              className="mono block w-full px-2.5 py-1.5 text-left text-[12px] text-text-hi hover:bg-canvas"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
