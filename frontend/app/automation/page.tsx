'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Zap, Plus, Copy, Workflow } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { STAGE_OPTIONS } from '@/lib/workflowNodeTypes';
import { hasModuleAccess } from '@/lib/permissions';
import { QuickSetup } from './QuickSetup';
import { AutomationActivity } from './AutomationActivity';
import styles from './automation.module.css';

interface WorkflowSummary {
    id: string;
    name: string;
    description: string;
    trigger_stage: string | null;
    status: 'draft' | 'active' | 'paused' | 'archived';
    is_default_for_trigger: boolean;
    sort_order: number;
}

interface TemplateSummary {
    id: string;
    template_key: string;
    name: string;
    description: string;
    trigger_stage: string | null;
    node_count: number;
}

const STAGE_LABEL: Record<string, string> = Object.fromEntries(STAGE_OPTIONS.map(s => [s.value, s.label]));

export default function AutomationPage() {
    const { accessToken, isLoading, user } = useAuth();
    const router = useRouter();
    const [tab, setTab] = useState<'quick' | 'workflows' | 'templates' | 'activity'>('quick');
    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
    const [templates, setTemplates] = useState<TemplateSummary[]>([]);
    const [loading, setLoading] = useState(false);
    const [creating, setCreating] = useState(false);
    const [draggedId, setDraggedId] = useState<string | null>(null);
    const [draggingOverId, setDraggingOverId] = useState<string | null>(null);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'automation', 'admin')) {
            router.replace('/leads');
        }
    }, [isLoading, accessToken, user, router]);

    const load = useCallback(async () => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        setLoading(true);
        try {
            const [wRes, tRes] = await Promise.all([
                fetch('/api/workflows', { headers: h }),
                fetch('/api/workflows/templates', { headers: h }),
            ]);
            const wd = await wRes.json();
            const td = await tRes.json();
            if (wd.success) setWorkflows(wd.data.workflows);
            if (td.success) setTemplates(td.data.templates);
        } catch {}
        setLoading(false);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const activeWorkflows = workflows.filter(w => w.status === 'active').sort((a, b) => a.sort_order - b.sort_order);
    const otherWorkflows = workflows.filter(w => w.status !== 'active').sort((a, b) => a.sort_order - b.sort_order);

    const createWorkflow = async () => {
        if (!accessToken) return;
        setCreating(true);
        try {
            const res = await fetch('/api/workflows', {
                method: 'POST',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'New Workflow', trigger_type: 'manual' }),
            });
            const data = await res.json();
            if (data.success) router.push(`/automation/${data.data.workflow.id}`);
        } catch {}
        setCreating(false);
    };

    // ── Drag & drop reordering (within a status group only) ────────────────
    const persistOrder = async (ids: string[]) => {
        if (!accessToken) return;
        try {
            await fetch('/api/workflows/reorder', {
                method: 'PATCH',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ order: ids }),
            });
        } catch {}
    };

    const handleDragStart = (id: string) => setDraggedId(id);
    const handleDragOver = (e: React.DragEvent, overId: string) => {
        e.preventDefault();
        setDraggingOverId(overId);
    };
    const handleDrop = (e: React.DragEvent, targetId: string, group: WorkflowSummary[]) => {
        e.preventDefault();
        setDraggingOverId(null);
        if (!draggedId || draggedId === targetId) { setDraggedId(null); return; }
        const groupIds = group.map(w => w.id);
        const fromIdx = groupIds.indexOf(draggedId);
        const toIdx = groupIds.indexOf(targetId);
        if (fromIdx === -1 || toIdx === -1) { setDraggedId(null); return; }
        const reordered = [...groupIds];
        reordered.splice(fromIdx, 1);
        reordered.splice(toIdx, 0, draggedId);
        setDraggedId(null);
        // sort_order only needs to be correct relative to other members of the
        // same group — groups are always rendered from independently filtered
        // + sorted slices of `workflows`, never the raw array order.
        setWorkflows(prev => prev.map(w => {
            const idx = reordered.indexOf(w.id);
            return idx === -1 ? w : { ...w, sort_order: idx };
        }));
        persistOrder(reordered);
    };

    const duplicateTemplate = async (templateId: string, name: string) => {
        if (!accessToken) return;
        try {
            const res = await fetch(`/api/workflows/${templateId}/duplicate`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            const data = await res.json();
            if (data.success) router.push(`/automation/${data.data.workflow.id}`);
        } catch {}
    };

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Zap size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>Automation &amp; Lead Behavior Engine</h1>
                        <p>Simple on/off switches for SMS and calls — or build a fully custom branching journey below.</p>
                    </div>
                    <div className={styles.headerActions}>
                        <button className={styles.btnPrimary} onClick={createWorkflow} disabled={creating}>
                            <Plus size={15} /> New Workflow
                        </button>
                    </div>
                </div>

                <div className={styles.tabs}>
                    <button className={`${styles.tab} ${tab === 'quick' ? styles.tabActive : ''}`} onClick={() => setTab('quick')}>
                        Quick Setup
                    </button>
                    <button className={`${styles.tab} ${tab === 'workflows' ? styles.tabActive : ''}`} onClick={() => setTab('workflows')}>
                        Your Workflows ({workflows.length})
                    </button>
                    <button className={`${styles.tab} ${tab === 'templates' ? styles.tabActive : ''}`} onClick={() => setTab('templates')}>
                        Advanced: Template Library ({templates.length})
                    </button>
                    <button className={`${styles.tab} ${tab === 'activity' ? styles.tabActive : ''}`} onClick={() => setTab('activity')}>
                        Live Activity
                    </button>
                </div>

                {tab === 'quick' && <QuickSetup />}
                {tab === 'activity' && <AutomationActivity />}

                {loading && tab !== 'quick' && <div style={{ color: 'var(--text-3)', fontSize: 13 }}>Loading…</div>}

                {!loading && tab === 'workflows' && (
                    workflows.length === 0 ? (
                        <div className={styles.emptyState}>
                            <Workflow size={36} strokeWidth={1.2} />
                            <p>No workflows yet. Start from the Template Library or build one from scratch.</p>
                        </div>
                    ) : (
                        <>
                            {[
                                { label: 'Active', items: activeWorkflows },
                                { label: 'Drafts & Paused', items: otherWorkflows },
                            ].map(section => section.items.length > 0 && (
                                <div key={section.label} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                    <div style={{
                                        fontSize: 11.5, fontWeight: 700, color: 'var(--text-4)',
                                        textTransform: 'uppercase', letterSpacing: '0.05em',
                                    }}>
                                        {section.label} ({section.items.length})
                                    </div>
                                    <div className={styles.grid}>
                                        {section.items.map(wf => (
                                            <div
                                                key={wf.id}
                                                className={styles.card}
                                                draggable
                                                onDragStart={() => handleDragStart(wf.id)}
                                                onDragOver={e => handleDragOver(e, wf.id)}
                                                onDragLeave={() => setDraggingOverId(null)}
                                                onDrop={e => handleDrop(e, wf.id, section.items)}
                                                onClick={() => router.push(`/automation/${wf.id}`)}
                                                style={{
                                                    opacity: draggedId === wf.id ? 0.4 : 1,
                                                    outline: draggingOverId === wf.id && draggedId !== wf.id ? '2px solid var(--primary)' : undefined,
                                                }}
                                            >
                                                <div className={styles.cardTop}>
                                                    <span className={styles.cardName}>{wf.name}</span>
                                                    <span className={`${styles.pill} ${
                                                        wf.status === 'active' ? styles.pillActive : wf.status === 'paused' ? styles.pillPaused : styles.pillDraft
                                                    }`}>{wf.status}</span>
                                                </div>
                                                <div className={styles.cardDesc}>{wf.description || 'No description'}</div>
                                                <div className={styles.cardMeta}>
                                                    {wf.trigger_stage && <span>Triggers on: {STAGE_LABEL[wf.trigger_stage] || wf.trigger_stage}</span>}
                                                    {wf.is_default_for_trigger && <span>· Default</span>}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </>
                    )
                )}

                {!loading && tab === 'templates' && (
                    <div className={styles.grid}>
                        {templates.map(t => (
                            <div key={t.id} className={styles.card}>
                                <div className={styles.cardTop}>
                                    <span className={styles.cardName}>{t.name}</span>
                                    <span className={styles.pill} style={{ background: 'var(--primary-subtle)', color: 'var(--primary-text)' }}>
                                        {t.node_count} steps
                                    </span>
                                </div>
                                <div className={styles.cardDesc}>{t.description}</div>
                                <div className={styles.cardMeta}>
                                    {t.trigger_stage ? <span>Triggers on: {STAGE_LABEL[t.trigger_stage] || t.trigger_stage}</span> : <span>Manual enrollment</span>}
                                </div>
                                <button className={styles.btnSecondary} onClick={() => duplicateTemplate(t.id, t.name)}>
                                    <Copy size={13} /> Use this template
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
