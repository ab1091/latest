'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTheme } from '@/contexts/ThemeContext';
import { useAuth } from '@/contexts/AuthContext';
import { Sun, Moon, ArrowRight, Play, Sparkles, ArrowLeft, MessageCircle, Phone, Users, Zap, FileText, Shield } from 'lucide-react';
import styles from './page.module.css';

const FEATURES = [
    {
        n: '01',
        title: 'WhatsApp Automation',
        sub: 'Twilio · Auto-messaging',
        desc: 'Add a lead and AI instantly sends a personalized WhatsApp welcome message. No reply in 2 days? A follow-up goes out automatically. Full conversation handled by AI.',
        danger: false,
        href: '/leads',
    },
    {
        n: '02',
        title: 'AI Voice Calls',
        sub: 'Vapi · Outbound calling',
        desc: 'Initiate outbound AI voice calls to leads with one click. The AI knows the lead\'s conversation history, qualifies them, and updates the CRM with outcomes.',
        danger: false,
        href: '/leads',
    },
    {
        n: '03',
        title: 'Lead Management CRM',
        sub: 'Full pipeline visibility',
        desc: 'Import CSV or add leads manually. Tag-based routing assigns the right AI agent per lead. Track every status: new → contacted → qualified → converted.',
        danger: false,
        href: '/crm',
    },
    {
        n: '04',
        title: 'Multi-Agent Routing',
        sub: 'Smart tag matching',
        desc: 'Multiple AI agents for different products and services. Tag-based matching routes each lead to the right agent automatically. No data mixing.',
        danger: false,
        href: '/agents',
    },
    {
        n: '05',
        title: 'Call Transcripts',
        sub: 'Every word, logged',
        desc: 'Every AI voice call is recorded with full transcripts, outcome tagging (qualified, no_answer, voicemail), duration tracking, and searchable call history.',
        danger: false,
        href: '/calls',
    },
    {
        n: '06',
        title: 'Smart Compliance',
        sub: 'Respects customer preferences',
        desc: 'Customer preferences are respected automatically. Calls and messages only during appropriate hours in the lead\'s timezone. Max 2 call attempts per lead.',
        danger: false,
        href: null,
    },
];

const STEPS = [
    {
        n: '01',
        title: 'Add your leads',
        desc: 'Import a CSV or add leads manually with name, phone, tags, and preferred channel. Bulk import handles thousands of leads at once.',
    },
    {
        n: '02',
        title: 'AI messages them instantly',
        desc: 'The moment a lead is added with tags, your AI agent sends a personalized WhatsApp message automatically — day or night.',
    },
    {
        n: '03',
        title: 'Conversations qualify leads',
        desc: 'AI responds to replies, answers questions, and moves leads through your pipeline. You see every message in the conversations view.',
    },
    {
        n: '04',
        title: 'Close with a voice call',
        desc: 'When a lead is warm, trigger an outbound AI voice call with one click. The AI uses the chat history as context to continue naturally.',
    },
];

const COMPARISON_ROWS = [
    ['Lead response time',     '< 30 seconds, 24/7',      'Hours or next business day'],
    ['WhatsApp follow-up',     'Automatic, AI-written',   'Manual, often forgotten'],
    ['Call handling',          'Unlimited concurrent',    '1 agent at a time'],
    ['Lead qualification',     'Conversational AI',       'Manual form or cold call'],
    ['Follow-up after no reply', 'Auto after 2 days',     'Depends on agent memory'],
    ['CRM update',             'Real-time, automatic',    'Manual data entry'],
];

const FOOTER_COLUMNS = [
    { title: 'Product',  links: ['Features', 'How It Works', 'Pricing', 'Changelog'] },
    { title: 'Platform', links: ['WhatsApp AI', 'Voice Calls', 'Lead CRM', 'Multi-Agent'] },
    { title: 'Company',  links: ['About AllZone', 'Blog', 'Careers', 'Contact'] },
    { title: 'Legal',    links: ['Privacy Policy', 'Terms', 'DPA', 'Security'] },
];

