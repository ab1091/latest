import './globals.css';
import type { Metadata } from 'next';
import { Inter, Outfit } from 'next/font/google';
import { AuthProvider } from '@/contexts/AuthContext';
import { AgencyScopeProvider } from '@/contexts/AgencyScopeContext';
import ClientGoogleProvider from '@/components/ClientGoogleProvider';
import { DialerProvider } from '@/contexts/DialerContext';

export const metadata: Metadata = {
    title: 'AllZone AI',
    description: 'AI-powered lead automation for insurance agents. WhatsApp + voice calls, fully automated.',
};

const inter = Inter({
    subsets: ['latin'],
    variable: '--font-sans',
});

const outfit = Outfit({
    subsets: ['latin'],
    variable: '--font-display',
});

const themeBootScript = `
(() => {
  const root = document.documentElement;
  const saved = localStorage.getItem('callsync-theme');
  if (saved) {
    root.setAttribute('data-theme', saved);
    root.style.colorScheme = saved;
  } else {
    // Default to dark for premium look, or check system
    root.setAttribute('data-theme', 'dark');
    root.style.colorScheme = 'dark';
  }
})();
`;

import { ThemeProvider } from '@/contexts/ThemeContext';

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en" suppressHydrationWarning>
            <head>
                <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
            </head>
            <body className={`${inter.variable} ${outfit.variable}`}>
                <ClientGoogleProvider>
                    <AuthProvider>
                        <AgencyScopeProvider>
                            <ThemeProvider>
                                <DialerProvider>
                                    {children}
                                </DialerProvider>
                            </ThemeProvider>
                        </AgencyScopeProvider>
                    </AuthProvider>
                </ClientGoogleProvider>
            </body>
        </html>
    );
}
