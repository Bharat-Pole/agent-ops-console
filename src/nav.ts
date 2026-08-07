// Section 4 — Information architecture / left navigation. Single source for the
// nav model, used by LeftNav and (loosely) the router. Group labels are the
// Databricks-style uppercase section labels from the spec.

import {
  Home,
  LayoutGrid,
  Wand2,
  MessagesSquare,
  FileText,
  Wrench,
  Database,
  Share2,
  ShieldCheck,
  ClipboardCheck,
  Activity,
  Layers,
  Network,
  Settings,
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
      { label: 'Onboarding', to: '/onboarding', icon: Wand2 },
      { label: 'Workflow Builder', to: '/builder', icon: Network },
      { label: 'Playground', to: '/playground', icon: MessagesSquare },
    ],
  },
  {
    label: 'ASSETS',
    items: [
      { label: 'Prompt Repository', to: '/prompts', icon: FileText },
      { label: 'Tools & MCP', to: '/tools', icon: Wrench },
      { label: 'Knowledge & RAG', to: '/knowledge', icon: Database },
      { label: 'A2A Directory', to: '/a2a', icon: Share2 },
      { label: 'Model Repository', to: '/models', icon: Layers },
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
  {
    label: 'PLATFORM',
    items: [{ label: 'Admin Console', to: '/admin', icon: Settings }],
  },
];
