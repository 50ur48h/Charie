# Charie front end: rules for Muse Code

Read the top AGENTS.md first. This file adds the front-end rules; where they conflict, this file wins.

## What's here
- `shared/src/theme/`: the 6 color themes and text styles.
- `shared/src/components/`: the shared building blocks.
- `shared/src/layout/`: app frames, sidebars and page headers.
- `shared/src/charts/`: the chart wrapper and chart blocks (ECharts).
- `shared/src/answer/`: the blocks an answer is made of.
- `shared/src/knowledge/`, `shared/src/questions/`: knowledge and owner-question pieces.
- `shared/src/api/`: the API client and the exact API shapes. `shared/src/mocks/`: sample data and the fake API.
- `chat/src/`: the chat app's pages. `learner/src/`: the learner app's pages.
- `e2e/`: Playwright screen tests.

## Rules
1. Use the building blocks in `frontend/shared`. Don't copy them into an app.
2. Colors come only from the theme (Tailwind theme names or CSS variables). Never put a hex color in a component.
3. Charts go only through `<Chart>` in `shared/charts`.
4. Icons come only from `lucide-react`.
5. API calls go only through `shared/api` with TanStack Query. Never call `fetch` inside a component.
6. Sample data and the fake API live only in `shared/mocks`. Production code never imports them.
7. Every screen works at 1440, 820 and 390 px wide.
8. Buttons have labels, focus is always visible, and streaming text uses `aria-live="polite"`.
9. Each screen matches its design in `docs/designs/calm/`. Check with Playwright screenshots and `/taste`.
10. The words on screen are exactly the ones in the sub-phase file, in plain English.

## Tests
- Vitest files live next to the component they test.
- Playwright specs live in `e2e/`. Screenshots are checked at 1440, 820 and 390 px wide.

## Commands
`npm install` · `npm run dev:chat` · `npm run dev:learner` · `npm run dev:chat:mock` · `npm run dev:learner:mock` · `npm test` · `npm run lint` · `npm run typecheck` · `npm run build` · `npm run e2e:mock`
