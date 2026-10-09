'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { CheckCircle, ChevronRight, ChevronLeft } from 'lucide-react';

interface Service  { id: string; name: string; duration_minutes: number; price: number; }
interface Provider { id: string; name: string; specialty: string; }

type Step = 1 | 2 | 3 | 4;

export default function UserBook() {
    const { accessToken } = useAuth();
    const [step,     setStep]     = useState<Step>(1);
    const [services,  setServices]  = useState<Service[]>([]);
    const [providers, setProviders] = useState<Provider[]>([]);
    const [selectedService,  setSelectedService]  = useState<Service | null>(null);
    const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null);
    const [date,   setDate]   = useState('');
    const [time,   setTime]   = useState('');
    const [notes,  setNotes]  = useState('');
    const [error,  setError]  = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        fetch('/api/appointments/services/list', { headers: h })
            .then(r => r.json()).then(d => setServices(d.data?.services || [])).catch(() => {});
        fetch('/api/appointments/providers', { headers: h })
            .then(r => r.json()).then(d => setProviders(d.data?.providers || [])).catch(() => {});
    }, [accessToken]);

    const nextStep = () => {
        setError(null);
        if (step === 1 && !selectedService) { setError('Please select a service.'); return; }
        if (step === 2 && !selectedProvider) { setError('Please select a provider.'); return; }
        if (step === 3 && (!date || !time))  { setError('Please select a date and time.'); return; }
        setStep((step + 1) as Step);
    };

    const handleSubmit = async () => {
        if (!date || !time) { setError('Please select a date and time.'); return; }
        setSubmitting(true);
        setError(null);
        try {
            const startTime = new Date(`${date}T${time}:00`).toISOString();
            const res = await fetch('/api/appointments', {
                method: 'POST',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    serviceId:  selectedService?.id,
                    providerId: selectedProvider?.id,
                    startTime,
                    notes: notes || undefined,
                }),
            });
            const d = await res.json();
            if (!res.ok) {
                setError(res.status === 409 ? 'This time slot is already booked. Please choose another.' : (d.detail || 'Failed to book appointment.'));
                return;
            }
            setSuccess(true);
        } catch {
            setError('Unable to connect. Please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    const cardStyle: React.CSSProperties = {
        background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 12,
        padding: '14px 16px', cursor: 'pointer', marginBottom: 10, transition: 'border-color 0.15s',
    };
    const cardActive: React.CSSProperties = {
        borderColor: 'var(--primary)', background: 'rgba(185, 134, 42,0.06)',
    };
    const inputStyle: React.CSSProperties = {
        width: '100%', padding: '10px 13px', borderRadius: 9,
        border: '1px solid var(--border-default)', background: 'var(--bg-elevated)',
        color: 'var(--text-1)', fontSize: 14, boxSizing: 'border-box', outline: 'none',
    };

    if (success) {
        return (
            <div style={{ maxWidth: 500, textAlign: 'center', padding: '60px 0' }}>
                <CheckCircle size={52} color="#10b981" style={{ marginBottom: 16 }} />
                <h2 style={{ fontWeight: 800, fontSize: 22, margin: '0 0 8px' }}>Appointment Booked!</h2>
                <p style={{ color: 'var(--text-4)', marginBottom: 24 }}>
                    {selectedService?.name} with {selectedProvider?.name}<br />
                    {date} at {time}
                </p>
                <button onClick={() => { setSuccess(false); setStep(1); setSelectedService(null); setSelectedProvider(null); setDate(''); setTime(''); setNotes(''); }}
                    style={{ padding: '10px 24px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 9, cursor: 'pointer', fontWeight: 600 }}>
                    Book Another
                </button>
            </div>
        );
    }

    const steps = ['Service', 'Provider', 'Date & Time', 'Confirm'];

    return (
        <div style={{ maxWidth: 560 }}>
            <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 8px' }}>Book Appointment</h1>

            {/* Progress */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 28 }}>
                {steps.map((label, i) => {
                    const n = i + 1;
                    const done = step > n;
                    const active = step === n;
                    return (
                        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <div style={{
                                width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: 11, fontWeight: 700,
                                background: done || active ? 'var(--primary)' : 'var(--bg-elevated)',
                                color: done || active ? '#fff' : 'var(--text-4)',
                                border: `2px solid ${done || active ? 'var(--primary)' : 'var(--border-default)'}`,
                            }}>{n}</div>
                            <span style={{ fontSize: 12, fontWeight: active ? 700 : 400, color: active ? 'var(--text-1)' : 'var(--text-4)' }}>{label}</span>
                            {i < steps.length - 1 && <ChevronRight size={14} color="var(--text-4)" />}
                        </div>
                    );
                })}
            </div>

            {/* Step 1: Service */}
            {step === 1 && (
                <div>
                    <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Select a Service</h2>
                    {services.length === 0 && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading services...</p>}
                    {services.map(svc => (
                        <div key={svc.id} onClick={() => setSelectedService(svc)}
                            style={{ ...cardStyle, ...(selectedService?.id === svc.id ? cardActive : {}) }}>
                            <div style={{ fontWeight: 600, fontSize: 14 }}>{svc.name}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 3 }}>
                                {svc.duration_minutes} min · ${svc.price}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Step 2: Provider */}
            {step === 2 && (
                <div>
                    <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Select a Provider</h2>
                    {providers.length === 0 && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading providers...</p>}
                    {providers.map(p => (
                        <div key={p.id} onClick={() => setSelectedProvider(p)}
                            style={{ ...cardStyle, ...(selectedProvider?.id === p.id ? cardActive : {}) }}>
                            <div style={{ fontWeight: 600, fontSize: 14 }}>{p.name}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 3 }}>{p.specialty}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Step 3: Date & Time */}
            {step === 3 && (
                <div>
                    <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Select Date & Time</h2>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-4)', marginBottom: 6 }}>Date</label>
                        <input type="date" value={date} onChange={e => setDate(e.target.value)} style={inputStyle}
                            min={new Date().toISOString().split('T')[0]} />
                    </div>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-4)', marginBottom: 6 }}>Time</label>
                        <input type="time" value={time} onChange={e => setTime(e.target.value)} style={inputStyle} />
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-4)', marginBottom: 6 }}>Notes (optional)</label>
                        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
                            placeholder="Any special requests or notes..."
                            style={{ ...inputStyle, resize: 'vertical' as const }} />
                    </div>
                </div>
            )}

            {/* Step 4: Confirm */}
            {step === 4 && (
                <div>
                    <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Confirm Booking</h2>
                    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 12, padding: 20, marginBottom: 16 }}>
                        {[
                            ['Service',  selectedService?.name || '—'],
                            ['Provider', selectedProvider?.name || '—'],
                            ['Date',     date || '—'],
                            ['Time',     time || '—'],
                            ['Google Calendar', 'shieldsquadagency@gmail.com'],
                            ...(notes ? [['Notes', notes]] : []),
                        ].map(([label, value]) => (
                            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, fontSize: 14 }}>
                                <span style={{ color: 'var(--text-4)', fontWeight: 600 }}>{label}</span>
                                <span style={{ color: 'var(--text-1)', maxWidth: '60%', textAlign: 'right' }}>{value}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {error && <p style={{ color: '#f87171', fontSize: 13, marginBottom: 12 }}>{error}</p>}

            {/* Navigation */}
            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                {step > 1 && (
                    <button onClick={() => { setError(null); setStep((step - 1) as Step); }}
                        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 18px', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 9, cursor: 'pointer', fontWeight: 600, color: 'var(--text-2)' }}>
                        <ChevronLeft size={15} /> Back
                    </button>
                )}
                {step < 4 ? (
                    <button onClick={nextStep}
                        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '10px 18px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 9, cursor: 'pointer', fontWeight: 600 }}>
                        Next <ChevronRight size={15} />
                    </button>
                ) : (
                    <button onClick={handleSubmit} disabled={submitting}
                        style={{ flex: 1, padding: '10px 18px', background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', borderRadius: 9, cursor: submitting ? 'not-allowed' : 'pointer', fontWeight: 600, opacity: submitting ? 0.6 : 1 }}>
                        {submitting ? 'Booking...' : 'Confirm Booking'}
                    </button>
                )}
            </div>
        </div>
    );
}
