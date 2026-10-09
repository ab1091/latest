'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useRouter } from 'next/navigation';

interface User {
    id: string;
    email: string;
    firstName?: string;
    lastName?: string;
    phone?: string;
    role: string;
    business_id?: string;
    businessId?: string;
    google_connected?: boolean;
    permissions?: string[];
}

interface AuthContextType {
    user: User | null;
    accessToken: string | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    login: (email: string, password: string) => Promise<void>;
    signup: (email: string, password: string, firstName?: string, lastName?: string) => Promise<void>;
    logout: () => void;
    refreshToken: () => Promise<void>;
    refreshUser: () => Promise<void>;
    googleLogin: (code: string) => Promise<void>;
    isLoggingOut: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_URL = '/api';

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoggingOut, setIsLoggingOut] = useState(false);
    const router = useRouter();

    // Load stored auth on mount, then silently refresh if token is near expiry
    useEffect(() => {
        const storedToken = localStorage.getItem('accessToken');
        const storedUser = localStorage.getItem('user');

        if (storedToken && storedUser) {
            setAccessToken(storedToken);
            setUser(JSON.parse(storedUser));

            // Check expiry — refresh if token expires within 5 minutes
            try {
                const payload = JSON.parse(atob(storedToken.split('.')[1]));
                const expiresInMs = payload.exp * 1000 - Date.now();
                if (expiresInMs < 5 * 60 * 1000) {
                    // Refresh in background, don't block mount
                    const storedRefreshToken = localStorage.getItem('refreshToken');
                    if (storedRefreshToken) {
                        fetch('/api/auth/refresh-token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ refreshToken: storedRefreshToken }),
                        })
                            .then(r => r.json())
                            .then(data => {
                                if (data?.data?.accessToken) {
                                    setAccessToken(data.data.accessToken);
                                    localStorage.setItem('accessToken', data.data.accessToken);
                                }
                            })
                            .catch(() => {}); // silent — user stays logged in with old token
                    }
                }
            } catch {}
        }

        setIsLoading(false);
    }, []);

    const login = async (email: string, password: string) => {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });

        let data;
        try {
            data = await response.json();
        } catch (err) {
            throw new Error(`Server error (${response.status}): Please try again later.`);
        }

        if (!response.ok) {
            throw new Error(data.error || 'Login failed');
        }

        const { user: userData, accessToken: token, refreshToken: refresh } = data.data;

        setUser(userData);
        setAccessToken(token);

        localStorage.setItem('accessToken', token);
        localStorage.setItem('refreshToken', refresh);
        localStorage.setItem('user', JSON.stringify(userData));
    };

    const googleLogin = async (code: string) => {
        const response = await fetch(`${API_URL}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
        });

        let data;
        try {
            data = await response.json();
        } catch (err) {
            throw new Error(`Server error (${response.status}): Please try again later.`);
        }

        if (!response.ok) {
            throw new Error(data.error || 'Google login failed');
        }

        const { user: userData, accessToken: token, refreshToken: refresh } = data.data;

        setUser(userData);
        setAccessToken(token);

        localStorage.setItem('accessToken', token);
        localStorage.setItem('refreshToken', refresh);
        localStorage.setItem('user', JSON.stringify(userData));
    };

    const signup = async (email: string, password: string, firstName?: string, lastName?: string) => {
        const response = await fetch(`${API_URL}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, firstName, lastName }),
        });

        let data;
        try {
            data = await response.json();
        } catch (err) {
            throw new Error(`Server error (${response.status}): Please try again later.`);
        }

        if (!response.ok) {
            throw new Error(data.error || 'Signup failed');
        }

        const { user: userData, accessToken: token, refreshToken: refresh } = data.data;

        setUser(userData);
        setAccessToken(token);

        localStorage.setItem('accessToken', token);
        localStorage.setItem('refreshToken', refresh);
        localStorage.setItem('user', JSON.stringify(userData));
    };

    const logout = useCallback(() => {
        setIsLoggingOut(true);
        setUser(null);
        setAccessToken(null);
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        localStorage.removeItem('user');
        router.push('/');
        // Reset after a short delay to allow navigation to complete
        setTimeout(() => setIsLoggingOut(false), 1000);
    }, [router]);

    const refreshToken = useCallback(async () => {
        const storedRefreshToken = localStorage.getItem('refreshToken');

        if (!storedRefreshToken) {
            logout();
            return;
        }

        try {
            const response = await fetch(`${API_URL}/auth/refresh-token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refreshToken: storedRefreshToken }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error);
            }

            const { accessToken: newAccessToken } = data.data;
            // Note: backend might not return new refresh token

            setAccessToken(newAccessToken);
            localStorage.setItem('accessToken', newAccessToken);

        } catch {
            logout();
        }
    }, [logout]);
    
    const refreshUser = async () => {
        if (!accessToken) return;
        
        try {
            const response = await fetch(`${API_URL}/auth/me`, {
                headers: { 'Authorization': `Bearer ${accessToken}` },
            });
            
            const data = await response.json();
            if (response.ok && data.success) {
                const userData = data.data.user;
                setUser(userData);
                localStorage.setItem('user', JSON.stringify(userData));
            }
        } catch (error) {
            console.error('Failed to refresh user:', error);
        }
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                accessToken,
                isLoading,
                isAuthenticated: !!user && !!accessToken,
                login,
                googleLogin,
                signup,
                logout,
                refreshToken,
                refreshUser,
                isLoggingOut,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
