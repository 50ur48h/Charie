"use client";

/** Which Meta model answers the next question, remembered per browser. */

import { useEffect, useState, useSyncExternalStore } from "react";

import type { Api, ModelChoices } from "@/lib/api-client";
import { createPersisted } from "@/lib/persisted";

/** "muse-spark-1.3" → "Muse Spark 1.3". */
export function modelName(id: string): string {
  return id
    .split("-")
    .map((part) => (/^\d/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(" ");
}

const stored = createPersisted("charie.model", "", (value): value is string => value.length > 0);

export interface ModelChoice {
  /** The model the next question is sent with, or null until the list arrives. */
  model: string | null;
  choices: ModelChoices | null;
  setModel: (id: string) => void;
}

export function useModelChoice(api: Api, orgId: string): ModelChoice {
  const [choices, setChoices] = useState<ModelChoices | null>(null);
  const remembered = useSyncExternalStore(stored.subscribe, stored.get, stored.getServer);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const loaded = await api.models(orgId);
        if (alive) setChoices(loaded);
      } catch {
        // No list means no picker; the API still answers with its default model.
        if (alive) setChoices(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [api, orgId]);

  const offered = choices?.models.some((option) => option.id === remembered) ?? false;
  const model = choices ? (offered ? remembered : choices.default) : null;
  return { model, choices, setModel: (id) => stored.set(id) };
}
