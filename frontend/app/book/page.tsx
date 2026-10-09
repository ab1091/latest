'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Calendar as CalendarIcon,
    Clock,
    User,
    FileText,
    CheckCircle,
    PhoneCall,
    Bot,
    ArrowRight,
    Stethoscope,
    Heart,
    Brain,
    Activity,
    ChevronRight,
    ChevronLeft,
    Sparkles,
    Search,
    ChevronDown,
    CalendarDays,
} from 'lucide-react';
import { SideNav } from '@/components/SideNav/SideNav';
import styles from './book.module.css';

interface Service { id: string; name: string; duration_minutes: number; price: number; category?: string; }
interface Provider { id: string; name: string; specialty: string; image?: string; bio?: string; }
interface Appointment { id: string; start_time: string; service_name?: string; provider_name?: string; status: string; }

type Tab = 'manual' | 'inbound' | 'outbound';
type Step = 1 | 2 | 3 | 4;

export default function BookPage() {
    const router = useRouter();
    const { isAuthenticated, accessToken, isLoading: authLoading } = useAuth();

    const [activeTab, setActiveTab] = useState<Tab>('manual');
    const [step, setStep] = useState<Step>(1);

    // Data
    const [services, setServices] = useState<Service[]>([]);
    const [providers, setProviders] = useState<Provider[]>([]);
    const [appointments, setAppointments] = useState<Appointment[]>([]);

    // Selections
    const [selectedService, setSelectedService] = useState<Service | null>(null);
    const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null);
    const [date, setDate] = useState('');
    const [time, setTime] = useState('');
    const [notes, setNotes] = useState('');
    const [selectedAppointmentId, setSelectedAppointmentId] = useState('');
    const [isAptMenuOpen, setIsAptMenuOpen] = useState(false);

    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    // Outbound AI call state
    const [outboundPhone, setOutboundPhone] = useState('');
    const [outboundPatient, setOutboundPatient] = useState('');
    const [outboundCallState, setOutboundCallState] = useState<'idle' | 'calling' | 'success' | 'error'>('idle');
    const [outboundCallSid, setOutboundCallSid] = useState('');
    const [outboundError, setOutboundError] = useState('');

    // Inbound calls state
    const [inboundCalls, setInboundCalls] = useState<{ callId: string; patientName: string; createdAt: string; status: string; serviceName?: string; appointmentDate?: string; durationSeconds?: number }[]>([]);

    // Search/Filter State
    const [serviceSearch, setServiceSearch] = useState('');
    const [providerSearch, setProviderSearch] = useState('');

    const filteredServices = useMemo(() => {
        return services.filter(s =>
            s.name.toLowerCase().includes(serviceSearch.toLowerCase()) ||
            s.category?.toLowerCase().includes(serviceSearch.toLowerCase())
        );
    }, [services, serviceSearch]);

    const filteredProviders = useMemo(() => {
        return providers.filter(p =>
            p.name.toLowerCase().includes(providerSearch.toLowerCase()) ||
            p.specialty.toLowerCase().includes(providerSearch.toLowerCase())
        );
    }, [providers, providerSearch]);

    useEffect(() => {
        if (!authLoading && !isAuthenticated) router.push('/login');
    }, [authLoading, isAuthenticated, router]);

    useEffect(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };

        fetch('/api/appointments/services/list', { headers: h })
            .then(r => r.json()).then(d => setServices(d.data?.services || [])).catch(() => { });

        fetch('/api/appointments/providers', { headers: h })
            .then(r => r.json()).then(d => setProviders(d.data?.providers || [])).catch(() => { });

        fetch('/api/appointments', { headers: h })
            .then(r => r.json())
            .then(d => {
                const upcoming = (d.data?.appointments || []).filter((a: Appointment) =>
                    parseApiDate(a.start_time).getTime() > Date.now() && a.status !== 'cancelled'
                );
                setAppointments(upcoming);
                if (upcoming.length > 0) setSelectedAppointmentId(upcoming[0].id);
            }).catch(() => { });

        fetch('/api/appointments/calls/all', { headers: h })
            .then(r => r.json())
            .then(d => {
                const inbound = (d.data || []).filter((c: any) => c.direction === 'inbound');
                setInboundCalls(inbound.slice(0, 5));
            }).catch(() => { });
    }, [accessToken]);

    const handleSubmit = async () => {
        if (!date || !time) { setError('Please select a date and time.'); return; }
        setIsSubmitting(true);
        setError(null);

        const startTime = new Date(`${date}T${time}:00`).toISOString();

        try {
            const res = await fetch('/api/appointments', {
                method: 'POST',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    serviceId: selectedService?.id,
                    providerId: selectedProvider?.id,
                    startTime,
                    notes: notes || undefined
                }),
            });
            const data = await res.json();
            if (!res.ok) {
                if (res.status === 409) {
                    setError('This time slot is already booked. Please choose a different time.');
                } else {
                    setError(data.detail || data.error || 'Failed to book appointment');
                }
                return;
            }
            setSuccess(true);
        } catch {
            setError('Unable to connect to server');
        } finally {
            setIsSubmitting(false);
        }
    };

    const nextStep = () => {
        if (step === 1 && !selectedService) { setError('Please select a service.'); return; }
        if (step === 2 && !selectedProvider) { setError('Please select a provider.'); return; }
        if (step === 3 && (!date || !time)) { setError('Please select a date and time.'); return; }
        setError(null);
        setStep((s) => (s + 1) as Step);
    };

    const prevStep = () => {
        setStep((s) => (s - 1) as Step);
    };

    const placeOutboundCall = async () => {
        if (!outboundPhone || outboundCallState === 'calling') return;
        const phone = outboundPhone.replace(/\s/g, '');
        const phoneNumber = phone.startsWith('+') ? phone : `+1${phone.replace(/\D/g, '')}`;
        const token = accessToken || localStorage.getItem('accessToken') || '';
        setOutboundCallState('calling');
        setOutboundError('');
        try {
            const res = await fetch('/api/dialer/call', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ phoneNumber, patientName: outboundPatient }),
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || 'Call failed');
            setOutboundCallSid(data.callSid);
            setOutboundCallState('success');
        } catch (err: any) {
            setOutboundError(err.message || 'Failed to place call');
            setOutboundCallState('error');
        }
    };

    if (authLoading) return null;

    if (success) return (
        <div className={styles.page}>
            <div className={styles.stars} />
            <SideNav />
            <div className={styles.main}>
                <div className={styles.successScreen}>
                    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', bounce: 0.4 }}>
                        <div className={styles.successIcon}>
                            <CheckCircle size={48} />
                        </div>
                    </motion.div>
                    <motion.h2 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                        Appointment Confirmed
                    </motion.h2>
                    <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
                        Your session with {selectedProvider?.name} is scheduled for {new Date(`${date}T${time}`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })} at {time}. Synced with Google Calendar (shieldsquadagency@gmail.com).
                    </motion.p>
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className={styles.successActions}>
                        <button className={styles.btnPrimary} onClick={() => router.push('/dashboard')}>Go to Appointments</button>
                        <button className={styles.btnSecondary} onClick={() => { setSuccess(false); setStep(1); setDate(''); setTime(''); setSelectedService(null); setSelectedProvider(null); }}>Book Another</button>
                    </motion.div>
                </div>
            </div>
        </div>
    );

    const today = new Date().toISOString().split('T')[0];

    const serviceIcons: Record<string, any> = {
        'Neurology': Brain,
        'Cardiology': Heart,
        'General Checkup': Stethoscope,
        'Dermatology': Activity,
    };

    const CalendarPicker = ({ value, onChange, minDate }: { value: string, onChange: (d: string) => void, minDate: string }) => {
        const [viewDate, setViewDate] = useState(new Date(value || new Date()));
        const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        
        const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();
        const firstDayOfMonth = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1).getDay();
        
        const prevMonth = () => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1));
        const nextMonth = () => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1));

        const days = [];
        for (let i = 0; i < firstDayOfMonth; i++) days.push(null);
        for (let i = 1; i <= daysInMonth; i++) days.push(i);

        const isSelected = (day: number) => {
            if (!day) return false;
            const d = new Date(viewDate.getFullYear(), viewDate.getMonth(), day);
            return d.toISOString().split('T')[0] === value;
        };

        const isPast = (day: number) => {
            if (!day) return false;
            const d = new Date(viewDate.getFullYear(), viewDate.getMonth(), day);
            return d.toISOString().split('T')[0] < minDate;
        };

        return (
            <div className={styles.calendarContainer}>
                <div className={styles.calendarHeader}>
                    <button type="button" onClick={prevMonth} className={styles.calNav}><ChevronLeft size={16} /></button>
                    <div className={styles.calMonth}>{months[viewDate.getMonth()]} {viewDate.getFullYear()}</div>
                    <button type="button" onClick={nextMonth} className={styles.calNav}><ChevronRight size={16} /></button>
                </div>
                <div className={styles.calGrid}>
                    {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(d => <div key={d} className={styles.calWeekday}>{d}</div>)}
                    {days.map((d, i) => (
                        <button
                            key={i}
                            type="button"
                            disabled={!d || isPast(d)}
                            onClick={() => d && onChange(new Date(viewDate.getFullYear(), viewDate.getMonth(), d).toISOString().split('T')[0])}
                            className={`${styles.calDay} ${d ? styles.calDayActive : ''} ${isSelected(d || 0) ? styles.calDaySelected : ''} ${isPast(d || 0) ? styles.calDayDisabled : ''}`}
                        >
                            {d}
                        </button>
                    ))}
                </div>
            </div>
        );
    };

    return (
        <div className={styles.page}>
            <div className={styles.stars} />
            <SideNav />

            <main className={styles.main}>
                <header className={styles.pageHeader}>
                    <div className={styles.headerTitleRow}>
                        <h1 className={styles.titleText}>Book Appointment</h1>
                        <div className={styles.premiumBadge}>
                            <Sparkles size={12} />
                            <span>Premium Experience</span>
                        </div>
                    </div>
                    <p className={styles.headerSub}>Schedule manually or use our high-fidelity AI voice assistant</p>
                </header>

                <div className={styles.tabsContainer}>
                    <div className={styles.tabs}>
                        <button
                            className={`${styles.tab} ${activeTab === 'manual' ? styles.tabActive : ''}`}
                            onClick={() => { setActiveTab('manual'); setStep(1); }}
                        >
                            <User size={14} />
                            Manual Booking
                        </button>
                        <button
                            className={`${styles.tab} ${activeTab === 'inbound' ? styles.tabActive : ''}`}
                            onClick={() => setActiveTab('inbound')}
                        >
                            <Bot size={14} />
                            Inbound AI
                        </button>
                        <button
                            className={`${styles.tab} ${activeTab === 'outbound' ? styles.tabActive : ''}`}
                            onClick={() => setActiveTab('outbound')}
                        >
                            <PhoneCall size={14} />
                            Outbound AI
                        </button>
                    </div>
                </div>

                <AnimatePresence mode="wait">
                    {activeTab === 'manual' && (
                        <motion.div
                            key="manual"
                            initial={{ opacity: 0, y: 15 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -15 }}
                            className={styles.bookingFlow}
                        >
                            {/* Progress Stepper */}
                            <div className={styles.stepper}>
                                <div className={styles.stepperLine}>
                                    <div
                                        className={styles.stepperProgress}
                                        style={{ width: `${((step - 1) / 3) * 100}%` }}
                                    />
                                </div>
                                {[1, 2, 3, 4].map((s) => (
                                    <div key={s} className={`${styles.step} ${step >= s ? styles.stepActive : ''}`}>
                                        <div className={styles.stepCircle}>{s}</div>
                                        <span className={styles.stepLabel}>
                                            {s === 1 && 'Service'}
                                            {s === 2 && 'Provider'}
                                            {s === 3 && 'Schedule'}
                                            {s === 4 && 'Confirm'}
                                        </span>
                                    </div>
                                ))}
                            </div>

                            <div className={styles.stepContent}>
                                {/* Step 1: Services */}
                                {step === 1 && (
                                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.serviceGrid}>
                                        <h2 className={styles.stepTitle}>Select a Service</h2>

                                        <div className={styles.searchBar}>
                                            <Search className={styles.searchIcon} size={18} />
                                            <input
                                                type="text"
                                                className={styles.searchInput}
                                                placeholder="Search services or categories..."
                                                value={serviceSearch}
                                                onChange={(e) => setServiceSearch(e.target.value)}
                                            />
                                        </div>

                                        <div className={styles.scrollContainer}>
                                            <div className={styles.grid}>
                                                {filteredServices.map((s) => {
                                                    const Icon = serviceIcons[s.name] || Stethoscope;
                                                    const isSelected = selectedService?.id === s.id;
                                                    const category = s.category || 'Consultation';

                                                    return (
                                                        <button
                                                            key={s.id}
                                                            type="button"
                                                            className={`${styles.serviceCard} ${isSelected ? styles.cardSelected : ''}`}
                                                            onClick={() => setSelectedService(s)}
                                                            onMouseMove={(e) => {
                                                                const rect = e.currentTarget.getBoundingClientRect();
                                                                const x = e.clientX - rect.left;
                                                                const y = e.clientY - rect.top;
                                                                e.currentTarget.style.setProperty('--mouse-x', `${x}px`);
                                                                e.currentTarget.style.setProperty('--mouse-y', `${y}px`);
                                                            }}
                                                        >
                                                            <div className={styles.serviceIcon}><Icon size={26} /></div>
                                                            <div className={styles.serviceInfo}>
                                                                <span className={styles.serviceCategory}>{category}</span>
                                                                <div className={styles.serviceName}>{s.name}</div>
                                                                <div className={styles.serviceMeta}>
                                                                    <div className={styles.metaItem}><Clock size={12} /> {s.duration_minutes}m</div>
                                                                    <div className={styles.metaItem}><Sparkles size={12} /> ${s.price || '80'}</div>
                                                                </div>
                                                            </div>
                                                            {isSelected && <CheckCircle className={styles.checkIcon} size={18} />}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </motion.div>
                                )}

                                {/* Step 2: Providers */}
                                {step === 2 && (
                                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.providerGrid}>
                                        <h2 className={styles.stepTitle}>Choose a Specialist</h2>

                                        <div className={styles.searchBar}>
                                            <Search className={styles.searchIcon} size={18} />
                                            <input
                                                type="text"
                                                className={styles.searchInput}
                                                placeholder="Search by name or specialty..."
                                                value={providerSearch}
                                                onChange={(e) => setProviderSearch(e.target.value)}
                                            />
                                        </div>

                                        <div className={styles.scrollContainer}>
                                            <div className={styles.grid}>
                                                {filteredProviders.map((p) => {
                                                    const isSelected = selectedProvider?.id === p.id;
                                                    return (
                                                        <button
                                                            key={p.id}
                                                            type="button"
                                                            className={`${styles.providerCard} ${isSelected ? styles.cardSelected : ''}`}
                                                            onClick={() => setSelectedProvider(p)}
                                                        >
                                                            <div className={styles.providerAvatar}>{p.name[0]}</div>
                                                            <div className={styles.providerInfo}>
                                                                <div className={styles.providerName}>{p.name}</div>
                                                                <div className={styles.providerSpecialty}>{p.specialty || 'General Practitioner'}</div>
                                                            </div>
                                                            {isSelected && <CheckCircle className={styles.checkIcon} size={18} />}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </motion.div>
                                )}

                                {/* Step 3: Schedule */}
                                {step === 3 && (
                                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.scheduleView}>
                                        <h2 className={styles.stepTitle}>Set Date & Time</h2>
                                        <div className={styles.scheduleGrid}>
                                            <div className={styles.calendarWrap}>
                                                <label className={styles.groupLabel}><CalendarDays size={14} /> Select Date</label>
                                                <CalendarPicker
                                                    value={date}
                                                    minDate={today}
                                                    onChange={setDate}
                                                />
                                            </div>
                                            <div className={styles.timeSlotsWrap}>
                                                <label><Clock size={14} /> Available Slots</label>
                                                <div className={styles.timeGrid}>
                                                    {[
                                                        { value: '10:00', label: '10:00 AM' },
                                                        { value: '14:00', label: '2:00 PM' },
                                                        { value: '16:00', label: '4:00 PM' },
                                                    ].map((t) => (
                                                        <button
                                                            key={t.value}
                                                            type="button"
                                                            className={`${styles.timeSlot} ${time === t.value ? styles.slotSelected : ''}`}
                                                            onClick={() => setTime(t.value)}
                                                        >
                                                            {t.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}

                                {/* Step 4: Confirm */}
                                {step === 4 && (
                                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={styles.confirmView}>
                                        <h2 className={styles.stepTitle}>Final Confirmation</h2>
                                        <div className={styles.summaryCard}>
                                            <div className={styles.summaryRow}>
                                                <div className={styles.summaryItem}>
                                                    <label>Service</label>
                                                    <div>{selectedService?.name}</div>
                                                </div>
                                                <div className={styles.summaryItem}>
                                                    <label>Specialist</label>
                                                    <div>{selectedProvider?.name}</div>
                                                </div>
                                            </div>
                                            <div className={styles.summaryRow}>
                                                <div className={styles.summaryItem}>
                                                    <label>Date</label>
                                                    <div>{date}</div>
                                                </div>
                                                <div className={styles.summaryItem}>
                                                    <label>Time</label>
                                                    <div>{time}</div>
                                                </div>
                                            </div>
                                            <div className={styles.summaryRow}>
                                                <div className={styles.summaryItem}>
                                                    <label>Google Calendar</label>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#38bdf8', fontWeight: 600, fontSize: 13 }}>
                                                        <CalendarDays size={14} />
                                                        <span>shieldsquadagency@gmail.com</span>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className={styles.summaryItem}>
                                                <label>Notes (Optional)</label>
                                                <textarea
                                                    value={notes}
                                                    onChange={(e) => setNotes(e.target.value)}
                                                    placeholder="Anything the doctor should know beforehand..."
                                                    className={styles.notesArea}
                                                />
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </div>

                            {error && <div className={styles.errorBanner}>{error}</div>}

                            <div className={styles.footerActions}>
                                {step > 1 && (
                                    <button className={styles.btnBack} onClick={prevStep}>
                                        <ChevronLeft size={18} /> Back
                                    </button>
                                )}
                                <div style={{ flex: 1 }} />
                                {step < 4 ? (
                                    <button className={styles.btnContinue} onClick={nextStep}>
                                        Continue <ChevronRight size={18} />
                                    </button>
                                ) : (
                                    <button className={styles.btnSubmit} onClick={handleSubmit} disabled={isSubmitting}>
                                        {isSubmitting ? 'Confirming...' : 'Finalize Booking'}
                                    </button>
                                )}
                            </div>
                        </motion.div>
                    )}

                    {activeTab === 'inbound' && (
                        <motion.div
                            key="inbound"
                            initial={{ opacity: 0, y: 15 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -15 }}
                            className={styles.aiModule}
                        >
                            <div className={styles.aiHeader}>
                                <div className={styles.aiGlow}>
                                    <Bot size={40} />
                                </div>
                                <h2>High-Fidelity AI Assistant</h2>
                                <p>Call our medically-trained voice agent to handle your appointments in natural language.</p>
                            </div>
                            <div className={styles.aiCard}>
                                <div className={styles.aiStatusPill}>
                                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
                                    Agent Online
                                </div>

                                {/* Phone number to call */}
                                <div style={{ textAlign: 'center', padding: '16px 0 8px' }}>
                                    <div style={{ fontSize: 13, color: 'var(--text-muted, #888)', marginBottom: 6 }}>Call to Book an Appointment</div>
                                    <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: 1, color: 'var(--text-primary, #fff)' }}>
                                        📞 +1 (762) 477-1759
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted, #888)', marginTop: 4 }}>Aria AI will answer — available 24/7</div>
                                </div>

                                <div className={styles.aiInfoGrid}>
                                    <div className={styles.infoCard}>
                                        <span className={styles.infoLabel}>Latency</span>
                                        <span className={styles.infoValue}>~500ms</span>
                                    </div>
                                    <div className={styles.infoCard}>
                                        <span className={styles.infoLabel}>Language</span>
                                        <span className={styles.infoValue}>English (US)</span>
                                    </div>
                                    <div className={styles.infoCard}>
                                        <span className={styles.infoLabel}>Model</span>
                                        <span className={styles.infoValue}>Groq Llama 3.1</span>
                                    </div>
                                </div>

                                {/* Recent inbound calls */}
                                <div style={{ marginTop: 20, width: '100%' }}>
                                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted, #888)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>
                                        Recent Inbound Calls
                                    </div>
                                    {inboundCalls.length === 0 ? (
                                        <div style={{ fontSize: 13, color: 'var(--text-muted, #888)', textAlign: 'center', padding: '12px 0' }}>
                                            No inbound calls yet — call +1 (762) 477-1759 to test
                                        </div>
                                    ) : (
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                            {inboundCalls.map(call => (
                                                <div key={call.callId} style={{
                                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                    padding: '10px 14px', borderRadius: 10,
                                                    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)'
                                                }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                        <div style={{
                                                            width: 8, height: 8, borderRadius: '50%',
                                                            background: call.status === 'ended' ? '#22c55e' : '#f59e0b', flexShrink: 0
                                                        }} />
                                                        <div>
                                                            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary, #fff)' }}>
                                                                {call.patientName}
                                                            </div>
                                                            {call.serviceName && (
                                                                <div style={{ fontSize: 11, color: 'var(--text-muted, #888)' }}>{call.serviceName}</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <div style={{ textAlign: 'right' }}>
                                                        <div style={{ fontSize: 11, color: 'var(--text-muted, #888)' }}>
                                                            {parseApiDate(call.createdAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}
                                                        </div>
                                                        {call.durationSeconds && (
                                                            <div style={{ fontSize: 11, color: 'var(--text-muted, #888)' }}>
                                                                {Math.floor(call.durationSeconds / 60)}m {call.durationSeconds % 60}s
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                <div className={styles.aiFeatures}>
                                    <div className={styles.feature}><Sparkles size={14} /> <span>Smart Scheduling</span></div>
                                    <div className={styles.feature}><Sparkles size={14} /> <span>Clinical Context</span></div>
                                    <div className={styles.feature}><Sparkles size={14} /> <span>CRM Sync</span></div>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {activeTab === 'outbound' && (
                        <motion.div
                            key="outbound"
                            initial={{ opacity: 0, y: 15 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -15 }}
                            className={styles.aiModule}
                        >
                            <div className={styles.aiHeader}>
                                <div className={styles.aiGlowSecondary}>
                                    <PhoneCall size={38} />
                                </div>
                                <h2>Outbound AI Agent</h2>
                                <p>Aria will call the patient, introduce herself, and guide them through booking an appointment.</p>
                            </div>

                            <div className={styles.outboundCard}>
                                <div className={styles.aiStatusPill}>
                                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
                                    Agent Ready
                                </div>

                                {outboundCallState === 'success' ? (
                                    <div className={styles.callSuccessBox}>
                                        <CheckCircle size={32} style={{ color: 'var(--status-success)' }} />
                                        <div>
                                            <div className={styles.callSuccessTitle}>Call Placed Successfully</div>
                                            <div className={styles.callSuccessSub}>Aria is now calling {outboundPhone}. She will guide the patient through booking.</div>
                                            {outboundCallSid && <div className={styles.callSidText}>SID: {outboundCallSid}</div>}
                                        </div>
                                        <button
                                            className={styles.btnGhost}
                                            onClick={() => { setOutboundCallState('idle'); setOutboundPhone(''); setOutboundPatient(''); setOutboundCallSid(''); }}
                                        >
                                            Make Another Call
                                        </button>
                                    </div>
                                ) : (
                                    <>
                                        <div className={styles.fieldGroup}>
                                            <label className={styles.groupLabel}>Patient Phone Number</label>
                                            <input
                                                type="tel"
                                                className={styles.outboundInput}
                                                placeholder="+1 (408) 555-0000 or +92 300 1234567"
                                                value={outboundPhone}
                                                onChange={e => setOutboundPhone(e.target.value)}
                                                disabled={outboundCallState === 'calling'}
                                            />
                                        </div>

                                        <div className={styles.fieldGroup}>
                                            <label className={styles.groupLabel}>Patient Name (optional)</label>
                                            <input
                                                type="text"
                                                className={styles.outboundInput}
                                                placeholder="e.g. John Smith"
                                                value={outboundPatient}
                                                onChange={e => setOutboundPatient(e.target.value)}
                                                disabled={outboundCallState === 'calling'}
                                            />
                                        </div>

                                        {outboundError && (
                                            <div className={styles.errorBanner}>{outboundError}</div>
                                        )}

                                        <button
                                            className={styles.btnPrimaryLarge}
                                            onClick={placeOutboundCall}
                                            disabled={!outboundPhone || outboundCallState === 'calling'}
                                        >
                                            {outboundCallState === 'calling' ? (
                                                <><span className={styles.spinnerInline} /> Placing call…</>
                                            ) : (
                                                <><PhoneCall size={18} /> Call Patient Now</>
                                            )}
                                        </button>

                                        <div className={styles.aiInfoGrid} style={{ marginTop: '1.5rem' }}>
                                            <div className={styles.infoCard}>
                                                <span className={styles.infoLabel}>AI Model</span>
                                                <span className={styles.infoValue}>Groq Llama 3.1</span>
                                            </div>
                                            <div className={styles.infoCard}>
                                                <span className={styles.infoLabel}>Voice</span>
                                                <span className={styles.infoValue}>ElevenLabs (Bella)</span>
                                            </div>
                                            <div className={styles.infoCard}>
                                                <span className={styles.infoLabel}>Provider</span>
                                                <span className={styles.infoValue}>Twilio PSTN</span>
                                            </div>
                                        </div>
                                    </>
                                )}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </main>
        </div>
    );
}
