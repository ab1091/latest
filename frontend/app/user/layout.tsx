'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { UserSideNav } from '@/components/UserSideNav/UserSideNav';
import { UserTopBar } from '@/components/UserTopBar/UserTopBar';

export default function UserLayout({ children }: { children: React.ReactNode }) {
    const { user, isLoading, isAuthenticated } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (isLoading) return;
        if (!isAuthenticated) {
            router.replace('/login');
        } else if (user?.role === 'admin' || user?.role === 'staff' || user?.role === 'super_admin') {
            router.replace('/dashboard');
        }
    }, [isLoading, isAuthenticated, user, router]);

    if (isLoading) return null;
    if (!isAuthenticated) return null;
    if (user?.role === 'admin' || user?.role === 'staff' || user?.role === 'super_admin') return null;

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <UserSideNav />
            <div style={{ marginLeft: '220px', flex: 1, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
                <UserTopBar />
                <main style={{ flex: 1, padding: '28px 32px', overflowY: 'auto' }}>
                    {children}
                </main>
            </div>
        </div>
    );
}
