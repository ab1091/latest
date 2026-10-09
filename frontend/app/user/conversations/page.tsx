'use client';

import { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { MessageCircle, Send, Bot, User, RefreshCw, ToggleLeft, ToggleRight, Phone, Tag } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useSearchParams } from 'next/navigation';

const POLL_MS  = 3000;

interface Conversation {
    id: string; lead_id: string; agent_id: string | null;
    channel: string; ai_active: boolean;
    first_name: string; last_name: string; phone: string;
    tags: string[]; agent_name: string | null;
    last_message: string | null; last_message_at: string | null;
}
interface Message {
    id: string; conversation_id: string;
    role: 'user' | 'agent' | 'human'; content: string; created_at: string;
}

const s: Record<string, React.CSSProperties> = {
    page:     { display: 'flex', height: 'calc(100vh - 64px)', minHeight: 0 },
    list:     { width: 280, flexShrink: 0, borderRight: '1px solid var(--border-default)', display: 'flex', flexDirection: 'column', overflow: 'hidden' },
    listHead: { padding: '14px 16px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 14 },
    item:     { padding: '12px 16px', cursor: 'pointer', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: 10, alignItems: 'center' },
    itemAct:  { background: 'rgba(185, 134, 42,0.08)' },
    avatar:   { width: 36, height: 36, borderRadius: '50%', background: 'var(--primary)', color: 'var(--on-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13, flexShrink: 0 },
    meta:     { flex: 1, minWidth: 0 },
    name:     { fontWeight: 600, fontSize: 13 },
    last:     { fontSize: 12, color: 'var(--text-4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
    chat:     { flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 },
    header:   { padding: '12px 18px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 },
    msgs:     { flex: 1, overflowY: 'auto' as const, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10 },
    bubble:   { display: 'flex', gap: 8, maxWidth: '80%' },
    bubbU:    { alignSelf: 'flex-end', flexDirection: 'row-reverse' as const },
    bubbA:    { alignSelf: 'flex-start' },
    bIcon:    { width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 },
    bText:    { padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.5 },
    bTime:    { fontSize: 10, color: 'var(--text-4)', marginTop: 3 },
    input:    { padding: '12px 16px', borderTop: '1px solid var(--border-default)', display: 'flex', gap: 8, flexShrink: 0 },
    inp:      { flex: 1, padding: '9px 13px', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 9, color: 'var(--text-1)', fontSize: 13, outline: 'none' },
    send:     { padding: '9px 14px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center' },
    empty:    { textAlign: 'center' as const, padding: '60px 20px', color: 'var(--text-4)', flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' },
    toggle:   { display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', background: 'none', border: 'none', fontSize: 12, color: 'var(--text-2)', padding: '4px 8px', borderRadius: 6 },
};

function UserConversationsInner() {
    const { accessToken } = useAuth();
    const searchParams    = useSearchParams();

    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [activeConv,    setActiveConv]    = useState<Conversation | null>(null);
    const [messages,      setMessages]      = useState<Message[]>([]);
    const [msgLoading,    setMsgLoading]    = useState(false);
    const [loading,       setLoading]       = useState(false);
    const [input,         setInput]         = useState('');
    const [sending,       setSending]       = useState(false);

    const bottomRef     = useRef<HTMLDivElement>(null);
    const activeConvRef = useRef<Conversation | null>(null);
    const msgCountRef   = useRef(0);
    const pollRef       = useRef<ReturnType<typeof setInterval> | null>(null);
    const initialLoad   = useRef(true);

    const h = useCallback(() => ({ Authorization: `Bearer ${accessToken}` }), [accessToken]);

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

    useEffect(() => { loadConversations(); }, [loadConversations]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

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

    useEffect(() => {
        activeConvRef.current = activeConv;
        if (pollRef.current) clearInterval(pollRef.current);
        if (activeConv) pollRef.current = setInterval(pollMessages, POLL_MS);
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, [activeConv, pollMessages]);

    const selectConv = useCallback(async (conv: Conversation) => {
        setActiveConv(conv);
        setMsgLoading(true);
        msgCountRef.current = 0;
        try {
            const res = await fetch(`/api/conversations/${conv.id}/messages`, { headers: h() });
            const d   = await res.json();
            if (d.success) { setMessages(d.data.messages); msgCountRef.current = d.data.messages.length; }
        } catch {}
        setMsgLoading(false);
    }, [h]);

    const channelFilter = searchParams.get('channel');
    const visibleConvs  = channelFilter
        ? conversations.filter(c => c.channel === channelFilter)
        : conversations;

    useEffect(() => {
        if (!initialLoad.current || conversations.length === 0) return;
        const convId = searchParams.get('conv');
        if (convId) {
            const found = conversations.find(c => c.id === convId);
            if (found) { selectConv(found); initialLoad.current = false; }
        }
    }, [conversations, searchParams, selectConv]);

    const sendMessage = async () => {
        if (!input.trim() || !activeConv) return;
        setSending(true);
        const content = input.trim();
        setInput('');
        try {
            const res = await fetch(`/api/conversations/${activeConv.id}/messages`, {
                method: 'POST',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ content, role: 'human' }),
            });
            const d = await res.json();
            if (d.success) { setMessages(m => [...m, d.data.message]); msgCountRef.current += 1; }
        } catch {}
        setSending(false);
    };

    const toggleAI = async () => {
        if (!activeConv) return;
        const res = await fetch(`/api/conversations/${activeConv.id}/toggle-ai`, { method: 'PATCH', headers: h() });
        const d = await res.json();
        if (d.success) {
            const updated = { ...activeConv, ai_active: d.data.ai_active };
            setActiveConv(updated);
            setConversations(cs => cs.map(c => c.id === activeConv.id ? { ...c, ai_active: d.data.ai_active } : c));
        }
    };

    const initials = (c: Conversation) => `${c.first_name?.[0] || ''}${c.last_name?.[0] || ''}`.toUpperCase() || '?';

    return (
        <div style={s.page}>
            {/* Left: conversation list */}
            <div style={s.list}>
                <div style={s.listHead}>
                    <MessageCircle size={15} />
                    <span style={{ flex: 1 }}>
                        {channelFilter === 'sms' ? 'SMS' : channelFilter === 'whatsapp' ? 'WhatsApp' : 'All Chats'}
                    </span>
                    <button onClick={() => loadConversations()} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)', padding: 4 }}>
                        <RefreshCw size={13} />
                    </button>
                </div>
                <div style={{ overflowY: 'auto', flex: 1 }}>
                    {loading && <div style={{ padding: '20px 16px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>}
                    {!loading && visibleConvs.length === 0 && (
                        <div style={{ padding: '24px 16px', color: 'var(--text-4)', fontSize: 13 }}>
                            {channelFilter ? `No ${channelFilter} conversations yet.` : 'No conversations yet.'}
                        </div>
                    )}
                    {visibleConvs.map(conv => (
                        <div key={conv.id}
                            style={{ ...s.item, ...(activeConv?.id === conv.id ? s.itemAct : {}) }}
                            onClick={() => selectConv(conv)}>
                            <div style={s.avatar}>{initials(conv)}</div>
                            <div style={s.meta}>
                                <div style={s.name}>{conv.first_name} {conv.last_name}</div>
                                <div style={s.last}>
                                    {conv.last_message ? conv.last_message.slice(0, 35) + (conv.last_message.length > 35 ? '…' : '') : conv.phone || '—'}
                                </div>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                                {conv.ai_active && <Bot size={12} color="var(--primary)" />}
                                <span style={{ fontSize: 11 }}>🟢</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Center: chat */}
            <div style={s.chat}>
                {!activeConv ? (
                    <div style={s.empty}>
                        <MessageCircle size={40} strokeWidth={1.2} style={{ opacity: 0.2, marginBottom: 12 }} />
                        <p style={{ margin: 0, fontWeight: 600 }}>Select a conversation</p>
                    </div>
                ) : (
                    <>
                        <div style={s.header}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{ ...s.avatar, width: 38, height: 38, fontSize: 14, borderRadius: 10 }}>{initials(activeConv)}</div>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: 15 }}>{activeConv.first_name} {activeConv.last_name}</div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                                        <span style={{ fontSize: 12, color: 'var(--text-4)' }}>{activeConv.phone}</span>
                                        <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'rgba(37,211,102,0.1)', border: '1px solid rgba(37,211,102,0.3)', color: '#25d366', fontWeight: 600 }}>🟢 WhatsApp</span>
                                        {activeConv.tags?.length > 0 && activeConv.tags.slice(0,2).map(t => (
                                            <span key={t} style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'rgba(212, 169, 79,0.1)', color: 'var(--primary)', fontWeight: 600 }}>{t}</span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                {activeConv.phone && (
                                    <a href={`tel:${activeConv.phone}`} style={{
                                        display: 'flex', alignItems: 'center', gap: 6,
                                        padding: '7px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600,
                                        background: 'rgba(212, 169, 79,0.1)', color: 'var(--primary)',
                                        border: '1px solid rgba(212, 169, 79,0.2)', textDecoration: 'none',
                                    }}>
                                        <Phone size={13} /> Call
                                    </a>
                                )}
                                <button style={s.toggle} onClick={toggleAI}>
                                    {activeConv.ai_active
                                        ? <><ToggleRight size={20} color="var(--primary)" /><span style={{ color: 'var(--primary)', fontWeight: 600 }}>AI Active</span></>
                                        : <><ToggleLeft size={20} color="var(--text-4)" /><span>AI Paused</span></>}
                                </button>
                            </div>
                        </div>

                        <div style={s.msgs}>
                            {msgLoading && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading messages...</div>}
                            {!msgLoading && messages.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>No messages yet.</div>}
                            {messages.map(msg => {
                                const isOutgoing = msg.role === 'agent' || msg.role === 'human';
                                return (
                                    <div key={msg.id} style={{ ...s.bubble, ...(isOutgoing ? s.bubbU : s.bubbA) }}>
                                        <div style={{
                                            ...s.bIcon,
                                            background: isOutgoing ? 'rgba(185, 134, 42,0.12)' : 'var(--bg-elevated)',
                                            border: `1px solid ${isOutgoing ? 'rgba(185, 134, 42,0.2)' : 'var(--border-default)'}`,
                                            color: isOutgoing ? 'var(--primary)' : 'var(--text-4)',
                                        }}>
                                            {isOutgoing ? <Bot size={11} /> : <User size={11} />}
                                        </div>
                                        <div>
                                            <div style={{
                                                ...s.bText,
                                                background: isOutgoing ? 'var(--primary)' : 'var(--bg-elevated)',
                                                border: `1px solid ${isOutgoing ? 'transparent' : 'var(--border-default)'}`,
                                                color: isOutgoing ? '#fff' : 'var(--text-1)',
                                                borderBottomRightRadius: isOutgoing ? 4 : 12,
                                                borderBottomLeftRadius: isOutgoing ? 12 : 4,
                                            }}>
                                                {msg.content}
                                            </div>
                                            <div style={{ ...s.bTime, textAlign: isOutgoing ? 'right' : 'left' }}>
                                                {parseApiDate(msg.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                            <div ref={bottomRef} />
                        </div>

                        <div style={s.input}>
                            <input
                                style={s.inp}
                                placeholder={activeConv.ai_active ? 'AI is active — or type to send via WhatsApp...' : 'Type a WhatsApp message...'}
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                                disabled={sending}
                            />
                            <button style={{ ...s.send, opacity: sending || !input.trim() ? 0.5 : 1 }}
                                onClick={sendMessage} disabled={sending || !input.trim()}>
                                <Send size={15} />
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

export default function UserConversationsPage() {
    return (
        <Suspense>
            <UserConversationsInner />
        </Suspense>
    );
}
