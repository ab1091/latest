export type Role = 'customer' | 'staff' | 'admin' | 'super_admin';

export const ROLE_RANK: Record<Role, number> = { customer: 0, staff: 1, admin: 2, super_admin: 3 };

export interface PermissionUser {
    role: string;
    permissions?: string[];
}

/** Single source of truth for every individually-shareable section — used by
 * both the sidebar (what shows) and each page's own guard (what's actually
 * allowed if someone opens the URL directly). */
export const PERMISSION_MODULES: { key: string; label: string }[] = [
    { key: 'leads',            label: 'Leads' },
    { key: 'automation',       label: 'Automation' },
    { key: 'lead_configs',     label: 'Lead Configs' },
    { key: 'crm_settings',     label: 'CRM Settings' },
    { key: 'communication',    label: 'Communication' },
    { key: 'ai_agents',        label: 'AI Agents' },
    { key: 'team_management',  label: 'Team Management' },
    { key: 'analytics',        label: 'Reports & Analytics' },
    { key: 'integrations',     label: 'Integrations' },
    { key: 'billing',          label: 'Billing' },
];

/**
 * True if this user may access the given module. Admin/super_admin always
 * pass. Otherwise their role rank must clear minRole, OR the module key must
 * be in their explicitly-granted `permissions` — permissions only ever ADD
 * access on top of the role floor, never take away what the role already
 * grants, so existing accounts never lose anything by default.
 */
export function hasModuleAccess(user: PermissionUser | null | undefined, moduleKey: string, minRole: Role = 'staff'): boolean {
    if (!user) return false;
    if (user.role === 'admin' || user.role === 'super_admin') return true;
    const rank = ROLE_RANK[user.role as Role] ?? 0;
    if (rank >= ROLE_RANK[minRole]) return true;
    return !!user.permissions?.includes(moduleKey);
}
