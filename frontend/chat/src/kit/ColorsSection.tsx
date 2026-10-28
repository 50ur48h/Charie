import { useEffect, useState } from "react";
import { THEME_CHANGE_EVENT } from "@charie/shared";
import KitSection from "./KitSection";

export const COLOR_TOKENS = [
  "--bg",
  "--sidebar",
  "--surface",
  "--surface-2",
  "--border",
  "--border-soft",
  "--text",
  "--text-2",
  "--prose",
  "--muted",
  "--muted-2",
  "--placeholder",
  "--accent",
  "--accent-ink",
  "--accent-soft",
  "--accent-hover",
  "--bubble",
  "--head-hover",
  "--focus",
  "--shadow-rgb",
  "--good",
  "--good-ink",
  "--good-soft",
  "--bad",
  "--bad-ink",
  "--bad-soft",
  "--warn",
  "--warn-ink",
  "--warn-soft",
  "--code-bg",
  "--code-ink",
  "--code-kw",
  "--code-str",
  "--chart-pos",
  "--chart-neg",
  "--chart-grid",
  "--chart-muted",
  "--chart-edge",
];

export function swatchBackground(token: string): string {
  return token === "--shadow-rgb" ? "rgb(var(--shadow-rgb))" : `var(${token})`;
}

function tokenValue(token: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  if (!raw) return swatchBackground(token);
  return token === "--shadow-rgb" ? `rgb(${raw})` : raw;
}

export default function ColorsSection() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const refresh = () => setTick((n) => n + 1);
    window.addEventListener(THEME_CHANGE_EVENT, refresh);
    return () => window.removeEventListener(THEME_CHANGE_EVENT, refresh);
  }, []);
  return (
    <KitSection id="colors" title="Colors">
      <ul className="flex flex-wrap gap-4">
        {COLOR_TOKENS.map((token) => (
          <li key={token} className="w-28">
            <span
              data-token={token}
              className="block h-12 w-12 rounded-[11px] border border-border"
              style={{ backgroundColor: swatchBackground(token) }}
            />
            <span className="mt-1 block text-xs text-text-2">{token}</span>
            <span className="block text-xs text-muted">{tokenValue(token)}</span>
          </li>
        ))}
      </ul>
    </KitSection>
  );
}
