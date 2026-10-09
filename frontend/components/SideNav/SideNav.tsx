'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    LayoutDashboard,
    SlidersHorizontal,
    LogOut,
    Menu,
    X,
    Sun,
    Moon,
    Users,
    Bot,
    MessageCircle,
    BarChart2,
    UserCog,
    Zap,
    Settings2,
    CreditCard,
    LayoutGrid,
    Plug,
    Building2,
    ArrowLeftRight,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useAgencyScope } from '@/contexts/AgencyScopeContext';
import { useTheme } from '@/contexts/ThemeContext';
import { DialerModal } from '@/components/Dialer/DialerModal';
import { ROLE_RANK, hasModuleAccess, type Role } from '@/lib/permissions';
import styles from './SideNav.module.css';

const AGENCY_GATE_EXEMPT = new Set(['/settings', '/platform']);

type NavItem = {
    label: string;
    href: string;
    icon: typeof LayoutDashboard;
    /** Minimum role required to see this item. Defaults to 'customer' (any logged-in user). */
    minRole?: Role;
    /** Shareable module key — lets a specific staff/customer see this item even
     * below minRole, if an admin has explicitly granted it (see lib/permissions). */
    moduleKey?: string;
};

type NavSection = {
    title: string | null;
    items: NavItem[];
};

