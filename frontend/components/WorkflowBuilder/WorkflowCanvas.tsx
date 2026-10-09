'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ReactFlow, ReactFlowProvider, Background, Controls, MiniMap, MarkerType,
    addEdge, reconnectEdge, useNodesState, useEdgesState, type Connection, type Edge, type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Save, Loader2 } from 'lucide-react';
import { NODE_TYPE_META, type NodeType } from '@/lib/workflowNodeTypes';
import { NODE_TYPES } from './WorkflowNode';
import { NodePalette } from './NodePalette';
import { NodeConfigPanel } from './NodeConfigPanel';
import type { WorkflowNodeData } from './WorkflowNode';
import styles from './WorkflowBuilder.module.css';

interface BackendNode {
    node_key: string;
    node_type: NodeType;
    config: Record<string, any>;
    position_x: number;
    position_y: number;
}

interface BackendEdge {
    from_node_key: string;
    to_node_key: string;
    branch_label: string | null;
}

interface WorkflowDetail {
    id: string;
    name: string;
    nodes: BackendNode[];
    edges: BackendEdge[];
}

// Seeded templates (and anything duplicated from them) never got real
// position_x/position_y — every node lands at (0,0), so nodes visually pile
// on top of each other and the connecting edges collapse to zero-length
// paths hidden underneath the stack. Detect that (two or more nodes sharing
// the exact same coordinate means positions were never actually set) and
// fall back to a computed layered layout instead of trusting the raw values.
function needsAutoLayout(nodes: BackendNode[]): boolean {
    const seen = new Set<string>();
    for (const n of nodes) {
        const key = `${n.position_x}:${n.position_y}`;
        if (seen.has(key)) return true;
        seen.add(key);
    }
    return false;
}

function autoLayout(nodes: BackendNode[], edges: BackendEdge[]): Record<string, { x: number; y: number }> {
    const outgoing: Record<string, string[]> = {};
    const indegree: Record<string, number> = {};
    nodes.forEach((n) => { outgoing[n.node_key] = []; indegree[n.node_key] = 0; });
    edges.forEach((e) => {
        if (outgoing[e.from_node_key] && indegree[e.to_node_key] !== undefined) {
            outgoing[e.from_node_key].push(e.to_node_key);
            indegree[e.to_node_key] += 1;
        }
    });

    // Layer nodes by longest path from any root (indegree 0) so branches
    // that later reconverge still land in a sane column.
    const depth: Record<string, number> = {};
    const roots = nodes.filter((n) => indegree[n.node_key] === 0).map((n) => n.node_key);
    const queue = roots.length ? [...roots] : nodes.slice(0, 1).map((n) => n.node_key);
    queue.forEach((k) => { depth[k] = 0; });
    for (let i = 0; i < queue.length; i++) {
        const cur = queue[i];
        for (const child of outgoing[cur] || []) {
            const next = (depth[cur] ?? 0) + 1;
            if (depth[child] === undefined || next > depth[child]) depth[child] = next;
            if (!queue.includes(child)) queue.push(child);
        }
    }
    nodes.forEach((n) => { if (depth[n.node_key] === undefined) depth[n.node_key] = 0; });

    const byDepth: Record<number, string[]> = {};
    nodes.forEach((n) => { (byDepth[depth[n.node_key]] ||= []).push(n.node_key); });

    // Node handles are Left (target) / Right (source) — a left-to-right
    // flow, matching standard automation-builder conventions (Zapier/n8n
    // style): every depth is a straight vertical column, no diagonal drift.
    // Branch siblings at the same depth spread vertically around a shared
    // baseline (0) so reconverging paths stay easy to trace instead of
    // cascading into an illegible staircase.
    const X_GAP = 380;
    const Y_BRANCH_GAP = 210;
    const pos: Record<string, { x: number; y: number }> = {};

    // A branch node's TRUE/REPLIED output is drawn above its FALSE/NO_REPLY
    // output (see WorkflowNode.tsx's branchHandleRow order) — without
    // accounting for that, a column's left-to-right array order was the only
    // thing deciding top vs bottom, so a child reached via the *bottom*
    // handle could easily land *above* a sibling reached via the *top*
    // handle, forcing their connecting lines to cross. Order each column by
    // a barycenter: the average Y of each node's parent(s), nudged up for a
    // true/replied edge and down for a false/no_reply edge, so a node fed
    // from a top handle is placed above one fed from a bottom handle.
    const configByKey = Object.fromEntries(nodes.map((n) => [n.node_key, n.config || {}]));
    const HANDLE_BIAS = 60;
    const edgeBias = (e: BackendEdge): number => {
        if (!e.branch_label) return 0;
        const cfg = configByKey[e.from_node_key] || {};
        return e.branch_label === cfg.true_branch ? -HANDLE_BIAS : HANDLE_BIAS;
    };
    const parentEdges: Record<string, BackendEdge[]> = {};
    edges.forEach((e) => { (parentEdges[e.to_node_key] ||= []).push(e); });

    Object.keys(byDepth).map(Number).sort((a, b) => a - b).forEach((d) => {
        const keys = byDepth[d];
        let ordered = keys;
        if (d > 0) {
            const target: Record<string, number> = {};
            keys.forEach((key) => {
                const pe = parentEdges[key] || [];
                target[key] = pe.length
                    ? pe.reduce((acc, e) => acc + (pos[e.from_node_key]?.y ?? 0) + edgeBias(e), 0) / pe.length
                    : 0;
            });
            ordered = [...keys].sort((a, b) => target[a] - target[b]);
        }
        ordered.forEach((key, i) => {
            pos[key] = { x: d * X_GAP, y: (i - (ordered.length - 1) / 2) * Y_BRANCH_GAP };
        });
    });
    return pos;
}

