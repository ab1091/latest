// The API returns naive timestamps with no timezone marker (the DB now
// stores/returns correct UTC wall-clock values, but psycopg2's naive
// datetime objects serialize without a trailing 'Z' or offset). Without
// this, `new Date()` falls back to parsing the string as browser-local
// time per the ECMAScript spec, silently shifting every displayed time by
// the difference between the viewer's timezone and UTC — confirmed live,
// a call that had just ended displayed as hours in the past.
//
// Use this instead of `new Date(apiString)` anywhere a date/time string
// came from our own API (created_at, start_time, due_at, etc.). Don't use
// it for dates built from local user input (form pickers, calendar nav) —
// those are already correct as plain `new Date(...)`.
export function parseApiDate(iso: string): Date {
    const hasTzMarker = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
    return new Date(hasTzMarker ? iso : `${iso}Z`);
}
