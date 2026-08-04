import { useState } from 'react';
import { X } from 'lucide-react';

export function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const t = draft.trim().replace(/,$/, '');
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft('');
  };
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-control border border-border bg-canvas px-2 py-1.5 focus-within:border-border-strong">
      {value.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded bg-raised px-1.5 py-0.5 text-[12px] text-text-hi">
          {t}
          <button onClick={() => onChange(value.filter((x) => x !== t))} className="text-text-low hover:text-err"><X size={11} /></button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); }
          else if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1));
        }}
        onBlur={add}
        placeholder={value.length ? '' : placeholder}
        className="min-w-[120px] flex-1 bg-transparent py-0.5 text-[13px] text-text-hi placeholder:text-text-low outline-none"
      />
    </div>
  );
}
