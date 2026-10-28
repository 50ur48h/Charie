import { Brand, LogoMark } from "@charie/shared";
import KitSection from "./KitSection";

export default function FramesSection() {
  return (
    <KitSection id="frames" title="Frames">
      <div className="flex flex-wrap items-end gap-6">
        <LogoMark size={28} />
        <LogoMark size={34} />
        <LogoMark size={52} />
      </div>
      <div className="mt-4 grid gap-4 min-[1000px]:grid-cols-2">
        <div className="rounded-card border border-border bg-surface px-4 py-3 shadow-card">
          <Brand app="chat" href="/__kit/chat-frame" />
        </div>
        <div className="rounded-card border border-border bg-surface px-4 py-3 shadow-card">
          <Brand app="learner" href="/__kit/learner-frame" />
        </div>
      </div>
      <nav className="mt-4 flex flex-wrap gap-4" aria-label="Frame demos">
        <a href="/__kit/chat-frame">Open the chat frame</a>
        <a href="/__kit/learner-frame">Open the learner frame</a>
      </nav>
    </KitSection>
  );
}
