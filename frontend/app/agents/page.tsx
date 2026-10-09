'use client';

import { useState, useEffect, useCallback } from 'react';
import { Bot, Plus, Edit2, Trash2, ToggleLeft, ToggleRight, X, Save, Zap, Globe } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './agents.module.css';


interface Agent {
    id: string;
    name: string;
    role: string;
    persona: string;
    system_prompt: string;
    call_prompt: string;
    sms_prompt: string;
    ghl_tag: string;
    tone: string;
    language: string;
    status: 'active' | 'inactive';
    created_at: string;
    voice_provider: string | null;
    voice_id: string | null;
}

const EMPTY_FORM = {
    name: '', role: 'Lead Qualifier', persona: '',
    system_prompt: '', call_prompt: '', sms_prompt: '',
    ghl_tag: '', tone: 'professional', language: 'English', status: 'active',
    voice_provider: '', voice_id: '',
};

// Built-in voice choices. Empty = "no override", falls back to the
// language-default voice (Vapi's "Elliot", currently male) exactly as
// every agent behaved before per-agent voice existed.
const VOICE_OPTIONS = [
    { label: 'Default (Elliot)', provider: '',      voiceId: '' },
    { label: 'Jenny (female)',   provider: 'azure',  voiceId: 'en-US-JennyNeural' },
];

const AVATAR_GRADIENTS = [
    'linear-gradient(135deg,#b9862a,#d4a94f)',
    'linear-gradient(135deg,#6366f1,#8b5cf6)',
    'linear-gradient(135deg,#f59e0b,#f97316)',
    'linear-gradient(135deg,#ec4899,#f43f5e)',
    'linear-gradient(135deg,#3b82f6,#6366f1)',
    'linear-gradient(135deg,#10b981,#14b8a6)',
];

function getGradient(name: string) {
    const code = name.charCodeAt(0) || 0;
    return AVATAR_GRADIENTS[code % AVATAR_GRADIENTS.length];
}

