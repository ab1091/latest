'use client';

import { useState, useEffect, useCallback, useRef, useMemo, Suspense } from 'react';
import {
    Users, Plus, Upload, Search,
    MessageCircle, Trash2, RefreshCw, X, Check, Send, Zap, AlertTriangle, Pencil,
    Phone, Mail, Tag, ChevronRight, LayoutGrid, List, RotateCcw, Calendar, Play, Pause
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { useRouter, useSearchParams } from 'next/navigation';
import { DateRangeFilter, DEFAULT_DATE_RANGE, inDateRange, type DateRangeValue } from '@/components/DateRangeFilter/DateRangeFilter';
import { BehaviorFilters, DEFAULT_BEHAVIOR_FILTERS, activeBehaviorFilterCount, type BehaviorFilterValue } from '@/components/BehaviorFilters/BehaviorFilters';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './leads.module.css';


interface Lead {
    id: string;
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    tags: string[];
    // sub_status = internal granular detail; stage = client-facing 5-stage pipeline.
    sub_status: 'new' | 'contacted' | 'stale' | 'responded' | 'follow_up_sent' | 'qualified' | 'quoted' | 'appointment_scheduled' | 'converted' | 'dead';
    stage: 'new_lead' | 'old_lead' | 'connected' | 'quoted' | 'appointment_scheduled' | 'closed' | 'dead';
    strategy: string;
    source: string;
    notes: string;
    agent_id: string | null;
    created_at: string;
    preferred_channel: string;
    policy_type: string;
    score: number;
    score_band: 'hot' | 'warm' | 'cold' | 'new';
    opted_out: boolean;
    has_replied: boolean;
    open_tasks_count: number;
    next_appointment_at: string | null;
    last_appointment_status: string | null;
}

const BAND_COLOR: Record<string, string> = { hot: '#f87171', warm: '#fbbf24', cold: '#7fded0', new: '#89a7a1' };

// sub_status -> stage, mirrors crm-service/core/lead_lifecycle.py STAGE_OF
const STAGE_OF: Record<string, string> = {
    new: 'new_lead', contacted: 'new_lead', follow_up_sent: 'new_lead',
    stale: 'old_lead',
    responded: 'connected', qualified: 'connected',
    quoted: 'quoted', appointment_scheduled: 'appointment_scheduled',
    converted: 'closed', dead: 'dead',
};

// representative sub_status used when a user manually drags a card into a stage column
const STAGE_TO_SUB_STATUS: Record<string, string> = {
    new_lead: 'new', old_lead: 'stale', connected: 'responded', quoted: 'quoted',
    appointment_scheduled: 'appointment_scheduled', closed: 'converted', dead: 'dead',
};

const STATUS_COLORS: Record<string, string> = {
    new_lead:  styles.statusNew,
    old_lead:  styles.statusOld,
    connected: styles.statusContacted,
    quoted:    styles.statusQualified,
    appointment_scheduled: styles.statusQualified,
    closed:    styles.statusConverted,
    dead:      styles.statusDead,
};

const STATUS_LABELS: Record<string, string> = {
    new_lead: 'New Lead', old_lead: 'Old Lead', connected: 'Connected', quoted: 'Quoted',
    appointment_scheduled: 'Appointment Scheduled',
    closed: 'Closed', dead: 'Trip Lead',
};

// "Old Lead" isn't real pipeline progress — it's just a New Lead that went
// stale — so it's folded into the New Lead column as a badge (see cardTags
// below) rather than getting its own column. The stage value itself is
// unchanged on the backend; this is a display-only simplification.
const PIPELINE_COLUMNS = [
    { key: 'new_lead',  label: 'New Lead',  color: '#818cf8', bg: 'rgba(99,102,241,0.08)'  },
    { key: 'connected', label: 'Connected', color: '#38bdf8', bg: 'rgba(56,189,248,0.08)' },
    { key: 'quoted',    label: 'Quoted',    color: '#34d399', bg: 'rgba(16,185,129,0.08)' },
    { key: 'appointment_scheduled', label: 'Appt Scheduled', color: '#a78bfa', bg: 'rgba(167,139,250,0.08)' },
    { key: 'closed',    label: 'Closed',    color: '#e8c877', bg: 'rgba(185, 134, 42,0.08)' },
    { key: 'dead',      label: 'Trip Lead', color: '#f87171', bg: 'rgba(248,113,113,0.08)' },
];

export default function LeadsPage() {
    return (
        <Suspense fallback={null}>
            <LeadsPageContent />
        </Suspense>
    );
}

function LeadsPageContent() {
    const { accessToken, user, isLoading, refreshToken } = useAuth();
    const router = useRouter();
    const searchParams = useSearchParams();
    const [leads, setLeads] = useState<Lead[]>([]);
    const [viewMode, setViewMode] = useState<'pipeline' | 'list'>(searchParams.get('view') === 'list' ? 'list' : 'pipeline');
    const [draggedId, setDraggedId] = useState<string | null>(null);
    const [draggingOver, setDraggingOver] = useState<string | null>(null);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'leads', 'staff')) {
            router.replace('/user/leads');
        }
    }, [isLoading, accessToken, user, router]);

    const [loading, setLoading] = useState(false);
    const [search, setSearch] = useState('');
    const [filterStatus, setFilterStatus] = useState('');
    // ?status= drives the initial value — lets the dashboard's Converted/
    // Qualified/Not Interested tiles link straight to that exact sub_status
    // instead of the broader (and coarser) pipeline stage.
    const [filterSubStatus] = useState(searchParams.get('status') || '');
    const [filterTag, setFilterTag] = useState('');
    const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_DATE_RANGE);
    const [behaviorFilters, setBehaviorFilters] = useState<BehaviorFilterValue>(DEFAULT_BEHAVIOR_FILTERS);

    // Bulk SMS
    const [selected,    setSelected]    = useState<Set<string>>(new Set());
    const [showBulk,    setShowBulk]    = useState(false);
    const [bulkMsg,     setBulkMsg]     = useState('');
    const [bulkSending, setBulkSending] = useState(false);
    const [bulkResult,  setBulkResult]  = useState<any>(null);

    // CSV import
    const [showImport,    setShowImport]    = useState(false);
    const [importing,     setImporting]     = useState(false);
    const [importResult,  setImportResult]  = useState<any>(null);
    const [updateExisting,setUpdateExisting]= useState(false);
    // Column-mapping step — lets the user pick which sheet column is which
    // field (phone especially) instead of relying on guessed header names,
    // since sheets often use headers like "Mobile Number" or "Full Name"
    // that don't auto-match and used to silently import with no phone at all.
    const [pendingFile,  setPendingFile]  = useState<File | null>(null);
    const [previewing,   setPreviewing]   = useState(false);
    const [preview,      setPreview]      = useState<{ headers: string[]; sample_rows: any[]; total_rows: number } | null>(null);
    const [colMap,       setColMap]       = useState<Record<string, string>>({});
    const fileRef = useRef<HTMLInputElement>(null);

    // Add lead modal
    const [showAdd, setShowAdd] = useState(false);
    const [addForm, setAddForm] = useState({
        first_name: '', last_name: '', email: '', phone: '',
        tags: '', notes: '', auto_sms: true, preferred_channel: 'sms', policy_type: ''
    });
    const [adding,         setAdding]         = useState(false);
    const [duplicatePopup, setDuplicatePopup] = useState(false);

    // Edit lead modal
    const [editLead, setEditLead] = useState<Lead | null>(null);
    const [editForm, setEditForm] = useState({
        first_name: '', last_name: '', email: '', phone: '',
        tags: '', notes: '', status: 'new', strategy: '', policy_type: ''
    });
    const [saving, setSaving] = useState(false);

    const h = useMemo(() => ({ Authorization: `Bearer ${accessToken}` }), [accessToken]);

    // Automation on/off — pauses/resumes the workflow(s) that auto-enroll
    // new leads (e.g. the CSV-import flow), so a large upload doesn't fire
    // outreach until the user is ready. Backed by the same toggle as the
    // Automation "Quick Setup" page (sms_auto_enabled).
    const [autoEnabled, setAutoEnabled] = useState<boolean | null>(null);
    const [autoToggling, setAutoToggling] = useState(false);

    const loadAutomation = useCallback(async () => {
        if (!accessToken) return;
        try {
            const res = await fetch('/api/automation-settings', { headers: h });
            const d = await res.json();
            if (d.success) setAutoEnabled(!!d.data.settings.sms_auto_enabled);
        } catch {}
    }, [accessToken, h]);

    useEffect(() => { loadAutomation(); }, [loadAutomation]);

    const toggleAutomation = async () => {
        if (!accessToken || autoEnabled === null || autoToggling) return;
        const next = !autoEnabled;
        if (!next && !confirm('Stop automation? New leads (including CSV imports) will no longer receive automatic texts/calls until you turn it back on.')) return;
        setAutoToggling(true);
        try {
            const res = await fetch('/api/automation-settings', {
                method: 'PATCH',
                headers: { ...h, 'Content-Type': 'application/json' },
                body: JSON.stringify({ sms_auto_enabled: next }),
            });
            const d = await res.json();
            if (d.success) setAutoEnabled(!!d.data.settings.sms_auto_enabled);
        } catch {}
        setAutoToggling(false);
    };

    const load = useCallback(async (opts?: { silent?: boolean }) => {
        if (!accessToken) return;
        if (!opts?.silent) setLoading(true);
        try {
            let url = `/api/leads`;
            const params = new URLSearchParams();
            if (filterStatus)    params.set('stage', filterStatus);
            if (filterSubStatus) params.set('status', filterSubStatus);
            if (filterTag)    params.set('tag', filterTag);
            if (behaviorFilters.scoreBand)   params.set('score_band', behaviorFilters.scoreBand);
            if (behaviorFilters.engagement)  params.set('engagement', behaviorFilters.engagement);
            if (behaviorFilters.followUp)    params.set('follow_up', behaviorFilters.followUp);
            if (behaviorFilters.appointment) params.set('appointment', behaviorFilters.appointment);
            if (behaviorFilters.optedOut)    params.set('opted_out', behaviorFilters.optedOut);
            if (params.toString()) url += '?' + params.toString();
            const res = await fetch(url, { headers: h });
            if (res.status === 401) {
                // The board previously swallowed expired-session responses and
                // kept rendering its last successful snapshot forever. Refresh
                // auth; the new accessToken will change `load` and trigger the
                // normal effect above to fetch authoritative stage data again.
                await refreshToken();
            } else {
                if (!res.ok) throw new Error(`Failed to load leads (${res.status})`);
                const d = await res.json();
                if (d.success) setLeads(d.data.leads);
            }
        } catch {}
        if (!opts?.silent) setLoading(false);
    }, [accessToken, filterStatus, filterSubStatus, filterTag, behaviorFilters, h, refreshToken]);

    useEffect(() => { load(); }, [load]);

    // Background auto-refresh — the board has no live/websocket updates, so
    // without this a lead that moves stage (e.g. New Lead -> Connected the
    // moment they reply) just sits stale in its old column until someone
    // happens to change a filter or hit the manual refresh button. `silent`
    // skips the loading-spinner/flicker so it doesn't interrupt whoever's
    // looking at the board.
    useEffect(() => {
        if (!accessToken) return;
        const id = setInterval(() => {
            if (draggedId) return; // don't yank the board out from under an in-progress drag
            load({ silent: true });
        }, 8000);
        return () => clearInterval(id);
    }, [accessToken, load, draggedId]);

    const allTags = Array.from(new Set(leads.flatMap(l => l.tags)));

    const filtered = leads.filter(l => {
        const q = search.toLowerCase();
        const matchesSearch = !q ||
            `${l.first_name} ${l.last_name}`.toLowerCase().includes(q) ||
            l.email.toLowerCase().includes(q) ||
            l.phone.includes(q) ||
            l.tags.some(t => t.toLowerCase().includes(q));
        return matchesSearch && inDateRange(l.created_at, dateRange);
    });

    const initials = (l: Lead) =>
        `${l.first_name?.[0] || ''}${l.last_name?.[0] || ''}`.toUpperCase() || '?';

    // ── Drag & Drop ──────────────────────────────────────────────────────────
    const handleDragStart = (leadId: string) => setDraggedId(leadId);
    const handleDragOver  = (e: React.DragEvent, colKey: string) => {
        e.preventDefault();
        setDraggingOver(colKey);
    };
    const handleDrop = async (e: React.DragEvent, colKey: string) => {
        e.preventDefault();
        setDraggingOver(null);
        if (!draggedId) return;
        const lead = leads.find(l => l.id === draggedId);
        if (!lead || lead.stage === colKey) { setDraggedId(null); return; }
        const toSubStatus = STAGE_TO_SUB_STATUS[colKey] || 'new';
        setLeads(prev => prev.map(l => l.id === draggedId ? { ...l, stage: colKey as any, sub_status: toSubStatus as any } : l));
        setDraggedId(null);
        try {
            // Manual drag is an explicit override — force=true bypasses the
            // state machine's normal transition validation.
            await fetch(`/api/leads/${draggedId}/transition`, {
                method: 'POST',
                headers: { ...h, 'Content-Type': 'application/json' },
                body: JSON.stringify({ event: 'manual_override', to_sub_status: toSubStatus, force: true }),
            });
        } catch { load(); }
    };

    // ── CRUD ─────────────────────────────────────────────────────────────────
    const MAPPING_FIELD_LABELS: [string, string][] = [
        ['first_name',  'First Name'],
        ['last_name',   'Last Name'],
        ['phone',       'Phone'],
        ['email',       'Email'],
        ['tags',        'Tags'],
        ['status',      'Status'],
        ['notes',       'Notes'],
        ['policy_type', 'Policy Type'],
    ];

    // Step 1: pick a file → parse it server-side and show the detected
    // columns with a best-guess mapping, so the user can fix any column
    // (phone especially) the guess got wrong before anything is imported.
    const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setPendingFile(file);
        setPreviewing(true); setImportResult(null); setPreview(null);
        const form = new FormData();
        form.append('file', file);
        try {
            const res = await fetch(`/api/leads/import/preview`, { method: 'POST', headers: h, body: form });
            const d = await res.json().catch(() => null);
            if (!res.ok || !d?.success) {
                const message = res.status === 401
                    ? 'Your session has expired. Sign in again, then retry the import.'
                    : d?.detail || d?.error || `Could not read this file (server returned ${res.status}).`;
                setImportResult({ error: message });
                setPendingFile(null);
            } else {
                setPreview(d.data);
                setColMap(d.data.guesses || {});
            }
        } catch (err: any) {
            setImportResult({ error: err?.message || 'Could not reach the server. Please try again.' });
            setPendingFile(null);
        }
        setPreviewing(false);
        if (fileRef.current) fileRef.current.value = '';
    };

    // Step 2: confirm the mapping → actually create the leads.
    const confirmImport = async () => {
        if (!pendingFile) return;
        setImporting(true); setImportResult(null);
        const form = new FormData();
        form.append('file', pendingFile);
        form.append('update_existing', updateExisting ? 'true' : 'false');
        form.append('mapping', JSON.stringify(colMap));
        try {
            const res = await fetch(`/api/leads/import`, { method: 'POST', headers: h, body: form });
            const d = await res.json().catch(() => null);
            if (!res.ok || !d?.success) {
                const message = res.status === 401
                    ? 'Your session has expired. Sign in again, then retry the import.'
                    : d?.detail || d?.error || `Import failed (server returned ${res.status}).`;
                setImportResult({ error: message });
            } else {
                setImportResult(d.data);
                load();
            }
        } catch (err: any) {
            setImportResult({ error: err?.message || 'Could not reach the server. Please try again.' });
        }
        setImporting(false);
        setPendingFile(null);
        setPreview(null);
    };

    const cancelMapping = () => {
        setPendingFile(null);
        setPreview(null);
        setColMap({});
    };

    const handleAdd = async () => {
        setAdding(true);
        try {
            const tags = addForm.tags.split(',').map(t => t.trim()).filter(Boolean);
            const res = await fetch(`/api/leads`, {
                method: 'POST',
                headers: { ...h, 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...addForm, tags }),
            });
            if (res.status === 409) { setDuplicatePopup(true); setAdding(false); return; }
            const d = await res.json();
            if (d.success) {
                setShowAdd(false);
                setAddForm({ first_name: '', last_name: '', email: '', phone: '', tags: '', notes: '', auto_sms: true, preferred_channel: 'sms', policy_type: '' });
                load();
            }
        } catch {}
        setAdding(false);
    };

    const openEdit = (lead: Lead) => {
        setEditLead(lead);
        setEditForm({
            first_name: lead.first_name, last_name: lead.last_name,
            email: lead.email, phone: lead.phone,
            tags: lead.tags.join(', '), notes: lead.notes || '',
            status: lead.sub_status, strategy: lead.strategy || '',
            policy_type: lead.policy_type || '',
        });
    };

    const handleSaveEdit = async () => {
        if (!editLead) return;
        setSaving(true);
        try {
            const tags = editForm.tags.split(',').map(t => t.trim()).filter(Boolean);
            const res = await fetch(`/api/leads/${editLead.id}`, {
                method: 'PATCH',
                headers: { ...h, 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...editForm, tags }),
            });
            const d = await res.json();
            if (d.success) { setEditLead(null); load(); }
        } catch {}
        setSaving(false);
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Delete this lead?')) return;
        await fetch(`/api/leads/${id}`, { method: 'DELETE', headers: h });
        load();
    };

    const toggleSelect    = (id: string) =>
        setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleSelectAll = () =>
        setSelected(selected.size === filtered.length ? new Set() : new Set(filtered.map(l => l.id)));

    const deleteSelected = async () => {
        if (!confirm(`Delete ${selected.size} selected lead${selected.size > 1 ? 's' : ''}?`)) return;
        await Promise.all(Array.from(selected).map(id => fetch(`/api/leads/${id}`, { method: 'DELETE', headers: h })));
        setSelected(new Set()); load();
    };

    const sendBulkSMS = async () => {
        setBulkSending(true); setBulkResult(null);
        let sent = 0, failed = 0;
        for (const lead_id of Array.from(selected)) {
            try {
                const res = await fetch(`/api/sms/send`, {
                    method: 'POST',
                    headers: { ...h, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lead_id, message: bulkMsg || undefined }),
                });
                (await res.json()).success ? sent++ : failed++;
            } catch { failed++; }
        }
        setBulkResult({ sent, failed });
        setBulkSending(false);
        if (sent > 0) { setSelected(new Set()); load(); }
    };

    const openChat = async (lead: Lead) => {
        const res = await fetch(`/api/conversations`, {
            method: 'POST',
            headers: { ...h, 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_id: lead.id }),
        });
        const d = await res.json();
        if (d.success) router.push(`/conversations?conv=${d.data.conversation.id}`);
    };

    const clearAllData = async () => {
        if (!confirm('⚠️ Delete ALL leads and conversations? This cannot be undone.')) return;
        try { await fetch(`/api/leads/clear-all`, { method: 'DELETE', headers: h }); load(); } catch {}
    };

    // ─────────────────────────────────────────────────────────────────────────
    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>

                {/* ── Header ── */}
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Users size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>Leads</h1>
                        <p>{leads.length} contacts in your pipeline</p>
                    </div>
                    <div className={styles.headerActions}>
                        {leads.length > 0 && (
                            <button className={styles.btnDanger} onClick={clearAllData}>
                                <AlertTriangle size={15} /> Clear All
                            </button>
                        )}
                        {autoEnabled !== null && (
                            <button
                                className={autoEnabled ? styles.btnSecondary : styles.btnDanger}
                                onClick={toggleAutomation}
                                disabled={autoToggling}
                                title={autoEnabled
                                    ? 'Automation is running — new leads get automatic texts/calls'
                                    : 'Automation is stopped — new leads will NOT get automatic texts/calls'}
                            >
                                {autoEnabled ? <Pause size={15} /> : <Play size={15} />}
                                {autoToggling ? 'Updating...' : autoEnabled ? 'Stop Automation' : 'Start Automation'}
                            </button>
                        )}
                        <button className={styles.btnSecondary} onClick={() => setShowImport(true)}>
                            <Upload size={15} /> Import CSV
                        </button>
                        <button className={styles.btnPrimary} onClick={() => setShowAdd(true)}>
                            <Plus size={15} /> Add Lead
                        </button>
                    </div>
                </div>

                {/* ── Toolbar: view toggle + search + filters ── */}
                <div className={styles.toolbar}>
                    {/* Pipeline / List toggle */}
                    <div className={styles.viewToggle}>
                        <button
                            className={viewMode === 'pipeline' ? styles.viewBtnActive : styles.viewBtn}
                            onClick={() => setViewMode('pipeline')}
                        >
                            <LayoutGrid size={14} /> Pipeline
                        </button>
                        <button
                            className={viewMode === 'list' ? styles.viewBtnActive : styles.viewBtn}
                            onClick={() => setViewMode('list')}
                        >
                            <List size={14} /> Leads
                        </button>
                    </div>

                    {/* Search */}
                    <div className={styles.searchBox}>
                        <Search size={15} />
                        <input
                            className={styles.searchInput}
                            placeholder="Search by name, email, phone or tag..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                        />
                        {search && (
                            <button onClick={() => setSearch('')} className={styles.clearSearch}>
                                <X size={13} />
                            </button>
                        )}
                    </div>

                    {/* Tag filter */}
                    {allTags.length > 0 && (
                        <select className={styles.filterSelect} value={filterTag}
                            onChange={e => setFilterTag(e.target.value)}>
                            <option value="">All Tags</option>
                            {allTags.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                    )}

                    {/* Status filter — list mode only */}
                    {viewMode === 'list' && (
                        <select className={styles.filterSelect} value={filterStatus}
                            onChange={e => setFilterStatus(e.target.value)}>
                            <option value="">All Statuses</option>
                            {Object.entries(STATUS_LABELS).map(([v, l]) => (
                                <option key={v} value={v}>{l}</option>
                            ))}
                        </select>
                    )}

                    <BehaviorFilters value={behaviorFilters} onChange={setBehaviorFilters} />

                    <DateRangeFilter value={dateRange} onChange={setDateRange} />

                    <button className={styles.btnSecondary} style={{ gap: 6, whiteSpace: 'nowrap', padding: '0.5rem 1rem' }}>
                        <RotateCcw size={13} /> Smart Cycle
                    </button>

                    <button className={styles.refreshBtn} onClick={() => load()}>
                        <RefreshCw size={14} className={loading ? styles.spin : ''} />
                    </button>
                </div>

                {/* ── Bulk action bar ── */}
                {selected.size > 0 && (
                    <div className={styles.bulkBar}>
                        <span>{selected.size} lead{selected.size > 1 ? 's' : ''} selected</span>
                        <button onClick={() => setShowBulk(true)} className={styles.btnBulk}>
                            <Send size={13} /> Bulk SMS
                        </button>
                        <button onClick={deleteSelected} style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                            background: '#ef4444', color: '#fff', fontSize: 13, fontWeight: 600,
                        }}>
                            <Trash2 size={14} /> Delete Selected
                        </button>
                    </div>
                )}

                {/* ══════════════════════════════════════════════════
                    PIPELINE (KANBAN) VIEW
                ══════════════════════════════════════════════════ */}
                {viewMode === 'pipeline' && (
                    <div
                        className={styles.kanbanBoard}
                        style={{ gridTemplateColumns: `repeat(${PIPELINE_COLUMNS.length}, 1fr)` }}
                    >
                        {PIPELINE_COLUMNS.map(col => {
                            // New Lead column also absorbs old_lead cards (see note above).
                            const colLeads = filtered.filter(l =>
                                col.key === 'new_lead' ? (l.stage === 'new_lead' || l.stage === 'old_lead') : l.stage === col.key
                            );
                            const isOver   = draggingOver === col.key;
                            return (
                                <div
                                    key={col.key}
                                    className={styles.kanbanCol}
                                    style={{
                                        borderTopColor: col.color,
                                        borderColor:  isOver ? col.color : undefined,
                                        background:   isOver ? col.bg   : undefined,
                                        boxShadow:    isOver ? `0 0 0 2px ${col.color}44` : undefined,
                                    }}
                                    onDragOver={e => handleDragOver(e, col.key)}
                                    onDrop={e => handleDrop(e, col.key)}
                                    onDragLeave={() => setDraggingOver(null)}
                                >
                                    {/* Column header */}
                                    <div className={styles.colHeader} style={{ background: `linear-gradient(180deg, ${col.bg}, transparent)` }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <div className={styles.colDot} style={{ background: col.color, boxShadow: `0 0 0 4px ${col.color}22` }} />
                                            <span className={styles.colTitle}>{col.label}</span>
                                        </div>
                                        <span className={styles.colCount} style={{ background: col.bg, color: col.color }}>
                                            {colLeads.length}
                                        </span>
                                    </div>

                                    {/* Cards */}
                                    <div className={styles.cardList}>
                                        {colLeads.length === 0 ? (
                                            <div className={styles.emptyCol} style={{ background: col.bg, borderColor: `${col.color}33`, color: col.color }}>
                                                <Users size={20} strokeWidth={1.5} style={{ opacity: 0.55 }} />
                                                <span>No leads here yet</span>
                                            </div>
                                        ) : colLeads.map((lead, idx) => (
                                            <div
                                                key={lead.id}
                                                className={styles.card}
                                                style={{
                                                    opacity: draggedId === lead.id ? 0.4 : 1,
                                                    ...(lead.score_band === 'hot' ? { minHeight: 150, borderLeft: `3px solid ${BAND_COLOR.hot}` } : {}),
                                                }}
                                                draggable
                                                onDragStart={() => handleDragStart(lead.id)}
                                                onClick={() => router.push(`/leads/${lead.id}`)}
                                            >
                                                {/* Avatar + name */}
                                                <div className={styles.cardTop}>
                                                    <div className={styles.cardAvatarWrap}>
                                                        <div className={styles.cardAvatar} title={`${lead.score_band} lead · score ${lead.score}`} style={{ background: col.bg, color: col.color, borderColor: `${col.color}33`, boxShadow: `0 0 0 2px ${BAND_COLOR[lead.score_band] || BAND_COLOR.new}` }}>
                                                            {initials(lead)}
                                                        </div>
                                                        <div className={styles.cardNum}>{idx + 1}</div>
                                                    </div>
                                                    <div className={styles.cardInfo}>
                                                        <div className={styles.cardName}>
                                                            {lead.first_name} {lead.last_name}
                                                        </div>
                                                    </div>
                                                    <div className={styles.cardActions} onClick={e => e.stopPropagation()}>
                                                        <button className={styles.cardIconBtn} style={{ color: '#a78bfa', background: 'rgba(139,92,246,0.18)', border: '1px solid rgba(139,92,246,0.35)' }}
                                                            title="Chat" onClick={() => openChat(lead)}>
                                                            <MessageCircle size={12} />
                                                        </button>
                                                        <button className={styles.cardIconBtn} style={{ color: '#818cf8', background: 'rgba(99,102,241,0.18)', border: '1px solid rgba(99,102,241,0.35)' }}
                                                            title="Edit" onClick={() => openEdit(lead)}>
                                                            <Pencil size={12} />
                                                        </button>
                                                    </div>
                                                </div>

                                                {/* Behavior badges */}
                                                {(lead.opted_out || lead.open_tasks_count > 0 || lead.next_appointment_at || !lead.has_replied || lead.stage === 'old_lead') && (
                                                    <div className={styles.cardTags}>
                                                        {lead.opted_out && (
                                                            <span className={styles.cardTag} style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>Do Not Contact</span>
                                                        )}
                                                        {lead.open_tasks_count > 0 && (
                                                            <span className={styles.cardTag} style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}>Follow-up needed</span>
                                                        )}
                                                        {lead.next_appointment_at && (
                                                            <span className={styles.cardTag} style={{ background: 'rgba(56,189,248,0.15)', color: '#38bdf8' }}>Appt booked</span>
                                                        )}
                                                        {lead.stage === 'old_lead' ? (
                                                            <span className={styles.cardTag} style={{ background: 'rgba(251,146,60,0.15)', color: '#fb923c' }}>Stale — no reply 24h+</span>
                                                        ) : (!lead.has_replied && !lead.opted_out && (
                                                            lead.stage === 'new_lead' ? (
                                                                <span className={styles.cardTag} style={{ background: 'rgba(148,163,184,0.15)', color: '#94a3b8' }}>No reply yet</span>
                                                            ) : (
                                                                // Reached this stage with no text reply on file — the only other way in
                                                                // is a real answered-call conversation (see lead_lifecycle.py's
                                                                // call_outcome_engaged event). Label it accurately instead of implying
                                                                // nothing happened.
                                                                <span className={styles.cardTag} style={{ background: 'rgba(34,211,238,0.15)', color: '#22d3ee' }}>Talked on call</span>
                                                            )
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* ══════════════════════════════════════════════════
                    LIST (TABLE) VIEW
                ══════════════════════════════════════════════════ */}
                {viewMode === 'list' && (
                    <>
                        {/* Status quick-filter tabs — mirrors the actual pipeline stages/colors */}
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {([{ key: '', label: 'All', color: 'var(--accent)' }, ...PIPELINE_COLUMNS] as { key: string; label: string; color: string }[]).map(({ key, label, color }) => {
                                const count    = key === '' ? leads.length : leads.filter(l => l.stage === key).length;
                                const isActive = filterStatus === key;
                                return (
                                    <button key={key} onClick={() => setFilterStatus(key)} style={{
                                        padding: '5px 14px', borderRadius: 20, border: 'none', cursor: 'pointer',
                                        fontSize: 13, fontWeight: isActive ? 600 : 500,
                                        background: isActive ? color : `${color}22`,
                                        color: isActive ? '#fff' : color,
                                        boxShadow: isActive ? '0 2px 8px rgba(0,0,0,0.15)' : 'none',
                                    }}>
                                        {label} <span style={{ opacity: 0.8, fontSize: 11 }}>({count})</span>
                                    </button>
                                );
                            })}
                        </div>

                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th style={{ width: '36px' }}>#</th>
                                        <th style={{ width: '40px' }}>
                                            <input type="checkbox"
                                                checked={filtered.length > 0 && selected.size === filtered.length}
                                                onChange={toggleSelectAll} />
                                        </th>
                                        <th>Lead</th>
                                        <th>Status</th>
                                        <th>Behavior</th>
                                        <th>Strategy</th>
                                        <th>Policy Type</th>
                                        <th>Phone</th>
                                        <th>Tags</th>
                                        <th>Edit</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr><td colSpan={10} className={styles.empty}>Loading...</td></tr>
                                    ) : filtered.length === 0 ? (
                                        <tr><td colSpan={10} className={styles.empty}>No leads found. Import a CSV or add manually.</td></tr>
                                    ) : filtered.map((lead, idx) => (
                                        <tr key={lead.id} className={`${styles.row} ${selected.has(lead.id) ? styles.rowSelected : ''}`}>
                                            <td style={{ color: 'var(--text-4)', fontSize: 12, fontWeight: 600 }}>{idx + 1}</td>
                                            <td onClick={e => e.stopPropagation()}>
                                                <input type="checkbox"
                                                    checked={selected.has(lead.id)}
                                                    onChange={() => toggleSelect(lead.id)} />
                                            </td>
                                            <td onClick={() => router.push(`/leads/${lead.id}`)} style={{ cursor: 'pointer' }}>
                                                <div className={styles.leadCell}>
                                                    <div className={styles.avatar} title={`${lead.score_band} lead · score ${lead.score}`} style={{ boxShadow: `0 0 0 2px ${BAND_COLOR[lead.score_band] || BAND_COLOR.new}` }}>{initials(lead)}</div>
                                                    <div>
                                                        <div className={styles.leadName} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                                            {lead.first_name} {lead.last_name}
                                                            <ChevronRight size={12} style={{ opacity: 0.4 }} />
                                                        </div>
                                                        <div className={styles.leadEmail}>{lead.email || lead.phone}</div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td>
                                                <span className={`${styles.statusBadge} ${STATUS_COLORS[lead.stage] || ''}`}>
                                                    {STATUS_LABELS[lead.stage] || lead.stage}
                                                </span>
                                            </td>
                                            <td>
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, maxWidth: 160 }}>
                                                    {lead.opted_out && (
                                                        <span className={styles.cardTag} style={{ background: 'rgba(239,68,68,0.15)', color: '#f87171' }}>DNC</span>
                                                    )}
                                                    {lead.open_tasks_count > 0 && (
                                                        <span className={styles.cardTag} style={{ background: 'rgba(251,191,36,0.15)', color: '#fbbf24' }}>Follow-up</span>
                                                    )}
                                                    {lead.next_appointment_at && (
                                                        <span className={styles.cardTag} style={{ background: 'rgba(56,189,248,0.15)', color: '#38bdf8' }}>Appt</span>
                                                    )}
                                                    {!lead.has_replied && !lead.opted_out && (
                                                        <span className={styles.cardTag} style={{ background: 'rgba(148,163,184,0.15)', color: '#94a3b8' }}>No reply</span>
                                                    )}
                                                </div>
                                            </td>
                                            <td className={styles.strategyCell}>{lead.strategy || '—'}</td>
                                            <td className={styles.strategyCell}>{lead.policy_type || '—'}</td>
                                            <td className={styles.phoneCell}>{lead.phone || '—'}</td>
                                            <td>
                                                <div className={styles.tagsList}>
                                                    {lead.tags.length === 0
                                                        ? <span className={styles.noTags}>—</span>
                                                        : lead.tags.map(t => <span key={t} className={styles.tag}>{t}</span>)}
                                                </div>
                                            </td>
                                            <td onClick={e => e.stopPropagation()}>
                                                <button className={styles.chatBtn} onClick={() => openEdit(lead)}
                                                    style={{ background: 'rgba(99,102,241,0.18)', border: '1px solid rgba(99,102,241,0.35)', color: '#818cf8' }}>
                                                    <Pencil size={14} />
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </>
                )}
            </div>

            {/* ══ Import CSV Modal ══ */}
            {showImport && (
                <div className={styles.modalOverlay} onClick={() => { setShowImport(false); cancelMapping(); }}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2>{preview ? 'Map Your Columns' : 'Import Leads via CSV'}</h2>
                            <button className={styles.closeBtn} onClick={() => { setShowImport(false); cancelMapping(); }}><X size={18} /></button>
                        </div>
                        <div className={styles.modalBody}>
                            {!preview ? (
                                <>
                                    <div className={styles.csvNote}>
                                        <p>Any column headers work — you&apos;ll pick which column is which field next.</p>
                                    </div>
                                    {(user?.role === 'admin' || user?.role === 'super_admin') && (
                                        <div className={styles.toggleRow} style={{ borderColor: updateExisting ? 'rgba(99,102,241,0.3)' : 'var(--border)', background: updateExisting ? 'rgba(99,102,241,0.08)' : 'rgba(107,114,128,0.06)' }}
                                            onClick={() => setUpdateExisting(v => !v)}>
                                            <div>
                                                <div className={styles.toggleLabel}>Update existing leads</div>
                                                <div className={styles.toggleDesc}>{updateExisting ? 'Existing leads (matched by phone) will be updated' : 'Existing leads will be skipped (default)'}</div>
                                            </div>
                                            <div className={styles.toggle} style={{ background: updateExisting ? '#6366f1' : '#4b5563' }}>
                                                <div className={styles.toggleThumb} style={{ left: updateExisting ? 21 : 3 }} />
                                            </div>
                                        </div>
                                    )}
                                    <label className={styles.fileLabel}>
                                        <Upload size={20} />
                                        {previewing ? 'Reading file...' : 'Choose CSV or Excel file'}
                                        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" hidden onChange={handleFileSelected} disabled={previewing} />
                                    </label>
                                    {importResult && (
                                        <div className={styles.importResult}>
                                            {importResult.error ? (
                                                <p className={styles.importError}>{importResult.error}</p>
                                            ) : (
                                                <>
                                                    <p className={styles.importSuccess}>
                                                        <Check size={14} />
                                                        {importResult.created > 0 && `${importResult.created} leads created`}
                                                        {importResult.updated > 0 && `, ${importResult.updated} updated`}
                                                        {importResult.skipped > 0 && `, ${importResult.skipped} skipped`}
                                                    </p>
                                                    {importResult.errors?.length > 0 && (
                                                        <ul className={styles.importErrors}>
                                                            {importResult.errors.map((msg: string, idx: number) => (
                                                                <li key={idx}>{msg}</li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    )}
                                </>
                            ) : (
                                <>
                                    <div className={styles.csvNote}>
                                        <p>Found <strong>{preview.total_rows}</strong> row{preview.total_rows === 1 ? '' : 's'} in <strong>{pendingFile?.name}</strong>. Pick which column is which — <strong>Phone</strong> is required, the rest are optional.</p>
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, margin: '12px 0' }}>
                                        {MAPPING_FIELD_LABELS.map(([field, label]) => (
                                            <div key={field} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                <div style={{ width: 90, fontSize: 13, color: 'var(--text-2)', flexShrink: 0 }}>
                                                    {label}{field === 'phone' && <span style={{ color: '#f87171' }}> *</span>}
                                                </div>
                                                <select
                                                    className={styles.filterSelect}
                                                    style={{ flex: 1 }}
                                                    value={colMap[field] || ''}
                                                    onChange={e => setColMap(prev => ({ ...prev, [field]: e.target.value }))}
                                                >
                                                    <option value="">— Don&apos;t import —</option>
                                                    {preview.headers.map(hcol => (
                                                        <option key={hcol} value={hcol}>{hcol}</option>
                                                    ))}
                                                </select>
                                            </div>
                                        ))}
                                    </div>
                                    {preview.sample_rows.length > 0 && (
                                        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>
                                            <div style={{ marginBottom: 4 }}>Preview of first row:</div>
                                            <div style={{ background: 'rgba(107,114,128,0.08)', borderRadius: 8, padding: 8, fontFamily: 'monospace', overflowX: 'auto', whiteSpace: 'nowrap' }}>
                                                {colMap.phone
                                                    ? `phone → "${preview.sample_rows[0][colMap.phone] || '(empty)'}"`
                                                    : <span style={{ color: '#f87171' }}>No phone column selected — imported leads won&apos;t have a phone number</span>}
                                            </div>
                                        </div>
                                    )}
                                    {importResult && (
                                        <div className={styles.importResult}>
                                            {importResult.error ? (
                                                <p className={styles.importError}>{importResult.error}</p>
                                            ) : (
                                                <>
                                                    <p className={styles.importSuccess}>
                                                        <Check size={14} />
                                                        {importResult.created > 0 && `${importResult.created} leads created`}
                                                        {importResult.updated > 0 && `, ${importResult.updated} updated`}
                                                        {importResult.skipped > 0 && `, ${importResult.skipped} skipped`}
                                                    </p>
                                                    {importResult.errors?.length > 0 && (
                                                        <ul className={styles.importErrors}>
                                                            {importResult.errors.map((msg: string, idx: number) => (
                                                                <li key={idx}>{msg}</li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                </>
                                            )}
                                        </div>
                                    )}
                                    {!importResult && (
                                        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                                            <button className={styles.btnSecondary} onClick={cancelMapping} disabled={importing}>
                                                Back
                                            </button>
                                            <button className={styles.btnPrimary} onClick={confirmImport} disabled={importing || !colMap.phone}>
                                                {importing ? 'Importing...' : `Import ${preview.total_rows} Lead${preview.total_rows === 1 ? '' : 's'}`}
                                            </button>
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* ══ Bulk SMS Modal ══ */}
            {showBulk && (
                <div className={styles.modalOverlay} onClick={() => setShowBulk(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2>Send SMS Campaign</h2>
                            <button className={styles.closeBtn} onClick={() => setShowBulk(false)}><X size={18} /></button>
                        </div>
                        <div className={styles.modalBody}>
                            <div className={styles.csvNote}>
                                <p>Sending to <strong>{selected.size} lead{selected.size > 1 ? 's' : ''}</strong></p>
                                <p>Leave message empty → AI generates opening message per lead automatically</p>
                            </div>
                            <div className={styles.formGroupFull}>
                                <label>Custom Message (optional)</label>
                                <textarea className={styles.textarea} rows={4}
                                    placeholder="Hi {name}, we noticed you're interested in..."
                                    value={bulkMsg} onChange={e => setBulkMsg(e.target.value)} />
                            </div>
                            {bulkResult && (
                                <div className={styles.importResult}>
                                    <p className={styles.importSuccess}>
                                        <Check size={14} /> {bulkResult.sent} SMS sent
                                        {bulkResult.failed > 0 && `, ${bulkResult.failed} failed`}
                                    </p>
                                </div>
                            )}
                            <div className={styles.modalFooter}>
                                <button className={styles.btnSecondary} onClick={() => setShowBulk(false)}>Cancel</button>
                                <button className={styles.btnBulk} onClick={sendBulkSMS} disabled={bulkSending}>
                                    <Zap size={14} /> {bulkSending ? 'Sending...' : `Send to ${selected.size} leads`}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* ══ Add Lead Modal ══ */}
            {showAdd && (
                <div className={styles.modalOverlay} onClick={() => setShowAdd(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2>Add Lead</h2>
                            <button className={styles.closeBtn} onClick={() => setShowAdd(false)}><X size={18} /></button>
                        </div>
                        <div className={styles.modalBody}>
                            <div className={styles.formGrid}>
                                <div className={styles.formGroup}>
                                    <label>First Name *</label>
                                    <input className={styles.input} value={addForm.first_name}
                                        onChange={e => setAddForm(f => ({ ...f, first_name: e.target.value }))} />
                                </div>
                                <div className={styles.formGroup}>
                                    <label>Last Name</label>
                                    <input className={styles.input} value={addForm.last_name}
                                        onChange={e => setAddForm(f => ({ ...f, last_name: e.target.value }))} />
                                </div>
                                <div className={styles.formGroup}>
                                    <label>Email</label>
                                    <input className={styles.input} type="email" value={addForm.email}
                                        onChange={e => setAddForm(f => ({ ...f, email: e.target.value }))} />
                                </div>
                                <div className={styles.formGroup}>
                                    <label>Phone *</label>
                                    <input className={styles.input} value={addForm.phone}
                                        onChange={e => setAddForm(f => ({ ...f, phone: e.target.value }))} />
                                </div>
                                <div className={styles.formGroup}>
                                    <label>Channel</label>
                                    <select className={styles.input} value={addForm.preferred_channel}
                                        onChange={e => setAddForm(f => ({ ...f, preferred_channel: e.target.value }))}>
                                        <option value="sms">SMS</option>
                                        <option value="whatsapp">WhatsApp</option>
                                    </select>
                                </div>
                                <div className={styles.formGroup}>
                                    <label>Policy Type</label>
                                    <input className={styles.input} placeholder="Auto, Home, Life..."
                                        value={addForm.policy_type}
                                        onChange={e => setAddForm(f => ({ ...f, policy_type: e.target.value }))} />
                                </div>
                                <div className={styles.formGroupFull}>
                                    <label>Tags (comma separated)</label>
                                    <input className={styles.input} placeholder="home-loan, medical, sales"
                                        value={addForm.tags}
                                        onChange={e => setAddForm(f => ({ ...f, tags: e.target.value }))} />
                                </div>
                                <div className={styles.formGroupFull}>
                                    <label>Notes</label>
                                    <textarea className={styles.textarea} rows={3} value={addForm.notes}
                                        onChange={e => setAddForm(f => ({ ...f, notes: e.target.value }))} />
                                </div>
                            </div>
                            <div className={styles.toggleRow} style={{ borderColor: addForm.auto_sms ? 'rgba(185, 134, 42,0.25)' : 'var(--border)', background: addForm.auto_sms ? 'rgba(185, 134, 42,0.08)' : 'rgba(107,114,128,0.06)' }}
                                onClick={() => setAddForm(f => ({ ...f, auto_sms: !f.auto_sms }))}>
                                <div>
                                    <div className={styles.toggleLabel}>Auto SMS</div>
                                    <div className={styles.toggleDesc}>{addForm.auto_sms ? 'AI will send a welcome message automatically' : 'No message sent — you can message manually'}</div>
                                </div>
                                <div className={styles.toggle} style={{ background: addForm.auto_sms ? 'var(--primary)' : '#4b5563' }}>
                                    <div className={styles.toggleThumb} style={{ left: addForm.auto_sms ? 21 : 3 }} />
                                </div>
                            </div>
                            <div className={styles.modalFooter}>
                                <button className={styles.btnSecondary} onClick={() => setShowAdd(false)}>Cancel</button>
                                <button className={styles.btnPrimary} onClick={handleAdd} disabled={adding || !addForm.first_name}>
                                    {adding ? 'Adding...' : 'Add Lead'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* ══ Duplicate Popup ══ */}
            {duplicatePopup && (
                <div className={styles.modalOverlay} onClick={() => setDuplicatePopup(false)}>
                    <div className={styles.modal} style={{ maxWidth: 380 }} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}><AlertTriangle size={18} color="#f59e0b" /> Duplicate Lead</h2>
                            <button className={styles.closeBtn} onClick={() => setDuplicatePopup(false)}><X size={18} /></button>
                        </div>
                        <div className={styles.modalBody}>
                            <p style={{ fontSize: 14, color: 'var(--text-2)', marginBottom: 20 }}>A lead with this phone number already exists in your pipeline.</p>
                            <div className={styles.modalFooter}>
                                <button className={styles.btnSecondary} onClick={() => setDuplicatePopup(false)}>Close</button>
                                <button className={styles.btnPrimary} onClick={() => { setDuplicatePopup(false); setShowAdd(false); setSearch(addForm.phone); setViewMode('list'); }}>Find Existing Lead</button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* ══ Edit Lead Modal ══ */}
            {editLead && (
                <div className={styles.modalOverlay} onClick={() => setEditLead(null)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <h2>Edit Lead</h2>
                            <button className={styles.closeBtn} onClick={() => setEditLead(null)}><X size={18} /></button>
                        </div>
                        <div className={styles.modalBody}>
                            <div className={styles.formGrid}>
                                <div className={styles.formGroup}><label>First Name *</label><input className={styles.input} value={editForm.first_name} onChange={e => setEditForm(f => ({ ...f, first_name: e.target.value }))} /></div>
                                <div className={styles.formGroup}><label>Last Name</label><input className={styles.input} value={editForm.last_name} onChange={e => setEditForm(f => ({ ...f, last_name: e.target.value }))} /></div>
                                <div className={styles.formGroup}><label>Email</label><input className={styles.input} type="email" value={editForm.email} onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} /></div>
                                <div className={styles.formGroup}><label>Phone</label><input className={styles.input} value={editForm.phone} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))} /></div>
                                <div className={styles.formGroup}>
                                    <label>Status</label>
                                    <select className={styles.input} value={editForm.status} onChange={e => setEditForm(f => ({ ...f, status: e.target.value }))}>
                                        <option value="new">New</option>
                                        <option value="contacted">Contacted</option>
                                        <option value="stale">Old Lead</option>
                                        <option value="responded">Responded</option>
                                        <option value="follow_up_sent">Follow-up Sent</option>
                                        <option value="qualified">Qualified</option>
                                        <option value="quoted">Quoted</option>
                                        <option value="appointment_scheduled">Appointment Scheduled</option>
                                        <option value="converted">Converted</option>
                                        <option value="dead">Trip Lead</option>
                                    </select>
                                </div>
                                <div className={styles.formGroup}><label>Strategy</label><input className={styles.input} value={editForm.strategy} onChange={e => setEditForm(f => ({ ...f, strategy: e.target.value }))} /></div>
                                <div className={styles.formGroup}><label>Policy Type</label><input className={styles.input} placeholder="Auto, Home, Life..." value={editForm.policy_type} onChange={e => setEditForm(f => ({ ...f, policy_type: e.target.value }))} /></div>
                                <div className={styles.formGroupFull}><label>Tags (comma separated)</label><input className={styles.input} placeholder="medical, sales, vip" value={editForm.tags} onChange={e => setEditForm(f => ({ ...f, tags: e.target.value }))} /></div>
                                <div className={styles.formGroupFull}><label>Notes</label><textarea className={styles.textarea} rows={3} value={editForm.notes} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))} /></div>
                            </div>
                            <div className={styles.modalFooter}>
                                <button className={styles.btnSecondary} onClick={() => setEditLead(null)}>Cancel</button>
                                <button className={styles.btnPrimary} onClick={handleSaveEdit} disabled={saving || !editForm.first_name}>
                                    {saving ? 'Saving...' : 'Save Changes'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
