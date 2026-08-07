import React, { useCallback, useRef, useState } from 'react';
import {
  Upload, Link2, FileText, Database, AlertCircle, ChevronDown, ChevronUp,
  Puzzle, Ticket, Github, Wrench, BarChart3, PlugZap, CheckCircle2, XCircle,
} from 'lucide-react';
import { Modal, Button } from '@/components/primitives';
import { cn } from '@/utils/cn';

type Tab = 'file' | 'url' | 'text' | 'database' | 'confluence' | 'jira' | 'github' | 'servicenow' | 'bigquery';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (sourceId: string, runId: string) => void;
}

const SENSITIVITY_OPTIONS = ['public', 'internal', 'confidential', 'restricted'] as const;
const ACCEPT = '.pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls';

type TestState = { status: 'idle' | 'testing' | 'ok' | 'fail'; detail?: string };

function TestConnectionButton({ getConfig, sourceType }: { getConfig: () => unknown; sourceType: string }) {
  const [state, setState] = useState<TestState>({ status: 'idle' });

  async function run() {
    setState({ status: 'testing' });
    try {
      const res = await fetch('/v1/knowledge/sources/test-connection', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: sourceType, config: getConfig() }),
      });
      const data = await res.json().catch(() => ({ ok: false, detail: `HTTP ${res.status}` }));
      setState({ status: data.ok ? 'ok' : 'fail', detail: data.detail });
    } catch (e: unknown) {
      setState({ status: 'fail', detail: e instanceof Error ? e.message : 'Network error' });
    }
  }

  return (
    <div className="space-y-1.5">
      <Button variant="subtle" size="sm" icon={<PlugZap size={12} />} onClick={run} disabled={state.status === 'testing'}>
        {state.status === 'testing' ? 'Testing…' : 'Test Connection'}
      </Button>
      {state.status !== 'idle' && state.status !== 'testing' && (
        <div className={cn(
          'flex items-start gap-1.5 rounded-md px-2.5 py-1.5 text-[11px]',
          state.status === 'ok' ? 'bg-ok/10 text-ok' : 'bg-err/10 text-err',
        )}>
          {state.status === 'ok' ? <CheckCircle2 size={12} className="mt-0.5 shrink-0" /> : <XCircle size={12} className="mt-0.5 shrink-0" />}
          <span className="break-all">{state.detail}</span>
        </div>
      )}
    </div>
  );
}

