import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { TopBar } from './TopBar';
import { LeftNav } from './LeftNav';
import { Toaster } from './Toaster';
import { CommandK } from './CommandK';
import { HelpModal } from './HelpModal';
import { useWorkspace } from '@/kernel/store';

export function AppShell() {
  const searchOpen = useWorkspace((s) => s.ui.searchOpen);
  const setSearchOpen = useWorkspace((s) => s.setSearchOpen);
  const [helpOpen, setHelpOpen] = useState(false);

  // Cmd/Ctrl+K opens global search from anywhere (Section 3.1 / M9 keyboard nav).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setSearchOpen]);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TopBar onOpenSearch={() => setSearchOpen(true)} onOpenHelp={() => setHelpOpen(true)} />
      <div className="flex flex-1 overflow-hidden">
        <LeftNav />
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-[1440px] px-6 py-5">
            <Outlet />
          </div>
        </main>
      </div>
      <Toaster />
      <CommandK open={searchOpen} onClose={() => setSearchOpen(false)} />
      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
