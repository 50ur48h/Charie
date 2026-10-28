import type { ReactNode } from "react";

export function PageHeader({
  title,
  lead,
  actions,
}: {
  title: string;
  lead?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end gap-4">
      <div>
        <h1 className="page-title">{title}</h1>
        {lead && <p className="page-lead">{lead}</p>}
      </div>
      {actions && <div className="ml-auto flex flex-none gap-2">{actions}</div>}
    </div>
  );
}

export function Page({ narrow, children }: { narrow?: boolean; children: ReactNode }) {
  return (
    <div
      className={
        narrow
          ? "mx-auto max-w-[860px] px-9 pb-16 pt-9 max-[900px]:px-[18px] max-[900px]:pb-12 max-[900px]:pt-6"
          : "mx-auto max-w-[1080px] px-9 pb-16 pt-9 max-[900px]:px-[18px] max-[900px]:pb-12 max-[900px]:pt-6"
      }
    >
      {children}
    </div>
  );
}
