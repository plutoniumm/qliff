from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .run import compile_summary, run_sweep
from .schema import (
    CompileResponse,
    RunEvent,
    RunRequest,
    RunResponse,
    TemplateInfo,
)

router = APIRouter()

# Canonical families the UI can offer. repetition/surface codes are graphlike
# (MWPM default); BP+OSD is offered everywhere as the dense-mechanism fallback.
_TEMPLATES = [
    TemplateInfo(
        family="repetition",
        label="Repetition code",
        min_distance=2,
        decoders=["mwpm", "bposd"],
    ),
    TemplateInfo(
        family="rotated_surface",
        label="Rotated surface code",
        min_distance=2,
        decoders=["mwpm", "bposd"],
    ),
    TemplateInfo(
        family="unrotated_surface",
        label="Unrotated surface code",
        min_distance=2,
        decoders=["mwpm", "bposd"],
    ),
    TemplateInfo(
        family="toric",
        label="Toric code",
        min_distance=2,
        decoders=["mwpm", "bposd"],
    ),
]


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/templates")
def templates() -> list[TemplateInfo]:
    """
    The code families the builder can offer, with their valid decoders.
    """
    return _TEMPLATES


@router.post("/compile")
def compile_request(req: RunRequest) -> CompileResponse:
    """
    Static circuit summary. compile_summary guards bad specs -> ok=False.
    """
    return compile_summary(req)


@router.post("/run")
def run(req: RunRequest) -> RunResponse:
    """
    Non-streaming LER run for clients that don't want a WebSocket.
    """
    return run_sweep(req)


@router.websocket("/run")
async def run_stream(ws: WebSocket) -> None:
    """
    Accept a RunRequest as JSON, then stream one RunEvent{"point"} per swept p,
    a final {"done"}, or {"error", message} on failure. The blocking sweep runs
    in a worker thread and feeds points back through an asyncio.Queue so the
    socket stays responsive.
    """
    await ws.accept()
    try:
        payload = await ws.receive_json()
        req = RunRequest.model_validate(payload)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await _send_error(ws, str(exc))
        await ws.close()

        return

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_point(point) -> None:
        # called from the worker thread; hop back onto the event loop.
        loop.call_soon_threadsafe(queue.put_nowait, point)

    async def drive() -> None:
        try:
            await loop.run_in_executor(None, lambda: run_sweep(req, on_point))
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)
        except Exception as exc:  # surface engine errors to the client.
            loop.call_soon_threadsafe(queue.put_nowait, _Err(str(exc)))

    task = asyncio.ensure_future(drive())
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                await ws.send_json(RunEvent(type="done").model_dump())
                break
            if isinstance(item, _Err):
                await _send_error(ws, item.message)
                break
            await ws.send_json(RunEvent(type="point", point=item).model_dump())
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        # the client may already be gone; closing twice is harmless to ignore.
        try:
            await ws.close()
        except RuntimeError:
            pass


class _Err:
    """
    Internal queue sentinel carrying an error message from the worker.
    """

    def __init__(self, message: str):
        self.message = message


_DONE = object()


async def _send_error(ws: WebSocket, message: str) -> None:
    await ws.send_json(RunEvent(type="error", message=message).model_dump())
