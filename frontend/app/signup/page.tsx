'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { motion } from 'framer-motion';
import styles from '../login/auth.module.css';

export default function SignupPage() {
    const router = useRouter();
    const { signup } = useAuth();
    const [formData, setFormData] = useState({
        firstName: '',
        lastName: '',
        email: '',
        password: '',
        company: '',
    });
    const [error, setError] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setFormData((prev) => ({
            ...prev,
            [e.target.name]: e.target.value,
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (formData.password.length < 8) {
            setError('Password must be at least 8 characters');
            return;
        }

        setIsSubmitting(true);

        try {
            // Note: Our auth endpoint only takes email, password, firstName, lastName right now.
            // We'll pass them in. In a real scenario, we might also pass 'company'.
            await signup(
                formData.email,
                formData.password,
                formData.firstName,
                formData.lastName
            );
            router.push('/');
        } catch (err: any) {
            setError(err.message || 'Failed to create account');
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
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 2v20M17 5v14M7 5v14M22 10v4M2 10v4" />
                        </svg>
                    </div>
                    CallSync AI
                </Link>

                <div className={styles.marketingContent}>
                    <motion.h1
                        initial="hidden"
                        animate="visible"
                        variants={{
                            hidden: { opacity: 0 },
                            visible: {
                                opacity: 1,
                                transition: {
                                    staggerChildren: 0.03,
                                    delayChildren: 0.2
                                }
                            }
                        }}
                    >
                        <div className={styles.headingLine1}>
                            {"Your AI".split("").map((char, index) => (
                                <motion.span
                                    key={`line1-${index}`}
                                    style={{ display: 'inline-block' }}
                                    variants={{
                                        hidden: { opacity: 0, y: 10 },
                                        visible: { opacity: 1, y: 0 }
                                    }}
                                >
                                    {char === " " ? "\u00A0" : char}
                                </motion.span>
                            ))}
                        </div>
                        <div className={styles.headingLine2}>
                            {"receptionist.".split("").map((char, index) => (
                                <motion.span
                                    key={`line2-${index}`}
                                    style={{ display: 'inline-block' }}
                                    variants={{
                                        hidden: { opacity: 0, y: 10 },
                                        visible: { opacity: 1, y: 0 }
                                    }}
                                >
                                    {char === " " ? "\u00A0" : char}
                                </motion.span>
                            ))}
                        </div>
                        <motion.span
                            className={styles.headingLine3}
                        >
                            {"Always on.".split("").map((char, index) => (
                                <motion.span
                                    key={`line3-${index}`}
                                    style={{ display: 'inline-block' }}
                                    variants={{
                                        hidden: { opacity: 0, y: 10 },
                                        visible: { opacity: 1, y: 0 }
                                    }}
                                >
                                    {char === " " ? "\u00A0" : char}
                                </motion.span>
                            ))}
                        </motion.span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 2.2, duration: 1 }}
                    >
                        Automates appointment scheduling through natural phone conversations. No missed calls. No hold times.
                    </motion.p>
                </div>

                <div className={styles.stats}>
                    <div className={styles.statItem}>
                        <span className={styles.statNum}>2.4M+</span>
                        <span className={styles.statLabel}>AI calls handled</span>
                    </div>
                    <div className={styles.statItem}>
                        <span className={styles.statNum}>340+</span>
                        <span className={styles.statLabel}>businesses trust us</span>
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
                        <h1 className={styles.title}>Create your account</h1>
                        <p className={styles.subtitle}>Start your free trial — no credit card required</p>
                    </div>

                    {error && (
                        <div className={styles.error}>
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className={styles.form}>
                        <div className={styles.row}>
                            <div className={styles.inputGroup}>
                                <label htmlFor="firstName">First Name</label>
                                <input
                                    id="firstName"
                                    name="firstName"
                                    type="text"
                                    value={formData.firstName}
                                    onChange={handleChange}
                                    placeholder="Ada"
                                    required
                                    disabled={isSubmitting}
                                />
                            </div>
                            <div className={styles.inputGroup}>
                                <label htmlFor="lastName">Last Name</label>
                                <input
                                    id="lastName"
                                    name="lastName"
                                    type="text"
                                    value={formData.lastName}
                                    onChange={handleChange}
                                    placeholder="Lovelace"
                                    required
                                    disabled={isSubmitting}
                                />
                            </div>
                        </div>

                        <div className={styles.inputGroup}>
                            <label htmlFor="email">Work Email</label>
                            <input
                                id="email"
                                name="email"
                                type="email"
                                value={formData.email}
                                onChange={handleChange}
                                placeholder="ada@clinic.com"
                                required
                                disabled={isSubmitting}
                            />
                        </div>

                        <div className={styles.inputGroup}>
                            <label htmlFor="password">Password</label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                value={formData.password}
                                onChange={handleChange}
                                placeholder="••••••••"
                                required
                                disabled={isSubmitting}
                            />
                        </div>

                        <div className={styles.inputGroup}>
                            <label htmlFor="company">Company / Clinic Name</label>
                            <input
                                id="company"
                                name="company"
                                type="text"
                                value={formData.company}
                                onChange={handleChange}
                                placeholder="Riverside Medical"
                                required
                                disabled={isSubmitting}
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className={styles.primaryBtn}
                        >
                            {isSubmitting ? (
                                <Loader2 className="spinner" size={18} />
                            ) : (
                                'Create free account'
                            )}
                        </button>
                    </form>

                    <div className={styles.termsText}>
                        By signing up you agree to our Terms of Service and Privacy Policy.
                    </div>

                    <div className={styles.footer}>
                        Already have an account? <Link href="/login" className={styles.link}>Sign in</Link>
                    </div>
                </motion.div>
            </div>
        </div>
    );
}
