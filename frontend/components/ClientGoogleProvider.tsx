"use client";

import { GoogleOAuthProvider } from '@react-oauth/google';
import React from 'react';

// You might want to move this to an env var
// Ensure NEXT_PUBLIC_GOOGLE_CLIENT_ID is set in .env.local
const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "YOUR_GOOGLE_CLIENT_ID";

export default function ClientGoogleProvider({
    children,
}: {
    children: React.ReactNode;
}) {
    if (clientId === "YOUR_GOOGLE_CLIENT_ID") {
        console.warn("Google Client ID not found. Please set NEXT_PUBLIC_GOOGLE_CLIENT_ID in .env.local");
    }

    return (
        <GoogleOAuthProvider clientId={clientId}>
            {children}
        </GoogleOAuthProvider>
    );
}