const TRANSCRIPT_LINES = [
    { role: 'ai',     text: 'Hi John! I\'m Sara from AllZone. I see you\'re interested in our services — great timing. Is this a good moment?' },
    { role: 'lead',   text: 'Yes, I\'ve been meaning to sort out coverage for my family.' },
    { role: 'ai',     text: 'Perfect. For a family of 4, our most popular plan covers $500K from just $29/month. Want me to walk you through it?' },
    { role: 'lead',   text: 'That sounds really affordable, yes please.' },
    { role: 'system', text: 'Lead qualified · Status → Converted' },
];

function LogoMark({ size = 32 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="currentColor" />
            <rect x="4.5"  y="12" width="3" height="8"  rx="1.5" fill="#fff" opacity="0.7"  />
            <rect x="9.5"  y="8"  width="3" height="16" rx="1.5" fill="#fff" opacity="0.85" />
            <rect x="14.5" y="4"  width="3" height="24" rx="1.5" fill="#fff" />
            <rect x="19.5" y="8"  width="3" height="16" rx="1.5" fill="#fff" opacity="0.85" />
            <rect x="24.5" y="12" width="3" height="8"  rx="1.5" fill="#fff" opacity="0.7"  />
        </svg>
    );
}

export default function HomePage() {
    const router       = useRouter();
    const { isAuthenticated, user, logout, isLoading: authLoading } = useAuth();
    const { theme, toggleTheme } = useTheme();
    const [error, setError] = useState<string | null>(null);
    const [step, setStep]   = useState(0);

    useEffect(() => {
        if (step >= TRANSCRIPT_LINES.length) return;
        const t = window.setTimeout(() => setStep(s => s + 1), step === 0 ? 600 : 1500);
        return () => window.clearTimeout(t);
    }, [step]);

    const dashboardUrl  = isAuthenticated && user && !['admin', 'staff', 'super_admin'].includes(user.role) ? '/user/dashboard' : '/dashboard';
    const goToPrimary   = () => router.push(isAuthenticated ? dashboardUrl : '/signup');
    const goToSecondary = () => router.push(isAuthenticated ? dashboardUrl : '/login');

    if (authLoading) {
        return (
            <div className={styles.loadingScreen}>
                <div className={styles.loadingSpinner} />
                <p>Loading AllZone AI…</p>
            </div>
        );
    }

    return (
        <div className={styles.page}>
            {/* ── Navbar ───────────────────────────────────────────────────── */}
            <header className={styles.navbar}>
                <div className={styles.wrap}>
                    <Link href="/" className={styles.brand}>
                        <span className={styles.logoMark}><LogoMark size={30} /></span>
                        <span className={styles.brandText}>AllZone AI</span>
                    </Link>

                    <nav className={styles.navLinks}>
                        <a href="#features">Features</a>
                        <a href="#how-it-works">How It Works</a>
                        <a href="#pricing">Pricing</a>
                    </nav>

                    <div className={styles.navActions}>
                        <button type="button" className={styles.themeToggleNav} onClick={toggleTheme}
                            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
                            {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
                        </button>
                        {isAuthenticated ? (
                            <>
                                <button type="button" className={styles.navButtonGhost} onClick={() => router.back()}>
                                    <ArrowLeft size={15} /> Back
                                </button>
                                <Link href={dashboardUrl} className={styles.navButtonGhost}>Dashboard</Link>
                                <button type="button" className={styles.navButtonPrimary} onClick={logout}>Logout</button>
                            </>
                        ) : (
                            <>
                                <Link href="/login" className={styles.navButtonGhost}>Sign in</Link>
                                <button type="button" className={styles.navButtonPrimary} onClick={goToPrimary}>Get started</button>
                            </>
                        )}
                    </div>
                </div>
            </header>

            <main>
                {/* ── Hero ─────────────────────────────────────────────────── */}
                <section className={styles.heroSection}>
                    <div className={styles.heroGrid}>
                        <div className={styles.heroCopy}>
                            <div className={`${styles.fadeUp} ${styles.delay1} ${styles.heroBadge}`}>
                                <span className={styles.heroBadgePill}>New</span>
                                <span>WhatsApp auto-follow-up now live</span>
                            </div>

                            <h1 className={`${styles.fadeUp} ${styles.delay2} ${styles.heroTitle}`}>
                                Your leads,<br />
                                <span>closed on autopilot.</span>
                            </h1>

                            <p className={`${styles.fadeUp} ${styles.delay3} ${styles.heroSubtitle}`}>
                                AllZone AI messages leads the moment they arrive, follows up automatically,
                                and calls them with an AI voice agent — so your team focuses only on ready buyers.
                            </p>

                            <div className={`${styles.fadeUp} ${styles.delay3} ${styles.heroActions}`}>
                                <button type="button" className={styles.primaryCta} onClick={goToPrimary}>
                                    Start free trial
                                    <ArrowRight size={16} />
                                </button>
                                <button type="button" className={styles.secondaryCta} onClick={goToSecondary}>
                                    <Play size={15} />
                                    See it in action
                                </button>
                            </div>

                            <div className={`${styles.fadeUp} ${styles.delay3} ${styles.heroTrust}`}>
                                <div>
                                    <strong>10x</strong>
                                    <span>faster lead response</span>
                                </div>
                                <div>
                                    <strong>2-day</strong>
                                    <span>auto follow-up</span>
                                </div>
                                <div>
                                    <strong>Auto</strong>
                                    <span>opt-out handling</span>
                                </div>
                            </div>
                        </div>

                        {/* Live WhatsApp / AI voice transcript */}
                        <div className={styles.transcriptCard}>
                            <div className={styles.transcriptHeader}>
                                <span className={styles.liveIndicator} />
                                <span className={styles.transcriptLabel}>AI WhatsApp · Live</span>
                                <span className={styles.transcriptClinic}>AllZone AI</span>
                            </div>

                            <div className={styles.transcriptMessages}>
                                {TRANSCRIPT_LINES.slice(0, step).map((line) => {
                                    if (line.role === 'system') {
                                        return (
                                            <div key={line.text} className={styles.systemBubble}>
                                                <span>✓</span>
                                                <span>{line.text}</span>
                                            </div>
                                        );
                                    }
                                    const isAi = line.role === 'ai';
                                    return (
                                        <div key={line.text} className={`${styles.messageRow} ${isAi ? styles.messageRowAi : styles.messageRowPatient}`}>
                                            {isAi && <div className={styles.aiBadge}>AI</div>}
                                            <div className={`${styles.messageBubble} ${isAi ? styles.messageBubbleAi : styles.messageBubblePatient}`}>
                                                {line.text}
                                            </div>
                                        </div>
                                    );
                                })}
                                {step > 0 && step < TRANSCRIPT_LINES.length && (
                                    <div className={styles.typingDots}>
                                        <span /><span /><span />
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </section>

                {/* ── Features ─────────────────────────────────────────────── */}
                <section id="features" className={styles.section}>
                    <div className={styles.wrap}>
                        <div className={styles.sectionHeader}>
                            <span className={styles.sectionEyebrow}>Platform</span>
                            <h2>Everything your sales team does. Done automatically.</h2>
                        </div>
                        <div className={styles.featuresGrid}>
                            {FEATURES.map((feature) => {
                                const inner = (
                                    <>
                                        <div className={styles.featureTop}>
                                            <span className={styles.featureNumber}>{feature.n}</span>
                                            <span className={`${styles.featureTag} ${feature.danger ? styles.featureTagDanger : ''}`}>{feature.sub}</span>
                                        </div>
                                        <h3>{feature.title}</h3>
                                        <p>{feature.desc}</p>
                                        {feature.href && <span className={styles.featureArrow}>→</span>}
                                    </>
                                );
                                return feature.href && isAuthenticated ? (
                                    <Link key={feature.n} href={feature.href} className={`${styles.featureCard} ${styles.featureCardLink}`}>
                                        {inner}
                                    </Link>
                                ) : (
                                    <article key={feature.n} className={styles.featureCard}>
                                        {inner}
                                    </article>
                                );
                            })}
                        </div>
                    </div>
                </section>

                {/* ── How it works ─────────────────────────────────────────── */}
                <section id="how-it-works" className={`${styles.section} ${styles.sectionMuted}`}>
                    <div className={styles.wrap}>
                        <div className={styles.sectionHeader}>
                            <span className={styles.sectionEyebrow}>Process</span>
                            <h2>From lead added to deal closed — automatically.</h2>
                        </div>
                        <div className={styles.stepsGrid}>
                            <div className={styles.stepsLine} />
                            {STEPS.map((stepItem) => (
                                <article key={stepItem.n} className={styles.stepCard}>
                                    <div className={styles.stepNumber}>{stepItem.n}</div>
                                    <h3>{stepItem.title}</h3>
                                    <p>{stepItem.desc}</p>
                                </article>
                            ))}
                        </div>
                    </div>
                </section>

                {/* ── Comparison ───────────────────────────────────────────── */}
                <section id="pricing" className={styles.section}>
                    <div className={styles.wrap}>
                        <div className={styles.sectionHeader}>
                            <span className={styles.sectionEyebrow}>Comparison</span>
                            <h2>AI agent vs. traditional agent.</h2>
                        </div>
                        <div className={styles.comparisonTable}>
                            <div className={styles.comparisonHead}>
                                <div>Capability</div>
                                <div className={styles.comparisonBrandHead}>
                                    <span className={styles.logoMarkSmall}><LogoMark size={16} /></span>
                                    AllZone AI
                                </div>
                                <div>Traditional Agent</div>
                            </div>
                            {COMPARISON_ROWS.map(([capability, ai, trad]) => (
                                <div key={capability} className={styles.comparisonRow}>
                                    <div>{capability}</div>
                                    <div className={styles.comparisonHighlight}><span>✓</span>{ai}</div>
                                    <div>{trad}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                {/* ── CTA ──────────────────────────────────────────────────── */}
                <section className={styles.ctaSection}>
                    <div className={styles.wrap}>
                        <div className={styles.ctaBadge}>White-label ready · AI powered · Auto opt-out</div>
                        <h2>Stop losing leads.<br /><span>Start closing them.</span></h2>
                        <p>
                            Set up in one afternoon — connect your lead source, configure your AI agent,
                            and watch WhatsApp conversations start automatically.
                        </p>
                        <div className={styles.ctaActions}>
                            <button type="button" className={styles.ctaPrimary} onClick={goToPrimary}>
                                Start free trial
                                <ArrowRight size={16} />
                            </button>
                            <button type="button" className={styles.ctaSecondary} onClick={goToSecondary}>Book a demo</button>
                        </div>
                    </div>
                </section>
            </main>

            {/* ── Footer ───────────────────────────────────────────────────── */}
            <footer className={styles.footer}>
                <div className={styles.wrap}>
                    <div className={styles.footerGrid}>
                        <div>
                            <div className={styles.footerBrand}>
                                <span className={styles.logoMark}><LogoMark size={28} /></span>
                                <span className={styles.footerBrandText}>AllZone AI</span>
                            </div>
                            <p className={styles.footerIntro}>
                                AI-powered lead automation. WhatsApp + voice calls, fully automated.
                            </p>
                            <p className={styles.footerMeta}>Built by AllZone Technologies</p>
                        </div>
                        {FOOTER_COLUMNS.map((column) => (
                            <div key={column.title}>
                                <div className={styles.footerHeading}>{column.title}</div>
                                <div className={styles.footerLinks}>
                                    {column.links.map((link) => <a key={link} href="#">{link}</a>)}
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className={styles.footerBottom}>
                        <span>© 2026 AllZone Technologies. All rights reserved.</span>
                        <span>Vapi · Twilio · WhatsApp · Groq</span>
                    </div>
                </div>
            </footer>

            {error && (
                <button type="button" className={styles.errorToast} onClick={() => setError(null)}>
                    <Sparkles size={16} />
                    {error}
                </button>
            )}
        </div>
    );
}
