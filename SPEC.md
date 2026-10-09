# Spec: Direct Human Dialer & Clinic Explorer

## 1. Objective
Enable a "Human-in-the-loop" experience where patients can discover clinics and doctors via an advanced filtering UI and initiate direct, browser-to-phone voice calls. 

**Core Goal**: Bridge the gap between digital discovery and human connection without AI mediation in the live call session.

## 2. Tech Stack
- **Frontend**: Next.js 14 (App Router), Vapi Web SDK (WebRTC Bridge), Lucide React (Icons).
- **Backend**: Express.js, TypeScript, PostgreSQL (pg driver).
- **Communication**: Vapi (acting as a PSTN gateway/bridge).

## 3. Commands
- **Dev**: `npm run dev` (Starts both frontend and backend)
- **DB Init**: `npm run db:init`
- **Seed**: `npm run db:seed:large`
- **Lint**: `npm run lint`

## 4. Project Structure (Key Additions)
```text
frontend/
├── app/
│   └── explorer/           → New Advanced Filter Page
├── components/
│   ├── Dialer/             → Global Dialer UI (Human focused)
│   ├── Explorer/
│   │   ├── FilterSidebar.tsx
│   │   └── ProviderGrid.tsx
│   └── ProviderCard/
│       └── CallButton.tsx
backend/
├── src/
│   └── routes/
│       └── dialer.ts       → Handles call initiation tokens and PSTN bridging
```

## 5. Code Style
### Frontend: Functional Composition & Tailwind
```tsx
// Example of a Premium Glassmorphism Dialer Button
export const DialerButton = ({ onCall }: { onCall: () => void }) => (
  <button 
    onClick={onCall}
    className="group relative flex items-center justify-center rounded-full bg-emerald-500/20 p-4 transition-all hover:bg-emerald-500/30 active:scale-95"
  >
    <Phone className="h-6 w-6 text-emerald-400 group-hover:animate-pulse" />
    <span className="absolute -top-12 scale-0 rounded bg-slate-800 px-2 py-1 text-xs text-white group-hover:scale-100">
      Call Clinic Directly
    </span>
  </button>
);
```

## 6. Testing Strategy
- **Manual Verification**: End-to-end call from browser to a verified test mobile number.
- **API Tests**: Verify that `/api/appointments/providers` handles multiple filter intersections (Location + Specialty + Availability).
- **Edge Cases**: Verify UI state when Vapi reports "No Answer", "Busy", or "Network Error".

## 7. Boundaries
- **Always**: Validate that a provider has a `phone` number before enabling the Call button.
- **Ask First**: If we should implement a "Call Recording" consent message before bridging the human call.
- **Never**: Use the AI assistant logic if the user clicks a "Direct Call" button.

## 8. Success Criteria
- [ ] Users can browse a list of all clinics/doctors.
- [ ] Advanced filters (Name Search, Location, Specialty, Availability) update the list in real-time.
- [ ] Clicking "Call" initiates a browser call that rings the doctor's actual phone number.
- [ ] The web UI displays "Connecting...", "Ringing...", or "Connected" based on the PSTN status.

## 9. Open Questions
- **Placeholder Numbers**: Should I pre-fill the database with mock phone numbers (e.g., your test number) for immediate verification?
- **Availability Logic**: Should "Available" status be determined by the existing `availability` table or by checking the `appointments` table for current conflicts?
