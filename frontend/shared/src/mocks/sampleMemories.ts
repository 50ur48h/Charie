import type { Memory } from "../api/memories";

// Mock memory store (mock only): the three preferences from the Calm
// Settings design. The real addresses arrive with P11.5; until then the fake
// API serves these same shapes.
const MEMORIES_KEY = "charie-mock-memories";

const SEEDS: Memory[] = [
  {
    id: 1,
    text: 'For me, "sales" means without delivery fees.',
    source: 'From the chat "Weekend vs weekday sales" · 12 Oct',
    saved_at: "2025-10-12T10:00:00Z",
  },
  {
    id: 2,
    text: "I mostly care about the Austin restaurants.",
    source: 'From the chat "Why did delivery drop in Austin?" · 20 Oct',
    saved_at: "2025-10-20T10:00:00Z",
  },
  {
    id: 3,
    text: "Show money in thousands, like $96.2K.",
    source: 'From the chat "Top dishes by profit" · 9 Oct',
    saved_at: "2025-10-09T10:00:00Z",
  },
];

function storage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

export function listMockMemories(): Memory[] {
  try {
    const raw = storage()?.getItem(MEMORIES_KEY);
    if (!raw) return [...SEEDS];
    const data = JSON.parse(raw) as Memory[];
    return Array.isArray(data) ? data : [...SEEDS];
  } catch {
    return [...SEEDS];
  }
}

function save(memories: Memory[]): void {
  try {
    storage()?.setItem(MEMORIES_KEY, JSON.stringify(memories));
  } catch {
    // Test-only state; ignore.
  }
}

// Forget one memory; false when the id is unknown.
export function deleteMockMemory(id: number): boolean {
  const memories = listMockMemories();
  const next = memories.filter((memory) => memory.id !== id);
  if (next.length === memories.length) return false;
  save(next);
  return true;
}

// Forget everything.
export function clearMockMemories(): void {
  save([]);
}
