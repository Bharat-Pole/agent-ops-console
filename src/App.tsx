import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AppShell } from '@/components/shell/AppShell';
import { AuthProvider, useAuth } from '@/api/auth';
import LoginPage from '@/modules/auth/LoginPage';

import HomePage from '@/modules/home/HomePage';
import ServerRegistryPage from '@/modules/registry/ServerRegistryPage';
import ServerAgentDetailPage from '@/modules/registry/ServerAgentDetailPage';
import IntentWizardPage from '@/modules/registry/IntentWizardPage';
import RecommendationPage from '@/modules/registry/RecommendationPage';
import WorkflowBuilderPage from '@/modules/builder/WorkflowBuilderPage';
import RunConsolePage from '@/modules/builder/RunConsolePage';
import OnboardingPage from '@/modules/onboarding/OnboardingPage';
import WizardPage from '@/modules/onboarding/WizardPage';
import PlaygroundPage from '@/modules/playground/PlaygroundPage';
import ServerPromptsPage from '@/modules/assets/ServerPromptsPage';
import ServerToolsPage from '@/modules/assets/ServerToolsPage';
import ServerMcpPage from '@/modules/assets/ServerMcpPage';
import ServerKnowledgePage from '@/modules/assets/ServerKnowledgePage';
import ServerRagPage from '@/modules/assets/ServerRagPage';
import ServerSecretsPage from '@/modules/assets/ServerSecretsPage';
import ApprovalsQueuePage from '@/modules/assets/ApprovalsQueuePage';
import ServerEvaluationsPage from '@/modules/assets/ServerEvaluationsPage';
import ServerMonitoringPage from '@/modules/assets/ServerMonitoringPage';
import A2APage from '@/modules/a2a/A2APage';
import NotFound from '@/modules/NotFound';

// Session gate: everything behind it requires a real backend login. Renders
// as a layout route so the URL (deep link) survives the login round-trip.
function AuthGate() {
  const { state } = useAuth();
  if (state.status === 'loading') {
    return <div className="flex h-screen items-center justify-center text-[13px] text-text-low">Checking session…</div>;
  }
  if (state.status === 'anon') return <LoginPage />;
  return <Outlet />;
}

// Section 4 — one route per module, nested detail routes. Deep-linking is
// first-class (acceptance #12): BrowserRouter + Vite SPA fallback means every
// route survives a hard refresh.
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
      <Routes>
        <Route element={<AuthGate />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/home" replace />} />
          <Route path="/home" element={<HomePage />} />

          {/* WORKSPACE — /agents is served by the real backend (Increment A);
              other modules remain on the in-browser kernel until their
              increment rewires them. */}
          <Route path="/agents" element={<ServerRegistryPage />} />
          <Route path="/agents/:id" element={<ServerAgentDetailPage />} />
          <Route path="/agents/:id/intent" element={<IntentWizardPage />} />
          <Route path="/agents/:id/recommendation" element={<RecommendationPage />} />
          <Route path="/agents/:id/workflows" element={<WorkflowBuilderPage />} />
          <Route path="/agents/:id/console" element={<RunConsolePage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/onboarding/:draftId/phase/:n" element={<WizardPage />} />
          <Route path="/playground" element={<PlaygroundPage />} />
          <Route path="/playground/:agentId" element={<PlaygroundPage />} />

          {/* ASSETS — server-backed (Increment C) */}
          <Route path="/prompts" element={<ServerPromptsPage />} />
          <Route path="/tools" element={<ServerToolsPage />} />
          <Route path="/mcp" element={<ServerMcpPage />} />
          <Route path="/knowledge" element={<ServerKnowledgePage />} />
          <Route path="/rag" element={<ServerRagPage />} />
          <Route path="/secrets" element={<ServerSecretsPage />} />
          <Route path="/a2a" element={<A2APage />} />
          <Route path="/a2a/:agentId" element={<A2APage />} />

          {/* GOVERNANCE — server approval queue */}
          <Route path="/governance" element={<ApprovalsQueuePage />} />

          {/* OPERATIONS */}
          <Route path="/evaluations" element={<ServerEvaluationsPage />} />
          <Route path="/monitoring" element={<ServerMonitoringPage />} />

          <Route path="*" element={<NotFound />} />
        </Route>
        </Route>
      </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
