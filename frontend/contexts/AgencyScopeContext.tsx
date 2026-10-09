'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useAuth } from './AuthContext';

interface Agency {
    id: string;
    name: string;
}

interface AgencyScopeContextType {
    agency: Agency | null;
    setAgency: (agency: Agency) => void;
    clearAgency: () => void;
}

const AgencyScopeContext = createContext<AgencyScopeContextType | undefined>(undefined);

const COOKIE_NAME = 'sa_business_id';
const STORAGE_KEY = 'sa_agency';

function writeCookie(value: string | null) {
    if (value) {
        document.cookie = `${COOKIE_NAME}=${encodeURIComponent(value)}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
    } else {
        document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
    }
}

export function AgencyScopeProvider({ children }: { children: ReactNode }) {
    const { user } = useAuth();
    const [agency, setAgencyState] = useState<Agency | null>(null);

    useEffect(() => {
        if (user?.role !== 'super_admin') return;
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                setAgencyState(parsed);
                writeCookie(parsed.id);
            } catch {}
        }
    }, [user?.role]);

    const setAgency = (next: Agency) => {
        setAgencyState(next);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        writeCookie(next.id);
    };

    const clearAgency = () => {
        setAgencyState(null);
        localStorage.removeItem(STORAGE_KEY);
        writeCookie(null);
    };

    return (
        <AgencyScopeContext.Provider value={{ agency, setAgency, clearAgency }}>
            {children}
        </AgencyScopeContext.Provider>
    );
}

export function useAgencyScope() {
    const ctx = useContext(AgencyScopeContext);
    if (!ctx) throw new Error('useAgencyScope must be used within AgencyScopeProvider');
    return ctx;
}
