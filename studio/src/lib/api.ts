// Typed client for the qliff server: REST (templates, compile) + a WebSocket
// streaming run. All payloads/responses are typed against the frozen wire
// schema in $lib/schema.

import type {
  TemplateInfo,
  DecoderInfo,
  ChannelInfo,
  RunRequest,
  RunResponse,
  CompileResponse,
  RunEvent,
} from "$lib/schema";

// The API is always same-origin: in production the Python server serves both the
// SPA and /api; in Vite dev the dev server proxies /api (REST + WS) to the qliff
// server (see studio/vite.config.ts). So the HTTP base is always "".
export function apiBase(): string {
  return "";
}

// Same-origin WebSocket base (http->ws, https->wss) from window.location.
export function wsBase(): string {
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

export function getDecoders(): Promise<DecoderInfo[]> {
  return getJson<DecoderInfo[]>("/api/decoders");
}

export function getChannels(): Promise<ChannelInfo[]> {
  return getJson<ChannelInfo[]>("/api/channels");
}

export function compile(req: RunRequest): Promise<CompileResponse> {
  return postJson<CompileResponse>("/api/compile", req);
}

// One-shot REST run: blocks until the whole sweep is computed, then returns the
// full RunResponse. Used as the automatic fallback when the WebSocket fails.
export function runOnce(req: RunRequest): Promise<RunResponse> {
  return postJson<RunResponse>("/api/run", req);
}

// Handle returned from runStream so the caller can tear the socket down.
export interface RunHandle {
  close(): void;
}

// How long to wait for the socket to open before declaring the transport dead
// (so a silently-hanging connect still trips the REST fallback).
const WS_OPEN_TIMEOUT_MS = 4000;

// Open a WebSocket to /api/run, send the request as JSON, and feed each parsed
// RunEvent frame to onEvent until a "done"/"error" frame arrives (the socket is
// closed automatically at that point). Connection/transport failures surface as
// a synthetic {type:"error", transport:true} event so callers (runWithFallback)
// can tell a dead socket apart from a real server-side error frame.
export function runStream(
  req: RunRequest,
  onEvent: (e: RunEvent) => void,
): RunHandle {
  const url = `${wsBase()}/api/run`;
  let socket: WebSocket | null = null;
  let finished = false;
  let openTimer: ReturnType<typeof setTimeout> | null = null;

  const clearOpenTimer = (): void => {
    if (openTimer !== null) {
      clearTimeout(openTimer);
      openTimer = null;
    }
  };

  const finish = (): void => {
    finished = true;
    clearOpenTimer();

    if (socket !== null && socket.readyState <= WebSocket.OPEN) {
      socket.close();
    }
  };

  const transportError = (message: string): void => {
    if (finished) {
      return;
    }

    onEvent({
      type: "error",
      transport: true,
      message,
    });
    finish();
  };

  try {
    socket = new WebSocket(url);
  } catch (err) {
    transportError(`failed to open ${url}: ${String(err)}`);

    return { close: () => {} };
  }

  openTimer = setTimeout(() => {
    if (socket !== null && socket.readyState !== WebSocket.OPEN) {
      transportError(`WebSocket to ${url} did not open in time`);
    }
  }, WS_OPEN_TIMEOUT_MS);

  socket.onopen = () => {
    clearOpenTimer();
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
    transportError(`WebSocket error talking to ${url}`);
  };

  socket.onclose = () => {
    // Closed before a terminal frame: a dead transport, so the UI can fall back.
    transportError("connection closed before completion");
  };

  return {
    close: () => {
      finished = true;
      clearOpenTimer();
      socket?.close();
    },
  };
}

// Run with automatic degradation. Tries the streaming WebSocket first so points
// (and the progress bar) arrive live. If the socket dies as a *transport*
// failure BEFORE any point streamed, transparently retry over POST /api/run and
// replay the response as synthetic point/done events — so onEvent only ever sees
// one event vocabulary and the caller always gets a visible outcome. A real
// server "error" frame, or a transport drop mid-stream, is surfaced as-is.
export function runWithFallback(
  req: RunRequest,
  onEvent: (e: RunEvent) => void,
): RunHandle {
  let sawPoint = false;
  let restAbort = false;

  const handle = runStream(req, (e: RunEvent) => {
    if (e.type === "point") {
      sawPoint = true;
      onEvent(e);

      return;
    }

    // A clean transport failure with nothing delivered yet: go REST instead of
    // surfacing the socket error. Signal the switch so the UI can show a spinner.
    if (
      e.type === "error" &&
      e.transport === true &&
      !sawPoint
    ) {
      onEvent({ type: "fallback", message: "streaming unavailable — running over HTTP…" });

      runOnce(req)
        .then((res) => {
          if (restAbort) {
            return;
          }

          for (const point of res.points) {
            onEvent({ type: "point", point });
          }

          onEvent({ type: "done" });
        })
        .catch((err) => {
          if (!restAbort) {
            onEvent({ type: "error", message: String(err) });
          }
        });

      return;
    }

    onEvent(e);
  });

  return {
    close: () => {
      restAbort = true;
      handle.close();
    },
  };
}
