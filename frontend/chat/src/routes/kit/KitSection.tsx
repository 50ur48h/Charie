import type { ReactNode } from "react";

export default function KitSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id}>
      <h2 className="section-title">{title}</h2>
      {children}
    </section>
  );
}
