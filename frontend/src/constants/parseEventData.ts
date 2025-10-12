import { type EventsHeaderState } from "../components/events/EventsPageHeader";

export function parseDate (
  startsAtISO: string,
  endsAtISO: string,
  timeZone: string
): string | undefined {
  const start = new Date(startsAtISO);
  const end = new Date(endsAtISO);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return undefined;

  // e.g., "Tue, Dec 16"
  const dayLabel = new Intl.DateTimeFormat(undefined, {
    timeZone,
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(start);

  // helper to get HH:MM (24h) in target tz
  const hhmm = (d: Date) => {
    const parts = new Intl.DateTimeFormat(undefined, {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
      .formatToParts(d)
      .reduce<Record<string, string>>((acc, p) => {
        if (p.type !== "literal") acc[p.type] = p.value;
        return acc;
      }, {});
    const pad = (n: string | undefined) =>
      !n ? "00" : n.length === 1 ? `0${n}` : n;
    return `${pad(parts.hour)}:${pad(parts.minute)}`;
  };

  const startHHMM = hhmm(start);
  const endHHMM = hhmm(end);

  // short tz label like CET/CEST or GMT+02:00 (locale-dependent)
  const tzShort =
    new Intl.DateTimeFormat(undefined, {
      timeZone,
      timeZoneName: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
      .formatToParts(start)
      .find((p) => p.type === "timeZoneName")?.value ?? timeZone;

  return `${dayLabel} · ${startHHMM}–${endHHMM} ${tzShort}`;
}


// Heuristic: returns true if the string is just a label like "Where:", "Location:", etc.
function isLabelOnly(raw: string): boolean {
  const trimmed = String(raw).trim();
  if (!trimmed) return true;
  // Drop leading symbols/emojis/punctuation (e.g., "📍", "-", etc.)
  const leadingStripped = trimmed.replace(/^[^A-Za-z0-9]+/, "");
  // Drop trailing punctuation like ':' or '-' if present
  const core = leadingStripped.replace(/[^A-Za-z0-9]+$/, "").toLowerCase();
  return /^(where|location|address|venue|place)$/.test(core);
}

export function parseLocation(locStr: string | undefined): string {
  const FALLBACK = "Zurich, Switzerland";
  if (!locStr) return FALLBACK;
  let s = String(locStr).trim();
  if (!s) return FALLBACK;
  if (isLabelOnly(s)) return FALLBACK;

  // 1) Cut at first occurrence of '/', '\\', or ':' (if present)
  const cutChars = ["/", "\\", ":"] as const;
  const firstCuts = cutChars
    .map((ch) => ({ ch, idx: s.indexOf(ch) }))
    .filter(({ idx }) => idx >= 0)
    .sort((a, b) => a.idx - b.idx);
  if (firstCuts.length > 0) {
    s = s.slice(0, firstCuts[0].idx).trim();
  }

  // Guard again after cutting
  if (isLabelOnly(s)) return FALLBACK;

  // 2) If there are 2 or more commas, keep up to (but excluding) the second comma
  const firstComma = s.indexOf(",");
  if (firstComma !== -1) {
    const secondComma = s.indexOf(",", firstComma + 1);
    if (secondComma !== -1) {
      s = s.slice(0, secondComma).trim();
    }
  }

  // Final cleanup; fall back if empty
  s = s.replace(/\s{2,}/g, " ").trim();
  const words = s.split(/\s+/).filter(Boolean);
  if (words.length > 6) return FALLBACK;
  if (s.length < 3 || /^[^A-Za-z0-9]+$/.test(s)) return FALLBACK;
  return s || FALLBACK;
}



/** Helpers for filtering **/
function monthIndexFromName(mon: string): number {
  const map: Record<string, number> = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
  };
  return map[mon.slice(0,3).toLowerCase()] ?? -1;
}

// Extract a JS Date for the *start day* from a display string like
// "Tue, Dec 16 · 08:00–09:30 CET" or "Tue, Dec 16, 2025 · 08:00–09:30 CET".
// If year is omitted, assume the current year.
function parseDisplayStartDate(dateStr: string, now = new Date()): Date | null {
  if (!dateStr) return null;
  // Grab parts: Weekday, Month, Day, optional Year
  // Examples it handles:
  //  - Tue, Dec 16 · 08:00–09:30 CET
  //  - Tue, Dec 16, 2025 · 08:00–09:30 CET
  const m = dateStr.match(/^[A-Za-z]{3},\s+([A-Za-z]{3,})\s+(\d{1,2})(?:,\s*(\d{4}))?/);
  if (!m) return null;
  const monName = m[1];
  const dayNum = Number(m[2]);
  const yr = m[3] ? Number(m[3]) : now.getFullYear();
  const monIdx = monthIndexFromName(monName);
  if (monIdx < 0 || !Number.isFinite(dayNum) || !Number.isFinite(yr)) return null;
  const d = new Date(yr, monIdx, dayNum);
  d.setHours(0, 0, 0, 0);
  return d;
}

export function inTimeframe(dateStr: string, timeframe: EventsHeaderState["timeframe"], now: Date): boolean {
  if (timeframe === "any") return true;
  const d = parseDisplayStartDate(dateStr, now);
  if (!d) return false;
  if (timeframe === "today") {
    return (
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    );
  }
  if (timeframe === "this_week") {
    const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
    const startOfWeek = (x: Date) => {
      const tmp = day(x);
      const dow = (tmp.getDay() + 6) % 7; // Mon=0
      tmp.setDate(tmp.getDate() - dow);
      tmp.setHours(0, 0, 0, 0);
      return tmp;
    };
    return startOfWeek(now).getTime() === startOfWeek(d).getTime();
  }
  if (timeframe === "this_month") {
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }
  return true;
}

// Locale-agnostic timeframe check using ISO start date
export function inTimeframeISO(startISO: string | undefined, timeframe: EventsHeaderState["timeframe"], now: Date): boolean {
  if (timeframe === "any") return true;
  if (!startISO) return false;
  const d = new Date(startISO);
  if (isNaN(d.getTime())) return false;
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
  const D = day(d);
  const N = day(now);
  if (timeframe === "today") {
    return D.getTime() === N.getTime();
  }
  if (timeframe === "this_week") {
    const startOfWeek = (x: Date) => {
      const tmp = day(x);
      const dow = (tmp.getDay() + 6) % 7; // Mon=0
      tmp.setDate(tmp.getDate() - dow);
      return tmp;
    };
    return startOfWeek(D).getTime() === startOfWeek(N).getTime();
  }
  if (timeframe === "this_month") {
    return D.getFullYear() === N.getFullYear() && D.getMonth() === N.getMonth();
  }
  return true;
}
