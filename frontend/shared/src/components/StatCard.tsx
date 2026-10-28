import type { ReactNode } from "react";
import { Card } from "./Card";

export function StatCard({
  label,
  value,
  foot,
  children,
}: {
  label: string;
  value: string;
  foot?: string;
  children?: ReactNode;
}) {
  return (
    <Card padded={false} className="p-[16px_18px]">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {foot && <p className="stat-foot">{foot}</p>}
      {children}
    </Card>
  );
}
