/**
 * Where the appearance choices are stored.
 *
 * A plain module, not a client one: the root layout is a server component and
 * inlines these into its pre-paint script. Imported from a `"use client"`
 * module they arrive on the server as client references rather than strings,
 * and the script would read `localStorage.getItem(undefined)`.
 */
export const THEME_STORAGE_KEY = "charie.theme";
export const PALETTE_STORAGE_KEY = "charie.palette";
