export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      width={size}
      height={size}
      className="flex-none text-accent"
    >
      <rect width="32" height="32" rx="9" fill="currentColor" />
      <path
        d="M20.95 11.05a7 7 0 1 0 0 9.9"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="21.6" cy="16" r="1.9" fill="#fff" />
    </svg>
  );
}

export function Brand({
  app,
  markSize = 28,
  href,
}: {
  app: "chat" | "learner";
  markSize?: number;
  href: string;
}) {
  return (
    <a href={href} className="flex items-center gap-2.5 text-accent">
      <LogoMark size={markSize} />
      <span className="font-serif text-[23px] font-semibold tracking-[-0.01em] text-text">
        Charie
      </span>
      {app === "learner" && (
        <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold tracking-[0.02em] text-accent-ink">
          Learner
        </span>
      )}
    </a>
  );
}
