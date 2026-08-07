import { useState, useRef, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { Plus, PanelLeftClose, PanelLeftOpen, Wand2, FileText, Wrench, Database } from 'lucide-react';
import { NAV } from '@/nav';
import { useWorkspace, type FeatureFlags } from '@/kernel/store';
import { cn } from '@/utils/cn';

const CREATE_MENU = [
  { label: 'New Agent', hint: 'Onboarding wizard', icon: Wand2, to: '/onboarding?new=1' },
  { label: 'New Prompt', hint: 'Prompt Repository', icon: FileText, to: '/prompts?new=1' },
  { label: 'Register Tool', hint: 'Tool Catalog', icon: Wrench, to: '/tools?new=1' },
  { label: 'Add Knowledge Source', hint: 'Knowledge & RAG', icon: Database, to: '/knowledge?new=1' },
];

// Routes gated by an Admin Console feature flag (see kernel/store.ts FeatureFlags).
const FLAG_GATED_ROUTES: Record<string, keyof FeatureFlags> = {
  '/models': 'model_repository',
  '/builder': 'workflow_builder',
};

export function LeftNav() {
  const collapsed = useWorkspace((s) => s.ui.navCollapsed);
  const toggleNav = useWorkspace((s) => s.toggleNav);
  const featureFlags = useWorkspace((s) => s.ui.featureFlags);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <nav
      className={cn(
        'flex h-full flex-col border-r border-border bg-nav transition-all duration-150',
        collapsed ? 'w-14' : 'w-60',
      )}
    >
      {/* + New */}
      <div className="relative p-2" ref={menuRef}>
        <button
          onClick={() => setMenuOpen((o) => !o)}
          className={cn(
            'flex w-full items-center gap-2 rounded-control bg-accent-new px-3 py-2 text-[13px] font-semibold text-white hover:brightness-110 focus-ring',
            collapsed && 'justify-center px-0',
          )}
        >
          <Plus size={16} />
          {!collapsed && <span>New</span>}
        </button>
        {menuOpen && (
          <div className="absolute left-2 right-2 z-50 mt-1 overflow-hidden rounded-card border border-border-strong bg-raised shadow-2xl animate-fade-in">
            {CREATE_MENU.map((m) => (
              <button
                key={m.label}
                onClick={() => {
                  setMenuOpen(false);
                  navigate(m.to);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-text-hi hover:bg-surface"
              >
                <m.icon size={15} className="text-text-mid" />
                <span className="flex flex-col">
                  <span>{m.label}</span>
                  <span className="text-[11px] text-text-low">{m.hint}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Nav groups */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {NAV.map((group, gi) => (
          <div key={gi} className="mb-2">
            {group.label && !collapsed && (
              <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-text-low">
                {group.label}
              </div>
            )}
            {group.label && collapsed && gi > 0 && <div className="my-2 mx-2 border-t border-border" />}
            {group.items.filter((it) => {
              const gate = FLAG_GATED_ROUTES[it.to];
              return !gate || featureFlags[gate];
            }).map((it) => {
              const active =
                location.pathname === it.to ||
                location.pathname.startsWith(it.to + '/') ||
                (it.match?.some((m) => location.pathname.startsWith(m)) ?? false);
              return (
                <NavLink
                  key={it.to}
                  to={it.to}
                  title={collapsed ? it.label : undefined}
                  className={cn(
                    'group relative mb-0.5 flex items-center gap-2.5 rounded-control px-2 py-1.5 text-[13px] transition',
                    active
                      ? 'bg-accent/15 text-text-hi font-medium'
                      : 'text-text-mid hover:bg-surface hover:text-text-hi',
                    collapsed && 'justify-center',
                  )}
                >
                  {active && <span className="absolute left-0 top-1 bottom-1 w-0.5 rounded-full bg-accent" />}
                  <it.icon size={16} className={active ? 'text-accent' : ''} />
                  {!collapsed && <span className="truncate">{it.label}</span>}
                </NavLink>
              );
            })}
          </div>
        ))}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={toggleNav}
        className="flex items-center gap-2 border-t border-border px-3 py-2.5 text-[12px] text-text-low hover:text-text-hi"
      >
        {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        {!collapsed && <span>Collapse</span>}
      </button>
    </nav>
  );
}
