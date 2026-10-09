'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { WorkflowCanvas } from '@/components/WorkflowBuilder/WorkflowCanvas';
import { STAGE_OPTIONS } from '@/lib/workflowNodeTypes';
import { hasModuleAccess } from '@/lib/permissions';
import styles from '../automation.module.css';

export default function WorkflowEditorPage() {
    const { accessToken, isLoading, user } = useAuth();
    const router = useRouter();
    const params = useParams();
    const workflowId = params.workflowId as string;

    const [workflow, setWorkflow] = useState<any>(null);
    const [name, setName] = useState('');
    const [status, setStatus] = useState('draft');
    const [triggerStage, setTriggerStage] = useState('');
    const [isDefault, setIsDefault] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'automation', 'admin')) {
            router.replace('/leads');
        }
    }, [isLoading, accessToken, user, router]);

    const load = useCallback(async () => {
        if (!accessToken) return;
        setLoading(true);
        try {
            const res = await fetch(`/api/workflows/${workflowId}`, { headers: { Authorization: `Bearer ${accessToken}` } });
            const data = await res.json();
            if (data.success) {
                setWorkflow(data.data.workflow);
                setName(data.data.workflow.name);
                setStatus(data.data.workflow.status);
                setTriggerStage(data.data.workflow.trigger_stage || '');
                setIsDefault(data.data.workflow.is_default_for_trigger);
            }
        } catch {}
        setLoading(false);
    }, [accessToken, workflowId]);

    useEffect(() => { load(); }, [load]);

    const patchMeta = async (patch: Record<string, any>) => {
        if (!accessToken) return;
        try {
            await fetch(`/api/workflows/${workflowId}`, {
                method: 'PATCH',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify(patch),
            });
        } catch {}
    };

    if (loading || !workflow) {
        return <div style={{ marginLeft: 220, padding: 40, color: 'var(--text-3)' }}>Loading…</div>;
    }

    return (
        <div className={styles.editorPage}>
            <div className={styles.editorHeader}>
                <a className={styles.backLink} onClick={() => router.push('/automation')} style={{ cursor: 'pointer' }}>
                    <ArrowLeft size={14} /> Back to Automation
                </a>
                <div style={{ width: 1, height: 20, background: 'var(--border-subtle)' }} />
                <input
                    className={styles.editorTitle}
                    value={name}
                    onChange={e => setName(e.target.value)}
                    onBlur={() => patchMeta({ name })}
                />
                <select className={styles.statusSelect} value={status} onChange={e => { setStatus(e.target.value); patchMeta({ status: e.target.value }); }}>
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="archived">Archived</option>
                </select>
                <select className={styles.statusSelect} value={triggerStage} onChange={e => {
                    const stage = e.target.value;
                    setTriggerStage(stage);
                    patchMeta({ trigger_stage: stage || null, trigger_type: stage ? 'stage_enter' : 'manual' });
                }}>
                    <option value="">No stage trigger (manual)</option>
                    {STAGE_OPTIONS.map(s => <option key={s.value} value={s.value}>Enter: {s.label}</option>)}
                </select>
                <label className={styles.checkboxRow}>
                    <input
                        type="checkbox"
                        checked={isDefault}
                        onChange={e => { setIsDefault(e.target.checked); patchMeta({ is_default_for_trigger: e.target.checked }); }}
                    />
                    Auto-enroll on trigger
                </label>
            </div>

            <WorkflowCanvas workflow={workflow} accessToken={accessToken!} onSaved={load} />
        </div>
    );
}
