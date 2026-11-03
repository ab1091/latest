'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    ArrowLeft, Phone, Mail, Tag, Clock, MessageCircle, Smartphone,
    Zap, Calendar, Plus, CheckCircle2, Circle, StickyNote, ListTodo, Workflow, Pencil,
    ShieldAlert, ShieldCheck,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { SideNav } from '@/components/SideNav/SideNav';
import styles from './workspace.module.css';

const STAGE_META: Record<string, { label: string; color: string }> = {
    new_lead: { label: 'New Lead', color: '#818cf8' },
    old_lead: { label: 'Old Lead', color: '#fb923c' },
    connected: { label: 'Connected', color: '#38bdf8' },
    quoted: { label: 'Quoted', color: '#34d399' },
    appointment_scheduled: { label: 'Appointment Scheduled', color: '#60a5fa' },
    closed: { label: 'Closed', color: '#e8c877' },
    dead: { label: 'Trip Lead', color: '#f87171' },
};

const BAND_COLOR: Record<string, string> = { hot: '#f87171', warm: '#fbbf24', cold: '#7fded0', new: '#89a7a1' };

function formatCountdown(ms: number): string {
    if (ms <= 0) return 'firing shortly…';
    const totalSeconds = Math.floor(ms / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    // Always show a ticking seconds digit — at "Xh Ym" precision alone the
    // display looks frozen for up to 60s at a time, which reads as static
    // rather than live.
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
    return `${minutes}m ${seconds}s`;
}

function formatDeliveryError(reason?: string | null): string {
    if (!reason) return '';
    const lower = reason.toLowerCase();
    if (lower.includes('bluebubbles') || lower.includes('message send error') || lower.includes('not registered') || lower.includes('500') || lower.includes('502')) {
        return 'Non-iMessage Number (Android or Landline)';
    }
    if (lower.includes('rate limit') || lower.includes('velocity')) {
        return 'Hourly Velocity Limit Reached';
    }
    return reason.slice(0, 60);
}

interface Lead {
    id: string; first_name: string; last_name: string; email: string; phone: string;
    tags: string[]; sub_status: string; stage: string; notes: string; preferred_channel: string;
    created_at: string; score: number; score_band: string;
    assigned_first_name?: string; assigned_last_name?: string;
    active_enrollment: {
        id: string; status: string; current_node_key: string; workflow_id: string; workflow_name: string; total_nodes: number;
        node_started_at: string | null; next_action_at: string | null;
    } | null;
    open_tasks_count: number;
    ai_summary?: string;
    ai_summary_updated_at?: string | null;
}

type CenterTab = 'timeline' | 'conversations' | 'calls' | 'summary' | 'notes' | 'tasks';

export default function LeadWorkspacePage() {
    const { accessToken, isLoading, user } = useAuth();
    const router = useRouter();
    const params = useParams();
    const leadId = params.leadId as string;

    const [lead, setLead] = useState<Lead | null>(null);
    const [events, setEvents] = useState<any[]>([]);
    const [conversations, setConversations] = useState<any[]>([]);
    const [appointments, setAppointments] = useState<any[]>([]);
    const [notes, setNotes] = useState<any[]>([]);
    const [tasks, setTasks] = useState<any[]>([]);
    const [tab, setTab] = useState<CenterTab>('timeline');
    const [expandedConvId, setExpandedConvId] = useState<string | null>(null);
    const [expandedCallIdx, setExpandedCallIdx] = useState<number | null>(null);
    const [threadMessages, setThreadMessages] = useState<any[]>([]);
    const [newNote, setNewNote] = useState('');
    const [newTask, setNewTask] = useState('');
    const [loading, setLoading] = useState(true);
    const [now, setNow] = useState(() => Date.now());
    const [summarizing, setSummarizing] = useState(false);
    const [summaryError, setSummaryError] = useState('');
    const [editingEmail, setEditingEmail] = useState(false);
    const [emailInput, setEmailInput] = useState('');
    const [savingEmail, setSavingEmail] = useState(false);

    useEffect(() => {
        const tick = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(tick);
    }, []);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role)) router.replace('/leads');
    }, [isLoading, accessToken, user, router]);

    const h = useMemo(() => ({ Authorization: `Bearer ${accessToken}` }), [accessToken]);
    const hJson = useMemo(() => ({ ...h, 'Content-Type': 'application/json' }), [h]);

    const load = useCallback(async (opts?: { silent?: boolean }) => {
        if (!accessToken) return;
        if (!opts?.silent) setLoading(true);
        try {
            const [leadRes, journeyRes, activityRes, notesRes, tasksRes] = await Promise.all([
                fetch(`/api/leads/${leadId}`, { headers: h }),
                fetch(`/api/leads/${leadId}/journey`, { headers: h }),
                fetch(`/api/leads/${leadId}/activity`, { headers: h }),
                fetch(`/api/notes?lead_id=${leadId}`, { headers: h }),
                fetch(`/api/tasks?lead_id=${leadId}`, { headers: h }),
            ]);
            const l = await leadRes.json();
            if (l.success) setLead(l.data.lead);
            const j = await journeyRes.json();
            if (j.success) setEvents(j.data.events || []);
            const a = await activityRes.json();
            if (a.success) {
                setConversations(a.data.conversations || []);
                setAppointments(a.data.appointments || []);
            }
            const n = await notesRes.json();
            if (n.success) setNotes(n.data.notes || []);
            const t = await tasksRes.json();
            if (t.success) setTasks(t.data.tasks || []);
        } catch {}
        if (!opts?.silent) setLoading(false);
    }, [accessToken, leadId, h]);

    useEffect(() => { load(); }, [load]);

    // Live auto-refresh: poll lead detail, messages, and journey silently every 3s
    useEffect(() => {
        if (!accessToken) return;
        const id = setInterval(() => {
            load({ silent: true });
        }, 3000);
        return () => clearInterval(id);
    }, [accessToken, load]);

    const [retryingMsgId, setRetryingMsgId] = useState<string | null>(null);
    const [safetyStatus, setSafetyStatus] = useState<any>(null);

    const fetchSafetyStatus = useCallback(async () => {
        try {
            const res = await fetch('/api/sms/safety-status', { headers: h });
            const d = await res.json();
            if (d.success) setSafetyStatus(d.data);
        } catch {}
    }, [h]);

    useEffect(() => {
        fetchSafetyStatus();
        const timer = setInterval(fetchSafetyStatus, 5000);
        return () => clearInterval(timer);
    }, [fetchSafetyStatus]);

    const resetCircuitBreaker = async () => {
        try {
            const res = await fetch('/api/sms/reset-circuit-breaker', {
                method: 'POST',
                headers: h
            });
            const d = await res.json();
            if (d.success) {
                await fetchSafetyStatus();
                alert('Safety Circuit Breaker reset. Outbound sending resumed.');
            }
        } catch {
            alert('Failed to reset circuit breaker');
        }
    };

    const retryLeadMessage = async (convId: string, msgId: string, channel: string = 'sms') => {
        setRetryingMsgId(msgId);
        try {
            const res = await fetch(`/api/conversations/${convId}/messages/${msgId}/retry`, {
                method: 'POST',
                headers: hJson,
                body: JSON.stringify({ channel })
            });
            const d = await res.json();
            if (d.data?.message) {
                setThreadMessages(ms => ms.map(m => m.id === msgId ? d.data.message : m));
            }
            if (!d.success) {
                alert(`Retry failed: ${d.detail || 'Could not deliver message'}`);
            }
            await fetchSafetyStatus();
        } catch {
            alert('Network error while retrying message');
        } finally {
            setRetryingMsgId(null);
        }
    };

    const fetchThreadMessages = useCallback(async (convId: string) => {
        try {
            const res = await fetch(`/api/conversations/${convId}/messages`, { headers: h });
            const d = await res.json();
            if (d.success) setThreadMessages(d.data.messages || []);
        } catch { setThreadMessages([]); }
    }, [h]);

    const toggleConv = (convId: string) => {
        if (expandedConvId === convId) { setExpandedConvId(null); return; }
        setExpandedConvId(convId);
        fetchThreadMessages(convId);
    };

    // Auto-refresh the open thread so new messages (bot replies, inbound
    // texts) show up without a manual page reload.
    useEffect(() => {
        if (!expandedConvId) return;
        const poll = setInterval(() => fetchThreadMessages(expandedConvId), 4000);
        return () => clearInterval(poll);
    }, [expandedConvId, fetchThreadMessages]);

    const addNote = async () => {
        if (!newNote.trim()) return;
        await fetch('/api/notes', { method: 'POST', headers: hJson, body: JSON.stringify({ lead_id: leadId, body: newNote }) });
        setNewNote('');
        load();
    };

    const addTask = async () => {
        if (!newTask.trim()) return;
        await fetch('/api/tasks', { method: 'POST', headers: hJson, body: JSON.stringify({ lead_id: leadId, title: newTask }) });
        setNewTask('');
        load();
    };

    const toggleTaskDone = async (taskId: string, currentStatus: string) => {
        await fetch(`/api/tasks/${taskId}`, {
            method: 'PATCH', headers: hJson,
            body: JSON.stringify({ status: currentStatus === 'done' ? 'open' : 'done' }),
        });
        load();
    };

    const generateSummary = async () => {
        setSummarizing(true);
        setSummaryError('');
        try {
            const res = await fetch(`/api/leads/${leadId}/generate-summary`, { method: 'POST', headers: h });
            const d = await res.json();
            if (d.success) {
                setLead(prev => prev ? { ...prev, ai_summary: d.data.summary, ai_summary_updated_at: new Date().toISOString() } : prev);
            } else {
                setSummaryError(d.detail || 'Failed to generate summary.');
            }
        } catch {
            setSummaryError('Failed to generate summary.');
        }
        setSummarizing(false);
    };

    const handleSaveEmail = async () => {
        const val = emailInput.trim();
        if (!val || val === lead?.email) {
            setEditingEmail(false);
            return;
        }
        setSavingEmail(true);
        try {
            const res = await fetch(`/api/leads/${leadId}`, {
                method: 'PATCH',
                headers: hJson,
                body: JSON.stringify({ email: val }),
            });
            const d = await res.json();
            if (d.success) {
                setLead(prev => prev ? { ...prev, email: val } : prev);
            }
        } catch {}
        setSavingEmail(false);
        setEditingEmail(false);
    };

    const initials = lead ? `${lead.first_name?.[0] || ''}${lead.last_name?.[0] || ''}`.toUpperCase() : '?';
    const stageMeta = lead ? (STAGE_META[lead.stage] || { label: lead.stage, color: '#818cf8' }) : null;
    const bandColor = lead ? (BAND_COLOR[lead.score_band] || '#89a7a1') : '#89a7a1';

    // Day-grouped timeline: includes stage moves, calls, appointments,
    // workflow steps, and sent emails.
    const days = useMemo(() => {
        const milestones = events.filter(e => e.type !== 'message' || e.data?.channel === 'email');
        const grouped: Record<string, any[]> = {};
        milestones.forEach(e => {
            const key = parseApiDate(e.timestamp).toDateString();
            if (!grouped[key]) grouped[key] = [];
            grouped[key].push(e);
        });
        return Object.entries(grouped);
    }, [events]);

    // Calls-only view, pulled from the same journey events the timeline uses —
    // keeps recordings/summaries in one place instead of buried in the mixed feed.
    const calls = useMemo(() => events.filter(e => e.type === 'call'), [events]);

    if (loading || !lead) {
        return <div style={{ marginLeft: 220, padding: 40, color: 'var(--text-3)' }}>Loading…</div>;
    }

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.topBar}>
                    <button className={styles.backLink} onClick={() => router.push('/leads')}>
                        <ArrowLeft size={14} /> Back to Leads
                    </button>
                </div>

                <div className={styles.workspace}>
                    {/* ── Left panel ── */}
                    <div className={`${styles.panel} ${styles.leftPanel}`}>
                        <div className={styles.avatarBlock}>
                            <div className={styles.avatar}>{initials}</div>
                            <div className={styles.leadName}>{lead.first_name} {lead.last_name}</div>
                            <span className={styles.stagePill} style={{ background: `${stageMeta!.color}22`, color: stageMeta!.color }}>
                                {stageMeta!.label}
                            </span>
                        </div>

                        <div className={styles.scoreCard}>
                            <div className={styles.scoreRing} style={{ background: `conic-gradient(${bandColor} ${lead.score * 3.6}deg, var(--surface-muted) 0deg)` }}>
                                <div style={{ width: 66, height: 66, borderRadius: '50%', background: 'var(--bg-raised)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                                    <span className={styles.scoreNum}>{lead.score}</span>
                                </div>
                            </div>
                            <span className={styles.scoreBand} style={{ color: bandColor }}>{lead.score_band} lead</span>
                        </div>

                        <div>
                            <div className={styles.sectionLabel}>Contact</div>
                            <div className={styles.infoList}>
                                <div className={styles.infoRow}><Phone size={12} /> {lead.phone || ''}</div>
                                <div className={styles.infoRow} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                                        <Mail size={12} style={{ flexShrink: 0 }} />
                                        {editingEmail ? (
                                            <input
                                                type="email"
                                                value={emailInput}
                                                onChange={e => setEmailInput(e.target.value)}
                                                autoFocus
                                                disabled={savingEmail}
                                                placeholder="lead@email.com"
                                                style={{
                                                    fontSize: 12, padding: '2px 6px', borderRadius: 4,
                                                    border: '1px solid var(--primary)', background: 'var(--bg-surface)',
                                                    color: 'var(--text-1)', width: '100%', outline: 'none',
                                                }}
                                                onKeyDown={e => {
                                                    if (e.key === 'Enter') handleSaveEmail();
                                                    if (e.key === 'Escape') setEditingEmail(false);
                                                }}
                                            />
                                        ) : (
                                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={lead.email}>
                                                {lead.email || ''}
                                            </span>
                                        )}
                                    </div>
                                    {editingEmail ? (
                                        <div style={{ display: 'flex', gap: 4, marginLeft: 6, flexShrink: 0 }}>
                                            <button
                                                onClick={handleSaveEmail}
                                                disabled={savingEmail}
                                                style={{ border: 'none', background: 'var(--primary)', color: '#fff', borderRadius: 4, padding: '2px 7px', fontSize: 10.5, fontWeight: 700, cursor: 'pointer' }}
                                            >
                                                {savingEmail ? '…' : 'Save'}
                                            </button>
                                            <button
                                                onClick={() => setEditingEmail(false)}
                                                style={{ border: 'none', background: 'rgba(107,114,128,0.15)', color: 'var(--text-3)', borderRadius: 4, padding: '2px 7px', fontSize: 10.5, cursor: 'pointer' }}
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            onClick={() => { setEmailInput(lead.email || ''); setEditingEmail(true); }}
                                            title="Update this email"
                                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: '2px 4px', color: 'var(--text-4)', display: 'flex', alignItems: 'center', borderRadius: 4 }}
                                        >
                                            <Pencil size={11} />
                                        </button>
                                    )}
                                </div>
                                <div className={styles.infoRow}><Tag size={12} /> {lead.preferred_channel}</div>
                                <div className={styles.infoRow}><Clock size={12} /> Added {parseApiDate(lead.created_at).toLocaleDateString()}</div>
                                {(lead.assigned_first_name || lead.assigned_last_name) && (
                                    <div className={styles.infoRow}><Zap size={12} /> {lead.assigned_first_name} {lead.assigned_last_name}</div>
                                )}
                            </div>
                        </div>

                        {lead.tags?.length > 0 && (
                            <div>
                                <div className={styles.sectionLabel}>Tags</div>
                                <div className={styles.tagRow}>
                                    {lead.tags.map(t => <span key={t} className={styles.tagPill}>{t}</span>)}
                                </div>
                            </div>
                        )}

                        <div>
                            <div className={styles.sectionLabel}>Quick Actions</div>
                            <div className={styles.quickActions}>
                                <button className={styles.quickActionBtn} onClick={() => setTab('notes')}>
                                    <StickyNote size={14} /> Add Note
                                </button>
                                <button className={styles.quickActionBtn} onClick={() => setTab('tasks')}>
                                    <ListTodo size={14} /> Add Task {lead.open_tasks_count > 0 && `(${lead.open_tasks_count} open)`}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* ── Center panel ── */}
                    <div className={`${styles.panel} ${styles.centerPanel}`}>
                        <div className={styles.tabRail}>
                            {(['timeline', 'conversations', 'calls', 'summary', 'notes', 'tasks'] as CenterTab[]).map(t => (
                                <button key={t} className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`} onClick={() => setTab(t)}>
                                    {t === 'timeline' ? 'Lead Journey' : t === 'summary' ? 'AI Summary' : t.charAt(0).toUpperCase() + t.slice(1)}
                                    {t === 'calls' && calls.length > 0 ? ` (${calls.length})` : ''}
                                </button>
                            ))}
                        </div>

                        {tab === 'timeline' && (
                            <div>
                                {days.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13, padding: '20px 0' }}>No activity yet for this lead.</div>}
                                {days.map(([dateStr, items], dayIdx) => (
                                    <div key={dateStr} className={styles.dayGroup}>
                                        <div className={styles.dayMarker}>
                                            <div className={styles.dayDot}>D{dayIdx + 1}</div>
                                            {dayIdx < days.length - 1 && <div className={styles.dayLine} />}
                                        </div>
                                        <div className={styles.dayContent}>
                                            <div className={styles.dayLabel}>{new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</div>
                                            {items.map((item: any, i: number) => (
                                                <TimelineEvent key={i} item={item} />
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'conversations' && (
                            <div>
                                {safetyStatus?.state === 'OPEN' ? (
                                    <div style={{
                                        background: 'rgba(239, 68, 68, 0.12)',
                                        border: '1px solid rgba(239, 68, 68, 0.3)',
                                        borderRadius: 8,
                                        padding: '10px 14px',
                                        marginBottom: 14,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'space-between',
                                        fontSize: 12,
                                        color: '#ef4444'
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <ShieldAlert size={16} />
                                            <span><strong>Outbound iMessage Paused:</strong> Safety Circuit Breaker active to protect your Apple account.</span>
                                        </div>
                                        <button
                                            onClick={resetCircuitBreaker}
                                            style={{
                                                background: '#ef4444',
                                                color: '#fff',
                                                border: 'none',
                                                borderRadius: 6,
                                                padding: '4px 10px',
                                                fontSize: 11,
                                                fontWeight: 600,
                                                cursor: 'pointer'
                                            }}>
                                            Resume Sending
                                        </button>
                                    </div>
                                ) : (
                                    <div style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 6,
                                        marginBottom: 12,
                                        fontSize: 11,
                                        color: '#10b981',
                                        padding: '4px 8px',
                                        background: 'rgba(16, 185, 129, 0.08)',
                                        borderRadius: 6,
                                        width: 'fit-content'
                                    }}>
                                        <ShieldCheck size={13} />
                                        <span>Humanoid Pacing Active (Anti-Ban Protection)</span>
                                    </div>
                                )}
                                {conversations.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>No conversations yet.</div>}
                                {conversations.map((conv: any) => {
                                    const isEmail = conv.channel === 'email';
                                    return (
                                        <div key={conv.id} style={{ marginBottom: 12 }}>
                                            <div className={styles.convCard} onClick={() => toggleConv(conv.id)} style={{
                                                borderColor: isEmail ? 'rgba(34, 197, 94, 0.3)' : undefined,
                                                background: isEmail ? 'rgba(34, 197, 94, 0.03)' : undefined,
                                            }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                    {isEmail ? (
                                                        <Mail size={15} color="#22c55e" />
                                                    ) : conv.channel === 'sms' ? (
                                                        <Smartphone size={15} />
                                                    ) : (
                                                        <MessageCircle size={15} />
                                                    )}
                                                    <span style={{ fontWeight: 700, fontSize: 13, textTransform: 'capitalize' }}>
                                                        {isEmail ? 'Email' : conv.channel}
                                                    </span>
                                                    {isEmail && (
                                                        <span style={{
                                                            fontSize: 10.5, fontWeight: 700, padding: '2px 8px', borderRadius: 12,
                                                            background: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', letterSpacing: '0.02em',
                                                        }}>
                                                            ✓ Email Sent OK
                                                        </span>
                                                    )}
                                                    <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-4)' }}>
                                                        {conv.last_message_at && parseApiDate(conv.last_message_at).toLocaleString()}
                                                    </span>
                                                </div>
                                                {conv.last_message && (
                                                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 6, lineHeight: 1.4 }}>
                                                        {isEmail && conv.last_message.startsWith('Subject:')
                                                            ? conv.last_message.split('\n')[0].replace('Subject:', '✉️ Subject:').trim()
                                                            : conv.last_message.slice(0, 120) + (conv.last_message.length > 120 ? '…' : '')}
                                                    </div>
                                                )}
                                            </div>

                                            {expandedConvId === conv.id && (
                                                isEmail ? (
                                                    <div className={styles.emailContainer}>
                                                        {threadMessages.length === 0 ? (
                                                            <div style={{ fontSize: 12, color: 'var(--text-4)', padding: 12 }}>Loading email...</div>
                                                        ) : threadMessages.map((m: any) => {
                                                            let subject = "Solution Proposal & Engineering Overview - AllZone Technologies";
                                                            let body = m.content;
                                                            if (m.content.startsWith("Subject:")) {
                                                                const parts = m.content.split("\n\n");
                                                                subject = parts[0].replace("Subject:", "").trim();
                                                                body = parts.slice(1).join("\n\n").trim();
                                                            }
                                                            body = body.replace(/\[Status:.*?\]/g, "").trim();

                                                            return (
                                                                <div key={m.id} className={styles.emailView}>
                                                                    <div className={styles.emailTopBar}>
                                                                        <div>
                                                                            <div className={styles.emailSubjectTitle}>{subject}</div>
                                                                            <div className={styles.emailMetaRow}>
                                                                                <span><strong>From:</strong> AllZone Technologies &lt;services@allzonetech.com&gt;</span>
                                                                                <span><strong>To:</strong> {lead.first_name} {lead.last_name} &lt;{lead.email}&gt;</span>
                                                                                {m.created_at && (
                                                                                    <span><strong>Sent:</strong> {parseApiDate(m.created_at).toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                        <span className={styles.emailDeliveredBadge}>
                                                                            <CheckCircle2 size={13} /> Email Sent OK
                                                                        </span>
                                                                    </div>
                                                                    <div className={styles.emailContentBody}>
                                                                        {body}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className={styles.thread}>
                                                        {threadMessages.length === 0 ? (
                                                            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>No messages.</div>
                                                        ) : threadMessages.map((m: any) => (
                                                            <div key={m.id} className={`${styles.bubble} ${m.role === 'user' ? styles.bubbleUser : styles.bubbleAgent}`} style={{
                                                                borderColor: m.status === 'failed' ? '#ef4444' : undefined,
                                                            }}>
                                                                <div>{m.content}</div>
                                                                {m.created_at && (
                                                                    <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 4, textAlign: m.role === 'user' ? 'left' : 'right' }}>
                                                                        {parseApiDate(m.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                                    </div>
                                                                )}
                                                                {m.status === 'failed' && (
                                                                    <div style={{
                                                                        marginTop: 6,
                                                                        padding: '6px 10px',
                                                                        borderRadius: 6,
                                                                        background: 'rgba(239, 68, 68, 0.12)',
                                                                        border: '1px solid rgba(239, 68, 68, 0.25)',
                                                                        fontSize: 11,
                                                                        color: '#ef4444'
                                                                    }}>
                                                                        <div style={{ fontWeight: 600, marginBottom: 2 }}>
                                                                            ⚠️ Delivery Failed: {formatDeliveryError(m.error_reason)}
                                                                        </div>
                                                                        <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                                                                            <button
                                                                                onClick={() => retryLeadMessage(conv.id, m.id, 'sms')}
                                                                                disabled={retryingMsgId === m.id}
                                                                                style={{
                                                                                    background: '#ef4444',
                                                                                    color: '#fff',
                                                                                    border: 'none',
                                                                                    borderRadius: 4,
                                                                                    padding: '2px 8px',
                                                                                    fontSize: 10.5,
                                                                                    fontWeight: 600,
                                                                                    cursor: 'pointer'
                                                                                }}>
                                                                                {retryingMsgId === m.id ? 'Retrying...' : 'Retry Send'}
                                                                            </button>
                                                                        </div>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        ))}
                                                    </div>
                                                )
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'calls' && (
                            <div>
                                {calls.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>No calls yet for this lead.</div>}
                                {calls.map((c: any, i: number) => {
                                    const d = c.data;
                                    return (
                                        <div key={i} className={styles.convCard} style={{ marginBottom: 10 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                <Phone size={14} />
                                                <span style={{ fontWeight: 700, fontSize: 12.5 }}>
                                                    Voice Call {d.outcome ? `(${d.outcome})` : ''}
                                                </span>
                                                <span style={{ marginLeft: 'auto', fontSize: 10.5, color: 'var(--text-4)' }}>
                                                    {parseApiDate(c.timestamp).toLocaleString()}
                                                </span>
                                            </div>
                                            {d.duration_seconds != null && (
                                                <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>
                                                    Duration: {Math.floor(d.duration_seconds / 60)}m {d.duration_seconds % 60}s
                                                </div>
                                            )}
                                            {d.summary && (
                                                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 6 }}>{d.summary}</div>
                                            )}
                                            {!d.summary && !d.recording_url && !d.transcript && (
                                                <div style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 6, fontStyle: 'italic' }}>
                                                    No recording or summary yet. This call may still be in progress or didn&apos;t complete.
                                                </div>
                                            )}
                                            {d.recording_url && (
                                                <audio controls style={{ width: '100%', height: 30, marginTop: 8 }}>
                                                    <source src={`/api/calls/${d.call_id}/recording`} />
                                                </audio>
                                            )}
                                            {d.transcript && (
                                                <div style={{ marginTop: 8 }}>
                                                    <button
                                                        onClick={() => setExpandedCallIdx(expandedCallIdx === i ? null : i)}
                                                        style={{
                                                            fontSize: 11, fontWeight: 600, color: 'var(--primary-text)',
                                                            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                                                        }}
                                                    >
                                                        {expandedCallIdx === i ? 'Hide Transcript' : 'View Transcript'}
                                                    </button>
                                                    {expandedCallIdx === i && (
                                                        <div style={{
                                                            marginTop: 6, padding: 10, borderRadius: 8,
                                                            background: 'var(--bg-2)', maxHeight: 300, overflowY: 'auto',
                                                        }}>
                                                            {d.transcript.split('\n').filter((l: string) => l.trim()).map((line: string, li: number) => (
                                                                <div key={li} style={{ fontSize: 11.5, lineHeight: 1.6, color: 'var(--text-2)' }}>
                                                                    {line}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {tab === 'summary' && (
                            <div>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                                    <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-2)' }}>AI Summary</span>
                                    <button
                                        onClick={generateSummary}
                                        disabled={summarizing}
                                        className={styles.quickActionBtn}
                                        style={{ opacity: summarizing ? 0.5 : 1, cursor: summarizing ? 'default' : 'pointer' }}
                                    >
                                        {summarizing ? 'Generating…' : lead.ai_summary ? 'Regenerate' : 'Generate'}
                                    </button>
                                </div>
                                {lead.ai_summary ? (
                                    <div className={styles.convCard}>
                                        <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>{lead.ai_summary}</div>
                                        {lead.ai_summary_updated_at && (
                                            <div style={{ fontSize: 10.5, color: 'var(--text-4)', marginTop: 8 }}>
                                                Updated {parseApiDate(lead.ai_summary_updated_at).toLocaleString()}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div style={{ color: 'var(--text-4)', fontSize: 13 }}>
                                        No summary yet. Click Generate to summarize this lead&apos;s SMS + call history.
                                    </div>
                                )}
                                {summaryError && (
                                    <div style={{ fontSize: 12, color: '#f87171', marginTop: 8 }}>{summaryError}</div>
                                )}
                            </div>
                        )}

                        {tab === 'notes' && (
                            <div>
                                <div className={styles.addBox}>
                                    <input value={newNote} onChange={e => setNewNote(e.target.value)} placeholder="Add a note…"
                                        onKeyDown={e => e.key === 'Enter' && addNote()} />
                                    <button className={styles.addBtn} onClick={addNote}><Plus size={13} /></button>
                                </div>
                                {notes.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>No notes yet.</div>}
                                {notes.map((n: any) => (
                                    <div key={n.id} className={styles.noteCard}>
                                        <div>{n.body}</div>
                                        <div style={{ fontSize: 10.5, color: 'var(--text-4)', marginTop: 6 }}>
                                            {n.first_name} {n.last_name} · {parseApiDate(n.created_at).toLocaleString()}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'tasks' && (
                            <div>
                                <div className={styles.addBox}>
                                    <input value={newTask} onChange={e => setNewTask(e.target.value)} placeholder="Add a task…"
                                        onKeyDown={e => e.key === 'Enter' && addTask()} />
                                    <button className={styles.addBtn} onClick={addTask}><Plus size={13} /></button>
                                </div>
                                {tasks.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>No tasks yet.</div>}
                                {tasks.map((t: any) => (
                                    <div key={t.id} className={styles.taskCard} style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: t.status === 'done' ? 0.5 : 1 }}>
                                        <button onClick={() => toggleTaskDone(t.id, t.status)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.status === 'done' ? 'var(--status-success)' : 'var(--text-4)' }}>
                                            {t.status === 'done' ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                                        </button>
                                        <span style={{ textDecoration: t.status === 'done' ? 'line-through' : 'none', flex: 1 }}>{t.title}</span>
                                        {t.due_at && <span style={{ fontSize: 10.5, color: 'var(--text-4)' }}>{parseApiDate(t.due_at).toLocaleDateString()}</span>}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* ── Right panel ── */}
                    <div className={`${styles.panel} ${styles.rightPanel}`}>
                        <div>
                            <div className={styles.sectionLabel}>Automation</div>
                            {lead.active_enrollment ? (
                                <div className={styles.enrollmentCard}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <Workflow size={13} color="var(--primary-text)" />
                                        <span style={{ fontSize: 12.5, fontWeight: 700 }}>{lead.active_enrollment.workflow_name}</span>
                                    </div>
                                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4, textTransform: 'capitalize' }}>{lead.active_enrollment.status}</div>
                                    {(() => {
                                        const { node_started_at, next_action_at } = lead.active_enrollment;
                                        if (!node_started_at || !next_action_at) {
                                            return (
                                                <div className={styles.progressBar}>
                                                    <div className={styles.progressFill} style={{ width: '100%' }} />
                                                </div>
                                            );
                                        }
                                        const start = parseApiDate(node_started_at).getTime();
                                        const end = parseApiDate(next_action_at).getTime();
                                        const total = Math.max(end - start, 1);
                                        const elapsed = Math.min(Math.max(now - start, 0), total);
                                        const pct = (elapsed / total) * 100;
                                        return (
                                            <>
                                                <div className={styles.progressBar}>
                                                    <div className={styles.progressFill} style={{ width: `${pct}%` }} />
                                                </div>
                                                <div className={styles.countdownText}>
                                                    Next step in {formatCountdown(end - now)}
                                                </div>
                                            </>
                                        );
                                    })()}
                                    <button className={styles.quickActionBtn} style={{ marginTop: 10, width: '100%', justifyContent: 'center' }}
                                        onClick={() => router.push(`/automation/${lead.active_enrollment!.workflow_id}`)}>
                                        View workflow
                                    </button>
                                </div>
                            ) : (
                                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>No active automation for this lead.</div>
                            )}
                        </div>

                        <div>
                            <div className={styles.sectionLabel}>Appointments</div>
                            {appointments.length === 0 ? (
                                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>None scheduled.</div>
                            ) : appointments.map((a: any) => (
                                <div key={a.id} className={styles.apptCard}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <Calendar size={12} />
                                        <span style={{ fontWeight: 700 }}>{parseApiDate(a.start_time).toLocaleDateString()}</span>
                                    </div>
                                    <div style={{ color: 'var(--text-4)', marginTop: 3 }}>
                                        {parseApiDate(a.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {a.status}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function TimelineEvent({ item }: { item: any }) {
    const time = parseApiDate(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const d = item.data;

    if (item.type === 'message') {
        const isEmail = d.channel === 'email';
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: isEmail ? 'rgba(34, 197, 94, 0.12)' : 'rgba(212, 169, 79,0.12)' }}>
                        {isEmail ? <Mail size={11} color="#22c55e" /> : <MessageCircle size={11} color="#d4a94f" />}
                    </span>
                    <span className={styles.eventTitle}>
                        {d.role === 'user' ? 'Lead replied' : isEmail ? 'Email sent OK' : 'Message sent'} ({d.channel})
                    </span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
                <div className={styles.eventBody} style={{ whiteSpace: 'pre-wrap' }}>{d.content}</div>
            </div>
        );
    }
    if (item.type === 'call') {
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: 'rgba(245,158,11,0.12)' }}><Phone size={11} color="#f59e0b" /></span>
                    <span className={styles.eventTitle}>Voice Call {d.outcome ? `(${d.outcome})` : ''}</span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
                {d.summary && <div className={styles.eventBody}>{d.summary}</div>}
                {d.recording_url && <audio controls style={{ width: '100%', height: 30, marginTop: 6 }}><source src={`/api/calls/${d.call_id}/recording`} /></audio>}
            </div>
        );
    }
    if (item.type === 'appointment') {
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: 'rgba(96,165,250,0.12)' }}><Calendar size={11} color="#60a5fa" /></span>
                    <span className={styles.eventTitle}>Appointment {d.status}</span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
            </div>
        );
    }
    if (item.type === 'status_change') {
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: 'rgba(99,102,241,0.12)' }}><Zap size={11} color="#818cf8" /></span>
                    <span className={styles.eventTitle}>{d.from_stage} → {d.to_stage}</span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
                <div className={styles.eventBody}>{d.event}</div>
            </div>
        );
    }
    if (item.type === 'workflow_node_run') {
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: 'rgba(52,211,153,0.12)' }}><Workflow size={11} color="#34d399" /></span>
                    <span className={styles.eventTitle}>{d.workflow_name}: {d.node_type} ({d.status})</span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
            </div>
        );
    }
    if (item.type === 'note') {
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: 'rgba(192,132,252,0.12)' }}><StickyNote size={11} color="#c084fc" /></span>
                    <span className={styles.eventTitle}>Note added</span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
                <div className={styles.eventBody}>{d.body}</div>
            </div>
        );
    }
    if (item.type === 'task') {
        return (
            <div className={styles.eventCard}>
                <div className={styles.eventTop}>
                    <span className={styles.eventIcon} style={{ background: 'rgba(248,113,113,0.12)' }}><ListTodo size={11} color="#f87171" /></span>
                    <span className={styles.eventTitle}>Task: {d.title}</span>
                    <span className={styles.eventTime}>{time}</span>
                </div>
            </div>
        );
    }
    return null;
}
