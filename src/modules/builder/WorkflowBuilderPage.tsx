// Workflow Builder (Increment D): React Flow canvas over server workflow
// versions. The canvas holds ZERO execution logic — validation verdicts,
// status transitions, and guardrail auto-inserts are all the server's and are
// rendered verbatim after each action.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ReactFlow, Background, Controls, addEdge, applyEdgeChanges, applyNodeChanges,
  type Connection, type Edge, type EdgeChange, type Node, type NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ArrowLeft, GitBranch, Play, Plus } from 'lucide-react';
import { PageHeader } from '@/components/shell/PageHeader';
import { Badge, Button, Card, CardHeader, ComboBox, Modal, type ComboOption } from '@/components/primitives';
import {
  apiErrorMessage, promptsApi, ragApi, toolsApi, workflowsApi,
  type EdgeCondition, type FlowNode, type ServerWorkflow, type ServerWorkflowVersion,
  type WorkflowGraph,
} from '@/api/client';
import { titleCase } from '@/utils/format';

const NODE_TYPES = ['rag', 'prompt', 'llm', 'tool_call', 'mcp_call', 'human_approval', 'guardrail', 'output_format'] as const;

const TYPE_COLOR: Record<string, string> = {
  rag: '#2563eb', prompt: '#7c3aed', llm: '#0891b2', tool_call: '#d97706',
  mcp_call: '#d97706', human_approval: '#dc2626', guardrail: '#dc2626',
  output_format: '#16a34a', structured_query: '#6b7280', evaluation: '#6b7280',
};

const STATUS_TONE: Record<string, 'ok' | 'accent' | 'warn' | 'neutral' | 'muted' | 'err'> = {
  draft: 'muted', validated: 'neutral', pending_approval: 'warn',
  approved: 'accent', active: 'ok', rejected: 'err', superseded: 'muted',
};

const INPUT = 'h-8 w-full rounded-control border border-border bg-canvas px-2 text-[12px] text-text-hi outline-none focus:border-border-strong';

/** React Flow ships light-theme node defaults; without this the boxes render
 *  near-white with pale text on the dark canvas and are unreadable. */
function nodeStyle(type: string, state: { selected?: boolean; invalid?: boolean } = {}) {
  return {
    background: 'var(--bg-raised)',
    color: 'var(--text-hi)',
    border: state.invalid
      ? '1px solid var(--err)'
      : state.selected
        ? '1px solid var(--accent)'
        : '1px solid var(--border)',
    borderLeft: `4px solid ${TYPE_COLOR[type] ?? '#6b7280'}`,
    boxShadow: state.selected ? '0 0 0 2px var(--accent)' : undefined,
    borderRadius: 6,
    padding: '8px 10px',
    fontSize: 11,
    lineHeight: 1.35,
    textAlign: 'left' as const,
    width: 190,
    whiteSpace: 'pre-wrap' as const,
  };
}

// Edge conditions — the vocabulary mirrors backend/app/engine/conditions.py.
// Anything not in these lists is refused server-side, so the palette stays
// closed here too rather than letting people author edges that cannot validate.
const CONDITION_FIELDS = [
  'user_input', 'prompt_parts', 'retrieved', 'context_block',
  'tool_results', 'llm_output', 'final_output',
  'citation_check', 'citation_check.passed',
  'hitl_decision', 'hitl_decision.approved',
];
const VALUE_OPS = ['eq', 'ne', 'contains', 'not_contains', 'gt', 'gte', 'lt', 'lte'];
const UNARY_OPS = ['is_empty', 'is_not_empty'];

function conditionLabel(when?: EdgeCondition): string {
  if (!when) return '';
  return UNARY_OPS.includes(when.op)
    ? `${when.field} ${when.op}`
    : `${when.field} ${when.op} ${JSON.stringify(when.value)}`;
}

