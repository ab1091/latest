'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
    MessageCircle, Send, ToggleLeft, ToggleRight,
    Bot, User, RefreshCw, Phone, PhoneOff, ShieldAlert, ShieldCheck
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { useSearchParams } from 'next/navigation';
import { DateRangeFilter, DEFAULT_DATE_RANGE, inDateRange, type DateRangeValue } from '@/components/DateRangeFilter/DateRangeFilter';
import styles from '@/app/conversations/conversations.module.css';

const POLL_MS  = 2500;

const STATUS_OPTIONS = ['new','contacted','qualified','converted','dead'];
const STATUS_COLORS: Record<string, string> = {
    new:       styles.sNew,
    contacted: styles.sContacted,
    qualified: styles.sQualified,
    converted: styles.sConverted,
    dead:      styles.sDead,
};

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

interface Conversation {
    id: string; lead_id: string; agent_id: string | null;
    channel: string; ai_active: boolean;
    first_name: string; last_name: string; phone: string;
    tags: string[]; agent_name: string | null;
    last_message: string | null; last_message_at: string | null;
    created_at?: string;
    has_reply?: boolean;
}
interface Message {
    id: string; conversation_id: string;
    role: 'user' | 'agent' | 'human' | 'draft'; content: string; created_at: string;
    status?: 'delivered' | 'sent' | 'failed' | 'pending';
    error_reason?: string | null;
    channel?: string;
}
interface LeadDetail {
    id: string; status: string; email: string; source: string; notes: string;
}