// The 12-item Lead Command Center nav, plus pre-existing features
// (Conversations/Calls/Appointments/CRM contacts) folded in alongside it.
const NAV_SECTIONS: NavSection[] = [
    {
        title: null,
        items: [
            { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
        ],
    },
    {
        title: 'Leads',
        items: [
            { label: 'Leads',              href: '/leads',               icon: Users,      minRole: 'staff', moduleKey: 'leads' },
            { label: 'Pipeline',           href: '/leads?view=pipeline', icon: LayoutGrid, minRole: 'staff', moduleKey: 'leads' },
            { label: 'Automation',         href: '/automation',         icon: Zap,        minRole: 'admin', moduleKey: 'automation' },
            { label: 'Lead Configs',       href: '/lead-configs',       icon: SlidersHorizontal, minRole: 'admin', moduleKey: 'lead_configs' },
            { label: 'CRM Settings',       href: '/crm-settings',       icon: Settings2,  minRole: 'admin', moduleKey: 'crm_settings' },
        ],
    },
    {
        title: 'Communication',
        items: [
            { label: 'Communication', href: '/communication', icon: MessageCircle, minRole: 'staff', moduleKey: 'communication' },
        ],
    },
    {
        title: 'AI',
        items: [
            { label: 'AI Agents', href: '/agents', icon: Bot, minRole: 'admin', moduleKey: 'ai_agents' },
        ],
    },
    {
        title: 'Organization',
        items: [
            { label: 'Team Management',    href: '/users',                        icon: UserCog,    minRole: 'admin', moduleKey: 'team_management' },
            { label: 'Reports & Analytics', href: '/analytics',                    icon: BarChart2,  minRole: 'admin', moduleKey: 'analytics' },
            { label: 'Integrations',        href: '/settings?tab=integrations',    icon: Plug,       minRole: 'admin', moduleKey: 'integrations' },
            { label: 'Billing',             href: '/billing',                     icon: CreditCard, minRole: 'admin', moduleKey: 'billing' },
        ],
    },
    {
        title: 'System',
        items: [
            { label: 'Settings', href: '/settings', icon: SlidersHorizontal },
        ],
    },
    {
        title: 'Platform',
        items: [
            { label: 'Platform', href: '/platform', icon: Building2, minRole: 'super_admin' },
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

export function SideNav() {
    const pathname = usePathname();
    const router = useRouter();
    const { user, accessToken, logout } = useAuth();
    const { agency, clearAgency } = useAgencyScope();
    const { theme, toggleTheme, mounted } = useTheme();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [dialerOpen, setDialerOpen] = useState(false);
    const [commCount, setCommCount] = useState<number | null>(null);
    const userRank = ROLE_RANK[(user?.role as Role) || 'customer'] ?? 0;
    const isSuperAdmin = user?.role === 'super_admin';

    useEffect(() => {
        if (!accessToken) return;
        const fetchCommCount = async () => {
            try {
                const res = await fetch('/api/conversations', {
                    headers: { Authorization: `Bearer ${accessToken}` },
                });
                const d = await res.json();
                if (d.success && Array.isArray(d.data?.conversations)) {
                    // Count of conversations with replies (real customer engagements)
                    const count = d.data.conversations.filter((c: any) => c.has_reply).length;
                    setCommCount(count);
                }
            } catch {}
        };
        fetchCommCount();
        const poll = setInterval(fetchCommCount, 15000);
        return () => clearInterval(poll);
    }, [accessToken]);

    const exitAgency = () => {
        clearAgency();
        router.push('/platform');
    };

    useEffect(() => {
        setMobileOpen(false);
    }, [pathname]);

    const displayName = [user?.firstName, user?.lastName].filter(Boolean).join(' ') || 'Admin User';
    const initials = useMemo(
        () => displayName.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase() || 'AU',
        [displayName],
    );

    return (
        <>
            <div className={styles.mobileBar}>
                <Link href="/" className={styles.logoLink}>
                    <span className={styles.logoMark}><LogoMark /></span>
                    <span>
                        <span className={styles.logoTitle}>AllZone</span>
                        <span className={styles.logoMeta}>v3.2.1 · Pro</span>
                    </span>
                </Link>
                <button
                    type="button"
                    className={styles.mobileMenuButton}
                    onClick={() => setMobileOpen((current) => !current)}
                    aria-expanded={mobileOpen}
                    aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
                >
                    {mobileOpen ? <X size={18} /> : <Menu size={18} />}
                </button>
            </div>

            {mobileOpen && <button type="button" className={styles.mobileBackdrop} onClick={() => setMobileOpen(false)} aria-label="Close navigation overlay" />}

            <aside className={`${styles.sidebar} ${mobileOpen ? styles.sidebarOpen : ''}`}>
                <div className={styles.logoBlock}>
                    <Link href="/" className={styles.logoLink}>
                        <span className={styles.logoMark}><LogoMark /></span>
                        <span>
                            <span className={styles.logoTitle}>AllZone</span>
                            <span className={styles.logoMeta}>v3.2.1 · Pro</span>
                        </span>
                    </Link>
                </div>

                {isSuperAdmin && agency && (
                    <button
                        type="button"
                        onClick={exitAgency}
                        title="Exit back to Platform view"
                        style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                            margin: '0 16px 12px', padding: '8px 10px', borderRadius: 8,
                            background: 'var(--primary-subtle)', border: '1px solid var(--primary-border)',
                            color: 'var(--primary-text)', fontSize: 11.5, fontWeight: 600,
                            cursor: 'pointer', textAlign: 'left',
                        }}
                    >
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            Viewing: {agency.name}
                        </span>
                        <ArrowLeftRight size={13} style={{ flexShrink: 0 }} />
                    </button>
                )}

                <div className={styles.themeBlockTop}>
                    <button
                        type="button"
                        className={styles.themeToggleCompact}
                        onClick={toggleTheme}
                        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                    >
                        <div className={styles.themeTrack}>
                            <div className={`${styles.themeThumb} ${theme === 'light' ? styles.themeThumbLight : ''}`}>
                                {mounted ? (
                                    theme === 'dark' ? <Moon size={10} fill="currentColor" /> : <Sun size={10} fill="currentColor" />
                                ) : (
                                    <div style={{ width: 10, height: 10 }} />
                                )}
                            </div>
                        </div>
                        <span className={styles.themeLabel}>
                            {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}
                        </span>
                    </button>
                </div>

                <nav className={styles.nav}>
                    {NAV_SECTIONS.map((section) => {
                        const items = section.items.filter((item) =>
                            item.moduleKey
                                ? hasModuleAccess(user, item.moduleKey, item.minRole || 'staff')
                                : userRank >= (ROLE_RANK[item.minRole || 'customer'])
                        );
                        if (items.length === 0) return null;

                        return (
                            <div key={section.title ?? 'primary'} className={styles.navSection}>
                                {section.title && <div className={styles.sectionLabel}>{section.title}</div>}
                                {items.map((item) => {
                                    const isActive = pathname === item.href.split('?')[0];
                                    const Icon = item.icon;
                                    // super_admin has no business of its own — every business-scoped
                                    // page (everything except Dashboard/Settings/Platform) is
                                    // meaningless without an agency selected from Platform first.
                                    const needsAgency = isSuperAdmin && !agency
                                        && !AGENCY_GATE_EXEMPT.has(item.href.split('?')[0]);
                                    const href = needsAgency ? '/platform' : item.href;
                                    return (
                                        <Link
                                            key={item.href}
                                            href={href}
                                            title={needsAgency ? 'Select an agency from Platform first' : undefined}
                                            className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                                        >
                                            <span className={styles.navIcon}><Icon size={15} /></span>
                                            <span className={styles.navText}>{item.label}</span>
                                            {item.href === '/communication' && typeof commCount === 'number' && commCount > 0 && (
                                                <span className={styles.navBadge}>{commCount}</span>
                                            )}
                                        </Link>
                                    );
                                })}
                            </div>
                        );
                    })}
                </nav>



                <div className={styles.userBlock}>
                    <div className={styles.userAvatar}>{initials}</div>
                    <div className={styles.userInfo}>
                        <div className={styles.userName}>{displayName}</div>
                        <div className={styles.userEmail}>{user?.email || 'admin@allzonetech.com'}</div>
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