/** Style + label an edge from its condition, so branches are readable on the canvas. */
function edgeView(edge: Edge): Edge {
  const when = (edge.data as { condition?: EdgeCondition } | undefined)?.condition;
  return {
    ...edge,
    label: when ? conditionLabel(when) : undefined,
    labelStyle: { fill: 'var(--text-mid)', fontSize: 10 },
    labelBgStyle: { fill: 'var(--surface)' },
    labelBgPadding: [4, 2] as [number, number],
    style: when
      ? { stroke: 'var(--accent)', strokeWidth: 1.5 }
      : { stroke: 'var(--border-strong)', strokeDasharray: '4 3' },
  };
}

function layout(graph: WorkflowGraph): Node[] {
  // simple layered layout: BFS depth → column, index in layer → row
  const ids = graph.nodes.map((n) => n.id);
  const indeg: Record<string, number> = Object.fromEntries(ids.map((i) => [i, 0]));
  const out: Record<string, string[]> = Object.fromEntries(ids.map((i) => [i, []]));
  for (const e of graph.edges) {
    if (out[e.from] && indeg[e.to] !== undefined) { out[e.from].push(e.to); indeg[e.to] += 1; }
  }
  const depth: Record<string, number> = {};
  const queue = ids.filter((i) => indeg[i] === 0).map((i) => [i, 0] as [string, number]);
  const seen = new Set<string>();
  while (queue.length) {
    const [id, d] = queue.shift()!;
    if (seen.has(id)) continue;
    seen.add(id);
    depth[id] = Math.max(depth[id] ?? 0, d);
    for (const nb of out[id]) queue.push([nb, d + 1]);
  }
  const perCol: Record<number, number> = {};
  return graph.nodes.map((n) => {
    const d = depth[n.id] ?? 0;
    const row = (perCol[d] = (perCol[d] ?? 0) + 1) - 1;
    return {
      id: n.id,
      position: { x: d * 230 + 20, y: row * 110 + 20 },
      data: { label: `${n.type}\n${n.label || n.id}`, ntype: n.type, nlabel: n.label, config: n.config ?? {} },
      style: nodeStyle(n.type),
    };
  });
}

function toGraph(nodes: Node[], edges: Edge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: (n.data as { ntype: string }).ntype,
      label: (n.data as { nlabel?: string }).nlabel ?? '',
      config: (n.data as { config?: Record<string, unknown> }).config ?? {},
    })) as FlowNode[],
    // `condition` must survive the round trip, or saving a branching workflow
    // silently flattens it back into an ambiguous multi-edge graph.
    edges: edges.map((e) => {
      const condition = (e.data as { condition?: EdgeCondition } | undefined)?.condition;
      return condition
        ? { from: e.source, to: e.target, condition }
        : { from: e.source, to: e.target };
    }),
  };
}