function toFlow(workflow: WorkflowDetail): { nodes: Node[]; edges: Edge[] } {
    const layout = needsAutoLayout(workflow.nodes) ? autoLayout(workflow.nodes, workflow.edges) : null;
    const nodes: Node[] = workflow.nodes.map((n) => ({
        id: n.node_key,
        type: 'workflowNode',
        position: layout ? layout[n.node_key] : { x: n.position_x || 0, y: n.position_y || 0 },
        data: { nodeType: n.node_type, config: n.config || {} } as WorkflowNodeData,
    }));
    const configByKey = Object.fromEntries(workflow.nodes.map(n => [n.node_key, n.config || {}]));
    const edges: Edge[] = workflow.edges.map((e, i) => {
        let sourceHandle: string | undefined;
        if (e.branch_label) {
            const cfg = configByKey[e.from_node_key] || {};
            sourceHandle = e.branch_label === cfg.true_branch ? 'true' : 'false';
        }
        return {
            id: `e_${i}_${e.from_node_key}_${e.to_node_key}`,
            source: e.from_node_key,
            target: e.to_node_key,
            sourceHandle,
            label: e.branch_label || undefined,
            data: { branch_label: e.branch_label },
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: 'var(--primary)' },
            style: { stroke: 'var(--primary)', strokeWidth: 3 },
            labelStyle: { fill: 'var(--text-1)', fontWeight: 600, fontSize: 11 },
            labelBgStyle: { fill: 'var(--bg-surface)' },
            labelBgPadding: [6, 3] as [number, number],
        };
    });
    return { nodes, edges };
}

let nodeKeyCounter = 0;
function newNodeKey(nodeType: NodeType) {
    nodeKeyCounter += 1;
    return `${nodeType}_${Date.now().toString(36)}${nodeKeyCounter}`;
}

