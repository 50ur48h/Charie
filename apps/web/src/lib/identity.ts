/** How to name a person on screen when the identity provider was sparing. */

export interface Named {
  email: string | null;
  name: string | null;
}

export function personLabel(person: Named, fallback = "Unknown"): string {
  return person.email ?? person.name ?? fallback;
}

/** True when we have no address for this person and should say so once. */
export function emailIsUnknown(person: Named): boolean {
  return person.email === null;
}
