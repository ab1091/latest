'use client';

import { useMemo, useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import {
    LayoutDashboard, Users, ListTodo, CalendarDays,
    Phone, MessageCircle, MessageSquare, SlidersHorizontal, LogOut,
    Menu, X, Sun, Moon, PhoneCall, Bot, ArrowLeft,
} from 'lucide-react';

function WhatsAppIcon({ size = 15 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
            <path d="M12 0C5.373 0 0 5.373 0 12c0 2.136.564 4.14 1.546 5.877L.057 23.877a.5.5 0 0 0 .609.61l6.098-1.49A11.942 11.942 0 0 0 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.907 0-3.694-.528-5.218-1.443l-.374-.224-3.878.948.97-3.78-.243-.389A9.937 9.937 0 0 1 2 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/>
        </svg>
    );
}
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { DialerModal } from '@/components/Dialer/DialerModal';
import styles from './UserSideNav.module.css';

const NAV_SECTIONS = [
    {
        title: null,
        items: [
            { label: 'Dashboard', href: '/user/dashboard', icon: LayoutDashboard },
        ],
    },
    {
        title: 'Leads',
        items: [
            { label: 'My Leads', href: '/user/leads', icon: Users },
        ],
    },
    {
        title: 'Communication',
        items: [
            { label: 'All Chats',  href: '/user/conversations',               icon: MessageCircle },
            { label: 'SMS',        href: '/user/conversations?channel=sms',       icon: MessageSquare },
            { label: 'WhatsApp',   href: '/user/conversations?channel=whatsapp',  icon: WhatsAppIcon },
            { label: 'Calls',      href: '/user/calls',                        icon: Phone },
        ],
    },
    {
        title: 'Scheduling',
        items: [
            { label: 'Appointments', href: '/user/appointments', icon: ListTodo },
            { label: 'Calendar',     href: '/user/calendar',     icon: CalendarDays },
        ],
    },
    {
        title: 'AI',
        items: [
            { label: 'My AI Agent', href: '/user/agents', icon: Bot },
        ],
    },
    {
        title: 'General',
        items: [
            { label: 'Settings', href: '/user/settings', icon: SlidersHorizontal },
        ],
    },
];

function LogoMark({ size = 26 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="currentColor" />
            <rect x="4.5" y="12" width="3" height="8" rx="1.5" fill="#fff" opacity="0.7" />
            <rect x="9.5" y="8" width="3" height="16" rx="1.5" fill="#fff" opacity="0.85" />
            <rect x="14.5" y="4" width="3" height="24" rx="1.5" fill="#fff" />
            <rect x="19.5" y="8" width="3" height="16" rx="1.5" fill="#fff" opacity="0.85" />
            <rect x="24.5" y="12" width="3" height="8" rx="1.5" fill="#fff" opacity="0.7" />
        </svg>
    );
}

export function UserSideNav() {
    const pathname      = usePathname();
    const searchParams  = useSearchParams();
    const { user, logout } = useAuth();
    const { theme, toggleTheme, mounted } = useTheme();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [dialerOpen, setDialerOpen] = useState(false);

    useEffect(() => { setMobileOpen(false); }, [pathname]);

    const displayName = [user?.firstName, user?.lastName].filter(Boolean).join(' ') || 'User';
    const initials = useMemo(
        () => displayName.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase() || 'U',
        [displayName],
    );

    return (
        <>
            <div className={styles.mobileBar}>
                <Link href="/user/dashboard" className={styles.logoLink}>
                    <span className={styles.logoMark}><LogoMark /></span>
                    <span>
                        <span className={styles.logoTitle}>AllZone</span>
                        <span className={styles.logoMeta}>User Portal</span>
                    </span>
                </Link>
                <button
                    type="button"
                    className={styles.mobileMenuButton}
                    onClick={() => setMobileOpen((c) => !c)}
                    aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
                >
                    {mobileOpen ? <X size={18} /> : <Menu size={18} />}
                </button>
            </div>

            {mobileOpen && (
                <button type="button" className={styles.mobileBackdrop} onClick={() => setMobileOpen(false)} aria-label="Close menu" />
            )}

            <aside className={`${styles.sidebar} ${mobileOpen ? styles.sidebarOpen : ''}`}>
                <div className={styles.logoBlock}>
                    <Link href="/user/dashboard" className={styles.logoLink}>
                        <span className={styles.logoMark}><LogoMark /></span>
                        <span>
                            <span className={styles.logoTitle}>AllZone</span>
                            <span className={styles.logoMeta}>User Portal</span>
                        </span>
                    </Link>
                </div>

                <div className={styles.themeBlockTop}>
                    <button type="button" className={styles.themeToggleCompact} onClick={toggleTheme}>
                        <div className={styles.themeTrack}>
                            <div className={`${styles.themeThumb} ${theme === 'light' ? styles.themeThumbLight : ''}`}>
                                {mounted ? (
                                    theme === 'dark' ? <Moon size={10} fill="currentColor" /> : <Sun size={10} fill="currentColor" />
                                ) : <div style={{ width: 10, height: 10 }} />}
                            </div>
                        </div>
                        <span className={styles.themeLabel}>{theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</span>
                    </button>
                </div>

                <nav className={styles.nav}>
                    {NAV_SECTIONS.map((section) => (
                        <div key={section.title ?? 'primary'} className={styles.navSection}>
                            {section.title && <div className={styles.sectionLabel}>{section.title}</div>}
                            {section.items.map((item) => {
                                const [itemPath, itemQuery] = item.href.split('?');
                                const itemChannel = itemQuery ? new URLSearchParams(itemQuery).get('channel') : null;
                                const isActive = pathname === itemPath &&
                                    (itemChannel ? searchParams.get('channel') === itemChannel : !searchParams.get('channel'));
                                const Icon = item.icon;
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                                    >
                                        <span className={styles.navIcon}><Icon size={15} /></span>
                                        <span className={styles.navText}>{item.label}</span>
                                    </Link>
                                );
                            })}
                        </div>
                    ))}
                </nav>


                <div className={styles.homeBlock}>
                    <Link href="/" className={styles.homeLink}>
                        <ArrowLeft size={13} />
                        <span>Back to Home</span>
                    </Link>
                </div>

                <div className={styles.userBlock}>
                    <div className={styles.userAvatar}>{initials}</div>
                    <div className={styles.userInfo}>
                        <div className={styles.userName}>{displayName}</div>
                        <div className={styles.userEmail}>{user?.email || ''}</div>
                    </div>
                    <button type="button" onClick={logout} className={styles.logoutButton} title="Log out">
                        <LogOut size={14} />
                    </button>
                </div>
            </aside>

            {dialerOpen && <DialerModal onClose={() => setDialerOpen(false)} />}
        </>
    );
}
