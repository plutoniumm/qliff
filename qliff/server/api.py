from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

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

# Canonical families the UI can offer. repetition/surface codes are graphlike
# (MWPM default); BP+OSD, MLD and TN are offered everywhere as denser fallbacks.
# `coherent` is offered separately (see /api/decoders) for non-Pauli channels.
_PAULI_DECODERS = ["mwpm", "bposd", "mld", "tn"]
# Stabiliser-pattern options the surface families offer along each axis. Rotated
# supports all three (pattern x start x edge = 8 variants); unrotated has no
# alternate boundary set so it omits `edge` (pattern x start = 4). repetition/toric
# expose none (a single option per axis => no selector).
_TEMPLATES = [
    TemplateInfo(
        family="repetition",
        label="Repetition code",
        min_distance=2,
        decoders=_PAULI_DECODERS,
    ),
    TemplateInfo(
        family="rotated_surface",
        label="Rotated surface code",
        min_distance=2,
        decoders=_PAULI_DECODERS,
        patterns=["css", "xzzx"],
        starts=["Z", "X"],
        edges=["even", "odd"],
    ),
    TemplateInfo(
        family="unrotated_surface",
        label="Unrotated surface code",
        min_distance=2,
        decoders=_PAULI_DECODERS,
        patterns=["css", "xzzx"],
        starts=["Z", "X"],
        edges=["even"],
    ),
    TemplateInfo(
        family="toric",
        label="Toric code",
        min_distance=2,
        decoders=_PAULI_DECODERS,
    ),
]

# Every decoder the UI can offer, with whether it honestly decodes only Pauli
# noise (DEM-backed) -- coherent/non-Pauli channels need the `coherent` decoder.
_DECODERS = [
    DecoderInfo(
        name="mwpm",
        label="MWPM",
        pauli_only=True,
        note="minimum-weight perfect matching (graphlike)",
    ),
    DecoderInfo(
        name="bposd",
        label="BP+OSD",
        pauli_only=True,
        note="belief propagation + ordered-statistics decoding",
    ),
    DecoderInfo(
        name="mld",
        label="MLD",
        pauli_only=False,
        note="exact max-likelihood TN (Pauli + coherent)",
    ),
    DecoderInfo(
        name="tn",
        label="TN",
        pauli_only=False,
        note="tensor-network max-likelihood (Pauli + coherent)",
    ),
    DecoderInfo(
        name="coherent",
        label="Coherent",
        pauli_only=False,
        note="non-Pauli/coherent TN",
    ),
]

# Every noise channel the UI can offer. `arg` is the strength shape ("p" scalar,
# "theta" rotation angle, "vec3" Pauli rates); non-Pauli channels need coherent.
_CHANNELS = [
    ChannelInfo(
        name="DEPOLARIZE1",
        label="Depolarizing (1Q)",
        is_pauli=True,
        arg="p",
        note="",
    ),
    ChannelInfo(
        name="DEPOLARIZE2",
        label="Depolarizing (2Q)",
        is_pauli=True,
        arg="p",
        note="",
    ),
    ChannelInfo(
        name="X_ERROR",
        label="Bit flip (X)",
        is_pauli=True,
        arg="p",
        note="",
    ),
    ChannelInfo(
        name="Z_ERROR",
        label="Phase flip (Z)",
        is_pauli=True,
        arg="p",
        note="",
    ),
    ChannelInfo(
        name="PAULI_CHANNEL_1",
        label="Pauli channel (1Q)",
        is_pauli=True,
        arg="vec3",
        note="",
    ),
    ChannelInfo(
        name="RZ",
        label="Z rotation",
        is_pauli=False,
        arg="theta",
        note="coherent",
    ),
    ChannelInfo(
        name="RX",
        label="X rotation",
        is_pauli=False,
        arg="theta",
        note="coherent",
    ),
    ChannelInfo(
        name="AMPLITUDE_DAMP",
        label="Amplitude damping",
        is_pauli=False,
        arg="p",
        note="",
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