export default function WorkflowBuilderPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<ServerWorkflow[]>([]);
  const [selected, setSelected] = useState<ServerWorkflowVersion | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  // registry options — you pick approved assets, never retype their slugs
  const [promptOptions, setPromptOptions] = useState<ComboOption[]>([]);
  const [ragOptions, setRagOptions] = useState<ComboOption[]>([]);
  const [toolOptions, setToolOptions] = useState<ComboOption[]>([]);

  useEffect(() => {
    promptsApi.list().then((packs) => setPromptOptions(
      packs.filter((p) => p.approved_version)   // only approved packs will validate
        .map((p) => ({ value: p.slug, hint: `v${p.approved_version} approved` })),
    )).catch(() => setPromptOptions([]));
    ragApi.list().then((pipes) => setRagOptions(
      pipes.map((p) => ({ value: p.name, hint: `${p.source_ids.length} sources` })),
    )).catch(() => setRagOptions([]));
    toolsApi.list().then((tools) => setToolOptions(
      tools.filter((t) => t.status === 'approved' && !t.is_write_class)
        .map((t) => ({ value: t.slug, hint: `${t.permission_type} · ${t.implementation.kind}` })),
    )).catch(() => setToolOptions([]));
  }, []);

  const editable = selected != null && (selected.status === 'draft' || selected.status === 'validated');

  const load = useCallback((keepVersionId?: string) => {
    workflowsApi.listForAgent(id).then((ws) => {
      setWorkflows(ws);
      const all = ws.flatMap((w) => w.versions);
      const keep = keepVersionId ? all.find((v) => v.id === keepVersionId) : null;
      const pick = keep ?? all[0] ?? null;
      if (pick) selectVersion(pick);
    }).catch((e) => setError(apiErrorMessage(e)));
  }, [id]);
  useEffect(() => load(), [load]);

  const selectVersion = (v: ServerWorkflowVersion) => {
    setSelected(v);
    setNodes(layout(v.graph ?? { nodes: [], edges: [] }));
    setEdges((v.graph?.edges ?? []).map((e, i) => edgeView({
      id: `e${i}`, source: e.from, target: e.to, data: { condition: e.condition },
    })));
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setInfo(null);
    setError(null);
  };

  const onNodesChange = useCallback((changes: NodeChange[]) => setNodes((ns) => applyNodeChanges(changes, ns)), []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => setEdges((es) => applyEdgeChanges(changes, es)), []);
  const onConnect = useCallback(
    (c: Connection) => setEdges((es) => addEdge(c, es).map((e) => edgeView(e))), []);

  const setEdgeCondition = (edgeId: string, when: EdgeCondition | undefined) =>
    setEdges((es) => es.map((e) =>
      e.id === edgeId ? edgeView({ ...e, data: { ...(e.data ?? {}), condition: when } }) : e));

  const act = async (fn: () => Promise<ServerWorkflowVersion>, label: string) => {
    setError(null); setInfo(null);
    try {
      const v = await fn();
      setInfo(`${label}: ${v.status}`);
      load(v.id);
    } catch (e) { setError(apiErrorMessage(e)); }
  };

  const save = () => selected && act(
    () => workflowsApi.updateDraft(selected.workflow_id, selected.version, toGraph(nodes, edges)), 'saved');
  const validate = () => selected && act(
    async () => {
      if (editable) await workflowsApi.updateDraft(selected.workflow_id, selected.version, toGraph(nodes, edges));
      return workflowsApi.validate(selected.workflow_id, selected.version);
    }, 'validated');

  const addNode = (type: string) => {
    const nid = `${type}_${Math.random().toString(36).slice(2, 6)}`;
    setNodes((ns) => [...ns, {
      id: nid, position: { x: 60 + ns.length * 30, y: 60 + ns.length * 20 },
      data: { label: `${type}\n${nid}`, ntype: type, nlabel: '', config: {} },
      style: nodeStyle(type),
    }]);
    setSelectedNodeId(nid);   // land straight in the config panel for the new node
  };

  const removeSelected = () => {
    if (!selectedNodeId) return;
    setNodes((ns) => ns.filter((n) => n.id !== selectedNodeId));
    setEdges((es) => es.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
    setSelectedNodeId(null);
  };

  const updateConfig = (patch: Record<string, unknown>) => {
    setNodes((ns) => ns.map((n) => n.id === selectedNodeId
      ? { ...n, data: { ...n.data, config: { ...(n.data as { config?: object }).config, ...patch } } }
      : n));
  };

  const selectedEdge = edges.find((e) => e.id === selectedEdgeId) ?? null;
  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const selectedType = selectedNode ? (selectedNode.data as { ntype: string }).ntype : null;
  const selectedConfig = (selectedNode?.data as { config?: Record<string, unknown> })?.config ?? {};

  const allVersions = useMemo(() => workflows.flatMap((w) =>
    w.versions.map((v) => ({ w, v }))), [workflows]);

  // node ids named in validation violations, e.g. ... node "prompt_1" has no ...
  const invalidNodeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const v of selected?.validation?.violations ?? []) {
      const match = /"([^"]+)"/.exec(v);
      if (match) ids.add(match[1]);
    }
    return ids;
  }, [selected]);

  // restyle for selection + validation without touching stored node data
  const styledNodes = useMemo(() => nodes.map((n) => ({
    ...n,
    style: nodeStyle((n.data as { ntype: string }).ntype, {
      selected: n.id === selectedNodeId,
      invalid: invalidNodeIds.has(n.id),
    }),
  })), [nodes, selectedNodeId, invalidNodeIds]);

  return (
    <div>
      <PageHeader
        title="Workflow Builder"
        description="Canvas edits a draft; validation, approval, and activation are server transitions."
        action={<div className="flex gap-2">
          <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={() => navigate(`/agents/${id}`)}>Agent</Button>
          <Button variant="ghost" icon={<Play size={14} />} onClick={() => navigate(`/agents/${id}/console`)}>Testing console</Button>
          <Button variant="new" icon={<Plus size={15} />} onClick={() => setCreateOpen(true)}>New workflow</Button>
        </div>}
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        {allVersions.map(({ w, v }) => (
          <button key={v.id} onClick={() => selectVersion(v)}
            className={`rounded-control border px-2.5 py-1 text-[12px] ${selected?.id === v.id ? 'border-border-strong bg-surface text-text-hi' : 'border-border bg-canvas text-text-mid'}`}>
            {w.name} v{v.version} <Badge tone={STATUS_TONE[v.status]}>{titleCase(v.status)}</Badge>
          </button>
        ))}
        {allVersions.length === 0 && <span className="text-[12px] text-text-low">No workflows yet — create one (optionally seeded from the recommendation).</span>}
      </div>

      {selected && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Button size="tiny" variant="subtle" disabled={!editable} onClick={save}>Save draft</Button>
            <Button size="tiny" variant="primary" disabled={!editable} onClick={validate}>Validate</Button>
            <Button size="tiny" variant="subtle" disabled={selected.status !== 'validated'}
              title={selected.status === 'validated' ? 'Send for governance approval'
                : `Validation must pass first — this version is "${selected.status}"`}
              onClick={() => act(() => workflowsApi.submit(selected.workflow_id, selected.version), 'submitted')}>Submit</Button>
            <Button size="tiny" variant="subtle" disabled={selected.status !== 'approved'}
              title={selected.status === 'approved' ? 'Make this the live version'
                : `Only approved versions activate — this one is "${selected.status}"`}
              onClick={() => act(() => workflowsApi.activate(selected.workflow_id, selected.version), 'activated')}>Activate</Button>
            <Button size="tiny" variant="ghost" icon={<GitBranch size={12} />}
              onClick={() => act(() => workflowsApi.fork(selected.workflow_id, selected.version), 'forked')}>Fork</Button>
            {editable && (
              <span className="ml-2 flex items-center gap-1">
                {NODE_TYPES.map((t) => (
                  <button key={t} onClick={() => addNode(t)}
                    className="rounded border border-border bg-canvas px-1.5 py-0.5 text-[10px] text-text-mid hover:text-text-hi"
                    style={{ borderLeftColor: TYPE_COLOR[t], borderLeftWidth: 3 }}>
                    + {t}
                  </button>
                ))}
                {selectedNodeId && <Button size="tiny" variant="danger" onClick={removeSelected}>Delete node</Button>}
              </span>
            )}
            {info && <span className="text-[12px] text-ok">{info}</span>}
            {error && <span className="text-[12px] text-red-400">{error}</span>}
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
            <div className="lg:col-span-3 h-[480px] rounded-card border border-border bg-canvas">
              <ReactFlow
                nodes={styledNodes} edges={edges}
                onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
                onNodeClick={(_, n) => { setSelectedNodeId(n.id); setSelectedEdgeId(null); }}
                onEdgeClick={(_, e) => { setSelectedEdgeId(e.id); setSelectedNodeId(null); }}
                onPaneClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
                nodesDraggable={editable} nodesConnectable={editable}
                fitView proOptions={{ hideAttribution: true }}
              >
                <Background gap={16} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>

            <div className="flex flex-col gap-3">
              {selectedEdge && (
                <EdgeInspector
                  edge={selectedEdge}
                  editable={editable}
                  siblingCount={edges.filter((e) => e.source === selectedEdge.source).length}
                  onChange={(when) => setEdgeCondition(selectedEdge.id, when)}
                />
              )}
              {selectedNode ? (
                <Card>
                  <CardHeader title={`Node: ${selectedNodeId}`} subtitle={selectedType ?? ''} />
                  <div className="flex flex-col gap-2">
                    {selectedType === 'prompt' && (
                      <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Prompt pack</span>
                        <ComboBox value={String(selectedConfig.pack_ref ?? '')} disabled={!editable}
                          options={promptOptions}
                          emptyHint="no approved prompt packs yet — create and approve one first"
                          onChange={(v) => updateConfig({ pack_ref: v })} /></label>
                    )}
                    {selectedType === 'rag' && (
                      <label className="block"><span className="mb-1 block text-[11px] text-text-mid">RAG pipeline</span>
                        <ComboBox value={String(selectedConfig.pipeline ?? '')} disabled={!editable}
                          options={ragOptions}
                          emptyHint="no pipelines yet — upload knowledge, then create a pipeline"
                          onChange={(v) => updateConfig({ pipeline: v })} /></label>
                    )}
                    {(selectedType === 'tool_call' || selectedType === 'mcp_call') && (
                      <>
                        <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Tool</span>
                          <ComboBox value={String(selectedConfig.tool_ref ?? '')} disabled={!editable}
                            options={toolOptions}
                            emptyHint="no approved read tools yet — register and approve one first"
                            onChange={(v) => updateConfig({ tool_ref: v })} /></label>
                        <JsonField
                          label="Request params"
                          hint="Use {{user_input}} to pass the live question."
                          disabled={!editable}
                          value={selectedConfig.params}
                          onChange={(v) => updateConfig({ params: v })}
                        />
                        <JsonField
                          label="Response extract (optional)"
                          hint='Shape the API JSON for the model, e.g. {"path":"items","fields":["title","description"]}'
                          disabled={!editable}
                          value={selectedConfig.response_extract}
                          onChange={(v) => updateConfig({ response_extract: v })}
                        />
                      </>
                    )}
                    {selectedType === 'llm' && (
                      <>
                        <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Temperature (clamped by risk policy)</span>
                          <input className={INPUT} disabled={!editable} type="number" step="0.1" min="0" max="1"
                            value={Number(selectedConfig.temperature ?? 0.2)}
                            onChange={(e) => updateConfig({ temperature: Number(e.target.value) })} /></label>
                        <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Instruction for this step (optional)</span>
                          <textarea className="min-h-[56px] w-full rounded-control border border-border bg-canvas px-2 py-1 text-[11px] text-text-hi outline-none focus:border-border-strong disabled:opacity-50"
                            disabled={!editable} value={String(selectedConfig.instruction ?? '')}
                            onChange={(e) => updateConfig({ instruction: e.target.value })}
                            placeholder="e.g. Reply with 2-4 search keywords only, no punctuation." />
                          <span className="mt-0.5 block text-[10px] text-text-low">
                            Added on top of the prompt pack, for this node only — lets one flow have several LLM steps.
                          </span></label>
                        <label className="flex items-center gap-2 text-[11px] text-text-mid">
                          <input type="checkbox" disabled={!editable}
                            checked={Boolean(selectedConfig.ignore_tool_results)}
                            onChange={(e) => updateConfig({ ignore_tool_results: e.target.checked })} />
                          Ignore earlier tool results
                        </label>
                      </>
                    )}
                    {selectedType === 'guardrail' && (
                      <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Blocked topics (comma-separated)</span>
                        <input className={INPUT} disabled={!editable}
                          value={((selectedConfig.blocked_topics as string[]) ?? []).join(', ')}
                          onChange={(e) => updateConfig({ blocked_topics: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} /></label>
                    )}
                    {selectedType === 'output_format' && (
                      <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Format</span>
                        <select className={INPUT} disabled={!editable} value={String(selectedConfig.format ?? 'text')}
                          onChange={(e) => updateConfig({ format: e.target.value })}>
                          {['text', 'structured_json', 'action_summary'].map((f) => <option key={f} value={f}>{f}</option>)}
                        </select></label>
                    )}
                    {selectedType === 'human_approval' && (
                      <div className="text-[11px] text-text-low">Pauses the run durably; owner/governance decide in the console.</div>
                    )}
                  </div>
                </Card>
              ) : (
                <Card>
                  <div className="text-[12px] text-text-low">
                    Click a node on the canvas to configure it. Drag between the small handles on
                    node edges to connect them.
                  </div>
                  {invalidNodeIds.size > 0 && (
                    <div className="mt-2 text-[12px] text-red-400">
                      Needs configuration: {[...invalidNodeIds].join(', ')} — outlined in red on the canvas.
                    </div>
                  )}
                </Card>
              )}

              {(selected.validation?.violations?.length || selected.validation?.warnings?.length || selected.validation?.adjustments?.length) ? (
                <Card>
                  <CardHeader title="Validation" subtitle={selected.validation.rules_version} />
                  {(selected.validation.violations ?? []).map((v, i) => <div key={`v${i}`} className="text-[12px] text-red-400">✕ {v}</div>)}
                  {(selected.validation.warnings ?? []).map((w, i) => <div key={`w${i}`} className="text-[12px] text-amber-400">⚠ {w}</div>)}
                  {(selected.validation.adjustments ?? []).map((a, i) => <div key={`a${i}`} className="text-[12px] text-text-mid">↺ {a}</div>)}
                </Card>
              ) : null}
            </div>
          </div>
        </>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New workflow" footer={null}>
        <CreateWorkflowForm agentId={id} onDone={(v) => { setCreateOpen(false); load(v); }} />
      </Modal>
    </div>
  );
}

/**
 * Edge condition editor.
 *
 * An edge with no condition is the DEFAULT branch — the `else`. The server
 * requires exactly one of those per branching node, so this says which one an
 * edge is rather than leaving people to infer it from a blank form.
 */
function EdgeInspector({
  edge, editable, siblingCount, onChange,
}: {
  edge: Edge;
  editable: boolean;
  siblingCount: number;
  onChange: (when: EdgeCondition | undefined) => void;
}) {
  const when = (edge.data as { condition?: EdgeCondition } | undefined)?.condition;
  const isUnary = when ? UNARY_OPS.includes(when.op) : false;
  const branching = siblingCount > 1;

  const update = (patch: Partial<EdgeCondition>) => {
    const next = { field: 'llm_output', op: 'contains', value: '', ...when, ...patch };
    if (UNARY_OPS.includes(next.op)) delete next.value;
    else if (next.value === undefined) next.value = '';
    onChange(next as EdgeCondition);
  };

  return (
    <Card>
      <CardHeader
        title={`Edge: ${edge.source} → ${edge.target}`}
        subtitle={when ? 'Conditional branch' : branching ? 'Default branch (else)' : 'Unconditional'}
      />
      <div className="flex flex-col gap-2">
        {!when && (
          <div className="text-[11px] text-text-low">
            {branching
              ? 'No condition: this is the default taken when no sibling condition matches. A branching node needs exactly one.'
              : 'No condition: execution always follows this edge.'}
          </div>
        )}
        {when && (
          <>
            <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Field</span>
              <select
                className="h-8 w-full rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
                disabled={!editable} value={when.field}
                onChange={(e) => update({ field: e.target.value })}>
                {CONDITION_FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>
            <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Operator</span>
              <select
                className="h-8 w-full rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
                disabled={!editable} value={when.op}
                onChange={(e) => update({ op: e.target.value })}>
                <optgroup label="compares a value">
                  {VALUE_OPS.map((o) => <option key={o} value={o}>{o}</option>)}
                </optgroup>
                <optgroup label="no value needed">
                  {UNARY_OPS.map((o) => <option key={o} value={o}>{o}</option>)}
                </optgroup>
              </select>
            </label>
            {!isUnary && (
              <label className="block"><span className="mb-1 block text-[11px] text-text-mid">Value</span>
                <input
                  className="h-8 w-full rounded-control border border-border bg-canvas px-1.5 text-[12px] text-text-hi outline-none"
                  disabled={!editable}
                  value={typeof when.value === 'string' ? when.value : JSON.stringify(when.value ?? '')}
                  onChange={(e) => update({ value: e.target.value })} />
                <span className="mt-1 block text-[10px] text-text-low">
                  Text comparisons ignore case. Use is_empty / is_not_empty for “nothing was retrieved”.
                </span>
              </label>
            )}
          </>
        )}
        {editable && (
          <button
            className="self-start text-[11px] text-accent hover:underline"
            onClick={() => (when ? onChange(undefined) : update({}))}>
            {when ? 'Make this the default branch' : 'Add a condition'}
          </button>
        )}
      </div>
    </Card>
  );
}

/** JSON sub-object editor that refuses to hand invalid JSON to the server. */
function JsonField({
  label, hint, value, onChange, disabled,
}: {
  label: string;
  hint: string;
  value: unknown;
  onChange: (parsed: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const serialized = value && Object.keys(value as object).length
    ? JSON.stringify(value, null, 1)
    : '';
  const [text, setText] = useState(serialized);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // reflect node switches until the user starts editing this instance
  useEffect(() => {
    if (!touched) setText(serialized);
  }, [serialized, touched]);

  const commit = (next: string) => {
    setText(next);
    setTouched(true);
    if (!next.trim()) {
      setError(null);
      onChange({});
      return;
    }
    try {
      onChange(JSON.parse(next));
      setError(null);
    } catch {
      setError('invalid JSON — not saved');
    }
  };

  return (
    <label className="block">
      <span className="mb-1 block text-[11px] text-text-mid">{label}</span>
      <textarea
        className="mono min-h-[70px] w-full rounded-control border border-border bg-canvas px-2 py-1 text-[11px] text-text-hi outline-none focus:border-border-strong disabled:opacity-50"
        disabled={disabled}
        value={text}
        onChange={(e) => commit(e.target.value)}
        placeholder="{ }"
      />
      <span className="mt-0.5 block text-[10px] text-text-low">{hint}</span>
      {error && <span className="mt-0.5 block text-[10px] text-red-400">{error}</span>}
    </label>
  );
}

function CreateWorkflowForm({ agentId, onDone }: { agentId: string; onDone: (versionId?: string) => void }) {
  const [name, setName] = useState('');
  const [seed, setSeed] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const w = await workflowsApi.create(agentId, { name, from_recommendation: seed });
      onDone(w.versions[0]?.id);
    } catch (e) { setError(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="block"><span className="mb-1 block text-[12px] text-text-mid">Name</span>
        <input className="h-9 w-full rounded-control border border-border bg-canvas px-2.5 text-[13px] text-text-hi outline-none focus:border-border-strong"
          value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
      <label className="flex items-center gap-2 text-[13px] text-text-mid">
        <input type="checkbox" checked={seed} onChange={(e) => setSeed(e.target.checked)} />
        Pre-populate from the design recommendation's flow
      </label>
      {error && <div className="text-[12px] text-red-400">{error}</div>}
      <div className="flex justify-end"><Button variant="primary" disabled={busy || name.trim().length < 3} onClick={submit}>{busy ? 'Creating…' : 'Create'}</Button></div>
    </div>
  );
}