function CanvasInner({ workflow, accessToken, onSaved }: { workflow: WorkflowDetail; accessToken: string; onSaved: () => void }) {
    const initial = useMemo(() => toFlow(workflow), [workflow.id]);
    const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [savedAt, setSavedAt] = useState<number | null>(null);

    const onConnect = useCallback((connection: Connection) => {
        setEdges((eds) => addEdge({
            ...connection,
            label: connection.sourceHandle === 'true' ? 'yes-branch' : connection.sourceHandle === 'false' ? 'no-branch' : undefined,
        }, eds));
    }, [setEdges]);

    // Drag an existing edge's endpoint onto a different node to re-route it.
    const onReconnect = useCallback((oldEdge: Edge, newConnection: Connection) => {
        setEdges((eds) => reconnectEdge(oldEdge, newConnection, eds));
    }, [setEdges]);

    const addNode = useCallback((nodeType: NodeType) => {
        const key = newNodeKey(nodeType);
        const meta = NODE_TYPE_META[nodeType];
        setNodes((nds) => [...nds, {
            id: key,
            type: 'workflowNode',
            position: { x: 120 + (nds.length % 4) * 200, y: 120 + Math.floor(nds.length / 4) * 140 },
            data: { nodeType, config: { ...meta.defaultConfig } } as WorkflowNodeData,
        }]);
    }, [setNodes]);

    const selectedNode = nodes.find(n => n.id === selectedId) || null;

    const updateSelectedConfig = useCallback((config: Record<string, any>) => {
        if (!selectedId) return;
        setNodes((nds) => nds.map(n => n.id === selectedId ? { ...n, data: { ...n.data, config } } : n));
    }, [selectedId, setNodes]);

    const deleteSelected = useCallback(() => {
        if (!selectedId) return;
        setNodes((nds) => nds.filter(n => n.id !== selectedId));
        setEdges((eds) => eds.filter(e => e.source !== selectedId && e.target !== selectedId));
        setSelectedId(null);
    }, [selectedId, setNodes, setEdges]);

    const save = useCallback(async () => {
        setSaving(true);
        setError(null);
        try {
            const nodePayload = nodes.map(n => ({
                node_key: n.id,
                node_type: (n.data as unknown as WorkflowNodeData).nodeType,
                config: (n.data as unknown as WorkflowNodeData).config || {},
                position_x: n.position.x,
                position_y: n.position.y,
            }));
            const edgePayload = edges.map(e => {
                let branchLabel: string | null = null;
                if (e.sourceHandle) {
                    const sourceNode = nodes.find(n => n.id === e.source);
                    const cfg = (sourceNode?.data as unknown as WorkflowNodeData)?.config || {};
                    branchLabel = e.sourceHandle === 'true' ? (cfg.true_branch || 'yes') : (cfg.false_branch || 'no');
                }
                return { from_node_key: e.source, to_node_key: e.target, branch_label: branchLabel };
            });

            const res = await fetch(`/api/workflows/${workflow.id}/graph`, {
                method: 'PUT',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ nodes: nodePayload, edges: edgePayload }),
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.detail || 'Save failed');
            }
            setSavedAt(Date.now());
            onSaved();
        } catch (e: any) {
            setError(e.message || 'Save failed');
        } finally {
            setSaving(false);
        }
    }, [nodes, edges, workflow.id, accessToken, onSaved]);

    return (
        <div style={{ position: 'relative', flex: 1, display: 'flex', minHeight: 0 }}>
            <div style={{ width: 220, borderRight: '1px solid var(--border-subtle)', padding: 14, overflowY: 'auto' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 10 }}>
                    Add a step
                </div>
                <NodePalette onAdd={addNode} />
            </div>

            <div style={{ flex: 1, position: 'relative' }}>
                <div style={{
                    position: 'absolute', top: 12, right: 12, zIndex: 5, display: 'flex', alignItems: 'center', gap: 10,
                }}>
                    {error && <span style={{ fontSize: 11.5, color: 'var(--status-danger)' }}>{error}</span>}
                    {savedAt && !error && <span style={{ fontSize: 11.5, color: 'var(--status-success)' }}>✓ Saved</span>}
                    <button
                        onClick={save}
                        disabled={saving}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 10,
                            background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', fontWeight: 600, fontSize: 13,
                            cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.7 : 1,
                        }}
                    >
                        {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
                        {saving ? 'Saving…' : 'Save Workflow'}
                    </button>
                </div>

                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onReconnect={onReconnect}
                    nodeTypes={NODE_TYPES}
                    onNodeClick={(_, node) => setSelectedId(node.id)}
                    onPaneClick={() => setSelectedId(null)}
                    defaultEdgeOptions={{
                        type: 'smoothstep',
                        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: 'var(--primary)' },
                        style: { stroke: 'var(--primary)', strokeWidth: 3 },
                    }}
                    fitView
                    fitViewOptions={{ maxZoom: 1.4, padding: 0.25 }}
                    proOptions={{ hideAttribution: true }}
                >
                    <Background gap={18} color="var(--border-subtle)" />
                    <Controls showInteractive={false} />
                    <MiniMap pannable zoomable style={{ background: 'var(--bg-surface)' }} />
                </ReactFlow>

                {selectedNode && (
                    <NodeConfigPanel
                        nodeKey={selectedNode.id}
                        data={selectedNode.data as unknown as WorkflowNodeData}
                        onChange={updateSelectedConfig}
                        onDelete={deleteSelected}
                        onClose={() => setSelectedId(null)}
                    />
                )}
            </div>
        </div>
    );
}

export function WorkflowCanvas(props: { workflow: WorkflowDetail; accessToken: string; onSaved: () => void }) {
    return (
        <ReactFlowProvider>
            <CanvasInner {...props} />
        </ReactFlowProvider>
    );
}
