'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useGoogleLogin, CodeResponse } from '@react-oauth/google';
import { motion } from 'framer-motion';
import styles from './auth.module.css';

export default function LoginPage() {
    const router = useRouter();
    const { login, googleLogin, isLoading } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleGoogleLogin = useGoogleLogin({
        flow: 'auth-code',
        scope: 'https://www.googleapis.com/auth/calendar.events',
        // @ts-ignore
        prompt: 'consent',
        onSuccess: async (codeResponse: CodeResponse) => {
            setIsSubmitting(true);
            try {
                await googleLogin(codeResponse.code);
                router.push('/');
            } catch (err: any) {
                setError(err.message || 'Google login failed');
                setIsSubmitting(false);
            }
        },
        onError: () => {
            setError('Google login failed');
        }
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsSubmitting(true);

        try {
            await login(email, password);
            const storedUser = localStorage.getItem('user');
            const userData = storedUser ? JSON.parse(storedUser) : null;
            if (userData?.role === 'super_admin') {
                // super_admin has no agency of its own — land on the cross-agency
                // Platform view unless they'd already picked one to manage.
                router.push(localStorage.getItem('sa_agency') ? '/dashboard' : '/platform');
            } else {
                const isAdmin = ['admin', 'staff'].includes(userData?.role);
                router.push(isAdmin ? '/dashboard' : '/user/dashboard');
            }
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className={styles.splitContainer}>
            {/* Left Marketing Pane */}
            <div className={styles.leftPane}>
                <Link href="/" className={styles.brandLockup}>
                    <div className={styles.brandIcon}>
                        <svg width="18" height="18" viewBox="0 0 32 32" fill="none">
                            <rect x="4.5" y="12" width="3" height="8" rx="1.5" fill="#fff" opacity="0.7" />
                            <rect x="9.5" y="8" width="3" height="16" rx="1.5" fill="#fff" opacity="0.85" />
                            <rect x="14.5" y="4" width="3" height="24" rx="1.5" fill="#fff" />
                            <rect x="19.5" y="8" width="3" height="16" rx="1.5" fill="#fff" opacity="0.85" />
                            <rect x="24.5" y="12" width="3" height="8" rx="1.5" fill="#fff" opacity="0.7" />
                        </svg>
                    </div>
                    AllZone
                </Link>

                <div className={styles.marketingContent}>
                    <motion.h1
                        initial="hidden"
                        animate="visible"
                        variants={{
                            hidden: { opacity: 0 },
                            visible: { opacity: 1, transition: { staggerChildren: 0.03, delayChildren: 0.2 } }
                        }}
                    >
                        <div className={styles.headingLine1}>
                            {"AI Agents that".split("").map((char, index) => (
                                <motion.span key={`l1-${index}`} style={{ display: 'inline-block' }}
                                    variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}>
                                    {char === " " ? "\u00A0" : char}
                                </motion.span>
                            ))}
                        </div>
                        <div className={styles.headingLine2}>
                            {"close deals.".split("").map((char, index) => (
                                <motion.span key={`l2-${index}`} style={{ display: 'inline-block' }}
                                    variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}>
                                    {char === " " ? "\u00A0" : char}
                                </motion.span>
                            ))}
                        </div>
                        <motion.span className={styles.headingLine3}>
                            {"24/7, no breaks.".split("").map((char, index) => (
                                <motion.span key={`l3-${index}`} style={{ display: 'inline-block' }}
                                    variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}>
                                    {char === " " ? "\u00A0" : char}
                                </motion.span>
                            ))}
                        </motion.span>
                    </motion.h1>
                    <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.2, duration: 1 }}>
                        AllZone puts AI agents on your sales team — calling leads, sending SMS, booking consultations, and following up automatically.
                    </motion.p>
                </div>

                <div className={styles.stats}>
                    <div className={styles.statItem}>
                        <span className={styles.statNum}>10K+</span>
                        <span className={styles.statLabel}>leads managed by AI</span>
                    </div>
                    <div className={styles.statItem}>
                        <span className={styles.statNum}>3x</span>
                        <span className={styles.statLabel}>faster lead response</span>
                    </div>
                    <div className={styles.statItem}>
                        <span className={styles.statNum}>99.9%</span>
                        <span className={styles.statLabel}>uptime SLA</span>
                    </div>
                </div>
            </div>

            {/* Right Form Pane */}
            <div className={styles.rightPane}>
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className={styles.formContainer}
                >
                    <div className={styles.header}>
                        <h1 className={styles.title}>Welcome back</h1>
                        <p className={styles.subtitle}>Sign in to your AllZone dashboard</p>
                    </div>

                    {error && (
                        <div className={styles.error}>
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className={styles.form}>
                        <div className={styles.inputGroup}>
                            <label htmlFor="email">Email</label>
                            <input
                                id="email"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="admin@allzone.ai"
                                required
                                disabled={isLoading || isSubmitting}
                            />
                        </div>

                        <div className={styles.inputGroup}>
                            <label htmlFor="password">Password</label>
                            <input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                required
                                disabled={isLoading || isSubmitting}
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading || isSubmitting}
                            className={styles.primaryBtn}
                        >
                            {(isLoading || isSubmitting) ? (
                                <Loader2 className="spinner" size={18} />
                            ) : (
                                'Sign in'
                            )}
                        </button>
                    </form>

                    <div className={styles.divider}>
                        <span>or</span>
                    </div>

                    <button
                        type="button"
                        onClick={() => handleGoogleLogin()}
                        className={styles.googleBtn}
                        disabled={isLoading || isSubmitting}
                    >
                        <svg width="18" height="18" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
                            <path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8c-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4C12.955 4 4 12.955 4 24s8.955 20 20 20s20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z" />
                            <path fill="#FF3D00" d="m6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4C16.318 4 9.656 8.337 6.306 14.691z" />
                            <path fill="#4CAF50" d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238C29.211 35.091 26.715 36 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z" />
                            <path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303c-.792 2.237-2.231 4.166-4.087 5.571c0 .001-.001.002-.001.003l6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z" />
                        </svg>
                        Continue with Google
                    </button>

                    <div className={styles.footer}>
                        No account? <Link href="/signup" className={styles.link}>Create one free</Link>
                    </div>
                </motion.div>
            </div>
        </div>
    );
}
