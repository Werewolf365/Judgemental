/** Per-event timezone for deadline input. Storage stays UTC everywhere;
 *  these helpers convert between the organizer's wall clock in the event's
 *  zone and the UTC "YYYY-MM-DDTHH:mm" shape the API speaks. */

/** Curated IANA zones for the deadline picker. UTC first (the default). */
export const ZONES = [
  "UTC",
  "Asia/Kolkata", "Asia/Dubai", "Asia/Dhaka", "Asia/Singapore", "Asia/Tokyo",
  "Europe/London", "Europe/Berlin", "Europe/Moscow", "Africa/Cairo",
  "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
  "America/Toronto", "America/Sao_Paulo", "Australia/Sydney", "Pacific/Auckland",
];

/** Minutes the zone is ahead of UTC at the given UTC instant. */
function offsetMinutes(zone: string, utcMs: number): number {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: zone, hour12: false, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  const parts: Record<string, string> = {};
  for (const p of dtf.formatToParts(new Date(utcMs))) parts[p.type] = p.value;
  const asUTC = Date.UTC(+parts.year, +parts.month - 1, +parts.day, (+parts.hour) % 24, +parts.minute, +parts.second);
  return Math.round((asUTC - utcMs) / 60000);
}

const q = (n: number) => String(n).padStart(2, "0");
const shape = (d: Date) =>
  `${d.getUTCFullYear()}-${q(d.getUTCMonth() + 1)}-${q(d.getUTCDate())}T${q(d.getUTCHours())}:${q(d.getUTCMinutes())}`;

/** "YYYY-MM-DDTHH:mm" wall clock in `zone` -> same shape in UTC. */
export function wallToUTC(local: string, zone: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(local || "");
  if (!m || !zone || zone === "UTC") return local;
  const wallAsUTC = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  let off = offsetMinutes(zone, wallAsUTC);
  off = offsetMinutes(zone, wallAsUTC - off * 60000); // refine once for DST edges
  return shape(new Date(wallAsUTC - off * 60000));
}

/** UTC instant (ISO, with or without offset) -> "YYYY-MM-DDTHH:mm" wall clock in `zone`. */
export function utcToWall(iso: string, zone: string): string {
  if (!iso) return "";
  if (!zone || zone === "UTC") return iso.slice(0, 16);
  const t = new Date(/[Zz]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z").getTime();
  if (isNaN(t)) return "";
  return shape(new Date(t + offsetMinutes(zone, t) * 60000));
}