export function AddSourceModal({ open, onClose, onCreated }: Props) {
  const [tab, setTab] = useState<Tab>('file');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // File tab state
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  // URL tab state
  const [url, setUrl] = useState('');
  const [urlName, setUrlName] = useState('');

  // Text tab state
  const [textBody, setTextBody] = useState('');
  const [textName, setTextName] = useState('');

  // Database tab state
  const [dbConnUrl, setDbConnUrl] = useState('');
  const [dbQuery, setDbQuery] = useState('');
  const [dbName, setDbName] = useState('');

  // Confluence tab state
  const [confBaseUrl, setConfBaseUrl] = useState('');
  const [confEmail, setConfEmail] = useState('');
  const [confToken, setConfToken] = useState('');
  const [confPageId, setConfPageId] = useState('');
  const [confSpaceKey, setConfSpaceKey] = useState('');
  const [confName, setConfName] = useState('');

  // Jira tab state
  const [jiraBaseUrl, setJiraBaseUrl] = useState('');
  const [jiraEmail, setJiraEmail] = useState('');
  const [jiraToken, setJiraToken] = useState('');
  const [jiraJql, setJiraJql] = useState('');
  const [jiraName, setJiraName] = useState('');

  // GitHub tab state
  const [ghRepoOwner, setGhRepoOwner] = useState('');
  const [ghRepo, setGhRepo] = useState('');
  const [ghPath, setGhPath] = useState('');
  const [ghBranch, setGhBranch] = useState('');
  const [ghToken, setGhToken] = useState('');
  const [ghName, setGhName] = useState('');

  // ServiceNow tab state
  const [snInstanceUrl, setSnInstanceUrl] = useState('');
  const [snTable, setSnTable] = useState('');
  const [snUsername, setSnUsername] = useState('');
  const [snPassword, setSnPassword] = useState('');
  const [snQuery, setSnQuery] = useState('');
  const [snName, setSnName] = useState('');

  // BigQuery tab state
  const [bqServiceAccountJson, setBqServiceAccountJson] = useState('');
  const [bqQuery, setBqQuery] = useState('');
  const [bqName, setBqName] = useState('');

  // Shared
  const [sensitivity, setSensitivity] = useState<'public' | 'internal' | 'confidential' | 'restricted'>('internal');
  const [ingestionMode, setIngestionMode] = useState<'hybrid' | 'vector' | 'sql'>('hybrid');
  const [embeddingProvider, setEmbeddingProvider] = useState<'openai' | 'local_bge_small'>('openai');
  const [domain, setDomain] = useState('');
  const [owner, setOwner] = useState('');
  const [tags, setTags] = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [chunkSize, setChunkSize] = useState(800);
  const [chunkOverlap, setChunkOverlap] = useState(100);

  function reset() {
    setTab('file'); setLoading(false); setError(null);
    setDragOver(false); setFile(null); setFileName('');
    setUrl(''); setUrlName(''); setTextBody(''); setTextName('');
    setDbConnUrl(''); setDbQuery(''); setDbName('');
    setConfBaseUrl(''); setConfEmail(''); setConfToken(''); setConfPageId(''); setConfSpaceKey(''); setConfName('');
    setJiraBaseUrl(''); setJiraEmail(''); setJiraToken(''); setJiraJql(''); setJiraName('');
    setGhRepoOwner(''); setGhRepo(''); setGhPath(''); setGhBranch(''); setGhToken(''); setGhName('');
    setSnInstanceUrl(''); setSnTable(''); setSnUsername(''); setSnPassword(''); setSnQuery(''); setSnName('');
    setBqServiceAccountJson(''); setBqQuery(''); setBqName('');
    setSensitivity('internal');
    setIngestionMode('hybrid');
    setEmbeddingProvider('openai');
    setDomain(''); setOwner(''); setTags(''); setValidUntil('');
    setShowAdvanced(false); setChunkSize(800); setChunkOverlap(100);
  }

  function sharedMeta() {
    return {
      domain: domain.trim(), owner: owner.trim(), tags, valid_until: validUntil,
      chunk_size: chunkSize, chunk_overlap: chunkOverlap, embedding_provider: embeddingProvider,
      ingestion_mode: ingestionMode,
    };
  }

  function handleClose() { reset(); onClose(); }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) { setFile(dropped); setFileName(dropped.name); }
  }, []);

  async function postJson(path: string, body: Record<string, unknown>) {
    const res = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Failed'); }
    return res.json();
  }

  async function handleSubmit() {
    setError(null);
    setLoading(true);
    try {
      if (tab === 'file') {
        if (!file) { setError('Please select a file.'); setLoading(false); return; }
        const form = new FormData();
        form.append('file', file);
        form.append('name', fileName || file.name);
        form.append('sensitivity', sensitivity);
        form.append('ingestion_mode', ingestionMode);
        form.append('domain', domain.trim());
        form.append('owner', owner.trim());
        form.append('tags', tags);
        form.append('valid_until', validUntil);
        form.append('chunk_size', String(chunkSize));
        form.append('chunk_overlap', String(chunkOverlap));
        form.append('embedding_provider', embeddingProvider);
        const res = await fetch('/v1/knowledge/sources/upload', { method: 'POST', body: form });
        if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Upload failed'); }
        const data = await res.json();
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'url') {
        if (!url.trim()) { setError('Please enter a URL.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/url', { url: url.trim(), name: urlName || url.trim(), sensitivity, ...sharedMeta() });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'database') {
        if (!dbConnUrl.trim()) { setError('Please enter a database connection URL.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/database', { connection_url: dbConnUrl.trim(), query: dbQuery.trim(), name: dbName.trim(), sensitivity, ...sharedMeta() });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'text') {
        if (!textBody.trim()) { setError('Please enter some text.'); setLoading(false); return; }
        if (!textName.trim()) { setError('Please provide a name.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/text', { text: textBody.trim(), name: textName.trim(), sensitivity, ...sharedMeta() });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'confluence') {
        if (!confBaseUrl.trim() || !confEmail.trim() || !confToken.trim()) { setError('Base URL, email, and API token are required.'); setLoading(false); return; }
        if (!confPageId.trim() && !confSpaceKey.trim()) { setError('Provide a page ID or a space key.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/confluence', {
          base_url: confBaseUrl.trim(), email: confEmail.trim(), api_token: confToken.trim(),
          page_id: confPageId.trim(), space_key: confSpaceKey.trim(), name: confName.trim(), sensitivity, ...sharedMeta(),
        });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'jira') {
        if (!jiraBaseUrl.trim() || !jiraEmail.trim() || !jiraToken.trim() || !jiraJql.trim()) { setError('Base URL, email, API token, and JQL are required.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/jira', {
          base_url: jiraBaseUrl.trim(), email: jiraEmail.trim(), api_token: jiraToken.trim(),
          jql: jiraJql.trim(), name: jiraName.trim(), sensitivity, ...sharedMeta(),
        });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'github') {
        if (!ghRepoOwner.trim() || !ghRepo.trim()) { setError('Repo owner and repo name are required.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/github', {
          repo_owner: ghRepoOwner.trim(), repo: ghRepo.trim(), path: ghPath.trim(), branch: ghBranch.trim(),
          token: ghToken.trim(), name: ghName.trim(), sensitivity, ...sharedMeta(),
        });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'servicenow') {
        if (!snInstanceUrl.trim() || !snTable.trim() || !snUsername.trim() || !snPassword.trim()) { setError('Instance URL, table, username, and password are required.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/servicenow', {
          instance_url: snInstanceUrl.trim(), table: snTable.trim(), username: snUsername.trim(),
          password: snPassword, query: snQuery.trim(), name: snName.trim(), sensitivity, ...sharedMeta(),
        });
        onCreated(data.source.id, data.run_id);
      } else if (tab === 'bigquery') {
        if (!bqServiceAccountJson.trim() || !bqQuery.trim()) { setError('Service account JSON and query are required.'); setLoading(false); return; }
        const data = await postJson('/v1/knowledge/sources/bigquery', {
          service_account_json: bqServiceAccountJson.trim(), query: bqQuery.trim(), name: bqName.trim(), sensitivity, ...sharedMeta(),
        });
        onCreated(data.source.id, data.run_id);
      }
      handleClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
      setLoading(false);
    }
  }

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'file', label: 'File', icon: <Upload size={13} /> },
    { key: 'url', label: 'URL', icon: <Link2 size={13} /> },
    { key: 'database', label: 'Database', icon: <Database size={13} /> },
    { key: 'text', label: 'Text', icon: <FileText size={13} /> },
    { key: 'confluence', label: 'Confluence', icon: <Puzzle size={13} /> },
    { key: 'jira', label: 'Jira', icon: <Ticket size={13} /> },
    { key: 'github', label: 'GitHub', icon: <Github size={13} /> },
    { key: 'servicenow', label: 'ServiceNow', icon: <Wrench size={13} /> },
    { key: 'bigquery', label: 'BigQuery', icon: <BarChart3 size={13} /> },
  ];

  const inputCls = "mt-1 w-full rounded-md border border-border bg-raised px-2.5 py-1.5 text-[13px] text-text-hi placeholder:text-text-low focus:border-accent focus:outline-none";
  const labelCls = "block text-[11px] font-medium text-text-low";

  return (
    <Modal open={open} onClose={handleClose} title="Add Knowledge Source" width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={loading}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={loading}>
            {loading ? 'Ingesting…' : 'Add Source'}
          </Button>
        </>
      }
    >
      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg border border-border bg-raised p-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'flex items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-all',
              tab === t.key
                ? 'bg-surface text-text-hi shadow-sm'
                : 'text-text-low hover:text-text-mid',
            )}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
        {/* File tab */}
        {tab === 'file' && (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
              className={cn(
                'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-all',
                dragOver ? 'border-accent bg-accent/5' : 'border-border hover:border-border-strong',
              )}
            >
              <Upload size={22} className={dragOver ? 'text-accent' : 'text-text-low'} />
              {file ? (
                <span className="text-[13px] font-medium text-text-hi">{file.name}</span>
              ) : (
                <>
                  <span className="text-[13px] font-medium text-text-hi">Drop a file or click to browse</span>
                  <span className="text-[11px] text-text-low">PDF, DOCX, TXT, MD — up to 50 MB</span>
                </>
              )}
              <input ref={fileRef} type="file" accept={ACCEPT} className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setFileName(f.name); } }}
              />
            </div>
            <label className={labelCls}>
              Display name
              <input value={fileName} onChange={(e) => setFileName(e.target.value)} placeholder="My Policy Document" className={inputCls} />
            </label>
          </>
        )}

        {/* URL tab */}
        {tab === 'url' && (
          <>
            <label className={labelCls}>
              URL
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/docs/policy" className={inputCls} />
            </label>
            <label className={labelCls}>
              Display name
              <input value={urlName} onChange={(e) => setUrlName(e.target.value)} placeholder="Product Docs Homepage" className={inputCls} />
            </label>
          </>
        )}

        {/* Database tab */}
        {tab === 'database' && (
          <>
            <label className={labelCls}>
              Connection URL
              <input value={dbConnUrl} onChange={(e) => setDbConnUrl(e.target.value)} placeholder="postgresql://user:password@localhost:5432/dbname" className={inputCls} />
              <span className="mt-1 block text-[10px] text-text-low">
                Automatically ingests all user tables & records in the database. Supports postgresql://, postgres://, mysql://, or sqlite://
              </span>
            </label>
            <label className={labelCls}>
              Display Name (Optional)
              <input value={dbName} onChange={(e) => setDbName(e.target.value)} placeholder="E.g. Incident Logs DB" className={inputCls} />
            </label>
          </>
        )}

        {/* Text tab */}
        {tab === 'text' && (
          <>
            <label className={labelCls}>
              Name
              <input value={textName} onChange={(e) => setTextName(e.target.value)} placeholder="E.g. Onboarding FAQ" className={inputCls} />
            </label>
            <label className={labelCls}>
              Content
              <textarea value={textBody} onChange={(e) => setTextBody(e.target.value)}
                placeholder="Paste or type your knowledge content here…" rows={8}
                className={cn(inputCls, 'resize-y')}
              />
            </label>
          </>
        )}

        {/* Confluence tab — real Confluence Cloud REST API v2, Basic auth (email + API token) */}
        {tab === 'confluence' && (
          <>
            <div className="rounded-md border border-info/30 bg-info/5 px-2.5 py-2 text-[10px] text-text-mid">
              Real API integration — requires a live Confluence Cloud instance and an
              <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noreferrer" className="text-accent hover:underline"> API token</a>.
              Test the connection before ingesting.
            </div>
            <label className={labelCls}>
              Base URL
              <input value={confBaseUrl} onChange={(e) => setConfBaseUrl(e.target.value)} placeholder="https://yourcompany.atlassian.net" className={inputCls} />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Account email
                <input value={confEmail} onChange={(e) => setConfEmail(e.target.value)} placeholder="you@company.com" className={inputCls} />
              </label>
              <label className={labelCls}>
                API token
                <input type="password" value={confToken} onChange={(e) => setConfToken(e.target.value)} placeholder="••••••••" className={inputCls} />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Page ID (single page)
                <input value={confPageId} onChange={(e) => setConfPageId(e.target.value)} placeholder="123456" className={inputCls} />
              </label>
              <label className={labelCls}>
                Space key (whole space)
                <input value={confSpaceKey} onChange={(e) => setConfSpaceKey(e.target.value)} placeholder="ENG" className={inputCls} />
              </label>
            </div>
            <label className={labelCls}>
              Display name (optional)
              <input value={confName} onChange={(e) => setConfName(e.target.value)} placeholder="Engineering Space" className={inputCls} />
            </label>
            <TestConnectionButton sourceType="confluence" getConfig={() => ({ base_url: confBaseUrl.trim(), email: confEmail.trim(), api_token: confToken.trim() })} />
          </>
        )}

        {/* Jira tab — real Jira Cloud REST API v3, Basic auth (email + API token) */}
        {tab === 'jira' && (
          <>
            <div className="rounded-md border border-info/30 bg-info/5 px-2.5 py-2 text-[10px] text-text-mid">
              Real API integration — requires a live Jira Cloud instance and an API token. Test the connection before ingesting.
            </div>
            <label className={labelCls}>
              Base URL
              <input value={jiraBaseUrl} onChange={(e) => setJiraBaseUrl(e.target.value)} placeholder="https://yourcompany.atlassian.net" className={inputCls} />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Account email
                <input value={jiraEmail} onChange={(e) => setJiraEmail(e.target.value)} placeholder="you@company.com" className={inputCls} />
              </label>
              <label className={labelCls}>
                API token
                <input type="password" value={jiraToken} onChange={(e) => setJiraToken(e.target.value)} placeholder="••••••••" className={inputCls} />
              </label>
            </div>
            <label className={labelCls}>
              JQL query
              <input value={jiraJql} onChange={(e) => setJiraJql(e.target.value)} placeholder="project = OPS ORDER BY created DESC" className={inputCls} />
            </label>
            <label className={labelCls}>
              Display name (optional)
              <input value={jiraName} onChange={(e) => setJiraName(e.target.value)} placeholder="OPS project tickets" className={inputCls} />
            </label>
            <TestConnectionButton sourceType="jira" getConfig={() => ({ base_url: jiraBaseUrl.trim(), email: jiraEmail.trim(), api_token: jiraToken.trim() })} />
          </>
        )}

        {/* GitHub tab — real GitHub REST API v3; public repos work with no token */}
        {tab === 'github' && (
          <>
            <div className="rounded-md border border-info/30 bg-info/5 px-2.5 py-2 text-[10px] text-text-mid">
              Real API integration. Public repos work with no token at GitHub's standard unauthenticated rate limit — add a personal access token for private repos or a higher limit.
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Repo owner / org
                <input value={ghRepoOwner} onChange={(e) => setGhRepoOwner(e.target.value)} placeholder="anthropics" className={inputCls} />
              </label>
              <label className={labelCls}>
                Repo name
                <input value={ghRepo} onChange={(e) => setGhRepo(e.target.value)} placeholder="claude-code" className={inputCls} />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Path (file or directory)
                <input value={ghPath} onChange={(e) => setGhPath(e.target.value)} placeholder="README.md or docs/" className={inputCls} />
              </label>
              <label className={labelCls}>
                Branch (optional)
                <input value={ghBranch} onChange={(e) => setGhBranch(e.target.value)} placeholder="main" className={inputCls} />
              </label>
            </div>
            <label className={labelCls}>
              Personal access token (optional — required for private repos)
              <input type="password" value={ghToken} onChange={(e) => setGhToken(e.target.value)} placeholder="••••••••" className={inputCls} />
            </label>
            <label className={labelCls}>
              Display name (optional)
              <input value={ghName} onChange={(e) => setGhName(e.target.value)} placeholder="Claude Code README" className={inputCls} />
            </label>
            <TestConnectionButton sourceType="github" getConfig={() => ({ repo_owner: ghRepoOwner.trim(), repo: ghRepo.trim(), token: ghToken.trim() })} />
          </>
        )}

        {/* ServiceNow tab — real Table API, Basic auth */}
        {tab === 'servicenow' && (
          <>
            <div className="rounded-md border border-info/30 bg-info/5 px-2.5 py-2 text-[10px] text-text-mid">
              Real API integration — requires a live ServiceNow instance and a service-account username/password. Test the connection before ingesting.
            </div>
            <label className={labelCls}>
              Instance URL
              <input value={snInstanceUrl} onChange={(e) => setSnInstanceUrl(e.target.value)} placeholder="https://yourinstance.service-now.com" className={inputCls} />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Table
                <input value={snTable} onChange={(e) => setSnTable(e.target.value)} placeholder="incident" className={inputCls} />
              </label>
              <label className={labelCls}>
                Query filter (sysparm_query, optional)
                <input value={snQuery} onChange={(e) => setSnQuery(e.target.value)} placeholder="active=true" className={inputCls} />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className={labelCls}>
                Username
                <input value={snUsername} onChange={(e) => setSnUsername(e.target.value)} className={inputCls} />
              </label>
              <label className={labelCls}>
                Password
                <input type="password" value={snPassword} onChange={(e) => setSnPassword(e.target.value)} className={inputCls} />
              </label>
            </div>
            <label className={labelCls}>
              Display name (optional)
              <input value={snName} onChange={(e) => setSnName(e.target.value)} placeholder="ServiceNow Incidents" className={inputCls} />
            </label>
            <TestConnectionButton sourceType="servicenow" getConfig={() => ({ instance_url: snInstanceUrl.trim(), username: snUsername.trim(), password: snPassword })} />
          </>
        )}

        {/* BigQuery tab — real google-cloud-bigquery client, service-account auth */}
        {tab === 'bigquery' && (
          <>
            <div className="rounded-md border border-info/30 bg-info/5 px-2.5 py-2 text-[10px] text-text-mid">
              Real API integration — requires a real GCP service-account key with BigQuery read access. Test the connection before ingesting.
            </div>
            <label className={labelCls}>
              Service account JSON key
              <textarea value={bqServiceAccountJson} onChange={(e) => setBqServiceAccountJson(e.target.value)}
                placeholder='{"type": "service_account", "project_id": "...", ...}' rows={4}
                className={cn(inputCls, 'resize-y mono')}
              />
            </label>
            <label className={labelCls}>
              SQL query (read-only SELECT / WITH)
              <textarea value={bqQuery} onChange={(e) => setBqQuery(e.target.value)}
                placeholder="SELECT * FROM `project.dataset.table` LIMIT 1000" rows={3}
                className={cn(inputCls, 'resize-y mono')}
              />
            </label>
            <label className={labelCls}>
              Display name (optional)
              <input value={bqName} onChange={(e) => setBqName(e.target.value)} placeholder="Revenue Analytics Table" className={inputCls} />
            </label>
            <TestConnectionButton sourceType="bigquery" getConfig={() => ({ service_account_json: bqServiceAccountJson.trim() })} />
          </>
        )}

        {/* Sensitivity */}
        <label className={labelCls}>
          Sensitivity
          <select value={sensitivity} onChange={(e) => setSensitivity(e.target.value as typeof sensitivity)} className={inputCls}>
            {SENSITIVITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>

        {/* Processing mode — controls whether this source gets chunked/embedded, kept
            queryable via SQL, or both. Applies to every source type, not just files. */}
        <label className={labelCls}>
          Processing Mode
          <select value={ingestionMode} onChange={(e) => setIngestionMode(e.target.value as typeof ingestionMode)} className={inputCls}>
            <option value="hybrid">⚡ Hybrid Mode (Vector RAG + SQL Analytics)</option>
            <option value="vector">🔹 Vector RAG Only (Embeddings & Semantic Search)</option>
            <option value="sql">📊 Pure SQL Mode (Skip Embeddings, Direct Text-to-SQL)</option>
          </select>
          <span className="mt-1 block text-[10px] text-text-low">
            Pure SQL Mode skips chunking/embedding entirely — use it for structured sources (Database, BigQuery, CSV/Excel) you only want to query, not semantically search.
          </span>
        </label>

        {/* Embedding provider — which model chunks get embedded with (RAG Pipeline Studio) */}
        <label className={labelCls}>
          Embedding Provider
          <select value={embeddingProvider} onChange={(e) => setEmbeddingProvider(e.target.value as typeof embeddingProvider)} className={inputCls}>
            <option value="openai">OpenAI — text-embedding-3-small (1536-dim, needs API credits)</option>
            <option value="local_bge_small">Local — BAAI/bge-small-en-v1.5 (384-dim, runs on-CPU, free)</option>
          </select>
          <span className="mt-1 block text-[10px] text-text-low">
            Sources can only be searched together in Retrieval Test if they share the same provider — the two vector spaces aren't comparable.
          </span>
        </label>

        {/* Tagging — domain / owner / tags / freshness (blueprint 3.2 Knowledge Base Layer) */}
        <div className="grid grid-cols-2 gap-2">
          <label className={labelCls}>
            Domain
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="e.g. engineering" className={inputCls} />
          </label>
          <label className={labelCls}>
            Owner
            <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="e.g. jane.doe" className={inputCls} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className={labelCls}>
            Tags (comma-separated)
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="ops, incidents" className={inputCls} />
          </label>
          <label className={labelCls}>
            Valid until (freshness)
            <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} className={inputCls} />
          </label>
        </div>

        {/* Advanced — configurable chunking (blueprint 3.3 RAG Pipeline Studio) */}
        <div className="rounded-lg border border-border">
          <button type="button" onClick={() => setShowAdvanced((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-[11px] font-medium text-text-low hover:text-text-mid"
          >
            <span>Advanced: chunking settings</span>
            {showAdvanced ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
          {showAdvanced && (
            <div className="grid grid-cols-2 gap-2 border-t border-border px-3 py-2.5">
              <label className={labelCls}>
                Chunk size (chars): <span className="text-text-hi font-semibold">{chunkSize}</span>
                <input type="range" min={200} max={2000} step={50} value={chunkSize}
                  onChange={(e) => setChunkSize(Number(e.target.value))} className="mt-1 w-full accent-accent" />
              </label>
              <label className={labelCls}>
                Chunk overlap (chars): <span className="text-text-hi font-semibold">{chunkOverlap}</span>
                <input type="range" min={0} max={400} step={10} value={chunkOverlap}
                  onChange={(e) => setChunkOverlap(Number(e.target.value))} className="mt-1 w-full accent-accent" />
              </label>
            </div>
          )}
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-err/30 bg-err/10 px-3 py-2 text-[12px] text-err">
            <AlertCircle size={13} /> {error}
          </div>
        )}
      </div>
    </Modal>
  );
}
