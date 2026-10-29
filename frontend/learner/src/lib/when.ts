// Plain-English dates for the learner screens: "26 Oct" (shortDate) and
// "2 hours ago" (timeAgo). Both take `now` so tests pin them.
const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

// "26 Oct", plus the year when it isn't this year ("26 Oct 2025").
export function shortDate(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const day = date.getDate();
  const month = MONTHS[date.getMonth()];
  return date.getFullYear() === now.getFullYear()
    ? `${day} ${month}`
    : `${day} ${month} ${date.getFullYear()}`;
}

// "Today", "Yesterday", or shortDate: which calendar day it was, in local
// time (so "Added" stays right near midnight and in every timezone).
export function dayOrDate(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const days = Math.round((today - day) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return shortDate(iso, now);
}

// "9:12 pm": the clock time in local time.
export function clockTime(iso: string): string {
  const date = new Date(iso);
  const hours = date.getHours();
  const twelve = hours % 12 === 0 ? 12 : hours % 12;
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${twelve}:${minutes} ${hours < 12 ? "am" : "pm"}`;
}

// "4 min", "1 h 48 min": how long learning took, start to finish.
export function howLong(startIso: string, endIso: string): string {
  const minutes = Math.max(0, Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}
// "just now", "1 minute ago", "{n} minutes ago", "1 hour ago",
// "{n} hours ago", "yesterday", "{n} days ago".
export function timeAgo(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 2) return "1 minute ago";
  if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 2) return "1 hour ago";
  if (hours < 48) return hours < 24 ? `${hours} hours ago` : "yesterday";
  return `${Math.floor(hours / 24)} days ago`;
}
