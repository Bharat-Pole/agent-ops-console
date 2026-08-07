import { useState } from 'react';
import { Button } from '@/components/primitives';
import { useAuth } from '@/api/auth';
import { apiErrorMessage } from '@/api/client';

// Seeded by backend/app/seed.py — shown as a dev convenience on the login
// screen. Passwords default to PLATFORM_SEED_PASSWORD (or 'changeme!').
const SEED_ACCOUNTS = [
  ['admin@platform.local', 'Platform Admin'],
  ['creator@platform.local', 'Agent Creator'],
  ['owner@platform.local', 'Agent Owner'],
  ['engineer@platform.local', 'AI Engineer'],
  ['governance@platform.local', 'Governance Reviewer'],
  ['security@platform.local', 'Security / Data Owner'],
] as const;

const INPUT_CLS =
  'h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(apiErrorMessage(err)); // uniform "invalid credentials" from the server
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-canvas">
      <div className="w-full max-w-sm">
        <div className="mb-5 flex items-center justify-center gap-2">
          <span className="text-accent-new">◆</span>
          <span className="text-[15px] text-text-mid">
            Brightspeed <span className="font-semibold text-text-hi">Agent Ops</span>
          </span>
        </div>

        <form onSubmit={submit} className="rounded-card border border-border bg-surface p-5">
          <h1 className="mb-4 text-[14px] font-semibold text-text-hi">Sign in</h1>
          <label className="mb-3 block">
            <span className="mb-1 block text-[12px] text-text-mid">Email</span>
            <input
              className={INPUT_CLS}
              type="text"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoFocus
            />
          </label>
          <label className="mb-4 block">
            <span className="mb-1 block text-[12px] text-text-mid">Password</span>
            <input
              className={INPUT_CLS}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <div className="mb-3 text-[12px] text-red-400">{error}</div>}
          <Button variant="primary" disabled={busy || !email || !password}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        {import.meta.env.DEV && (
          <div className="mt-4 rounded-card border border-border bg-surface p-4">
            <div className="mb-2 text-[11px] uppercase tracking-wide text-text-low">
              Seeded dev accounts (password: PLATFORM_SEED_PASSWORD, default "changeme!")
            </div>
            <div className="flex flex-col gap-1">
              {SEED_ACCOUNTS.map(([mail, label]) => (
                <button
                  key={mail}
                  type="button"
                  onClick={() => setEmail(mail)}
                  className="flex items-center justify-between rounded-control px-2 py-1 text-left text-[12px] text-text-mid hover:bg-canvas"
                >
                  <span className="mono">{mail}</span>
                  <span className="text-text-low">{label}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
