import { http, HttpResponse } from "msw";
import { readSavedTheme } from "../theme/theme";
import chats from "./data";

export const CHATS_URL = "*/api/chats";
export const ME_URL = "*/api/me";
export const HEALTH_URL = "*/api/health";
export const CATCH_ALL_URL = "*/api/*";

export const handlers = [
  http.get(HEALTH_URL, () => HttpResponse.json({ ok: true })),
  http.get(ME_URL, () =>
    HttpResponse.json({ logged_in: true, setup_done: true, theme: readSavedTheme() }),
  ),
  http.get(CHATS_URL, () => HttpResponse.json(chats)),
  http.all(CATCH_ALL_URL, () =>
    HttpResponse.json(
      { error: "not_mocked", message: "The sample data doesn't cover this yet." },
      { status: 501 },
    ),
  ),
];