export function ConversationsInner({ embedded = false }: { embedded?: boolean } = {}) {
    const { accessToken } = useAuth();
    const searchParams    = useSearchParams();

    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [channelFilter, setChannelFilter] = useState<string>('all');
    // ?engagement=replied drives the initial state — lets the dashboard's
    // "Conversations"/"Replied to Text" tiles link straight to only the
    // threads where the lead actually replied, not every outbound send.
    const [repliedOnly, setRepliedOnly] = useState<boolean>(searchParams.get('engagement') === 'replied');
    const [convSearch, setConvSearch] = useState('');
    const [convDateRange, setConvDateRange] = useState<DateRangeValue>(DEFAULT_DATE_RANGE);
    const [activeConv,    setActiveConv]    = useState<Conversation | null>(null);
    const [messages,      setMessages]      = useState<Message[]>([]);
    const [leadDetail,    setLeadDetail]    = useState<LeadDetail | null>(null);
    const [msgLoading,    setMsgLoading]    = useState(false);
    const [loading,       setLoading]       = useState(false);
    const [input,         setInput]         = useState('');
    const [sending,       setSending]       = useState(false);
    const [simulateLead,  setSimulateLead]  = useState(false);
    const [statusUpdating, setStatusUpdating] = useState(false);
    const [calling,       setCalling]       = useState(false);
    const [callActive,    setCallActive]    = useState(false);

    const bottomRef      = useRef<HTMLDivElement>(null);
    const activeConvRef  = useRef<Conversation | null>(null);
    const msgCountRef    = useRef(0);
    const pollRef        = useRef<ReturnType<typeof setInterval> | null>(null);
    const initialLoad    = useRef(true);
    const callIdRef      = useRef<string | null>(null);

    const h = useCallback(() => ({ Authorization: `Bearer ${accessToken}` }), [accessToken]);

    // ── Load conversations list ──────────────────────────────────────────────
    const loadConversations = useCallback(async (quiet = false) => {
        if (!accessToken) return;
        if (!quiet) setLoading(true);
        try {
            const res = await fetch(`/api/conversations`, { headers: h() });
            const d   = await res.json();
            if (d.success) setConversations(d.data.conversations);
        } catch {}
        if (!quiet) setLoading(false);
    }, [accessToken, h]);

    useEffect(() => {
        loadConversations();
        const convListTimer = setInterval(() => loadConversations(true), 3000);
        return () => clearInterval(convListTimer);
    }, [loadConversations]);

    // ── Auto-scroll to bottom ────────────────────────────────────────────────
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // ── Poll messages for active conversation ────────────────────────────────
    const pollMessages = useCallback(async () => {
        const conv = activeConvRef.current;
        if (!conv || !accessToken) return;
        try {
            const res = await fetch(`/api/conversations/${conv.id}/messages`, { headers: h() });
            const d   = await res.json();
            if (d.success) {
                const incoming: Message[] = d.data.messages;
                if (incoming.length !== msgCountRef.current) {
                    msgCountRef.current = incoming.length;
                    setMessages(incoming);
                    loadConversations(true);
                }
            }
        } catch {}
    }, [accessToken, h, loadConversations]);

    // Start/stop polling when active conversation changes
    useEffect(() => {
        activeConvRef.current = activeConv;
        if (pollRef.current) clearInterval(pollRef.current);
        if (activeConv) {
            pollRef.current = setInterval(pollMessages, POLL_MS);
        }
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [activeConv, pollMessages]);

    // ── Load lead detail ─────────────────────────────────────────────────────
    const loadLeadDetail = useCallback(async (leadId: string) => {
        try {
            const res = await fetch(`/api/leads/${leadId}`, { headers: h() });
            const d   = await res.json();
            if (d.success) setLeadDetail(d.data.lead);
        } catch {}
    }, [h]);

    // ── Select conversation ──────────────────────────────────────────────────
    const selectConv = useCallback(async (conv: Conversation) => {
        setActiveConv(conv);
        setMsgLoading(true);
        msgCountRef.current = 0;
        try {
            const res = await fetch(`/api/conversations/${conv.id}/messages`, { headers: h() });
            const d   = await res.json();
            if (d.success) {
                setMessages(d.data.messages);
                msgCountRef.current = d.data.messages.length;
            }
        } catch {}
        setMsgLoading(false);
        loadLeadDetail(conv.lead_id);
    }, [h, loadLeadDetail]);

    // Sync repliedOnly filter with query param on route change
    useEffect(() => {
        const eng = searchParams.get('engagement');
        if (eng === 'replied') {
            setRepliedOnly(true);
        } else if (eng === 'all') {
            setRepliedOnly(false);
        }
    }, [searchParams]);

    // Auto-select conv from URL param OR first relevant conversation on load
    useEffect(() => {
        if (conversations.length === 0) return;
        const convId = searchParams.get('conv');
        const isRepliedOnly = repliedOnly || searchParams.get('engagement') === 'replied';

        if (initialLoad.current) {
            initialLoad.current = false;
            let target: Conversation | undefined;
            if (convId) {
                target = conversations.find(c => c.id === convId);
            }
            if (!target && isRepliedOnly) {
                target = conversations.find(c => c.has_reply);
            }
            if (!target) {
                target = conversations[0];
            }
            if (target) selectConv(target);
        } else if (convId && activeConv?.id !== convId) {
            const target = conversations.find(c => c.id === convId);
            if (target) selectConv(target);
        }
    }, [conversations, searchParams, selectConv, repliedOnly, activeConv]);

    // If viewing 'Replied only' and currently active conversation has no reply, switch to one with replies
    useEffect(() => {
        if (repliedOnly && activeConv && !activeConv.has_reply && conversations.length > 0) {
            const repliedTarget = conversations.find(c => c.has_reply);
            if (repliedTarget && repliedTarget.id !== activeConv.id) {
                selectConv(repliedTarget);
            }
        }
    }, [repliedOnly, activeConv, conversations, selectConv]);

    // ── Send message ─────────────────────────────────────────────────────────
    const sendMessage = async () => {
        if (!input.trim() || !activeConv) return;
        setSending(true);
        const content = input.trim();
        setInput('');

        if (simulateLead) {
            // Testing helper — runs the exact same pipeline a real inbound text
            // does (AI reply, stage transitions, decline/qualify/quote checks),
            // instead of the normal box below which always sends AS the business.
            // The AI's reply lands via the real pipeline too, so just re-fetch
            // rather than optimistically appending a single message.
            try {
                await fetch(`/api/sms/simulate-inbound`, {
                    method: 'POST',
                    headers: { ...h(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ conversation_id: activeConv.id, message: content }),
                });
                await pollMessages();
            } catch {}
        } else {
            // Send outbound message (delivered via BlueBubbles iMessage)
            try {
                const res = await fetch(`/api/conversations/${activeConv.id}/messages`, {
                    method: 'POST',
                    headers: { ...h(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content, role: 'human' }),
                });
                const d = await res.json();
                if (d.success) {
                    setMessages(m => [...m, d.data.message]);
                    msgCountRef.current += 1;
                }
            } catch {}
        }
        setSending(false);
    };

    // ── Approve draft message ────────────────────────────────────────────────
    const approveDraft = async (msgId: string) => {
        if (!activeConv) return;
        try {
            const res = await fetch(`/api/conversations/${activeConv.id}/messages/${msgId}/approve`, {
                method: 'POST',
                headers: h(),
            });
            const d = await res.json();
            if (d.success) {
                setMessages(ms => ms.map(m => m.id === msgId ? { ...m, role: 'agent' } : m));
                loadConversations(true);
            } else {
                alert(d.detail || 'Approval failed');
            }
        } catch {
            alert('Failed to approve message');
        }
    };

    // ── Toggle AI ────────────────────────────────────────────────────────────
    const toggleAI = async () => {
        if (!activeConv) return;
        const res = await fetch(`/api/conversations/${activeConv.id}/toggle-ai`, {
            method: 'PATCH', headers: h(),
        });
        const d = await res.json();
        if (d.success) {
            const updated = { ...activeConv, ai_active: d.data.ai_active };
            setActiveConv(updated);
            setConversations(cs => cs.map(c => c.id === activeConv.id ? { ...c, ai_active: d.data.ai_active } : c));
        }
    };

    // ── Safety & Circuit Breaker ─────────────────────────────────────────────
    const [safetyStatus, setSafetyStatus] = useState<any>(null);
    const [retryingMsgId, setRetryingMsgId] = useState<string | null>(null);

    const fetchSafetyStatus = useCallback(async () => {
        try {
            const res = await fetch('/api/sms/safety-status', { headers: h() });
            const d = await res.json();
            if (d.success) setSafetyStatus(d.data);
        } catch {}
    }, [h]);

    useEffect(() => {
        fetchSafetyStatus();
        const timer = setInterval(fetchSafetyStatus, 15000);
        return () => clearInterval(timer);
    }, [fetchSafetyStatus]);

    const resetCircuitBreaker = async () => {
        try {
            const res = await fetch('/api/sms/reset-circuit-breaker', {
                method: 'POST',
                headers: h(),
            });
            const d = await res.json();
            if (d.success) {
                await fetchSafetyStatus();
                alert('Safety Circuit Breaker reset. Normal sending resumed.');
            }
        } catch {
            alert('Failed to reset circuit breaker');
        }
    };

    const retryMessage = async (msgId: string, channel: string = 'sms') => {
        if (!activeConv) return;
        setRetryingMsgId(msgId);
        try {
            const res = await fetch(`/api/conversations/${activeConv.id}/messages/${msgId}/retry`, {
                method: 'POST',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel })
            });
            const d = await res.json();
            if (d.data?.message) {
                setMessages(ms => ms.map(m => m.id === msgId ? d.data.message : m));
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

    // ── Update lead status ───────────────────────────────────────────────────
    const updateStatus = async (status: string) => {
        if (!leadDetail) return;
        setStatusUpdating(true);
        try {
            const res = await fetch(`/api/leads/${leadDetail.id}`, {
                method: 'PATCH',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ status }),
            });
            const d = await res.json();
            if (d.success) setLeadDetail(d.data.lead);
        } catch {}
        setStatusUpdating(false);
    };

    // ── Initiate outbound call ───────────────────────────────────────────────
    const initiateCall = async () => {
        if (!activeConv || !leadDetail || calling || callActive) return;
        setCalling(true);
        try {
            const res = await fetch(`/api/calls/outbound`, {
                method: 'POST',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_id: leadDetail.id, conv_id: activeConv.id }),
            });
            const d = await res.json();
            if (d.success) {
                callIdRef.current = d.data.call_id;
                setCallActive(true);
            } else {
                alert(d.detail || 'Call failed');
            }
        } catch {
            alert('Failed to initiate call');
        }
        setCalling(false);
    };

    // ── End active call ──────────────────────────────────────────────────────
    const endCall = () => {
        // Only clear UI state — do NOT delete the Vapi call via API.
        // Deleting via API prevents end-of-call-report from firing,
        // which means no transcript and no appointment is saved.
        // The call ends naturally when the lead hangs up their phone.
        setCallActive(false);
        callIdRef.current = null;
    };

    const initials = (c: Conversation) =>
        `${c.first_name?.[0] || ''}${c.last_name?.[0] || ''}`.toUpperCase() || '?';

    const visibleConversations = conversations.filter(c => {
        if (channelFilter !== 'all' && c.channel !== channelFilter) return false;
        if (repliedOnly && !c.has_reply) return false;
        if (!inDateRange(c.created_at, convDateRange)) return false;
        const q = convSearch.trim().toLowerCase();
        if (!q) return true;
        const haystack = `${c.first_name || ''} ${c.last_name || ''} ${c.phone || ''}`.toLowerCase();
        return haystack.includes(q);
    });

    const content = (
        <>
                {/* ── Left: conversation list ── */}
                <div className={styles.convList}>
                    <div className={styles.convListHeader}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                            <MessageCircle size={16} />
                            <span>Conversations</span>
                            <span style={{
                                fontSize: 11,
                                fontWeight: 700,
                                padding: '1px 6px',
                                borderRadius: 999,
                                background: 'var(--primary-subtle)',
                                color: 'var(--primary)',
                            }}>
                                {conversations.length}
                            </span>
                        </div>
                        <button className={styles.refreshListBtn} onClick={() => loadConversations()}>
                            <RefreshCw size={13} />
                        </button>
                    </div>

                    {/* Channel filter tabs */}
                    <div style={{ display: 'flex', gap: 4, padding: '8px 10px', borderBottom: '1px solid var(--border-default)' }}>
                        {[
                            { key: 'all',      label: 'All',      count: conversations.length },
                            { key: 'sms',      label: '💬 SMS',   count: conversations.filter(c => c.channel === 'sms').length },
                            { key: 'email',    label: '✉️ Email', count: conversations.filter(c => c.channel === 'email').length },
                            { key: 'whatsapp', label: '🟢 WA',    count: conversations.filter(c => c.channel === 'whatsapp').length },
                            { key: 'voice',    label: '📞 Calls', count: conversations.filter(c => c.channel === 'voice').length },
                        ].map(f => (
                            <button key={f.key} onClick={() => setChannelFilter(f.key)} style={{
                                flex: 1, padding: '5px 3px', borderRadius: 7, border: 'none',
                                fontSize: 10.5, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
                                background: channelFilter === f.key ? 'var(--primary)' : 'rgba(107,114,128,0.08)',
                                color: channelFilter === f.key ? '#fff' : 'var(--text-3)',
                                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 1,
                            }}>
                                <span>{f.label}</span>
                                <span style={{ opacity: 0.8, fontSize: 9.5 }}>{f.count}</span>
                            </button>
                        ))}
                    </div>

                    {/* Replied-only toggle */}
                    <div style={{ padding: '0 10px 8px' }}>
                        <button onClick={() => setRepliedOnly(v => !v)} style={{
                            width: '100%', padding: '6px 8px', borderRadius: 7, border: 'none',
                            fontSize: 11, fontWeight: 600, cursor: 'pointer', transition: 'all 0.15s',
                            background: repliedOnly ? 'var(--primary)' : 'rgba(107,114,128,0.08)',
                            color: repliedOnly ? '#fff' : 'var(--text-3)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                        }}>
                            <span>{repliedOnly ? '✓ Replied only' : 'Show replied only'}</span>
                            <span style={{
                                padding: '1px 6px',
                                borderRadius: 999,
                                fontSize: 10,
                                fontWeight: 700,
                                background: repliedOnly ? 'rgba(0,0,0,0.2)' : 'rgba(107,114,128,0.18)',
                                color: repliedOnly ? '#fff' : 'var(--text-2)',
                            }}>
                                {conversations.filter(c => c.has_reply).length}
                            </span>
                        </button>
                    </div>

                    {/* Name search + date filter */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 10px', borderBottom: '1px solid var(--border-default)' }}>
                        <div style={{ position: 'relative' }}>
                            <input
                                value={convSearch}
                                onChange={e => setConvSearch(e.target.value)}
                                placeholder="Search by name or phone..."
                                style={{
                                    padding: '6px 10px', borderRadius: 7, border: '1px solid var(--border-default)',
                                    background: 'var(--bg-card)', color: 'var(--text-1)', fontSize: 12.5, width: '100%',
                                    boxSizing: 'border-box',
                                }}
                            />
                            {convSearch.trim() && (
                                <span style={{
                                    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                                    fontSize: 10.5, color: 'var(--text-4)', background: 'var(--bg-surface)',
                                    padding: '1px 5px', borderRadius: 4,
                                }}>
                                    {visibleConversations.length} found
                                </span>
                            )}
                        </div>
                        <DateRangeFilter value={convDateRange} onChange={setConvDateRange} />
                    </div>

                    {loading && <div className={styles.emptyMsg}>Loading...</div>}
                    {!loading && conversations.length === 0 && (
                        <div className={styles.emptyMsg}>No conversations yet.<br />Add a lead to start an iMessage conversation.</div>
                    )}
                    {!loading && conversations.length > 0 && visibleConversations.length === 0 && (
                        <div className={styles.emptyMsg}>No conversations match this filter.</div>
                    )}
                    {visibleConversations.map(conv => (
                        <div key={conv.id}
                            className={`${styles.convItem} ${activeConv?.id === conv.id ? styles.convItemActive : ''}`}
                            onClick={() => selectConv(conv)}>
                            <div className={styles.convAvatar}>{initials(conv)}</div>
                            <div className={styles.convMeta}>
                                <div className={styles.convName}>{conv.first_name} {conv.last_name}</div>
                                <div className={styles.convLast}>
                                    {conv.last_message
                                        ? conv.last_message.slice(0, 35) + (conv.last_message.length > 35 ? '…' : '')
                                        : conv.phone || '-'}
                                </div>
                            </div>
                            <div className={styles.convRight}>
                                {conv.ai_active && <Bot size={12} className={styles.aiBadge} />}
                                <span className={styles.channelDot} title={conv.channel}>
                                    {conv.channel === 'whatsapp' ? '🟢' : conv.channel === 'sms' ? '💬' : conv.channel === 'email' ? '✉️' : conv.channel === 'voice' ? '📞' : '🌐'}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── Center: chat area ── */}
                <div className={styles.chatArea}>
                    {!activeConv ? (
                        <div className={styles.noConv}>
                            <MessageCircle size={40} strokeWidth={1.2} />
                            <p>Select a conversation</p>
                        </div>
                    ) : (
                        <>
                            {safetyStatus?.state === 'OPEN' && (
                                <div style={{
                                    background: 'rgba(239, 68, 68, 0.12)',
                                    borderBottom: '1px solid rgba(239, 68, 68, 0.25)',
                                    padding: '8px 16px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    fontSize: 12,
                                    color: '#ef4444',
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <ShieldAlert size={16} />
                                        <span><strong>Outbound iMessage Paused:</strong> Circuit Breaker active to protect your Apple account.</span>
                                    </div>
                                    <button
                                        onClick={resetCircuitBreaker}
                                        style={{
                                            background: '#ef4444',
                                            color: '#fff',
                                            border: 'none',
                                            borderRadius: 6,
                                            padding: '3px 10px',
                                            fontSize: 11,
                                            fontWeight: 600,
                                            cursor: 'pointer'
                                        }}>
                                        Resume Sending
                                    </button>
                                </div>
                            )}
                            {/* Header */}
                            <div className={styles.chatHeader}>
                                <div className={styles.chatContactInfo}>
                                    <div className={styles.chatAvatar}>{initials(activeConv)}</div>
                                    <div>
                                        <div className={styles.chatName}>
                                            {activeConv.first_name} {activeConv.last_name}
                                        </div>
                                        <div className={styles.chatPhone}>
                                            {activeConv.phone}
                                            <span className={styles.channelBadge}>
                                                {activeConv.channel === 'sms' ? '💬 SMS' : activeConv.channel === 'whatsapp' ? '🟢 WHATSAPP' : activeConv.channel === 'email' ? '✉️ EMAIL' : activeConv.channel?.toUpperCase()}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className={styles.chatHeaderRight}>
                                    <span style={{ fontSize: 11, color: '#10b981', display: 'flex', alignItems: 'center', gap: 4, marginRight: 6 }}>
                                        <ShieldCheck size={13} /> Protected
                                    </span>
                                    {activeConv.agent_name && (
                                        <span className={styles.agentLabel}>
                                            <Bot size={13} /> {activeConv.agent_name}
                                        </span>
                                    )}
                                    <button
                                        className={`${styles.callBtn} ${callActive ? styles.callBtnActive : ''}`}
                                        onClick={callActive ? endCall : initiateCall}
                                        disabled={calling || !leadDetail?.id}
                                        title={callActive ? 'Click to end call' : 'Call this lead'}>
                                        {callActive
                                            ? <><PhoneOff size={14} /><span>End Call</span></>
                                            : <><Phone size={14} /><span>{calling ? 'Calling…' : 'Call'}</span></>}
                                    </button>
                                    <button className={styles.aiToggle} onClick={toggleAI}>
                                        {activeConv.ai_active
                                            ? <><ToggleRight size={22} color="var(--primary)" /><span className={styles.aiOn}>AI Active</span></>
                                            : <><ToggleLeft  size={22} color="var(--text-4)"  /><span className={styles.aiOff}>AI Paused</span></>}
                                    </button>
                                </div>
                            </div>

                            {/* ── VOICE CALL view ── */}
                            {activeConv.channel === 'voice' ? (
                                <div className={styles.messageArea}>
                                    {msgLoading ? (
                                        <div className={styles.emptyMsg}>Loading...</div>
                                    ) : messages.length === 0 ? (
                                        <div className={styles.emptyMsg}>No call records yet.</div>
                                    ) : messages.map(msg => (
                                        <div key={msg.id} style={{
                                            margin: '12px 20px',
                                            padding: '16px 20px',
                                            borderRadius: 14,
                                            background: 'var(--bg-card)',
                                            border: '1px solid var(--border-default)',
                                            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                                        }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                                                <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(245,158,11,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                    <Phone size={16} color="#f59e0b" />
                                                </div>
                                                <div>
                                                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-1)' }}>Voice Call</div>
                                                    <div style={{ fontSize: 11, color: 'var(--text-4)' }}>
                                                        {new Date(msg.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                    </div>
                                                </div>
                                            </div>
                                            <div style={{ fontSize: 13, color: 'var(--text-2)', whiteSpace: 'pre-line', lineHeight: 1.6 }}>
                                                {msg.content}
                                            </div>
                                        </div>
                                    ))}
                                    <div ref={bottomRef} />
                                </div>
                            ) : (
                            <>
                            {/* ── SMS / WhatsApp messages ── */}
                            <div className={styles.messageArea}>
                                {msgLoading && <div className={styles.emptyMsg}>Loading messages...</div>}
                                {!msgLoading && messages.length === 0 && (
                                    <div className={styles.emptyMsg}>No messages yet.</div>
                                )}
                                {messages.map(msg => (
                                    <div key={msg.id}
                                        className={`${styles.bubble} ${
                                            msg.role === 'draft'  ? styles.bubbleDraft  :
                                            msg.role === 'human'  ? styles.bubbleHuman  :
                                            msg.role === 'agent'  ? styles.bubbleAgent  :
                                            styles.bubbleUser}`}>
                                        <div className={styles.bubbleIcon}>
                                            {msg.role === 'human' ? <User size={12} /> : <Bot size={12} />}
                                        </div>
                                        <div className={styles.bubbleContent}>
                                            {msg.role === 'draft' && (
                                                <div className={styles.draftLabel}>⏳ Draft (awaiting approval)</div>
                                            )}
                                            <p>{msg.content}</p>
                                            {msg.status === 'failed' && (
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
                                                        ⚠️ Delivery Failed: {formatDeliveryError(msg.error_reason)}
                                                    </div>
                                                    <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                                                        <button
                                                            onClick={() => retryMessage(msg.id, 'sms')}
                                                            disabled={retryingMsgId === msg.id}
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
                                                            {retryingMsgId === msg.id ? 'Retrying...' : 'Retry Send'}
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                            <div className={styles.bubbleFooter}>
                                                <span className={styles.bubbleTime}>
                                                    {new Date(msg.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                                {msg.role === 'draft' && (
                                                    <button
                                                        className={styles.approveBtn}
                                                        onClick={() => approveDraft(msg.id)}>
                                                        ✓ Approve &amp; Send
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                                <div ref={bottomRef} />
                            </div>

                            {/* Send-as toggle — lets staff simulate what the LEAD would say for
                                testing, instead of it always going out as the business. */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px 0' }}>
                                <button
                                    onClick={() => setSimulateLead(v => !v)}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: 5,
                                        padding: '3px 10px', borderRadius: 20, cursor: 'pointer',
                                        fontSize: 11.5, fontWeight: 600,
                                        border: `1px solid ${simulateLead ? 'var(--primary)' : 'var(--border-default)'}`,
                                        background: simulateLead ? 'var(--primary-subtle, rgba(99,102,241,0.12))' : 'transparent',
                                        color: simulateLead ? 'var(--primary)' : 'var(--text-4)',
                                    }}
                                    title="When on, your message is treated as if the LEAD sent it, which triggers a real AI reply. When off, you're messaging as the business."
                                >
                                    {simulateLead ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                                    {simulateLead ? 'Simulating lead reply' : 'Sending as agent'}
                                </button>
                            </div>

                            {/* Input */}
                            <div className={styles.inputRow}>
                                <input className={styles.msgInput}
                                    placeholder={
                                        simulateLead
                                            ? "Type what the lead would say to trigger a real AI reply..."
                                            : activeConv.ai_active
                                            ? 'AI is active, or type to send an iMessage...'
                                            : 'Type an iMessage...'
                                    }
                                    value={input}
                                    onChange={e => setInput(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                                    disabled={sending} />
                                <button className={styles.sendBtn} onClick={sendMessage}
                                    disabled={sending || !input.trim()}>
                                    <Send size={16} />
                                </button>
                            </div>
                            </>
                            )}
                        </>
                    )}
                </div>

                {/* ── Right: contact detail panel ── */}
                {activeConv && (
                    <div className={styles.detailPanel}>
                        <div className={styles.detailAvatar}>{initials(activeConv)}</div>
                        <div className={styles.detailName}>{activeConv.first_name} {activeConv.last_name}</div>
                        <div className={styles.detailPhone}>{activeConv.phone}</div>

                        {activeConv.tags?.length > 0 && (
                            <div className={styles.detailTags}>
                                {activeConv.tags.map(t => <span key={t} className={styles.tag}>{t}</span>)}
                            </div>
                        )}

                        {/* Lead Status */}
                        <div className={styles.detailSection}>Lead Status</div>
                        {leadDetail ? (
                            <select
                                className={`${styles.statusSelect} ${STATUS_COLORS[leadDetail.status] || ''}`}
                                value={leadDetail.status}
                                disabled={statusUpdating}
                                onChange={e => updateStatus(e.target.value)}>
                                {STATUS_OPTIONS.map(s => (
                                    <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                                ))}
                            </select>
                        ) : (
                            <div className={styles.detailValue}>—</div>
                        )}

                        <div className={styles.detailSection}>Channel</div>
                        <div className={styles.detailValue}>🟢 WhatsApp</div>

                        {activeConv.agent_name && (
                            <>
                                <div className={styles.detailSection}>AI Agent</div>
                                <div className={styles.detailValue}>{activeConv.agent_name}</div>
                            </>
                        )}

                        {leadDetail?.email && (
                            <>
                                <div className={styles.detailSection}>Email</div>
                                <div className={styles.detailValue}>{leadDetail.email}</div>
                            </>
                        )}

                        {leadDetail?.notes && (
                            <>
                                <div className={styles.detailSection}>Notes</div>
                                <div className={styles.detailValue}>{leadDetail.notes}</div>
                            </>
                        )}
                    </div>
                )}
        </>
    );

    if (embedded) {
        return <div className={`${styles.main} ${styles.mainEmbedded}`}>{content}</div>;
    }

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>{content}</div>
        </div>
    );
}
