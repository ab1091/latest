'use client';

import { useState, useEffect, useCallback } from 'react';
import { SlidersHorizontal, Plus, Trash2, Edit2, X, Save, ChevronRight, Bot, Calendar, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import { STAGE_OPTIONS } from '@/lib/workflowNodeTypes';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './lead-configs.module.css';


interface Condition {
    field:    'tag' | 'source' | 'status';
    operator: 'equals' | 'contains';
    value:    string;
}

interface LeadConfig {
    id:               string;
    name:             string;
    condition_logic:  'any' | 'all';
    conditions:       Condition[];
    agent_id:         string | null;
    agent_name:       string | null;
    agent_role:       string | null;
    provider_id:      string | null;
    calendar_enabled: boolean;
    status:           'active' | 'inactive';
    created_at:       string;
}

interface Agent {
    id: string;
    name: string;
    role: string;
}

const EMPTY_CONDITION: Condition = { field: 'tag', operator: 'equals', value: '' };
const EMPTY_FORM = {
    name: '', condition_logic: 'any' as 'any' | 'all',
    conditions: [{ ...EMPTY_CONDITION }],
    agent_id: '', calendar_enabled: false, status: 'active' as 'active' | 'inactive',
};

export default function LeadConfigsPage() {
    const { accessToken, user, isLoading } = useAuth();
    const router = useRouter();
    const [configs, setConfigs] = useState<LeadConfig[]>([]);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'lead_configs', 'admin')) {
            router.replace('/leads');
        }
    }, [isLoading, accessToken, user, router]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(false);
    const [showModal, setShowModal] = useState(false);
    const [editConfig, setEditConfig] = useState<LeadConfig | null>(null);
    const [form, setForm] = useState({ ...EMPTY_FORM });
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        setLoading(true);
        try {
            const [cfgRes, agentRes] = await Promise.all([
                fetch(`/api/lead-configs`, { headers: h }),
                fetch(`/api/agents`, { headers: h }),
            ]);
            const cd = await cfgRes.json();
            const ad = await agentRes.json();
            if (cd.success) setConfigs(cd.data.configs);
            if (ad.success) setAgents(ad.data.agents);
        } catch {}
        setLoading(false);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const openCreate = () => {
        setEditConfig(null);
        setForm({ ...EMPTY_FORM, conditions: [{ ...EMPTY_CONDITION }] });
        setShowModal(true);
    };

    const openEdit = (cfg: LeadConfig) => {
        setEditConfig(cfg);
        setForm({
            name:             cfg.name,
            condition_logic:  cfg.condition_logic,
            conditions:       cfg.conditions.length > 0 ? cfg.conditions : [{ ...EMPTY_CONDITION }],
            agent_id:         cfg.agent_id || '',
            calendar_enabled: cfg.calendar_enabled,
            status:           cfg.status,
        });
        setShowModal(true);
    };

    const handleSave = async () => {
        if (!form.name) return;
        setSaving(true);
        try {
            const payload = {
                ...form,
                agent_id: form.agent_id || null,
                conditions: form.conditions.filter(c => c.value.trim()),
            };
            const url    = editConfig ? `/api/lead-configs/${editConfig.id}` : `/api/lead-configs`;
            const method = editConfig ? 'PATCH' : 'POST';
            const res = await fetch(url, {
                method,
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await res.json();
            if (d.success) { setShowModal(false); load(); }
        } catch {}
        setSaving(false);
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Delete this rule?')) return;
        await fetch(`/api/lead-configs/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${accessToken}` } });
        load();
    };

    const addCondition = () =>
        setForm(f => ({ ...f, conditions: [...f.conditions, { ...EMPTY_CONDITION }] }));

    const removeCondition = (i: number) =>
        setForm(f => ({ ...f, conditions: f.conditions.filter((_, idx) => idx !== i) }));

    const updateCondition = (i: number, patch: Partial<Condition>) =>
        setForm(f => ({
            ...f,
            conditions: f.conditions.map((c, idx) => idx === i ? { ...c, ...patch } : c),
        }));

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><SlidersHorizontal size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>Lead Configuration</h1>
                        <p>Route leads to AI agents based on tag, source, or pipeline stage</p>
                    </div>
                    <button className={styles.btnPrimary} onClick={openCreate}>
                        <Plus size={15} /> New Rule
                    </button>
                </div>

                {/* How it works */}
                <div className={styles.howItWorks}>
                    <span className={styles.howLabel}>How it works:</span>
                    <span className={styles.howStep}><span className={styles.ifBadge}>IF</span> Lead has tag / source / stage</span>
                    <ChevronRight size={14} color="var(--text-4)" />
                    <span className={styles.howStep}><span className={styles.thenBadge}>THEN</span> Assign AI Agent + Calendar</span>
                </div>

                {loading && <div className={styles.loading}>Loading rules...</div>}

                {!loading && configs.length === 0 && (
                    <div className={styles.emptyState}>
                        <SlidersHorizontal size={38} strokeWidth={1.2} />
                        <p>No routing rules yet.<br />Create your first rule to auto-assign leads to agents.</p>
                        <button className={styles.btnPrimary} onClick={openCreate}><Plus size={14} /> Create Rule</button>
                    </div>
                )}

                <div className={styles.rulesList}>
                    {configs.map(cfg => (
                        <div key={cfg.id} className={`${styles.ruleCard} ${cfg.status === 'inactive' ? styles.ruleInactive : ''}`}>
                            <div className={styles.ruleHeader}>
                                <div className={styles.ruleName}>{cfg.name}</div>
                                <div className={styles.ruleActions}>
                                    <span className={`${styles.statusPill} ${cfg.status === 'active' ? styles.pillActive : styles.pillInactive}`}>
                                        {cfg.status}
                                    </span>
                                    <button className={styles.editBtn} onClick={() => openEdit(cfg)}><Edit2 size={14} /></button>
                                    <button className={styles.deleteBtn} onClick={() => handleDelete(cfg.id)}><Trash2 size={14} /></button>
                                </div>
                            </div>

                            <div className={styles.ruleBody}>
                                {/* IF block */}
                                <div className={styles.condBlock}>
                                    <div className={styles.blockLabel}>
                                        <span className={styles.ifBadge}>IF</span>
                                        <span className={styles.logicNote}>
                                            match <strong>{cfg.condition_logic}</strong> of:
                                        </span>
                                    </div>
                                    <div className={styles.condList}>
                                        {(cfg.conditions || []).length === 0
                                            ? <span className={styles.noConditions}>No conditions</span>
                                            : cfg.conditions.map((c, i) => (
                                                <div key={i} className={styles.condPill}>
                                                    <span className={styles.condField}>{c.field}</span>
                                                    <span className={styles.condOp}>{c.operator}</span>
                                                    <span className={styles.condVal}>
                                                        &quot;{c.field === 'status' ? (STAGE_OPTIONS.find(s => s.value === c.value)?.label || c.value) : c.value}&quot;
                                                    </span>
                                                </div>
                                            ))}
                                    </div>
                                </div>

                                <ChevronRight size={18} color="var(--text-4)" className={styles.arrow} />

                                {/* THEN block */}
                                <div className={styles.thenBlock}>
                                    <div className={styles.blockLabel}>
                                        <span className={styles.thenBadge}>THEN</span>
                                    </div>
                                    <div className={styles.thenItems}>
                                        {cfg.agent_name ? (
                                            <div className={styles.thenItem}>
                                                <Bot size={14} />
                                                <span>{cfg.agent_name}</span>
                                                <span className={styles.thenMeta}>{cfg.agent_role}</span>
                                            </div>
                                        ) : (
                                            <div className={styles.thenItemEmpty}>No agent assigned</div>
                                        )}
                                        {cfg.calendar_enabled && (
                                            <div className={styles.thenItem}>
                                                <Calendar size={14} />
                                                <span>Calendar booking enabled</span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Create / Edit Modal */}
            {showModal && (
                <div className={styles.overlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2>{editConfig ? 'Edit Rule' : 'New Routing Rule'}</h2>
                            <button className={styles.closeBtn} onClick={() => setShowModal(false)}><X size={18} /></button>
                        </div>

                        <div className={styles.modalBody}>
                            {/* Rule name */}
                            <div className={styles.formGroup}>
                                <label>Rule Name *</label>
                                <input className={styles.input} placeholder="e.g. Home Loan Leads"
                                    value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                            </div>

                            {/* IF CONDITIONS */}
                            <div className={styles.section}>
                                <div className={styles.sectionHeader}>
                                    <span className={styles.ifBadge}>IF</span>
                                    <span className={styles.sectionTitle}>Conditions</span>
                                    <select className={styles.logicSelect} value={form.condition_logic}
                                        onChange={e => setForm(f => ({ ...f, condition_logic: e.target.value as 'any' | 'all' }))}>
                                        <option value="any">Match ANY</option>
                                        <option value="all">Match ALL</option>
                                    </select>
                                </div>

                                {form.conditions.map((cond, i) => (
                                    <div key={i} className={styles.condRow}>
                                        <select className={styles.condSelect} value={cond.field}
                                            onChange={e => updateCondition(i, { field: e.target.value as Condition['field'], value: '' })}>
                                            <option value="tag">Tag</option>
                                            <option value="source">Source</option>
                                            <option value="status">Status</option>
                                        </select>
                                        <select className={styles.condSelect} value={cond.operator}
                                            onChange={e => updateCondition(i, { operator: e.target.value as Condition['operator'] })}>
                                            <option value="equals">equals</option>
                                            <option value="contains">contains</option>
                                        </select>
                                        {cond.field === 'status' ? (
                                            <select className={styles.condSelect} value={cond.value}
                                                onChange={e => updateCondition(i, { value: e.target.value })}>
                                                <option value="" disabled>Select stage...</option>
                                                {STAGE_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                                            </select>
                                        ) : (
                                            <input className={styles.condInput} placeholder="value..."
                                                value={cond.value}
                                                onChange={e => updateCondition(i, { value: e.target.value })} />
                                        )}
                                        {form.conditions.length > 1 && (
                                            <button className={styles.removeBtn} onClick={() => removeCondition(i)}>
                                                <X size={13} />
                                            </button>
                                        )}
                                    </div>
                                ))}

                                <button className={styles.addCondBtn} onClick={addCondition}>
                                    <Plus size={13} /> Add Condition
                                </button>
                            </div>

                            {/* THEN EXECUTE */}
                            <div className={styles.section}>
                                <div className={styles.sectionHeader}>
                                    <span className={styles.thenBadge}>THEN</span>
                                    <span className={styles.sectionTitle}>Execute</span>
                                </div>

                                <div className={styles.formGroup}>
                                    <label>Assign AI Agent</label>
                                    <select className={styles.select} value={form.agent_id}
                                        onChange={e => setForm(f => ({ ...f, agent_id: e.target.value }))}>
                                        <option value="">— No agent —</option>
                                        {agents.map(a => (
                                            <option key={a.id} value={a.id}>{a.name} ({a.role})</option>
                                        ))}
                                    </select>
                                </div>

                                <label className={styles.checkboxRow}>
                                    <input type="checkbox" checked={form.calendar_enabled}
                                        onChange={e => setForm(f => ({ ...f, calendar_enabled: e.target.checked }))} />
                                    <span>Enable calendar booking for matched leads</span>
                                </label>

                                <div className={styles.formGroup} style={{ marginTop: '1rem' }}>
                                    <label>Rule Status</label>
                                    <select className={styles.select} value={form.status}
                                        onChange={e => setForm(f => ({ ...f, status: e.target.value as 'active' | 'inactive' }))}>
                                        <option value="active">Active</option>
                                        <option value="inactive">Inactive</option>
                                    </select>
                                </div>
                            </div>
                        </div>

                        <div className={styles.modalFooter}>
                            <button className={styles.btnSecondary} onClick={() => setShowModal(false)}>Cancel</button>
                            <button className={styles.btnPrimary} onClick={handleSave}
                                disabled={saving || !form.name}>
                                <Save size={14} /> {saving ? 'Saving...' : (editConfig ? 'Update Rule' : 'Create Rule')}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
