import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '@/components/shell/AppShell';
import { api } from '@/kernel/api';

import HomePage from '@/modules/home/HomePage';
import RegistryPage from '@/modules/registry/RegistryPage';
import AgentDetailPage from '@/modules/registry/AgentDetailPage';
import OnboardingPage from '@/modules/onboarding/OnboardingPage';
import WizardPage from '@/modules/onboarding/WizardPage';
import PlaygroundPage from '@/modules/playground/PlaygroundPage';
import PromptsPage from '@/modules/prompts/PromptsPage';
import PromptDetailPage from '@/modules/prompts/PromptDetailPage';
import ToolsPage from '@/modules/tools/ToolsPage';
import KnowledgePage from '@/modules/knowledge/KnowledgePage';
import A2APage from '@/modules/a2a/A2APage';
import ModelsPage from '@/modules/models/ModelsPage';
import BuilderPage from '@/modules/builder/BuilderPage';
import AdminPage from '@/modules/admin/AdminPage';
import GovernancePage from '@/modules/governance/GovernancePage';
import EvaluationsPage from '@/modules/evaluations/EvaluationsPage';
import EvalDetailPage from '@/modules/evaluations/EvalDetailPage';
import MonitoringPage from '@/modules/monitoring/MonitoringPage';
import NotFound from '@/modules/NotFound';

// Section 4 — one route per module, nested detail routes. Deep-linking is
// first-class (acceptance #12): BrowserRouter + Vite SPA fallback means every
// route survives a hard refresh.
export default function App() {
  // Hydrate agents/approvals/audit log/eval packs with server-persisted truth
  // once on load. The client keeps its local seed data until this resolves —
  // no loading gate needed (see kernel/store.ts hydrateFromServer).
  useEffect(() => {
    void api.bootstrapWorkspace();
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/home" replace />} />
          <Route path="/home" element={<HomePage />} />

          {/* WORKSPACE */}
          <Route path="/agents" element={<RegistryPage />} />
          <Route path="/agents/:id" element={<AgentDetailPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/onboarding/:draftId/phase/:n" element={<WizardPage />} />
          <Route path="/builder" element={<BuilderPage />} />
          <Route path="/builder/:agentId" element={<BuilderPage />} />
          <Route path="/playground" element={<PlaygroundPage />} />
          <Route path="/playground/:agentId" element={<PlaygroundPage />} />

          {/* ASSETS */}
          <Route path="/prompts" element={<PromptsPage />} />
          <Route path="/prompts/:id" element={<PromptDetailPage />} />
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/a2a" element={<A2APage />} />
          <Route path="/a2a/:agentId" element={<A2APage />} />
          <Route path="/models" element={<ModelsPage />} />

          {/* PLATFORM */}
          <Route path="/admin" element={<AdminPage />} />

          {/* GOVERNANCE */}
          <Route path="/governance" element={<GovernancePage />} />

          {/* OPERATIONS */}
          <Route path="/evaluations" element={<EvaluationsPage />} />
          <Route path="/evaluations/:packId" element={<EvalDetailPage />} />
          <Route path="/monitoring" element={<MonitoringPage />} />

          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
