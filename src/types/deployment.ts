// Deployment & Access Management (Blueprint §5.10 / §9) — a real environment
// ladder and access grant register backing what used to be a single free-text
// config.deployment.environment string with no history.

export type Environment = 'staging' | 'production';
export type DeploymentAction = 'initial' | 'promote' | 'rollback';
export type DeploymentStatus = 'success' | 'failed';

export interface DeploymentRecord {
  id: string;
  agent_id: string;
  action: DeploymentAction;
  from_environment: Environment | null;
  to_environment: Environment;
  strategy: string;
  status: DeploymentStatus;
  reason: string | null;
  actor_persona: string;
  created_at: string;
}

export type AccessScope = 'owner' | 'admin' | 'viewer';

export interface AccessGrant {
  id: string;
  agent_id: string | null; // null = platform-wide grant
  grantee: string;
  role_label: string;
  scope: AccessScope;
  granted_by: string;
  status: 'active' | 'revoked';
  granted_at: string;
  revoked_at: string | null;
  revoked_by: string | null;
}
