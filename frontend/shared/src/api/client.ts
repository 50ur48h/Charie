interface ServerError {
  error?: string;
  message?: string;
}

const FALLBACKS: Record<number, string> = {
  401: "Please sign in again.",
  403: "You can't do that.",
  404: "We couldn't find that.",
  429: "Too many tries. Please wait a few minutes and try again.",
};

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T>(
  path: string,
  options?: { method?: string; body?: unknown; signal?: AbortSignal },
): Promise<T> {
  const method = options?.method ?? "GET";
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: {
        Accept: "application/json",
        ...(method === "GET" ? {} : { "Content-Type": "application/json" }),
      },
      ...(method === "GET" ? {} : { body: JSON.stringify(options?.body ?? {}) }),
      signal: options?.signal,
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach Charie. Check your connection and try again.");
  }
  if (response.status === 204) return undefined as T;
  let data: ServerError | null = null;
  try {
    data = (await response.json()) as ServerError;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const message =
      data?.message ??
      FALLBACKS[response.status] ??
      "Something went wrong on our side. Please try again.";
    const code = data?.error ?? `http_${response.status}`;
    throw new ApiError(response.status, code, message);
  }
  return data as T;
}
