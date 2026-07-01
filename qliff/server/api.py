from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ..noise.channel import CHANNEL_META
from ..qec.decoder import DECODER_SPECS
from ..qec.registry import FAMILIES
from .run import compile_summary, run_sweep
from .schema import (
    ChannelInfo,
    CompileResponse,
    DecoderInfo,
    RunEvent,
    RunRequest,
    RunResponse,
    TemplateInfo,
)

router = APIRouter()

# The three /api metadata payloads are DERIVED from the single registries so they can
# never drift from the engine: families from qliff.qec.registry (label / min distance
# / offered decoders / stabiliser-pattern axes), decoders from the decoder registry
# (label / Pauli-only capability / note), and channels from noise.channel.CHANNEL_META
# (label / arg shape / Pauli-ness). Adding a family/decoder/channel to its registry
# lights it up here automatically.
_TEMPLATES = [
    TemplateInfo(
        family=fam.name,
        label=fam.label,
        min_distance=fam.min_distance,
        decoders=list(fam.default_decoders),
        **{axis: list(opts) for axis, opts in fam.variant_axes.items()},
    )
    for fam in FAMILIES.values()
]

_DECODERS = [
    DecoderInfo(
        name=spec.name,
        label=spec.label,
        pauli_only=spec.pauli_only,
        note=spec.note,
    )
    for spec in DECODER_SPECS.values()
]

# UI hint shown beside the coherent rotations; every other channel fact (label, arg
# shape, Pauli-ness) reads straight from CHANNEL_META, so it cannot duplicate-drift.
_CHANNEL_NOTES = {
    "RZ": "coherent",
    "RX": "coherent",
}

_CHANNELS = [
    ChannelInfo(
        name=name,
        label=meta.label,
        is_pauli=meta.is_pauli,
        arg=meta.arg_shape,
        note=_CHANNEL_NOTES.get(name, ""),
    )
    for name, meta in CHANNEL_META.items()
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


@router.get("/decoders")
def decoders() -> list[DecoderInfo]:
    """
    The decoders the UI can offer, with their Pauli-only capability.
    """
    return _DECODERS


@router.get("/channels")
def channels() -> list[ChannelInfo]:
    """
    The noise channels the UI can offer, with their arg shape and Pauli-ness.
    """
    return _CHANNELS


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
    try:
        return run_sweep(req)
    except ValueError as exc:  # e.g. non-Pauli channel on a DEM decoder
        raise HTTPException(status_code=400, detail=str(exc))


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

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_point(point) -> None:
        # called from the worker thread; hop back onto the event loop.
        loop.call_soon_threadsafe(queue.put_nowait, point)

    def worker() -> None:
        # the blocking sweep runs here, off the event loop. A *daemon* thread (not
        # the default executor) so a Ctrl-C mid-sweep abandons it instantly instead
        # of the interpreter joining it at exit -- which would stall shutdown until
        # the whole sweep finished.
        try:
            run_sweep(req, on_point)
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)
        except Exception as exc:  # surface engine errors to the client.
            loop.call_soon_threadsafe(queue.put_nowait, _Err(str(exc)))

    threading.Thread(target=worker, daemon=True).start()
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
