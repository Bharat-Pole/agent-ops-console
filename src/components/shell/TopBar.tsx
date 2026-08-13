import { useState, useRef, useEffect } from 'react';
import { Search, HelpCircle, ChevronDown, LogOut } from 'lucide-react';
import { useAuth } from '@/api/auth';
import { titleCase } from '@/utils/format';

/**
 * Top bar.
 *
 * Removed in the obsolete-UI sweep: "Reset demo" (the only thing that ever
 * loaded seeded demo data into the client, which then persisted and made Home
 * and search report figures that were not real), the persona switcher (real
 * session auth decides permissions — a control that appears to change your role
 * but reaches no server is worse than none), workspace JSON import/export, and
 * the job tray (nothing has created a client-side job since execution moved to
 * the engine, so it could only ever be empty).
 *
 * What remains is the real session: who you are signed in as, and the roles the
 * SERVER grants you.
 */
export function TopBar({ onOpenSearch, onOpenHelp }: { onOpenSearch: () => void; onOpenHelp: () => void }) {
  const { me, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const initials = (me?.display_name || me?.email || '?')
    .split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('');

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-nav px-3">
      <div className="flex items-center gap-2 pr-2">
        <span className="text-accent-new">◆</span>
        <span className="text-[14px] text-text-mid">
          Brightspeed <span className="font-semibold text-text-hi">Agent Ops</span>
        </span>
      </div>

      <button
        onClick={onOpenSearch}
        className="group flex h-8 w-[360px] items-center gap-2 rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-low hover:border-border-strong"
      >
        <Search size={14} />
        <span>Search agents, prompts, tools, sources…</span>
        <kbd className="ml-auto rounded border border-border px-1.5 py-0.5 text-[10px] mono text-text-low">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <button
          onClick={onOpenHelp}
          title="About this console"
          className="rounded-control p-1.5 text-text-mid hover:bg-raised hover:text-text-hi"
        >
          <HelpCircle size={16} />
        </button>

        {me && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="flex items-center gap-2 rounded-control border border-border bg-canvas py-1 pl-1 pr-2 hover:border-border-strong"
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/20 text-[10px] font-semibold text-accent">
                {initials}
              </span>
              <span className="text-[12px] text-text-hi">{me.display_name || me.email}</span>
              <ChevronDown size={13} className="text-text-low" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 z-50 mt-1 w-72 overflow-hidden rounded-card border border-border-strong bg-raised shadow-2xl animate-fade-in">
                <div className="border-b border-border px-3 py-2">
                  <div className="text-[13px] text-text-hi">{me.email}</div>
                  <div className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-low">
                    Roles granted by the server
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {me.roles.length === 0 && (
                      <span className="text-[11px] text-text-low">none — read-only access</span>
                    )}
                    {me.roles.map((r) => (
                      <span key={r} className="rounded border border-border px-1.5 py-0.5 text-[10px] text-text-mid">
                        {titleCase(r)}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => void logout()}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-text-mid hover:bg-surface hover:text-text-hi"
                >
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
