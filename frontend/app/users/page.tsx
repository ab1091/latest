'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import { UserCog, Search, X, Bot, Shield, User, UserPlus, Eye, EyeOff } from 'lucide-react';
import { hasModuleAccess, PERMISSION_MODULES } from '@/lib/permissions';


interface UserRow {
    id: string; email: string;
    first_name?: string; last_name?: string;
    role: string;
    agent_id?: string | null; agent_name?: string | null;
    agent_ids?: string[]; agent_names?: string[];
    permissions?: string[];
    created_at: string;
}
interface Agent { id: string; name: string; status: string; }

const ROLE_COLOR: Record<string, { bg: string; color: string }> = {
    admin:    { bg: 'rgba(99,102,241,0.12)',  color: '#818cf8' },
    staff:    { bg: 'rgba(16,185,129,0.12)',  color: '#34d399' },
    customer: { bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24' },
};

export default function UsersPage() {
    const { accessToken, user, isLoading } = useAuth();
    const router = useRouter();
    const [users,   setUsers]   = useState<UserRow[]>([]);
    const [agents,  setAgents]  = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [search,  setSearch]  = useState('');
    const [editUser,   setEditUser]   = useState<UserRow | null>(null);
    const [editForm,   setEditForm]   = useState({ role: 'customer', agent_ids: [] as string[], password: '', permissions: [] as string[] });
    const [saving,     setSaving]     = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [showAdd,    setShowAdd]    = useState(false);
    const [addForm,    setAddForm]    = useState({ first_name: '', last_name: '', email: '', password: '', role: 'staff' });
    const [addSaving,  setAddSaving]  = useState(false);
    const [addError,   setAddError]   = useState('');

    const isStaff = user?.role === 'staff';
    const isAdmin = user?.role === 'admin' || user?.role === 'super_admin';

    // Auth guard — admin or staff
    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'team_management', 'admin')) { router.replace('/dashboard'); }
    }, [isLoading, accessToken, user, router]);

    const load = useCallback(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        Promise.all([
            fetch('/api/admin/users', { headers: h }).then(r => r.json()),
            fetch(`/api/agents`, { headers: h }).then(r => r.json()),
        ]).then(([u, a]) => {
            setUsers(u?.data?.users || []);
            setAgents(a?.data?.agents || []);
        }).catch(() => {}).finally(() => setLoading(false));
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const openEdit = (u: UserRow) => {
        setEditUser(u);
        const ids = u.agent_ids?.length ? u.agent_ids : (u.agent_id ? [u.agent_id] : []);
        setEditForm({ role: u.role, agent_ids: ids, password: '', permissions: u.permissions || [] });
        setShowPassword(false);
    };

    const toggleAgent = (agentId: string) => {
        setEditForm(f => {
            const ids = f.agent_ids.includes(agentId)
                ? f.agent_ids.filter(id => id !== agentId)
                : [...f.agent_ids, agentId];
            return { ...f, agent_ids: ids };
        });
    };

    const togglePermission = (moduleKey: string) => {
        setEditForm(f => {
            const perms = f.permissions.includes(moduleKey)
                ? f.permissions.filter(k => k !== moduleKey)
                : [...f.permissions, moduleKey];
            return { ...f, permissions: perms };
        });
    };

    const handleSave = async () => {
        if (!editUser) return;
        setSaving(true);
        try {
            const payload: Record<string, unknown> = { role: editForm.role, agent_ids: editForm.agent_ids };
            if (isAdmin && editForm.password.trim()) payload.password = editForm.password.trim();
            if (isAdmin) payload.permissions = editForm.permissions;
            await fetch(`/api/admin/users/${editUser.id}`, {
                method: 'PATCH',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            setEditUser(null);
            load();
        } catch {}
        setSaving(false);
    };

    const filtered = users.filter(u => {
        const name = `${u.first_name || ''} ${u.last_name || ''} ${u.email}`.toLowerCase();
        return name.includes(search.toLowerCase());
    });

    const handleAddUser = async () => {
        if (!addForm.email || !addForm.password || !addForm.first_name) {
            setAddError('First name, email and password are required'); return;
        }
        setAddSaving(true); setAddError('');
        try {
            const res = await fetch('/api/auth/signup', {
                method: 'POST',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify(addForm),
            });
            const d = await res.json();
            if (d.success) {
                setShowAdd(false);
                setAddForm({ first_name: '', last_name: '', email: '', password: '', role: isStaff ? 'customer' : 'staff' });
                load();
            } else {
                setAddError(d.detail || 'Failed to add user');
            }
        } catch { setAddError('Network error'); }
        setAddSaving(false);
    };

    const displayName = (u: UserRow) =>
        [u.first_name, u.last_name].filter(Boolean).join(' ') || '—';

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <SideNav />
            <main style={{ marginLeft: 220, flex: 1, padding: 32 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
                    <div>
                        <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>Users</h1>
                        <p style={{ color: 'var(--text-4)', fontSize: 13, marginTop: 4 }}>{users.length} total users</p>
                    </div>
                    <button onClick={() => { setAddForm(p => ({ ...p, role: isStaff ? 'customer' : 'staff' })); setShowAdd(true); }} style={{
                        display: 'flex', alignItems: 'center', gap: 7,
                        padding: '9px 18px', borderRadius: 10, border: 'none',
                        background: 'linear-gradient(135deg,#b9862a,#d4a94f)',
                        color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer',
                    }}>
                        <UserPlus size={15} /> Add User
                    </button>
                </div>

                {/* Search */}
                <div style={{ position: 'relative', marginBottom: 20, maxWidth: 360 }}>
                    <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-4)' }} />
                    <input placeholder="Search users..." value={search} onChange={e => setSearch(e.target.value)}
                        style={{ width: '100%', padding: '10px 14px 10px 36px', borderRadius: 9, border: '1px solid var(--border-default)', background: 'var(--bg-card)', color: 'var(--text-1)', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
                </div>

                {loading ? <p style={{ color: 'var(--text-4)' }}>Loading...</p> :
                filtered.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-4)' }}>
                        <UserCog size={40} style={{ opacity: 0.3, marginBottom: 12 }} />
                        <p>No users found.</p>
                    </div>
                ) : (
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 12, overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--border-default)', background: 'rgba(255,255,255,0.02)' }}>
                                    {['User', 'Email', 'Role', 'Assigned Agent', 'Joined', 'Actions'].map(col => (
                                        <th key={col} style={{ padding: '12px 16px', textAlign: 'left', fontSize: 11, color: 'var(--text-4)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{col}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((u, i) => {
                                    const rc = ROLE_COLOR[u.role] || ROLE_COLOR.customer;
                                    return (
                                        <tr key={u.id} style={{ borderBottom: i < filtered.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                                            <td style={{ padding: '13px 16px' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                    <div style={{ width: 34, height: 34, borderRadius: 8, background: rc.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, color: rc.color, flexShrink: 0 }}>
                                                        {displayName(u).split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase() || 'U'}
                                                    </div>
                                                    <span style={{ fontWeight: 600, fontSize: 14 }}>{displayName(u)}</span>
                                                </div>
                                            </td>
                                            <td style={{ padding: '13px 16px', fontSize: 13, color: 'var(--text-4)' }}>{u.email}</td>
                                            <td style={{ padding: '13px 16px' }}>
                                                <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: rc.bg, color: rc.color }}>
                                                    {u.role}
                                                </span>
                                            </td>
                                            <td style={{ padding: '13px 16px' }}>
                                                {(u.agent_names?.length || u.agent_name) ? (
                                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                                                        {(u.agent_names?.length ? u.agent_names : [u.agent_name!]).map((name, ni) => (
                                                            <div key={ni} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, background: 'rgba(212, 169, 79,0.1)', color: '#d4a94f', padding: '2px 8px', borderRadius: 20, fontWeight: 600 }}>
                                                                <Bot size={11} />
                                                                {name}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <span style={{ fontSize: 12, color: 'var(--text-4)' }}>Not assigned</span>
                                                )}
                                            </td>
                                            <td style={{ padding: '13px 16px', fontSize: 13, color: 'var(--text-4)' }}>
                                                {parseApiDate(u.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                            </td>
                                            <td style={{ padding: '13px 16px' }}>
                                                <button onClick={() => openEdit(u)} style={{
                                                    fontSize: 12, padding: '5px 12px', borderRadius: 7,
                                                    border: '1px solid var(--border-default)', background: 'transparent',
                                                    color: 'var(--text-1)', cursor: 'pointer', fontWeight: 600,
                                                }}>Edit</button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Edit User Modal */}
                {editUser && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 16, padding: 28, width: 440 }} onClick={e => e.stopPropagation()}>
                            {/* Modal header */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 22 }}>
                                <div>
                                    <div style={{ fontWeight: 800, fontSize: 16 }}>Edit User</div>
                                    <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 2 }}>{editUser.email}</div>
                                </div>
                                <button onClick={() => setEditUser(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)', padding: 4 }}><X size={18} /></button>
                            </div>

                            {/* Role */}
                            <div style={{ marginBottom: 18 }}>
                                <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-4)', display: 'block', marginBottom: 7, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    Role
                                </label>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                                    {[
                                        { val: 'customer', label: 'Customer', icon: User,   color: '#f59e0b' },
                                        { val: 'staff',    label: 'Staff',    icon: Shield,  color: '#10b981' },
                                        { val: 'admin',    label: 'Admin',    icon: UserCog, color: '#818cf8' },
                                    ].map(r => {
                                        const Icon = r.icon;
                                        const active = editForm.role === r.val;
                                        return (
                                            <button key={r.val} onClick={() => setEditForm(f => ({ ...f, role: r.val }))} style={{
                                                padding: '10px 8px', borderRadius: 9, border: `2px solid ${active ? r.color : 'var(--border-default)'}`,
                                                background: active ? `${r.color}12` : 'transparent',
                                                cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5,
                                                transition: 'all 0.15s',
                                            }}>
                                                <Icon size={16} color={active ? r.color : 'var(--text-4)'} />
                                                <span style={{ fontSize: 12, fontWeight: 700, color: active ? r.color : 'var(--text-4)' }}>{r.label}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Password reset — admin only */}
                            {isAdmin && (
                                <div style={{ marginBottom: 18 }}>
                                    <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-4)', display: 'block', marginBottom: 7, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Reset Password
                                    </label>
                                    <div style={{ position: 'relative' }}>
                                        <input
                                            type={showPassword ? 'text' : 'password'}
                                            value={editForm.password}
                                            onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))}
                                            placeholder="Leave blank to keep current password"
                                            style={{
                                                width: '100%', padding: '9px 38px 9px 12px', borderRadius: 9,
                                                border: '1px solid var(--border-default)', background: 'var(--bg-base)',
                                                color: 'var(--text-1)', fontSize: 13, boxSizing: 'border-box',
                                            }}
                                        />
                                        <button type="button" onClick={() => setShowPassword(v => !v)}
                                            tabIndex={-1}
                                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                                            style={{
                                                position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                                                background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)',
                                                padding: 4, display: 'flex',
                                            }}>
                                            {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Share Access — admin only, and only meaningful for non-admin targets
                                (admin/super_admin already see everything regardless) */}
                            {isAdmin && editForm.role !== 'admin' && (
                                <div style={{ marginBottom: 24 }}>
                                    <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-4)', display: 'block', marginBottom: 7, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Share Access
                                    </label>
                                    <div style={{ border: '1px solid var(--border-default)', borderRadius: 9, overflow: 'hidden', maxHeight: 200, overflowY: 'auto' }}>
                                        {PERMISSION_MODULES.map((m, mi) => {
                                            const checked = editForm.permissions.includes(m.key);
                                            return (
                                                <div key={m.key} onClick={() => togglePermission(m.key)} style={{
                                                    display: 'flex', alignItems: 'center', gap: 10,
                                                    padding: '9px 14px', cursor: 'pointer',
                                                    borderBottom: mi < PERMISSION_MODULES.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                                                    background: checked ? 'rgba(212, 169, 79,0.07)' : 'transparent',
                                                    transition: 'background 0.12s',
                                                }}>
                                                    <div style={{
                                                        width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                                                        border: `2px solid ${checked ? '#d4a94f' : 'var(--border-default)'}`,
                                                        background: checked ? '#d4a94f' : 'transparent',
                                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    }}>
                                                        {checked && <svg width="10" height="8" viewBox="0 0 10 8" fill="none"><path d="M1 4L3.5 6.5L9 1" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                                                    </div>
                                                    <span style={{ fontSize: 13, fontWeight: checked ? 700 : 400, color: checked ? 'var(--text-1)' : 'var(--text-3)', flex: 1 }}>{m.label}</span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                    <p style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 6 }}>
                                        Grants access to these sections on top of whatever their role already allows. Click to toggle.
                                    </p>
                                </div>
                            )}

                            {/* Assign Agents (multi) */}
                            <div style={{ marginBottom: 24 }}>
                                <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-4)', display: 'block', marginBottom: 7, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    Assign AI Agents
                                </label>
                                <div style={{ border: '1px solid var(--border-default)', borderRadius: 9, overflow: 'hidden', maxHeight: 180, overflowY: 'auto' }}>
                                    {agents.length === 0 ? (
                                        <div style={{ padding: '10px 14px', fontSize: 13, color: 'var(--text-4)' }}>No agents available</div>
                                    ) : agents.map((a, ai) => {
                                        const checked = editForm.agent_ids.includes(a.id);
                                        return (
                                            <div key={a.id} onClick={() => toggleAgent(a.id)} style={{
                                                display: 'flex', alignItems: 'center', gap: 10,
                                                padding: '9px 14px', cursor: 'pointer',
                                                borderBottom: ai < agents.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                                                background: checked ? 'rgba(212, 169, 79,0.07)' : 'transparent',
                                                transition: 'background 0.12s',
                                            }}>
                                                <div style={{
                                                    width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                                                    border: `2px solid ${checked ? '#d4a94f' : 'var(--border-default)'}`,
                                                    background: checked ? '#d4a94f' : 'transparent',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                }}>
                                                    {checked && <svg width="10" height="8" viewBox="0 0 10 8" fill="none"><path d="M1 4L3.5 6.5L9 1" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                                                </div>
                                                <Bot size={13} color={checked ? '#d4a94f' : 'var(--text-4)'} />
                                                <span style={{ fontSize: 13, fontWeight: checked ? 700 : 400, color: checked ? 'var(--text-1)' : 'var(--text-3)', flex: 1 }}>{a.name}</span>
                                                <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 20, background: a.status === 'active' ? 'rgba(16,185,129,0.12)' : 'rgba(107,114,128,0.12)', color: a.status === 'active' ? '#34d399' : 'var(--text-4)' }}>{a.status}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                                <p style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 6 }}>
                                    {editForm.agent_ids.length === 0 ? 'No agents assigned.' : `${editForm.agent_ids.length} agent${editForm.agent_ids.length > 1 ? 's' : ''} selected.`} Click to toggle.
                                </p>
                            </div>

                            <div style={{ display: 'flex', gap: 10 }}>
                                <button onClick={() => setEditUser(null)} style={{ flex: 1, padding: '10px', borderRadius: 9, border: '1px solid var(--border-default)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontWeight: 600 }}>Cancel</button>
                                <button onClick={handleSave} disabled={saving} style={{ flex: 1, padding: '10px', borderRadius: 9, border: 'none', background: '#d4a94f', color: '#14100a', cursor: 'pointer', fontWeight: 700, opacity: saving ? 0.7 : 1 }}>
                                    {saving ? 'Saving…' : 'Save Changes'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
                {/* Add User Modal */}
                {showAdd && (
                    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 16, padding: 28, width: 440 }} onClick={e => e.stopPropagation()}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
                                <div style={{ fontWeight: 800, fontSize: 16 }}>Add New User</div>
                                <button onClick={() => setShowAdd(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-4)' }}><X size={18} /></button>
                            </div>
                            {addError && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 12px', fontSize: 13, color: '#f87171', marginBottom: 16 }}>{addError}</div>}
                            {[
                                { label: 'First Name *', key: 'first_name', type: 'text' },
                                { label: 'Last Name',    key: 'last_name',  type: 'text' },
                                { label: 'Email *',      key: 'email',      type: 'email' },
                                { label: 'Password *',   key: 'password',   type: 'password' },
                            ].map(f => (
                                <div key={f.key} style={{ marginBottom: 14 }}>
                                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-4)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{f.label}</label>
                                    <input type={f.type} value={(addForm as any)[f.key]}
                                        onChange={e => setAddForm(p => ({ ...p, [f.key]: e.target.value }))}
                                        style={{ width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-default)', background: 'var(--bg-elevated)', color: 'var(--text-1)', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
                                </div>
                            ))}
                            {isStaff ? (
                                <div style={{ marginBottom: 20, padding: '10px 14px', borderRadius: 9, background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                                    <span style={{ fontSize: 12, color: '#fbbf24', fontWeight: 700 }}>Role: Customer</span>
                                    <span style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 8 }}>Staff can only add customer accounts</span>
                                </div>
                            ) : (
                                <div style={{ marginBottom: 20 }}>
                                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-4)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Role</label>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                                        {[
                                            { val: 'customer', label: 'Customer', color: '#f59e0b' },
                                            { val: 'staff',    label: 'Staff',    color: '#10b981' },
                                            { val: 'admin',    label: 'Admin',    color: '#818cf8' },
                                        ].map(r => (
                                            <button key={r.val} onClick={() => setAddForm(p => ({ ...p, role: r.val }))} style={{
                                                padding: '8px', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 12,
                                                border: `2px solid ${addForm.role === r.val ? r.color : 'var(--border-default)'}`,
                                                background: addForm.role === r.val ? `${r.color}14` : 'transparent',
                                                color: addForm.role === r.val ? r.color : 'var(--text-4)',
                                            }}>{r.label}</button>
                                        ))}
                                    </div>
                                </div>
                            )}
                            <div style={{ display: 'flex', gap: 10 }}>
                                <button onClick={() => setShowAdd(false)} style={{ flex: 1, padding: 10, borderRadius: 9, border: '1px solid var(--border-default)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontWeight: 600 }}>Cancel</button>
                                <button onClick={handleAddUser} disabled={addSaving} style={{ flex: 1, padding: 10, borderRadius: 9, border: 'none', background: '#d4a94f', color: '#14100a', cursor: 'pointer', fontWeight: 700, opacity: addSaving ? 0.7 : 1 }}>
                                    {addSaving ? 'Adding…' : 'Add User'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
}
