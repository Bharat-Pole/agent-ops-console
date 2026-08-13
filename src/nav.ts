// Section 4 — Information architecture / left navigation. Single source for the
// nav model, used by LeftNav and (loosely) the router. Group labels are the
// Databricks-style uppercase section labels from the spec.

import {
  Home,
  LayoutGrid,
  Wand2,
  FileText,
  Wrench,
  Plug,
  Database,
  Boxes,
  KeyRound,
  Cpu,
  Share2,
  ShieldCheck,
  ClipboardCheck,
  Activity,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  // extra path prefixes that should also mark this item active
  match?: string[];
}

export interface NavGroup {
  label: string | null; // null = ungrouped (Home)
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: null,
    items: [{ label: 'Home', to: '/home', icon: Home }],
  },
  {
    label: 'WORKSPACE',
    items: [
      { label: 'Agent Registry', to: '/agents', icon: LayoutGrid },
      // agent creation now starts in the server-backed registry; the legacy
      // /onboarding route redirects here so existing links keep working
      { label: 'New Agent', to: '/agents', icon: Wand2 },
      // Playground removed: it was a kernel-backed surface that could not see
      // server-created agents and ran them outside the governed engine. Testing
      // lives on the agent's own run console (/agents/:id/console).
    ],
  },
  {
    label: 'ASSETS',
    items: [
      { label: 'Tools', to: '/tools', icon: Wrench, match: ['/tools'] },
      { label: 'MCP Connectors', to: '/mcp', icon: Plug, match: ['/mcp'] },
      { label: 'Knowledge', to: '/knowledge', icon: Database, match: ['/knowledge'] },
      { label: 'RAG & Indexes', to: '/rag', icon: Boxes },
      { label: 'Prompt Repository', to: '/prompts', icon: FileText },
      { label: 'A2A Directory', to: '/a2a', icon: Share2 },
      { label: 'Model Catalog', to: '/models', icon: Cpu },
      { label: 'Secrets Vault', to: '/secrets', icon: KeyRound },
    ],
  },
  {
    label: 'GOVERNANCE',
    items: [{ label: 'Approvals & Gates', to: '/governance', icon: ShieldCheck }],
  },
  {
    label: 'OPERATIONS',
    items: [
      { label: 'Evaluations', to: '/evaluations', icon: ClipboardCheck },
      { label: 'Monitoring & FinOps', to: '/monitoring', icon: Activity },
    ],
  },
];