export default function AgentsPage() {
    const { accessToken, user, isLoading } = useAuth();
    const router = useRouter();
    const [agents, setAgents] = useState<Agent[]>([]);
    const isStaff = user?.role === 'staff';

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'ai_agents', 'admin')) {
            router.replace('/user/agents');
        }
    }, [isLoading, accessToken, user, router]);
    const [loading, setLoading] = useState(false);
    const [showModal, setShowModal] = useState(false);
    const [editAgent, setEditAgent] = useState<Agent | null>(null);
    const [form, setForm] = useState({ ...EMPTY_FORM });
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        setLoading(true);
        try {
            const res = await fetch(`/api/agents`, { headers: h });
            const d = await res.json();
            if (d.success) setAgents(d.data.agents);
        } catch {}
        setLoading(false);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const openCreate = () => {
        setEditAgent(null);
        setForm({ ...EMPTY_FORM });
        setShowModal(true);
    };

    const openEdit = (agent: Agent) => {
        setEditAgent(agent);
        setForm({
            name: agent.name, role: agent.role, persona: agent.persona,
            system_prompt: agent.system_prompt,
            call_prompt: agent.call_prompt || '',
            sms_prompt:  agent.sms_prompt  || '',
            ghl_tag: agent.ghl_tag, tone: agent.tone,
            language: agent.language, status: agent.status,
            voice_provider: agent.voice_provider || '',
            voice_id: agent.voice_id || '',
        });
        setShowModal(true);
    };

    const handleSave = async () => {
        if (!isStaff && !form.name) return;
        setSaving(true);
        try {
            const url    = editAgent ? `/api/agents/${editAgent.id}` : `/api/agents`;
            const method = editAgent ? 'PATCH' : 'POST';
            const payload = isStaff
                ? { tone: form.tone, language: form.language, ghl_tag: form.ghl_tag,
                    call_prompt: form.call_prompt, sms_prompt: form.sms_prompt }
                : form;
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
        if (!confirm('Delete this agent?')) return;
        await fetch(`/api/agents/${id}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${accessToken}` },
        });
        load();
    };

    const toggleStatus = async (agent: Agent) => {
        await fetch(`/api/agents/${agent.id}`, {
            method: 'PATCH',
            headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: agent.status === 'active' ? 'inactive' : 'active' }),
        });
        load();
    };

    const active   = agents.filter(a => a.status === 'active').length;
    const inactive = agents.filter(a => a.status === 'inactive').length;

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>

                {/* Header */}
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Bot size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>AI Agents</h1>
                        <p>Create and manage your AI conversation agents</p>
                    </div>
                    {!isStaff && (
                        <button className={styles.btnPrimary} onClick={openCreate}>
                            <Plus size={15} /> New Agent
                        </button>
                    )}
                </div>

                {/* Stats strip */}
                {agents.length > 0 && (
                    <div className={styles.statsStrip}>
                        <div className={styles.statPill}>
                            <span className={styles.statNum}>{agents.length}</span>
                            <span className={styles.statLabel}>Total Agents</span>
                        </div>
                        <div className={styles.statDivider} />
                        <div className={styles.statPill}>
                            <span className={styles.statNum} style={{ color: '#e8c877' }}>{active}</span>
                            <span className={styles.statLabel}>Active</span>
                        </div>
                        <div className={styles.statDivider} />
                        <div className={styles.statPill}>
                            <span className={styles.statNum} style={{ color: 'var(--text-4)' }}>{inactive}</span>
                            <span className={styles.statLabel}>Inactive</span>
                        </div>
                    </div>
                )}

                {loading && <div className={styles.loading}>Loading agents...</div>}

                {!loading && agents.length === 0 && (
                    <div className={styles.emptyState}>
                        <div className={styles.emptyIcon}><Bot size={36} strokeWidth={1.2} /></div>
                        <h3>No agents yet</h3>
                        <p>Create your first AI agent to start automating WhatsApp and voice conversations.</p>
                        <button className={styles.btnPrimary} onClick={openCreate}>
                            <Plus size={15} /> Create First Agent
                        </button>
                    </div>
                )}

                <div className={styles.agentGrid}>
                    {agents.map(agent => (
                        <div key={agent.id} className={`${styles.agentCard} ${agent.status === 'inactive' ? styles.agentInactive : ''}`}>

                            {/* Card top bar with gradient */}
                            <div className={styles.cardBanner} style={{ background: getGradient(agent.name) }}>
                                <div className={styles.bannerAvatar}>
                                    {agent.name[0]?.toUpperCase()}
                                </div>
                                <div className={styles.bannerToggle}>
                                    <button className={styles.toggleBtn} onClick={() => toggleStatus(agent)}
                                        title={agent.status === 'active' ? 'Deactivate' : 'Activate'}>
                                        {agent.status === 'active'
                                            ? <ToggleRight size={28} color="#fff" />
                                            : <ToggleLeft  size={28} color="rgba(255,255,255,0.5)" />}
                                    </button>
                                </div>
                            </div>

                            {/* Card body */}
                            <div className={styles.cardBody}>
                                <div className={styles.cardNameRow}>
                                    <div>
                                        <div className={styles.agentName}>{agent.name}</div>
                                        <div className={styles.agentRole}>{agent.role}</div>
                                    </div>
                                    <span className={`${styles.statusChip} ${agent.status === 'active' ? styles.chipActive : styles.chipInactive}`}>
                                        {agent.status}
                                    </span>
                                </div>

                                {agent.persona && (
                                    <p className={styles.personaPreview}>
                                        &ldquo;{agent.persona.slice(0, 90)}{agent.persona.length > 90 ? '…' : ''}&rdquo;
                                    </p>
                                )}

                                {/* Meta chips */}
                                <div className={styles.chipRow}>
                                    <span className={styles.langChip}>
                                        <Globe size={10} /> {agent.language}
                                    </span>
                                    {agent.voice_id && (
                                        <span className={styles.langChip} title={`${agent.voice_provider}:${agent.voice_id}`}>
                                            {agent.voice_id.toLowerCase().includes('jenny') ? '♀' : '🔊'} {agent.voice_id.replace(/^(en|ur|hi)-[A-Z]{2}-/, '').replace('Neural', '')}
                                        </span>
                                    )}
                                    {agent.ghl_tag && (
                                        <span className={styles.tagChip}>
                                            <Zap size={10} /> {agent.ghl_tag}
                                        </span>
                                    )}
                                </div>

                                {/* Prompt preview */}
                                <div className={styles.promptPreview}>
                                    {agent.call_prompt && (
                                        <span className={styles.promptChars} title="Call prompt">📞 {agent.call_prompt.length}ch</span>
                                    )}
                                    {agent.sms_prompt && (
                                        <span className={styles.promptChars} style={{marginLeft:6}} title="SMS/WhatsApp prompt">💬 {agent.sms_prompt.length}ch</span>
                                    )}
                                    {!agent.call_prompt && !agent.sms_prompt && agent.system_prompt && (
                                        <span className={styles.promptChars}>{agent.system_prompt.length} chars</span>
                                    )}
                                </div>

                                {/* Actions */}
                                <div className={styles.cardFooter}>
                                    <span className={styles.createdAt}>
                                        {parseApiDate(agent.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                    </span>
                                    <div className={styles.cardActions}>
                                        <button className={styles.editBtn} onClick={() => openEdit(agent)} title="Edit">
                                            <Edit2 size={13} />
                                        </button>
                                        {!isStaff && (
                                            <button className={styles.deleteBtn} onClick={() => handleDelete(agent.id)} title="Delete">
                                                <Trash2 size={13} />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Modal */}
            {showModal && (
                <div className={styles.overlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <div className={styles.modalTitleRow}>
                                <div className={styles.modalIcon} style={{ background: editAgent ? getGradient(editAgent.name) : 'linear-gradient(135deg,#b9862a,#d4a94f)' }}>
                                    <Bot size={16} color="#fff" />
                                </div>
                                <h2>{isStaff ? `Update ${editAgent?.name ?? 'Agent'} Settings` : (editAgent ? `Edit ${editAgent.name}` : 'New AI Agent')}</h2>
                            </div>
                            <button className={styles.closeBtn} onClick={() => setShowModal(false)}><X size={18} /></button>
                        </div>

                        <div className={styles.modalBody}>
                            <div className={styles.formGrid}>
                                {/* Super admin only fields */}
                                {!isStaff && (<>
                                    <div className={styles.formGroup}>
                                        <label>Agent Name *</label>
                                        <input className={styles.input} placeholder="e.g. Sara"
                                            value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                                    </div>
                                    <div className={styles.formGroup}>
                                        <label>Role</label>
                                        <input className={styles.input} placeholder="Lead Qualifier"
                                            value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} />
                                    </div>
                                    <div className={styles.formGroupFull}>
                                        <label>Persona</label>
                                        <textarea className={styles.textarea} rows={2}
                                            placeholder="Short description of agent's character and personality..."
                                            value={form.persona} onChange={e => setForm(f => ({ ...f, persona: e.target.value }))} />
                                    </div>
                                    <div className={styles.formGroupFull}>
                                        <label>System Prompt <span style={{fontWeight:400,color:'var(--text-4)',fontSize:11}}>(shared base instructions — used automatically for Call/SMS below if you leave those blank)</span></label>
                                        <textarea className={styles.textarea} rows={20}
                                            placeholder="e.g. You are Sara, a professional insurance agent for AllZone. Be warm, concise, and helpful. Always confirm details before booking or quoting."
                                            value={form.system_prompt} onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))} />
                                        <span className={styles.charCount}>{form.system_prompt.length} chars</span>
                                    </div>
                                    <div className={styles.formGroupFull}>
                                        <label>Call Prompt <span style={{fontWeight:400,color:'var(--text-4)',fontSize:11}}>(inbound + outbound calls — same prompt, context injected automatically; leave blank to use System Prompt)</span></label>
                                        <textarea className={styles.textarea} rows={20}
                                            placeholder="Leave blank to use System Prompt as-is, or override with call-specific instructions here."
                                            value={form.call_prompt} onChange={e => setForm(f => ({ ...f, call_prompt: e.target.value }))} />
                                        <span className={styles.charCount}>{form.call_prompt.length} chars</span>
                                    </div>
                                    <div className={styles.formGroup}>
                                        <label>Status</label>
                                        <select className={styles.select} value={form.status}
                                            onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                                            <option value="active">Active</option>
                                            <option value="inactive">Inactive</option>
                                        </select>
                                    </div>
                                    <div className={styles.formGroup}>
                                        <label>Voice (calls)</label>
                                        <select className={styles.select}
                                            value={`${form.voice_provider}|${form.voice_id}`}
                                            onChange={e => {
                                                const [provider, voiceId] = e.target.value.split('|');
                                                setForm(f => ({ ...f, voice_provider: provider, voice_id: voiceId }));
                                            }}>
                                            {VOICE_OPTIONS.map(v => (
                                                <option key={v.label} value={`${v.provider}|${v.voiceId}`}>{v.label}</option>
                                            ))}
                                        </select>
                                    </div>
                                </>)}

                                {/* Shared fields — visible to all roles */}
                                <div className={styles.formGroup}>
                                    <label>Tag (for routing)</label>
                                    <input className={styles.input} placeholder="e.g. insurance, medical"
                                        value={form.ghl_tag} onChange={e => setForm(f => ({ ...f, ghl_tag: e.target.value }))} />
                                </div>
                            </div>
                        </div>

                        <div className={styles.modalFooter}>
                            <button className={styles.btnSecondary} onClick={() => setShowModal(false)}>Cancel</button>
                            <button className={styles.btnPrimary} onClick={handleSave} disabled={saving || !form.name}>
                                <Save size={14} /> {saving ? 'Saving...' : (editAgent ? 'Update Agent' : 'Create Agent')}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
