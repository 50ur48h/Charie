import { useEffect } from "react";
import { THEMES, useTheme } from "@charie/shared";
import BasicBlocksSection from "./BasicBlocksSection";
import ChartsSection from "./ChartsSection";
import FramesSection from "./FramesSection";
import ColorsSection from "./ColorsSection";
import CompositeBlocksSection from "./CompositeBlocksSection";
import OverlaysSection from "./OverlaysSection";
import TextSection from "./TextSection";

export default function KitPage() {
  const [theme, setTheme] = useTheme();
  useEffect(() => {
    document.title = "Charie · Kit";
  }, []);
  return (
    <div className="mx-auto max-w-[1080px] bg-bg px-9 pb-16 pt-9 text-text">
      <h1 className="page-title">Charie kit</h1>
      <p className="page-lead">
        Every building block and chart in the Calm look. For development only; never in the
        real app.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label="Theme">
        <span className="field-label">Theme</span>
        {THEMES.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-pressed={theme === t.key}
            onClick={() => setTheme(t.key)}
            data-on-accent={theme === t.key ? true : undefined}
            className={theme === t.key ? "bg-accent text-white" : "bg-surface-2 text-text-2"}
          >
            {t.name}
          </button>
        ))}
      </div>
      <nav className="mt-4 flex flex-wrap gap-4" aria-label="Kit sections">
        <a href="#colors">Colors</a>
        <a href="#text">Text</a>
        <a href="#basic-blocks">Building blocks 1</a>
        <a href="#overlays">Building blocks 2</a>
        <a href="#composite-blocks">Building blocks 3</a>
        <a href="#charts">Charts</a>
        <a href="#frames">Frames</a>
      </nav>
      <ColorsSection />
      <TextSection />
      <BasicBlocksSection />
      <OverlaysSection />
      <CompositeBlocksSection />
      <ChartsSection />
      <FramesSection />
    </div>
  );
}
