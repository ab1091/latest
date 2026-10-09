'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Plus, Pencil, Trash2, Check, X, AlertTriangle } from 'lucide-react';
import { SideNav } from '@/components/SideNav/SideNav';
import styles from './admin.module.css';

interface Service { id: string; name: string; description: string | null; duration_minutes: number; price: number; is_active: number; }
interface Provider { id: string; name: string; specialty: string; bio: string | null; phone: string | null; email: string | null; is_active: number; }

type Tab = 'services' | 'providers' | 'staff' | 'settings';

const emptyService = { name: '', description: '', duration_minutes: 30, price: 0 };
const emptyProvider = { name: '', specialty: '', bio: '', phone: '', email: '' };

export default function AdminPage() {
    const router = useRouter();
    const { isAuthenticated, accessToken, isLoading: authLoading, user, isLoggingOut } = useAuth();
    const [tab, setTab] = useState<Tab>('services');

    const [services, setServices] = useState<Service[]>([]);
    const [providers, setProviders] = useState<Provider[]>([]);

    const [showServiceForm, setShowServiceForm] = useState(false);
    const [editingService, setEditingService] = useState<Service | null>(null);
    const [serviceForm, setServiceForm] = useState(emptyService);

    const [showProviderForm, setShowProviderForm] = useState(false);
    const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
    const [providerForm, setProviderForm] = useState(emptyProvider);

    const [settingsForm, setSettingsForm] = useState({ name: '', phone: '', email: '', timeZone: 'America/New_York', businessHours: 'Mon-Fri 8 AM - 6 PM', voiceProvider: 'Vapi (default)' });
    const [settingsSaved, setSettingsSaved] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!authLoading) {
            if (!isAuthenticated && !isLoggingOut) {
                router.push('/login');
            } else if (isAuthenticated && user?.role !== 'admin') {
                router.push('/dashboard');
            }
        }
    }, [authLoading, isAuthenticated, isLoggingOut, user, router]);

    const h = useMemo(() => ({ Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }), [accessToken]);

    const fetchAll = useCallback(async () => {
        if (!accessToken) return;
        const safeJson = async (res: Response): Promise<any> => res.ok ? res.json().catch(() => ({})) : {};
        const [sr, pr, st] = await Promise.all([
            fetch('/api/admin/services', { headers: h }).then(safeJson).catch(() => ({})),
            fetch('/api/admin/providers', { headers: h }).then(safeJson).catch(() => ({})),
            fetch('/api/admin/settings', { headers: h }).then(safeJson).catch(() => ({})),
        ]);
        setServices(sr?.data?.services || []);
        setProviders(pr?.data?.providers || []);
        if (st?.data) setSettingsForm({ name: st.data.name || '', phone: st.data.phone || '', email: st.data.email || '', timeZone: st.data.timeZone || 'America/New_York', businessHours: st.data.businessHours || 'Mon-Fri 8 AM - 6 PM', voiceProvider: st.data.voiceProvider || 'Vapi (default)' });
    }, [accessToken, h]);

    const saveSettings = async () => {
        if (!settingsForm.name.trim()) { setError('Clinic name is required'); return; }
        setSaving(true); setError(null); setSettingsSaved(false);
        try {
            const res = await fetch('/api/admin/settings', { method: 'PUT', headers: h, body: JSON.stringify(settingsForm) });
            const data = await res.json();
            if (!res.ok) { setError(data.error || 'Failed to save'); return; }
            setSettingsSaved(true);
            setTimeout(() => setSettingsSaved(false), 3000);
        } finally { setSaving(false); }
    };

    useEffect(() => { if (accessToken) void fetchAll(); }, [accessToken, fetchAll]);

    // ── Services ──
    const openAddService = () => { setEditingService(null); setServiceForm(emptyService); setShowServiceForm(true); setError(null); };
    const openEditService = (s: Service) => { setEditingService(s); setServiceForm({ name: s.name, description: s.description || '', duration_minutes: s.duration_minutes, price: s.price }); setShowServiceForm(true); setError(null); };

    const saveService = async () => {
        if (!serviceForm.name || !serviceForm.duration_minutes) { setError('Name and duration required'); return; }
        setSaving(true); setError(null);
        try {
            const url = editingService ? `/api/admin/services/${editingService.id}` : '/api/admin/services';
            const method = editingService ? 'PUT' : 'POST';
            const res = await fetch(url, { method, headers: h, body: JSON.stringify(serviceForm) });
            const data = await res.json();
            if (!res.ok) { setError(data.error || 'Failed'); return; }
            setShowServiceForm(false);
            await fetchAll();
        } finally { setSaving(false); }
    };

    const deleteService = async (id: string) => {
        if (!confirm('Deactivate this service?')) return;
        await fetch(`/api/admin/services/${id}`, { method: 'DELETE', headers: h });
        await fetchAll();
    };

    // ── Providers ──
    const openAddProvider = () => { setEditingProvider(null); setProviderForm(emptyProvider); setShowProviderForm(true); setError(null); };
    const openEditProvider = (p: Provider) => { setEditingProvider(p); setProviderForm({ name: p.name, specialty: p.specialty, bio: p.bio || '', phone: p.phone || '', email: p.email || '' }); setShowProviderForm(true); setError(null); };

    const saveProvider = async () => {
        if (!providerForm.name) { setError('Name required'); return; }
        setSaving(true); setError(null);
        try {
            const url = editingProvider ? `/api/admin/providers/${editingProvider.id}` : '/api/admin/providers';
            const method = editingProvider ? 'PUT' : 'POST';
            const res = await fetch(url, { method, headers: h, body: JSON.stringify(providerForm) });
            const data = await res.json();
            if (!res.ok) { setError(data.error || 'Failed'); return; }
            setShowProviderForm(false);
            await fetchAll();
        } finally { setSaving(false); }
    };

    const deleteProvider = async (id: string) => {
        if (!confirm('Deactivate this provider?')) return;
        await fetch(`/api/admin/providers/${id}`, { method: 'DELETE', headers: h });
        await fetchAll();
    };

    if (authLoading) return null;

    return (
        <div className={styles.page}>
            <div className={styles.stars} />
            <SideNav />

            <header className={styles.header}>
                <div>
                    <h1 className={styles.title}>Admin Panel</h1>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-3)', margin: 0 }}>Manage services, providers, and business settings</p>
                </div>
            </header>

            <main className={styles.main}>
                {/* Metrics Overview */}
                <div className={styles.metricsGrid}>
                    <div className={styles.metricCard}>
                        <div className={styles.metricLabel}>Total Services</div>
                        <div className={styles.metricValue}>{services.length}</div>
                        <div className={styles.metricTrend}>Active: {services.filter(s => s.is_active).length}</div>
                    </div>
                    <div className={styles.metricCard}>
                        <div className={styles.metricLabel}>Active Providers</div>
                        <div className={styles.metricValue}>{providers.length}</div>
                        <div className={styles.metricTrend}>Available: {providers.filter(p => p.is_active).length}</div>
                    </div>
                    <div className={styles.metricCard}>
                        <div className={styles.metricLabel}>System Health</div>
                        <div className={styles.metricValue}>100%</div>
                        <div className={styles.metricTrend} style={{ color: '#d4a94f' }}>All systems operational</div>
                    </div>
                </div>

                {/* Tabs */}
                <div className={styles.tabs}>
                    <button className={`${styles.tab} ${tab === 'services' ? styles.tabActive : ''}`} onClick={() => setTab('services')}>
                        Services
                    </button>
                    <button className={`${styles.tab} ${tab === 'providers' ? styles.tabActive : ''}`} onClick={() => setTab('providers')}>
                        Providers
                    </button>
                    <button className={`${styles.tab} ${tab === 'staff' ? styles.tabActive : ''}`} onClick={() => setTab('staff')}>
                        Staff Members
                    </button>
                    <button className={`${styles.tab} ${tab === 'settings' ? styles.tabActive : ''}`} onClick={() => setTab('settings')}>
                        Business Settings
                    </button>
                </div>

                {/* ── SERVICES TAB ── */}
                {tab === 'services' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <h2>Services</h2>
                            <button className={styles.addBtn} onClick={openAddService}>
                                <Plus size={16} /> Add Service
                            </button>
                        </div>

                        <div className={styles.list}>
                            {services.filter(s => s.is_active).map(s => (
                                <motion.div key={s.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={styles.item}>
                                    <div className={styles.itemInfo}>
                                        <span className={styles.itemName}>{s.name}</span>
                                        {s.description && <span className={styles.itemDesc}>{s.description}</span>}
                                    </div>
                                    <div className={styles.itemActions}>
                                        <button className={styles.editBtn} onClick={() => openEditService(s)} title="Edit">
                                            <Pencil size={14} />
                                        </button>
                                        <button className={styles.deleteBtn} onClick={() => deleteService(s.id)} title="Delete">
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                </motion.div>
                            ))}
                            {services.filter(s => s.is_active).length === 0 && (
                                <div className={styles.empty}>No services yet. Add one above.</div>
                            )}
                        </div>
                    </motion.div>
                )}

                {/* ── STAFF TAB (New from SS2) ── */}
                {tab === 'staff' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <h2>Staff Members</h2>
                            <button className={styles.addBtn}>
                                <Plus size={16} /> Add Member
                            </button>
                        </div>

                        <div className={styles.tableWrapper}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>NAME</th>
                                        <th>ROLE</th>
                                        <th>STATUS</th>
                                        <th>LAST LOGIN</th>
                                        <th className={styles.textRight}>ACTIONS</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {[
                                        { name: 'Dr. Sarah Wilson', email: 'sarah.w@clinic.com', role: 'Doctor / Provider', status: 'Active', last: '2 mins ago' },
                                        { name: 'Ahmed Raza', email: 'ahmed@clinic.com', role: 'Front Desk / Admin', status: 'Active', last: '1 hour ago' },
                                        { name: 'Jane Cooper', email: 'jane.c@clinic.com', role: 'Billing Specialist', status: 'Offline', last: 'Yesterday' }
                                    ].map((staff, idx) => (
                                        <tr key={idx}>
                                            <td>
                                                <div className={styles.staffName}>{staff.name}</div>
                                                <div className={styles.staffEmail}>{staff.email}</div>
                                            </td>
                                            <td><span className={styles.roleTag}>{staff.role}</span></td>
                                            <td>
                                                <span className={`${styles.statusTag} ${staff.status === 'Active' ? styles.statusActive : styles.statusOffline}`}>
                                                    {staff.status}
                                                </span>
                                            </td>
                                            <td>{staff.last}</td>
                                            <td className={styles.textRight}>
                                                <div className={styles.actionIcons}>
                                                    <button className={styles.iconBtn}><Pencil size={16} /></button>
                                                    <button className={`${styles.iconBtn} ${styles.iconBtnDanger}`}><Trash2 size={16} /></button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </motion.div>
                )}
                {tab === 'providers' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <h2>Doctors / Providers</h2>
                            <button className={styles.addBtn} onClick={openAddProvider}>
                                <Plus size={16} /> Add Provider
                            </button>
                        </div>

                        <div className={styles.list}>
                            {providers.filter(p => p.is_active).map(p => (
                                <motion.div key={p.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={styles.item}>
                                    <div className={styles.itemInfo}>
                                        <span className={styles.itemName}>{p.name}</span>
                                        {p.specialty && <span className={styles.itemDesc}>{p.specialty}</span>}
                                    </div>
                                    <div className={styles.itemActions}>
                                        <button className={styles.editBtn} onClick={() => openEditProvider(p)} title="Edit">
                                            <Pencil size={14} />
                                        </button>
                                        <button className={styles.deleteBtn} onClick={() => deleteProvider(p.id)} title="Remove">
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                </motion.div>
                            ))}
                            {providers.filter(p => p.is_active).length === 0 && (
                                <div className={styles.empty}>No providers yet. Add one above.</div>
                            )}
                        </div>
                    </motion.div>
                )}


                {/* ── SETTINGS TAB ── */}
                {tab === 'settings' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.section}>
                        <div className={styles.list}>
                        <div className={styles.settingsGrid}>
                            <label className={styles.inputLabel}>
                                Business Name
                                <input className={styles.input} value={settingsForm.name}
                                    onChange={e => setSettingsForm(f => ({ ...f, name: e.target.value }))}
                                    placeholder="e.g. Riverside Medical Clinic" />
                            </label>
                            <label className={styles.inputLabel}>
                                Phone Number
                                <input className={styles.input} value={settingsForm.phone}
                                    onChange={e => setSettingsForm(f => ({ ...f, phone: e.target.value }))}
                                    placeholder="+1 (555) 800-0000" />
                            </label>
                            <label className={styles.inputLabel}>
                                Email
                                <input className={styles.input} value={settingsForm.email}
                                    onChange={e => setSettingsForm(f => ({ ...f, email: e.target.value }))}
                                    placeholder="info@riverside.clinic" />
                            </label>
                            <label className={styles.inputLabel}>
                                Time Zone
                                <input className={styles.input} value={settingsForm.timeZone}
                                    onChange={e => setSettingsForm(f => ({ ...f, timeZone: e.target.value }))}
                                    placeholder="America/New_York" />
                            </label>
                            <label className={styles.inputLabel}>
                                Business Hours
                                <input className={styles.input} value={settingsForm.businessHours}
                                    onChange={e => setSettingsForm(f => ({ ...f, businessHours: e.target.value }))}
                                    placeholder="Mon–Fri 8 AM – 6 PM" />
                            </label>
                            <label className={styles.inputLabel}>
                                Voice Provider
                                <input className={styles.input} value={settingsForm.voiceProvider}
                                    onChange={e => setSettingsForm(f => ({ ...f, voiceProvider: e.target.value }))}
                                    placeholder="Vapi (default)" />
                            </label>
                        </div>
                        {error && <div className={styles.error}>{error}</div>}
                        {settingsSaved && <div style={{ color: '#d4a94f', fontSize: '0.82rem', marginTop: '1rem' }}>✓ Settings saved!</div>}
                        <button className={styles.saveBtn} onClick={saveSettings} disabled={saving} style={{ marginTop: '1.5rem', alignSelf: 'flex-start' }}>
                            {saving ? 'Saving...' : 'Save Changes'}
                        </button>
                        </div>
                    </motion.div>
                )}
            </main>

            {/* ── SERVICE MODAL ── */}
            <AnimatePresence>
                {showServiceForm && (
                    <div className={styles.backdrop}>
                        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} className={styles.modal}>
                            <div className={styles.modalHeader}>
                                <h3>{editingService ? 'Edit Service' : 'Add Service'}</h3>
                                <button onClick={() => setShowServiceForm(false)}><X size={18} /></button>
                            </div>
                            <div className={styles.modalBody}>
                                <label>Name *<input className={styles.input} value={serviceForm.name} onChange={e => setServiceForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. General Checkup" /></label>
                                <label>Description<input className={styles.input} value={serviceForm.description} onChange={e => setServiceForm(f => ({ ...f, description: e.target.value }))} placeholder="Optional" /></label>
                                <div className={styles.row}>
                                    <label>Duration (min) *<input type="number" className={styles.input} value={serviceForm.duration_minutes} onChange={e => setServiceForm(f => ({ ...f, duration_minutes: Number(e.target.value) }))} min={5} /></label>
                                    <label>Price (Rs)<input type="number" className={styles.input} value={serviceForm.price} onChange={e => setServiceForm(f => ({ ...f, price: Number(e.target.value) }))} min={0} /></label>
                                </div>
                                {error && <div className={styles.error}>{error}</div>}
                            </div>
                            <div className={styles.modalFooter}>
                                <button className={styles.cancelBtn} onClick={() => setShowServiceForm(false)}>Cancel</button>
                                <button className={styles.saveBtn} onClick={saveService} disabled={saving}>
                                    <Check size={16} /> {saving ? 'Saving...' : 'Save'}
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            {/* ── PROVIDER MODAL ── */}
            <AnimatePresence>
                {showProviderForm && (
                    <div className={styles.backdrop}>
                        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} className={styles.modal}>
                            <div className={styles.modalHeader}>
                                <h3>{editingProvider ? 'Edit Provider' : 'Add Provider'}</h3>
                                <button onClick={() => setShowProviderForm(false)}><X size={18} /></button>
                            </div>
                            <div className={styles.modalBody}>
                                <label>Name *<input className={styles.input} value={providerForm.name} onChange={e => setProviderForm(f => ({ ...f, name: e.target.value }))} placeholder="Dr. Ahmed Khan" /></label>
                                <label>Specialty<input className={styles.input} value={providerForm.specialty} onChange={e => setProviderForm(f => ({ ...f, specialty: e.target.value }))} placeholder="e.g. Cardiologist" /></label>
                                <label>Bio<input className={styles.input} value={providerForm.bio} onChange={e => setProviderForm(f => ({ ...f, bio: e.target.value }))} placeholder="Short description" /></label>
                                <div className={styles.row}>
                                    <label>Phone<input className={styles.input} value={providerForm.phone} onChange={e => setProviderForm(f => ({ ...f, phone: e.target.value }))} placeholder="+92..." /></label>
                                    <label>Email<input className={styles.input} value={providerForm.email} onChange={e => setProviderForm(f => ({ ...f, email: e.target.value }))} placeholder="doctor@clinic.com" /></label>
                                </div>
                                {error && <div className={styles.error}>{error}</div>}
                            </div>
                            <div className={styles.modalFooter}>
                                <button className={styles.cancelBtn} onClick={() => setShowProviderForm(false)}>Cancel</button>
                                <button className={styles.saveBtn} onClick={saveProvider} disabled={saving}>
                                    <Check size={16} /> {saving ? 'Saving...' : 'Save'}
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}
