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
