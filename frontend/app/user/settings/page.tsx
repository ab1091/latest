'use client';

import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Save } from 'lucide-react';

export default function UserSettings() {
    const { user, accessToken, refreshUser } = useAuth();
    const [form, setForm] = useState({
        firstName: user?.firstName || '',
        lastName: user?.lastName || '',
        email: user?.email || '',
        phone: user?.phone || '',
    });
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');

    const handleSave = async () => {
        setSaving(true);
        setMessage('');
        try {
            const res = await fetch('/api/auth/profile', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
                body: JSON.stringify(form),
            });
            if (res.ok) {
                setMessage('Profile updated successfully.');
                await refreshUser();
            } else {
                setMessage('Failed to update profile.');
            }
        } catch {
            setMessage('Error saving profile.');
        } finally {
            setSaving(false);
        }
    };

    const field = (label: string, key: keyof typeof form, type = 'text') => (
        <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6, color: 'var(--text-2)' }}>{label}</label>
            <input
                type={type}
                value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                style={{
                    width: '100%', padding: '10px 14px', borderRadius: 8,
                    border: '1px solid var(--border)', background: 'var(--input-bg)',
                    color: 'var(--text-1)', fontSize: 14, boxSizing: 'border-box',
                }}
            />
        </div>
    );

    return (
        <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Settings</h1>
            <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 32 }}>Manage your profile</p>

            <div style={{ maxWidth: 480, background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 12, padding: 24 }}>
                <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 20 }}>Profile Information</h2>
                {field('First Name', 'firstName')}
                {field('Last Name', 'lastName')}
                {field('Email', 'email', 'email')}
                {field('Phone', 'phone', 'tel')}

                {message && (
                    <p style={{ fontSize: 13, color: message.includes('success') ? '#10b981' : '#ef4444', marginBottom: 16 }}>{message}</p>
                )}

                <button
                    onClick={handleSave}
                    disabled={saving}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px',
                        background: '#d4a94f', color: '#14100a', border: 'none', borderRadius: 8,
                        cursor: 'pointer', fontSize: 13, fontWeight: 600, opacity: saving ? 0.7 : 1,
                    }}
                >
                    <Save size={14} /> {saving ? 'Saving...' : 'Save Changes'}
                </button>
            </div>
        </div>
    );
}
