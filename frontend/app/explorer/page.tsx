'use client';

export const dynamic = 'force-dynamic';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { SideNav } from '@/components/SideNav/SideNav';
import { ClinicCard } from '@/components/ClinicCard/ClinicCard';
import { useDialer } from '@/contexts/DialerContext';
import { useAuth } from '@/contexts/AuthContext';
import styles from './explorer.module.css';

interface Provider {
    id: string;
    name: string;
    specialty: string;
    bio: string;
    city: string;
    address: string;
    phone: string;
    email: string;
}

function isNonEmptyString(value: string | null | undefined): value is string {
    return typeof value === 'string' && value.trim().length > 0;
}

export default function ClinicExplorerPage() {
    const { startCall } = useDialer();
    const { accessToken } = useAuth();

    const [providers, setProviders] = useState<Provider[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filters, setFilters] = useState({
        search: '',
        city: '',
        specialty: '',
        available: false,
    });
    const [metadata, setMetadata] = useState({ cities: [] as string[], specialties: [] as string[] });

    const fetchMetadata = useCallback(async () => {
        if (!accessToken) return;
        try {
            const response = await fetch('/api/appointments/filters', {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            const payload = await response.json();
            if (payload.success) {
                setMetadata({
                    cities: (payload.data.cities || []).filter(isNonEmptyString),
                    specialties: (payload.data.specialties || []).filter(isNonEmptyString),
                });
            }
        } catch {
            setMetadata({ cities: [], specialties: [] });
        }
    }, [accessToken]);

    const fetchProviders = useCallback(async () => {
        if (!accessToken) return;
        setIsLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams();
            if (filters.search) params.append('search', filters.search);
            if (filters.city) params.append('city', filters.city);
            if (filters.specialty) params.append('specialty', filters.specialty);
            if (filters.available) params.append('available', 'true');

            const response = await fetch(`/api/appointments/providers?${params.toString()}`, {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            const payload = await response.json();
            if (!payload.success) {
                throw new Error(payload.error || 'Failed to fetch providers');
            }
            setProviders(payload.data.providers || []);
        } catch (issue: any) {
            setError(issue.message || 'Failed to load providers');
        } finally {
            setIsLoading(false);
        }
    }, [accessToken, filters]);

    useEffect(() => {
        void fetchMetadata();
    }, [fetchMetadata]);

    useEffect(() => {
        void fetchProviders();
    }, [fetchProviders]);

    const activeFilters = useMemo(() => {
        return [filters.search, filters.city, filters.specialty, filters.available].filter(Boolean).length;
    }, [filters]);

    return (
        <div className={styles.page}>
            <SideNav />
            <main className={styles.main}>
                <div className={styles.layout}>
                    <aside className={styles.filterRail}>
                        <div>
                            <h1 className={styles.title}>Find a Clinic</h1>
                            <p className={styles.subtitle}>Search providers and book directly.</p>
                        </div>

                        <div className={styles.filterCard}>
                            <div className={styles.field}>
                                <span className={styles.label}>Search</span>
                                <div className={styles.searchWrap}>
                                    <Search size={14} className={styles.searchIcon} />
                                    <input
                                        className={styles.input}
                                        value={filters.search}
                                        onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))}
                                        placeholder="Name or specialty…"
                                    />
                                </div>
                            </div>

                            <div className={styles.field}>
                                <span className={styles.label}>Specialty</span>
                                <select
                                    className={styles.select}
                                    value={filters.specialty}
                                    onChange={(event) => setFilters((current) => ({ ...current, specialty: event.target.value }))}
                                >
                                    <option value="">All</option>
                                    {metadata.specialties.map((specialty) => (
                                        <option key={specialty} value={specialty}>{specialty}</option>
                                    ))}
                                </select>
                            </div>

                            <div className={styles.field}>
                                <span className={styles.label}>Location</span>
                                <select
                                    className={styles.select}
                                    value={filters.city}
                                    onChange={(event) => setFilters((current) => ({ ...current, city: event.target.value }))}
                                >
                                    <option value="">All</option>
                                    {metadata.cities.map((city) => (
                                        <option key={city} value={city}>{city}</option>
                                    ))}
                                </select>
                            </div>

                            <button
                                type="button"
                                className={styles.availableRow}
                                onClick={() => setFilters((current) => ({ ...current, available: !current.available }))}
                            >
                                <div>
                                    <div className={styles.availableTitle}>Available Now</div>
                                    <div className={styles.availableMeta}>Show only available providers</div>
                                </div>
                                <div className={`${styles.toggle} ${filters.available ? styles.toggleActive : ''}`}>
                                    <div className={`${styles.toggleThumb} ${filters.available ? styles.toggleThumbActive : ''}`} />
                                </div>
                            </button>
                        </div>

                        <div className={styles.countCard}>
                            <span className={styles.countValue}>{providers.length}</span>
                            <span className={styles.countLabel}>providers found</span>
                        </div>

                        {activeFilters > 0 && (
                            <div className={styles.activeFilters}>
                                {filters.search && <span className={styles.filterChip}>{filters.search}</span>}
                                {filters.specialty && <span className={styles.filterChip}>{filters.specialty}</span>}
                                {filters.city && <span className={styles.filterChip}>{filters.city}</span>}
                                {filters.available && <span className={styles.filterChip}>Available</span>}
                            </div>
                        )}
                    </aside>

                    <section className={styles.resultsColumn}>
                        <div className={styles.resultsHeader}>
                            <div className={styles.resultsTitle}>All Providers</div>
                            <div className={styles.realtimePill}><span className={styles.realtimeDot} />Real-time</div>
                        </div>

                        <div className={styles.resultsScroll}>
                            {isLoading ? (
                                <div className={styles.emptyState}>Loading providers…</div>
                            ) : error ? (
                                <div className={styles.emptyState}>{error}</div>
                            ) : providers.length === 0 ? (
                                <div className={styles.emptyState}>No providers found. Try adjusting your filters.</div>
                            ) : (
                                <div className={styles.grid}>
                                    {providers.map((provider) => (
                                        <ClinicCard
                                            key={provider.id}
                                            provider={provider}
                                            canCall={Boolean(provider.phone)}
                                            onCallClick={startCall}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    </section>
                </div>
            </main>
        </div>
    );
}
