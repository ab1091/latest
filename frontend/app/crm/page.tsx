'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
    Users, Calendar, Phone, Mail, RefreshCw, Search, User, Download,
    Tag, MessageCircle, Zap, CheckCircle, Clock, XCircle
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import styles from './crm.module.css';


interface LocalContact {
    id: string; email: string; first_name: string; last_name: string;
    phone: string | null; role: string; created_at: string;
    total: string; confirmed: string; completed: string; cancelled: string;
    last_apt: string | null;
}
interface LocalAppointment {
    id: string; start_time: string; end_time: string; status: string;
    notes: string | null; provider_name: string; service_name: string;
}

interface Lead {
    id: string; first_name: string; last_name: string;
    email: string; phone: string; tags: string[];
    status: string; source: string; notes: string;
    created_at: string; preferred_channel: string;
}

type Tab = 'local' | 'leads' | 'history';

const STATUS_COLOR: Record<string, { bg: string; color: string }> = {
    new:              { bg: 'rgba(99,102,241,0.12)',  color: '#a5b4fc' },
    contacted:        { bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24' },
    responded:        { bg: 'rgba(59,130,246,0.12)',  color: '#60a5fa' },
    follow_up_sent:   { bg: 'rgba(168,85,247,0.12)', color: '#c084fc' },
    qualified:        { bg: 'rgba(16,185,129,0.12)',  color: '#34d399' },
    converted:        { bg: 'rgba(185, 134, 42,0.12)',  color: '#e8c877' },
    dead:             { bg: 'rgba(107,114,128,0.1)',  color: '#9ca3af' },
};

export default function CRMPage() {
    const { accessToken, isLoading } = useAuth();
    const router = useRouter();
    const [tab, setTab] = useState<Tab>('leads');
    const [search, setSearch] = useState('');

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) router.replace('/login');
    }, [isLoading, accessToken, router]);

    // Local contacts state
    const [localContacts, setLocalContacts]   = useState<LocalContact[]>([]);
    const [localLoading, setLocalLoading]     = useState(false);
    const [expandedLocal, setExpandedLocal]   = useState<string | null>(null);
    const [aptMap, setAptMap]                 = useState<Record<string, LocalAppointment[]>>({});
    const [aptLoading, setAptLoading]         = useState<string | null>(null);

    // Leads state
    const [leads, setLeads]           = useState<Lead[]>([]);
    const [leadsLoading, setLeadsLoading] = useState(false);
    const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

    // Call history state
    const [callHistory, setCallHistory]   = useState<any[]>([]);
    const [callsLoading, setCallsLoading] = useState(false);

    const h = useMemo(() => ({ Authorization: `Bearer ${accessToken}` }), [accessToken]);

    // ── Stats computed from leads ──────────────────────────────────────────────
    const leadStats = useMemo(() => ({
        total:     leads.length,
        contacted: leads.filter(l => l.status === 'contacted' || l.status === 'follow_up_sent').length,
        qualified: leads.filter(l => l.status === 'qualified').length,
        converted: leads.filter(l => l.status === 'converted').length,
        calls:     callHistory.length,
    }), [leads, callHistory]);

    // ── Load local contacts ───────────────────────────────────────────────────
    const loadLocal = useCallback(async () => {
        setLocalLoading(true);
        setAptMap({});
        try {
            const res = await fetch('/api/crm/contacts', { headers: h });
            const cd  = await res.json();
            if (cd.success) setLocalContacts(cd.data.contacts);
        } catch {}
        setLocalLoading(false);
    }, [h]);

    // ── Load leads ────────────────────────────────────────────────────────────
    const loadLeads = useCallback(async () => {
        if (!accessToken) return;
        setLeadsLoading(true);
        try {
            const res = await fetch(`/api/leads`, { headers: h });
            const d   = await res.json();
            if (d.success) setLeads(d.data.leads);
        } catch {}
        setLeadsLoading(false);
    }, [h, accessToken]);

    // ── Load call history ─────────────────────────────────────────────────────
    const loadCallHistory = useCallback(async () => {
        setCallsLoading(true);
        try {
            const res = await fetch('/api/crm/calls', { headers: h });
            const d   = await res.json();
            if (d.success) setCallHistory(d.data.calls);
        } catch {}
        setCallsLoading(false);
    }, [h]);

    useEffect(() => {
        if (!accessToken) return;
        loadLeads();
        loadCallHistory();
    }, [accessToken, loadLeads, loadCallHistory]);

    useEffect(() => {
        if (tab === 'local' && localContacts.length === 0) loadLocal();
        setExpandedLocal(null);
        setSelectedLead(null);
    }, [tab, loadLocal, localContacts.length]);

    // ── Select local contact ──────────────────────────────────────────────────
    const selectLocal = async (id: string) => {
        setExpandedLocal(id);
        if (aptMap[id]) return;
        setAptLoading(id);
        try {
            const res = await fetch(`/api/crm/contacts/${id}/appointments`, { headers: h });
            const d   = await res.json();
            if (d.success) setAptMap(m => ({ ...m, [id]: d.data.appointments }));
        } catch {}
        setAptLoading(null);
    };

    // ── CSV exports ───────────────────────────────────────────────────────────
    const exportLeadsCSV = () => {
        const headers = ['Name', 'Email', 'Phone', 'Tags', 'Status', 'Source', 'Created'];
        const rows = filteredLeads.map(l => [
            `${l.first_name} ${l.last_name}`, l.email, l.phone,
            l.tags.join('; '), l.status, l.source,
            parseApiDate(l.created_at).toLocaleDateString(),
        ]);
        const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
        a.download = 'leads.csv'; a.click();
    };

    const exportCallsCSV = () => {
        const headers = ['Date', 'Patient', 'Phone', 'Direction', 'Outcome', 'Duration'];
        const rows = callHistory.map(c => {
            const dt   = c.createdAt ? parseApiDate(c.createdAt) : null;
            const mins = Math.floor((c.durationSeconds || 0) / 60);
            const secs = (c.durationSeconds || 0) % 60;
            return [dt ? dt.toLocaleDateString() : '', c.patientName || c.phone, c.phone,
                c.direction, c.outcome, c.durationSeconds ? `${mins}m ${secs}s` : ''];
        });
        const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n');
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
        a.download = 'call-history.csv'; a.click();
    };

    // ── Filters ───────────────────────────────────────────────────────────────
    const filteredLeads = leads.filter(l => {
        const q = search.toLowerCase();
        return !q ||
            `${l.first_name} ${l.last_name}`.toLowerCase().includes(q) ||
            l.email.toLowerCase().includes(q) ||
            l.phone.includes(q) ||
            l.tags.some(t => t.toLowerCase().includes(q));
    });

    const localFiltered = localContacts.filter(c => {
        const q = search.toLowerCase();
        return !q || c.email.toLowerCase().includes(q) ||
            `${c.first_name} ${c.last_name}`.toLowerCase().includes(q) ||
            (c.phone || '').includes(q);
    });

    const initials = (fn: string, ln: string) =>
        `${fn?.[0] || ''}${ln?.[0] || ''}`.toUpperCase() || '?';

    const activeLocalContact = localContacts.find(c => c.id === expandedLocal);

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>

                {/* Header */}
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Users size={24} /></div>
                    <div className={styles.headerInfo}>
                        <h1>CRM</h1>
                        <p>Leads, contacts and call history — all in one place</p>
                    </div>
                    <div className={styles.headerActions}>
                        <button className={styles.syncBtn} onClick={() => { loadLeads(); loadCallHistory(); }}>
                            <RefreshCw size={14} className={leadsLoading ? styles.spinning : ''} />
                            Refresh
                        </button>
                    </div>
                </div>

                {/* Stats Row */}
                <div className={styles.statsRow}>
                    <div className={styles.statsCard}>
                        <div className={styles.statsLabel}>Total Leads</div>
                        <div className={styles.statsValue}>{leadStats.total}</div>
                    </div>
                    <div className={styles.statsCard}>
                        <div className={styles.statsLabel}>Contacted</div>
                        <div className={styles.statsValue}>{leadStats.contacted}</div>
                    </div>
                    <div className={styles.statsCard}>
                        <div className={styles.statsLabel}>Qualified</div>
                        <div className={styles.statsValue}>{leadStats.qualified}</div>
                    </div>
                    <div className={styles.statsCard}>
                        <div className={styles.statsLabel}>Converted</div>
                        <div className={styles.statsValue}>{leadStats.converted}</div>
                    </div>
                    <div className={styles.statsCard}>
                        <div className={styles.statsLabel}>Total Calls</div>
                        <div className={styles.statsValue}>{leadStats.calls}</div>
                    </div>
                </div>

                {/* Tabs + Actions */}
                <div className={styles.tabContainerOuter}>
                    <div className={styles.tabsList}>
                        <button className={tab === 'leads'   ? styles.tabActiveStyle : styles.tabInactiveStyle} onClick={() => setTab('leads')}>Leads</button>
                        <button className={tab === 'local'   ? styles.tabActiveStyle : styles.tabInactiveStyle} onClick={() => setTab('local')}>Contacts</button>
                        <button className={tab === 'history' ? styles.tabActiveStyle : styles.tabInactiveStyle} onClick={() => setTab('history')}>Call History</button>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                        {tab === 'leads'   && <button className={styles.syncBtn} onClick={exportLeadsCSV}><Download size={14} /> Export CSV</button>}
                        {tab === 'history' && <button className={styles.syncBtn} onClick={exportCallsCSV}><Download size={14} /> Export CSV</button>}
                    </div>
                </div>

                {/* Search (not for call history) */}
                {tab !== 'history' && (
                    <div className={styles.searchBox} style={{ marginBottom: '1rem' }}>
                        <Search size={18} color="var(--text-4)" />
                        <input className={styles.searchInput}
                            placeholder={tab === 'leads' ? 'Search leads by name, phone, tag...' : 'Search contacts...'}
                            value={search} onChange={e => setSearch(e.target.value)} />
                    </div>
                )}

                <div className={styles.contentGrid}>
                    {/* LEFT / MAIN PANEL */}
                    <div className={tab === 'history' ? styles.fullWidthPanel : styles.listPanel}>

                        {/* ── LEADS TAB ── */}
                        {tab === 'leads' && (
                            <div className={styles.tableContainer}>
                                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 1fr 1fr', padding: '10px 16px', fontSize: 11, fontWeight: 700, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid var(--border-default)' }}>
                                    <span>Lead</span><span>Tags</span><span>Status</span><span>Channel</span><span>Added</span>
                                </div>
                                {leadsLoading && <div className={styles.emptyState}>Loading leads...</div>}
                                {!leadsLoading && filteredLeads.length === 0 && (
                                    <div className={styles.emptyState}>No leads found. Add leads from the Leads page.</div>
                                )}
                                {!leadsLoading && filteredLeads.map(lead => {
                                    const sc = STATUS_COLOR[lead.status] || STATUS_COLOR.new;
                                    return (
                                        <div key={lead.id}
                                            className={`${styles.row} ${selectedLead?.id === lead.id ? styles.rowActive : ''}`}
                                            onClick={() => setSelectedLead(selectedLead?.id === lead.id ? null : lead)}
                                            style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 1fr 1fr', alignItems: 'center' }}>
                                            {/* Name + email */}
                                            <div className={styles.contactInfo}>
                                                <div className={styles.avatar} style={{ background: sc.bg, color: sc.color }}>
                                                    {initials(lead.first_name, lead.last_name)}
                                                </div>
                                                <div>
                                                    <div className={styles.name}>{lead.first_name} {lead.last_name}</div>
                                                    <div className={styles.email}>{lead.phone || lead.email || '—'}</div>
                                                </div>
                                            </div>
                                            {/* Tags */}
                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                                {lead.tags.length === 0 ? <span style={{ color: 'var(--text-4)', fontSize: 12 }}>—</span>
                                                    : lead.tags.slice(0, 2).map(t => (
                                                        <span key={t} style={{ padding: '2px 7px', borderRadius: 20, fontSize: 10, fontWeight: 600, background: 'rgba(212, 169, 79,0.1)', color: 'var(--primary)', border: '1px solid rgba(212, 169, 79,0.2)' }}>{t}</span>
                                                    ))}
                                                {lead.tags.length > 2 && <span style={{ fontSize: 10, color: 'var(--text-4)' }}>+{lead.tags.length - 2}</span>}
                                            </div>
                                            {/* Status */}
                                            <div>
                                                <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: sc.bg, color: sc.color }}>
                                                    {lead.status}
                                                </span>
                                            </div>
                                            {/* Channel */}
                                            <div style={{ fontSize: 12, color: 'var(--text-4)', display: 'flex', alignItems: 'center', gap: 5 }}>
                                                {lead.preferred_channel === 'whatsapp' ? <MessageCircle size={13} /> : <Phone size={13} />}
                                                {lead.preferred_channel || 'whatsapp'}
                                            </div>
                                            {/* Date */}
                                            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
                                                {parseApiDate(lead.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {/* ── LOCAL CONTACTS TAB ── */}
                        {tab === 'local' && (
                            <div className={styles.tableContainer}>
                                <div className={styles.tableHeader}>
                                    <span>Contact</span><span>Phone</span><span>Last Visit</span>
                                </div>
                                {localLoading && <div className={styles.emptyState}>Loading...</div>}
                                {!localLoading && localFiltered.length === 0 && <div className={styles.emptyState}>No contacts found.</div>}
                                {!localLoading && localFiltered.map(c => (
                                    <div key={c.id} className={`${styles.row} ${expandedLocal === c.id ? styles.rowActive : ''}`}
                                        onClick={() => selectLocal(c.id)}>
                                        <div className={styles.contactInfo}>
                                            <div className={styles.avatar}>{initials(c.first_name, c.last_name)}</div>
                                            <div>
                                                <div className={styles.name}>{c.first_name} {c.last_name}</div>
                                                <div className={styles.email}>{c.email}</div>
                                            </div>
                                        </div>
                                        <div className={styles.phone}>{c.phone || '—'}</div>
                                        <div className={styles.aptCount}>
                                            {c.last_apt
                                                ? parseApiDate(c.last_apt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                                                : 'No visits'}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* ── CALL HISTORY TAB ── */}
                        {tab === 'history' && (
                            <div className={styles.tableWrapper}>
                                <table className={styles.historyTable}>
                                    <thead>
                                        <tr>
                                            <th>DATE</th><th>TIME</th><th>LEAD / PHONE</th>
                                            <th>PHONE</th><th>DIRECTION</th><th>OUTCOME</th><th>DURATION</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {callsLoading ? (
                                            <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-4)' }}>Loading...</td></tr>
                                        ) : callHistory.length === 0 ? (
                                            <tr><td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-4)' }}>No calls found.</td></tr>
                                        ) : callHistory.map(call => {
                                            const dt   = call.createdAt ? parseApiDate(call.createdAt) : null;
                                            const mins = Math.floor((call.durationSeconds || 0) / 60);
                                            const secs = (call.durationSeconds || 0) % 60;
                                            return (
                                                <tr key={call.id}>
                                                    <td>{dt ? dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</td>
                                                    <td>{dt ? dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                                                    <td><div className={styles.patientCell}>{call.patientName && call.patientName !== '—' ? call.patientName : call.phone}</div></td>
                                                    <td>{call.phone}</td>
                                                    <td>
                                                        <span className={`${styles.statusBadge} ${call.direction === 'inbound' ? styles.inbound : styles.outbound}`}>
                                                            {call.direction === 'inbound' ? 'Inbound' : 'Outbound'}
                                                        </span>
                                                    </td>
                                                    <td>
                                                        <span className={styles.outcomeBadge}>
                                                            {call.outcome && call.outcome !== '—' ? call.outcome : 'Information'}
                                                        </span>
                                                    </td>
                                                    <td>{call.durationSeconds ? `${mins}m ${secs}s` : '—'}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>

                    {/* RIGHT DETAIL PANEL */}
                    {tab !== 'history' && (
                        <div className={styles.detailPanel}>

                            {/* Lead detail */}
                            {tab === 'leads' && selectedLead ? (
                                <>
                                    <div className={styles.detailHeader}>
                                        <div className={styles.detailAvatar}
                                            style={{ background: (STATUS_COLOR[selectedLead.status] || STATUS_COLOR.new).bg, color: (STATUS_COLOR[selectedLead.status] || STATUS_COLOR.new).color }}>
                                            {initials(selectedLead.first_name, selectedLead.last_name)}
                                        </div>
                                        <div>
                                            <div className={styles.detailName}>{selectedLead.first_name} {selectedLead.last_name}</div>
                                            <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                                                background: (STATUS_COLOR[selectedLead.status] || STATUS_COLOR.new).bg,
                                                color: (STATUS_COLOR[selectedLead.status] || STATUS_COLOR.new).color }}>
                                                {selectedLead.status}
                                            </span>
                                        </div>
                                    </div>
                                    <div className={styles.detailContent}>
                                        <div className={styles.sectionTitle}>Contact Info</div>
                                        <div className={styles.infoList}>
                                            {selectedLead.phone && (
                                                <div className={styles.infoItem}>
                                                    <Phone size={15} className={styles.infoIcon} />
                                                    <div className={styles.infoValue}>{selectedLead.phone}</div>
                                                </div>
                                            )}
                                            {selectedLead.email && (
                                                <div className={styles.infoItem}>
                                                    <Mail size={15} className={styles.infoIcon} />
                                                    <div className={styles.infoValue}>{selectedLead.email}</div>
                                                </div>
                                            )}
                                            <div className={styles.infoItem}>
                                                <MessageCircle size={15} className={styles.infoIcon} />
                                                <div className={styles.infoValue}>{selectedLead.preferred_channel || 'whatsapp'}</div>
                                            </div>
                                            <div className={styles.infoItem}>
                                                <Zap size={15} className={styles.infoIcon} />
                                                <div className={styles.infoValue}>Source: {selectedLead.source || 'manual'}</div>
                                            </div>
                                        </div>

                                        {selectedLead.tags.length > 0 && (
                                            <>
                                                <div className={styles.sectionTitle}>Tags</div>
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '0 1rem 1rem' }}>
                                                    {selectedLead.tags.map(t => (
                                                        <span key={t} style={{ padding: '4px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: 'rgba(212, 169, 79,0.1)', color: 'var(--primary)', border: '1px solid rgba(212, 169, 79,0.2)' }}>
                                                            <Tag size={10} style={{ marginRight: 4, verticalAlign: 'middle' }} />{t}
                                                        </span>
                                                    ))}
                                                </div>
                                            </>
                                        )}

                                        {selectedLead.notes && (
                                            <>
                                                <div className={styles.sectionTitle}>Notes</div>
                                                <div style={{ padding: '0 1rem 1rem', fontSize: 13, color: 'var(--text-3)', fontStyle: 'italic' }}>
                                                    &quot;{selectedLead.notes}&quot;
                                                </div>
                                            </>
                                        )}

                                        <div className={styles.sectionTitle}>Added</div>
                                        <div style={{ padding: '0 1rem 1rem', fontSize: 13, color: 'var(--text-4)' }}>
                                            {parseApiDate(selectedLead.created_at).toLocaleString('en-US', { month: 'long', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                        </div>
                                    </div>
                                </>
                            ) : tab === 'local' && activeLocalContact ? (
                                <>
                                    <div className={styles.detailHeader}>
                                        <div className={styles.detailAvatar}>{initials(activeLocalContact.first_name, activeLocalContact.last_name)}</div>
                                        <div>
                                            <div className={styles.detailName}>{activeLocalContact.first_name} {activeLocalContact.last_name}</div>
                                            <div className={styles.detailMeta}>Added {parseApiDate(activeLocalContact.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</div>
                                        </div>
                                    </div>
                                    <div className={styles.detailContent}>
                                        <div className={styles.sectionTitle}>Contact Info</div>
                                        <div className={styles.infoList}>
                                            <div className={styles.infoItem}>
                                                <Mail size={16} className={styles.infoIcon} />
                                                <div className={styles.infoValue}>{activeLocalContact.email}</div>
                                            </div>
                                            <div className={styles.infoItem}>
                                                <Phone size={16} className={styles.infoIcon} />
                                                <div className={styles.infoValue}>{activeLocalContact.phone || 'Not provided'}</div>
                                            </div>
                                        </div>
                                        <div className={styles.sectionTitle}>Appointments ({activeLocalContact.total})</div>
                                        <div className={styles.appointmentsList}>
                                            {aptLoading === activeLocalContact.id
                                                ? <div className={styles.emptyState}>Loading...</div>
                                                : (aptMap[activeLocalContact.id] || []).length === 0
                                                    ? <div className={styles.emptyState}>No appointments found.</div>
                                                    : (aptMap[activeLocalContact.id] || []).map(a => (
                                                        <div key={a.id} className={styles.aptCard}>
                                                            <div className={styles.aptHeader}>
                                                                <div className={styles.aptDate}>
                                                                    <Calendar size={14} color="var(--text-4)" />
                                                                    {parseApiDate(a.start_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · {parseApiDate(a.start_time).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                                                                </div>
                                                                <div className={`${styles.aptStatus} ${
                                                                    a.status === 'confirmed'  ? styles.statusConfirmed  :
                                                                    a.status === 'completed'  ? styles.statusCompleted  :
                                                                    a.status === 'cancelled'  ? styles.statusCancelled  : styles.statusDefault
                                                                }`}>{a.status}</div>
                                                            </div>
                                                            <div className={styles.aptService}>{a.service_name || 'Unknown Service'}</div>
                                                            {a.provider_name && <div className={styles.aptProvider}>with {a.provider_name}</div>}
                                                        </div>
                                                    ))
                                            }
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <div className={styles.emptyDetail}>
                                    <div>
                                        <User size={32} color="var(--text-4)" style={{ marginBottom: '1rem', opacity: 0.5 }} />
                                        <p>{tab === 'leads' ? 'Select a lead to view details' : 'Select a contact to view details'}</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
