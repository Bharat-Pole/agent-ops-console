import { useState, useRef, useEffect } from 'react';
import { Search, HelpCircle, RotateCcw, ChevronDown, Check, Download, Upload } from 'lucide-react';
import { useWorkspace } from '@/kernel/store';
import { PERSONA_LIST, PERSONAS } from '@/kernel/constants';
import { api } from '@/kernel/api';
import { JobTray } from './JobTray';
import { cn } from '@/utils/cn';

export function TopBar({ onOpenSearch, onOpenHelp }: { onOpenSearch: () => void; onOpenHelp: () => void }) {
  const persona = useWorkspace((s) => s.ui.persona);
  const setPersona = useWorkspace((s) => s.setPersona);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const pm = PERSONAS[persona];

  const doExport = () => {
    api.exportWorkspace();
    setMenuOpen(false);
  };
  const doImport = (file: File) => {
    api.importWorkspace(file);
    setMenuOpen(false);
  };

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-nav px-3">
      {/* Wordmark */}
      <div className="flex items-center gap-2 pr-2">
        <span className="text-accent-new">◆</span>
        <span className="text-[14px] text-text-mid">
          Brightspeed <span className="font-semibold text-text-hi">Agent Ops</span>
        </span>
      </div>

      {/* Global search trigger */}
      <button
        onClick={onOpenSearch}
        className="group flex h-8 w-[360px] items-center gap-2 rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-low hover:border-border-strong"
      >
        <Search size={14} />
        <span>Search agents, prompts, tools, sources, models…</span>
        <kbd className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10px] mono text-text-low">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <JobTray />

        <button
          onClick={() => api.reset()}
          title="Reset demo — re-seed the kernel"
          className="inline-flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-[12px] text-text-mid hover:bg-raised hover:text-text-hi"
        >
          <RotateCcw size={14} />
          Reset demo
        </button>

        <button
          onClick={onOpenHelp}
          title="Help & demo script"
          className="rounded-control p-1.5 text-text-mid hover:bg-raised hover:text-text-hi"
        >
          <HelpCircle size={16} />
        </button>

        {/* Persona switcher */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-2 rounded-control border border-border bg-canvas py-1 pl-1 pr-2 hover:border-border-strong"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/20 text-[10px] font-semibold text-accent">
              {pm.short}
            </span>
            <span className="text-[12px] text-text-hi">{pm.label}</span>
            <ChevronDown size={13} className="text-text-low" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 z-50 mt-1 w-72 overflow-hidden rounded-card border border-border-strong bg-raised shadow-2xl animate-fade-in">
              <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-text-low">
                Switch persona
              </div>
              {PERSONA_LIST.map((p) => {
                const m = PERSONAS[p];
                const on = p === persona;
                return (
                  <button
                    key={p}
                    onClick={() => {
                      setPersona(p);
                      setMenuOpen(false);
                    }}
                    className={cn(
                      'flex w-full items-start gap-2.5 px-3 py-2 text-left hover:bg-surface',
                      on && 'bg-surface',
                    )}
                  >
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/20 text-[10px] font-semibold text-accent">
                      {m.short}
                    </span>
                    <span className="flex flex-col">
                      <span className="flex items-center gap-1.5 text-[13px] text-text-hi">
                        {m.label}
                        {on && <Check size={12} className="text-ok" />}
                      </span>
                      <span className="text-[11px] text-text-low">{m.blurb}</span>
                    </span>
                  </button>
                );
              })}
              <div className="border-t border-border">
                <button
                  onClick={doExport}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-text-mid hover:bg-surface hover:text-text-hi"
                >
                  <Download size={14} /> Export workspace JSON
                </button>
                <button
                  onClick={() => fileRef.current?.click()}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-text-mid hover:bg-surface hover:text-text-hi"
                >
                  <Upload size={14} /> Import workspace JSON
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/json"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) doImport(f);
                    e.target.value = '';
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
