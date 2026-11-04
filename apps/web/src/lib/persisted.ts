/** A value this browser remembers, read the way React wants it read. */

export interface Persisted<T extends string> {
  /** The stored value, or the default. Safe to call during render. */
  get: () => T;
  /** Server-render snapshot: always the default, since there is no storage. */
  getServer: () => T;
  set: (value: T) => void;
  subscribe: (listener: () => void) => () => void;
}

export function createPersisted<T extends string>(
  key: string,
  fallback: T,
  isValid: (value: string) => value is T,
): Persisted<T> {
  const listeners = new Set<() => void>();

  const read = (): T => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw !== null && isValid(raw) ? raw : fallback;
    } catch {
      return fallback;
    }
  };

  return {
    get: read,
    getServer: () => fallback,
    set: (value: T) => {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        // Applies for this session and will not survive a reload.
      }
      for (const listener of listeners) listener();
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      // Another tab changing the same key is a real update.
      const onStorage = (event: StorageEvent) => {
        if (event.key !== key) return;
        listener();
      };
      window.addEventListener("storage", onStorage);
      return () => {
        listeners.delete(listener);
        window.removeEventListener("storage", onStorage);
      };
    },
  };
}
