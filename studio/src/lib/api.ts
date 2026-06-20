// Typed client for the qliff server: REST (templates, compile) + a WebSocket
// streaming run. All payloads/responses are typed against the frozen wire
// schema in $lib/schema.

import type {
  TemplateInfo,
  RunRequest,
  CompileResponse,
  RunEvent,
} from "$lib/schema";

// Resolve the HTTP base. Same-origin in production (served by the Python
// server). In Vite dev (port 5174) the SPA and the API live on different
// ports, so fall back to the dev server at 127.0.0.1:8731.
export function apiBase(): string {
  if (typeof window === "undefined") {
    return "";
  }

  if (window.location.port === "5174") {
    return "http://127.0.0.1:8731";
  }

  return "";
}

// Derive the WebSocket base from the HTTP base (http->ws, https->wss). An empty
// base means same-origin: build it from window.location.
export function wsBase(): string {
  const base = apiBase();

  if (base !== "") {
    return base.replace(/^http/, "ws");
  }

  if (typeof window === "undefined") {
    return "";
  }

  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";

  return `${scheme}//${window.location.host}`;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`);

  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`);
  }

  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status} ${res.statusText}`);
  }

  return (await res.json()) as T;
}

export function getTemplates(): Promise<TemplateInfo[]> {
  return getJson<TemplateInfo[]>("/api/templates");
}

export function compile(req: RunRequest): Promise<CompileResponse> {
  return postJson<CompileResponse>("/api/compile", req);
}

// Handle returned from runStream so the caller can tear the socket down.
export interface RunHandle {
  close(): void;
}

// Open a WebSocket to /api/run, send the request as JSON, and feed each parsed
// RunEvent frame to onEvent until a "done"/"error" frame arrives (the socket is
// closed automatically at that point). Connection failures surface as a
// synthetic {type:"error"} event so callers only handle one path.
export function runStream(
  req: RunRequest,
  onEvent: (e: RunEvent) => void,
): RunHandle {
  const url = `${wsBase()}/api/run`;
  let socket: WebSocket | null = null;
  let finished = false;

  const finish = (): void => {
    finished = true;

    if (socket !== null && socket.readyState <= WebSocket.OPEN) {
      socket.close();
    }
  };

  try {
    socket = new WebSocket(url);
  } catch (err) {
    onEvent({ type: "error", message: `failed to open ${url}: ${String(err)}` });

    return { close: () => {} };
  }

  socket.onopen = () => {
    socket?.send(JSON.stringify(req));
  };

  socket.onmessage = (ev: MessageEvent) => {
    if (finished) {
      return;
    }

    let frame: RunEvent;

    try {
      frame = JSON.parse(ev.data as string) as RunEvent;
    } catch {
      onEvent({ type: "error", message: "malformed frame from server" });
      finish();

      return;
    }

    onEvent(frame);

    if (frame.type === "done" || frame.type === "error") {
      finish();
    }
  };

  socket.onerror = () => {
    if (finished) {
      return;
    }

    onEvent({ type: "error", message: `WebSocket error talking to ${url}` });
    finish();
  };

  socket.onclose = () => {
    if (finished) {
      return;
    }

    // Closed before a terminal frame: treat as an error so the UI unblocks.
    onEvent({ type: "error", message: "connection closed before completion" });
    finished = true;
  };

  return {
    close: () => {
      finished = true;
      socket?.close();
    },
  };
}
