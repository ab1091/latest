'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useRouter } from 'next/navigation';
import { Users, Upload, Plus, X, Pencil, MessageCircle, Smartphone, ChevronRight, Phone, Mail, Tag, Clock } from 'lucide-react';

interface Lead {
    id: string; first_name: string; last_name: string;
    phone: string; email: string; status: string; tags: string[];
    notes?: string; created_at: string;
}


const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
    new:       { bg: 'rgba(99,102,241,0.12)',  color: '#a5b4fc' },
    contacted: { bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24' },
    qualified: { bg: 'rgba(16,185,129,0.12)',  color: '#34d399' },
    converted: { bg: 'rgba(185, 134, 42,0.12)',  color: '#e8c877' },
    dead:      { bg: 'rgba(107,114,128,0.1)',  color: '#9ca3af' },
};

export default function UserLeads() {
    const { accessToken } = useAuth();
    const router = useRouter();
    const [leads, setLeads]         = useState<Lead[]>([]);
    const [loading, setLoading]     = useState(true);
    const [importing, setImporting] = useState(false);
    const [importMsg, setImportMsg] = useState('');
    const [showAdd, setShowAdd]     = useState(false);
    const [form, setForm]           = useState({ first_name: '', last_name: '', phone: '', email: '', tags: '', notes: '', preferred_channel: 'whatsapp' });
    const [saving, setSaving]       = useState(false);

    // Edit modal
    const [editLead, setEditLead]   = useState<Lead | null>(null);
    const [editForm, setEditForm]   = useState({ first_name: '', last_name: '', phone: '', email: '', notes: '', status: 'new' });
    const [editSaving, setEditSaving] = useState(false);

    // Activity drawer
    const [drawerLead, setDrawerLead]     = useState<Lead | null>(null);
    const [drawerConvs, setDrawerConvs]   = useState<any[]>([]);
    const [drawerLoading, setDrawerLoading] = useState(false);

    const fileRef = useRef<HTMLInputElement>(null);
    const h = () => ({ Authorization: `Bearer ${accessToken}` });

    const fetchLeads = useCallback(() => {
        if (!accessToken) return;
        fetch(`/api/leads`, { headers: { Authorization: `Bearer ${accessToken}` } })
            .then(r => r.json())
            .then(d => setLeads(d?.data?.leads || []))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [accessToken]);

    useEffect(() => {
        fetchLeads();
        const timer = setInterval(fetchLeads, 3000);
        return () => clearInterval(timer);
    }, [fetchLeads]);

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        setImporting(true); setImportMsg('');
        const fd = new FormData(); fd.append('file', file);
        try {
            const res = await fetch(`/api/leads/import`, { method: 'POST', headers: h(), body: fd });
            const d = await res.json().catch(() => null);
            if (!res.ok || !d?.success) {
                setImportMsg(res.status === 401
                    ? 'Your session expired. Sign in again, then retry.'
                    : d?.detail || d?.error || `Import failed (server returned ${res.status}).`);
            } else {
                const { created = 0, updated = 0, skipped = 0 } = d.data || {};
                setImportMsg(`✓ ${created} imported${updated ? `, ${updated} updated` : ''}${skipped ? `, ${skipped} skipped` : ''}`);
                fetchLeads();
            }
        } catch (err: any) {
            setImportMsg(err?.message || 'Could not reach the server. Please try again.');
        }
        setImporting(false);
        if (fileRef.current) fileRef.current.value = '';
    };

    const handleAdd = async () => {
        if (!form.first_name) return;
        setSaving(true);
        try {
            const res = await fetch(`/api/leads`, {
                method: 'POST',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...form, tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [] }),
            });
            const d = await res.json();
            if (d.success) { setShowAdd(false); setForm({ first_name: '', last_name: '', phone: '', email: '', tags: '', notes: '', preferred_channel: 'whatsapp' }); fetchLeads(); }
        } catch {}
        setSaving(false);
    };

    const openEdit = (lead: Lead) => {
        setEditLead(lead);
        setEditForm({ first_name: lead.first_name, last_name: lead.last_name, phone: lead.phone, email: lead.email, notes: lead.notes || '', status: lead.status });
    };

    const handleSaveEdit = async () => {
        if (!editLead) return;
        setEditSaving(true);
        try {
            const res = await fetch(`/api/leads/${editLead.id}`, {
                method: 'PATCH',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify(editForm),
            });
            const d = await res.json();
            if (d.success) { setEditLead(null); fetchLeads(); }
        } catch {}
        setEditSaving(false);
    };

    const openDrawer = async (lead: Lead) => {
        setDrawerLead(lead); setDrawerConvs([]); setDrawerLoading(true);
        try {
            const res = await fetch(`/api/conversations?lead_id=${lead.id}`, { headers: h() });
            const d = await res.json();
            setDrawerConvs(d?.data?.conversations || []);
        } catch {}
        setDrawerLoading(false);
    };

    const openConversation = async (lead: Lead, channel: 'sms' | 'whatsapp' = 'sms') => {
        try {
            const res = await fetch(`/api/conversations`, {
                method: 'POST',
                headers: { ...h(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ lead_id: lead.id, channel }),
            });
            const d = await res.json();
            if (d.success) router.push(`/user/conversations?conv=${d.data.conversation.id}`);
        } catch {}
    };

    const initials = (l: Lead) => `${l.first_name?.[0] || ''}${l.last_name?.[0] || ''}`.toUpperCase() || '?';

    const inputStyle = { width: '100%', padding: '9px 12px', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, color: 'var(--text-1)', fontSize: 13, outline: 'none', boxSizing: 'border-box' as const };
    const labelStyle = { fontSize: 12, fontWeight: 600 as const, color: 'var(--text-4)', display: 'block' as const, marginBottom: 5 };

    return (
        <div style={{ maxWidth: 980 }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>My Leads</h1>
                    <p style={{ color: 'var(--text-4)', fontSize: 13, marginTop: 4 }}>{leads.length} leads</p>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    {importMsg && <span style={{ fontSize: 12, color: importMsg.startsWith('✓') ? '#34d399' : '#f87171', fontWeight: 600 }}>{importMsg}</span>}
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: 'var(--text-2)' }}>
                        <Upload size={14} />
                        {importing ? 'Importing…' : 'Import CSV'}
                        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" style={{ display: 'none' }} onChange={handleImport} disabled={importing} />
                    </label>
                    <button onClick={() => setShowAdd(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
                        <Plus size={14} /> Add Lead
                    </button>
                </div>
            </div>

            {/* Table */}
            {loading ? <p style={{ color: 'var(--text-4)' }}>Loading...</p> :
            leads.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-4)' }}>
                    <Users size={44} style={{ opacity: 0.2, marginBottom: 14 }} />
                    <p style={{ fontWeight: 600, marginBottom: 4 }}>No leads yet</p>
                    <p style={{ fontSize: 13 }}>Add a lead or import a CSV file.</p>
                </div>
            ) : (
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--border-default)', background: 'rgba(255,255,255,0.02)' }}>
                                {['Name', 'Phone', 'Tags', 'Status', 'Created', 'Actions'].map(col => (
                                    <th key={col} style={{ padding: '12px 18px', textAlign: 'left', fontSize: 11, color: 'var(--text-4)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{col}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {leads.map((lead, i) => {
                                const sc = STATUS_COLORS[lead.status] || STATUS_COLORS.new;
                                return (
                                    <tr key={lead.id} style={{ borderBottom: i < leads.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                                        <td style={{ padding: '13px 18px', cursor: 'pointer' }} onClick={() => openDrawer(lead)}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                <div style={{ width: 34, height: 34, borderRadius: 9, background: sc.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, color: sc.color, flexShrink: 0 }}>
                                                    {initials(lead)}
                                                </div>
                                                <div>
                                                    <div style={{ fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 4 }}>
                                                        {lead.first_name} {lead.last_name}
                                                        <ChevronRight size={12} style={{ opacity: 0.4 }} />
                                                    </div>
                                                    <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{lead.email || '—'}</div>
                                                </div>
                                            </div>
                                        </td>
                                        <td style={{ padding: '13px 18px', fontSize: 13, color: 'var(--text-2)' }}>{lead.phone || '—'}</td>
                                        <td style={{ padding: '13px 18px' }}>
                                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                                {(lead.tags || []).map(t => (
                                                    <span key={t} style={{ padding: '2px 7px', borderRadius: 20, fontSize: 10, fontWeight: 600, background: 'rgba(212, 169, 79,0.1)', color: 'var(--primary)', border: '1px solid rgba(212, 169, 79,0.2)' }}>{t}</span>
                                                ))}
                                                {(!lead.tags || lead.tags.length === 0) && <span style={{ color: 'var(--text-4)', fontSize: 12 }}>—</span>}
                                            </div>
                                        </td>
                                        <td style={{ padding: '13px 18px' }}>
                                            <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: sc.bg, color: sc.color }}>{lead.status}</span>
                                        </td>
                                        <td style={{ padding: '13px 18px', fontSize: 12, color: 'var(--text-4)' }}>
                                            {parseApiDate(lead.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                        </td>
                                        <td style={{ padding: '13px 18px' }}>
                                            <div style={{ display: 'flex', gap: 6 }}>
                                                <button onClick={() => openConversation(lead, 'whatsapp')} title="Open WhatsApp conversation" style={{ padding: '6px 10px', borderRadius: 7, border: 'none', background: 'rgba(37,211,102,0.1)', color: '#25d366', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600 }}>
                                                    <MessageCircle size={13} /> WhatsApp
                                                </button>
                                                <button onClick={() => openConversation(lead, 'sms')} title="Open SMS conversation" style={{ padding: '6px 10px', borderRadius: 7, border: 'none', background: 'rgba(212, 169, 79,0.1)', color: '#d4a94f', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600 }}>
                                                    <Smartphone size={13} /> SMS
                                                </button>
                                                <button onClick={() => openEdit(lead)} title="Edit lead" style={{ padding: '6px 10px', borderRadius: 7, border: 'none', background: 'rgba(99,102,241,0.1)', color: '#818cf8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600 }}>
                                                    <Pencil size={13} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Activity Drawer */}
            {drawerLead && (
                <>
                    <div onClick={() => setDrawerLead(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', zIndex: 200 }} />
                    <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 380, background: 'var(--bg-card)', borderLeft: '1px solid var(--border-default)', zIndex: 201, display: 'flex', flexDirection: 'column', overflowY: 'auto', boxShadow: '-8px 0 32px rgba(0,0,0,0.18)' }}>
                        <div style={{ padding: '20px 22px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(212, 169, 79,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14, color: '#d4a94f' }}>
                                    {initials(drawerLead)}
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: 15 }}>{drawerLead.first_name} {drawerLead.last_name}</div>
                                    <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: (STATUS_COLORS[drawerLead.status] || STATUS_COLORS.new).bg, color: (STATUS_COLORS[drawerLead.status] || STATUS_COLORS.new).color }}>
                                        {drawerLead.status}
                                    </span>
                                </div>
                            </div>
                            <button onClick={() => setDrawerLead(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)' }}><X size={18} /></button>
                        </div>

                        <div style={{ padding: '14px 22px', borderBottom: '1px solid var(--border-default)' }}>
                            {drawerLead.phone && <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, fontSize: 13 }}><Phone size={13} color="var(--text-4)" />{drawerLead.phone}</div>}
                            {drawerLead.email && <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, fontSize: 13 }}><Mail size={13} color="var(--text-4)" />{drawerLead.email}</div>}
                            {drawerLead.tags?.length > 0 && (
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                    <Tag size={13} color="var(--text-4)" />
                                    {drawerLead.tags.map(t => <span key={t} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 20, background: 'rgba(212, 169, 79,0.1)', color: '#d4a94f' }}>{t}</span>)}
                                </div>
                            )}
                            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                                <button onClick={() => { setDrawerLead(null); openEdit(drawerLead); }} style={{ padding: '7px 10px', borderRadius: 8, fontSize: 12, fontWeight: 600, background: 'rgba(99,102,241,0.1)', color: '#818cf8', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}>
                                    <Pencil size={13} /> Edit
                                </button>
                                <button onClick={() => openConversation(drawerLead, 'whatsapp').then(() => setDrawerLead(null))} style={{ flex: 1, padding: '7px 0', borderRadius: 8, fontSize: 12, fontWeight: 600, background: 'rgba(37,211,102,0.1)', color: '#25d366', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                                    <MessageCircle size={13} /> WhatsApp
                                </button>
                                <button onClick={() => openConversation(drawerLead, 'sms').then(() => setDrawerLead(null))} style={{ flex: 1, padding: '7px 0', borderRadius: 8, fontSize: 12, fontWeight: 600, background: 'rgba(212, 169, 79,0.1)', color: '#d4a94f', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                                    <Smartphone size={13} /> SMS
                                </button>
                            </div>
                        </div>

                        <div style={{ padding: '16px 22px', flex: 1 }}>
                            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 14 }}>Activity Timeline</div>
                            {drawerLoading ? <p style={{ fontSize: 13, color: 'var(--text-4)' }}>Loading...</p> :
                            drawerConvs.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-4)', fontSize: 13 }}>No activity yet for this lead.</div>
                            ) : drawerConvs.map((conv, i) => (
                                <div key={conv.id} style={{ display: 'flex', gap: 12, paddingBottom: 18, position: 'relative' }}>
                                    {i < drawerConvs.length - 1 && <div style={{ position: 'absolute', left: 15, top: 28, bottom: 0, width: 2, background: 'var(--border-default)' }} />}
                                    <div style={{ width: 32, height: 32, borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1,
                                        background: conv.channel === 'sms' ? 'rgba(212, 169, 79,0.12)' : conv.channel === 'voice' ? 'rgba(245,158,11,0.12)' : 'rgba(99,102,241,0.12)',
                                    }}>
                                        {conv.channel === 'sms' ? <Smartphone size={14} color="#d4a94f" /> : conv.channel === 'voice' ? <Phone size={14} color="#f59e0b" /> : <MessageCircle size={14} color="#818cf8" />}
                                    </div>
                                    <div style={{ flex: 1, paddingTop: 4 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span style={{ fontSize: 13, fontWeight: 600 }}>{conv.channel === 'sms' ? 'SMS' : conv.channel === 'voice' ? 'Voice Call' : 'Chat'}</span>
                                            <span style={{ fontSize: 10, padding: '1px 7px', borderRadius: 20, fontWeight: 700, background: conv.ai_active ? 'rgba(16,185,129,0.1)' : 'rgba(107,114,128,0.1)', color: conv.ai_active ? '#10b981' : '#6b7280' }}>{conv.ai_active ? 'AI' : 'Manual'}</span>
                                        </div>
                                        <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 2, maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{conv.last_message || 'No messages yet'}</div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4, fontSize: 11, color: 'var(--text-4)' }}>
                                            <Clock size={10} />
                                            {parseApiDate(conv.last_message_at || conv.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </>
            )}

            {/* Add Lead Modal */}
            {showAdd && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 16, padding: 28, width: 440 }} onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <span style={{ fontWeight: 800, fontSize: 16 }}>Add Lead</span>
                            <button onClick={() => setShowAdd(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)' }}><X size={18} /></button>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                            {[['first_name','First Name *','Sara'],['last_name','Last Name','Ahmed'],['phone','Phone','+1...'],['email','Email','sara@email.com']].map(([key,label,ph]) => (
                                <div key={key}>
                                    <label style={labelStyle}>{label}</label>
                                    <input value={(form as any)[key]} onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))} placeholder={ph} style={inputStyle} />
                                </div>
                            ))}
                        </div>
                        <div style={{ marginBottom: 14 }}>
                            <label style={labelStyle}>Tags (comma separated)</label>
                            <input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))} placeholder="loan, medical" style={inputStyle} />
                        </div>
                        <div style={{ marginBottom: 20 }}>
                            <label style={labelStyle}>Notes</label>
                            <textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} rows={2} style={{ ...inputStyle, resize: 'vertical' as const }} />
                        </div>
                        <div style={{ display: 'flex', gap: 10 }}>
                            <button onClick={() => setShowAdd(false)} style={{ flex: 1, padding: '9px', background: 'transparent', border: '1px solid var(--border-default)', borderRadius: 8, cursor: 'pointer', color: 'var(--text-2)', fontWeight: 600 }}>Cancel</button>
                            <button onClick={handleAdd} disabled={saving || !form.first_name} style={{ flex: 1, padding: '9px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, opacity: saving || !form.first_name ? 0.5 : 1 }}>
                                {saving ? 'Saving…' : 'Add Lead'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Edit Lead Modal */}
            {editLead && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 16, padding: 28, width: 440 }} onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <span style={{ fontWeight: 800, fontSize: 16 }}>Edit Lead</span>
                            <button onClick={() => setEditLead(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)' }}><X size={18} /></button>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                            {[['first_name','First Name *'],['last_name','Last Name'],['phone','Phone'],['email','Email']].map(([key,label]) => (
                                <div key={key}>
                                    <label style={labelStyle}>{label}</label>
                                    <input value={(editForm as any)[key]} onChange={e => setEditForm(p => ({ ...p, [key]: e.target.value }))} style={inputStyle} />
                                </div>
                            ))}
                        </div>
                        <div style={{ marginBottom: 14 }}>
                            <label style={labelStyle}>Status</label>
                            <select value={editForm.status} onChange={e => setEditForm(p => ({ ...p, status: e.target.value }))} style={inputStyle}>
                                <option value="new">New</option>
                                <option value="contacted">Contacted</option>
                                <option value="qualified">Qualified</option>
                                <option value="converted">Converted</option>
                                <option value="dead">Trip Lead</option>
                            </select>
                        </div>
                        <div style={{ marginBottom: 20 }}>
                            <label style={labelStyle}>Notes</label>
                            <textarea value={editForm.notes} onChange={e => setEditForm(p => ({ ...p, notes: e.target.value }))} rows={2} style={{ ...inputStyle, resize: 'vertical' as const }} />
                        </div>
                        <div style={{ display: 'flex', gap: 10 }}>
                            <button onClick={() => setEditLead(null)} style={{ flex: 1, padding: '9px', background: 'transparent', border: '1px solid var(--border-default)', borderRadius: 8, cursor: 'pointer', color: 'var(--text-2)', fontWeight: 600 }}>Cancel</button>
                            <button onClick={handleSaveEdit} disabled={editSaving} style={{ flex: 1, padding: '9px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, opacity: editSaving ? 0.5 : 1 }}>
                                {editSaving ? 'Saving…' : 'Save Changes'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
