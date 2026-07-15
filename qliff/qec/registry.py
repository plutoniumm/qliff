from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..circuit import Circuit
from .codes import (
    repetition_code,
    rotated_surface_code,
    toric_code,
    unrotated_surface_code,
)
from .color import (
    color_code,
    hex_color_layout,
    kagome_layout,
    triangular_layout,
)

# Single source of truth for the canonical code families the Studio server can
# offer. One CodeFamily record per family carries every fact the scattered server
# tables used to re-derive by name: the human `label`, the `min_distance`, the
# circuit `builder` (a uniform (distance, rounds, p, channel, pattern, start, edge)
# adapter over qec.codes / qec.color), the `num_data` sizer, the offered
# `default_decoders`, the stabiliser-pattern `variant_axes`, and whether the DEM is
# `graphlike`. Adding a family is a ONE-record append here -- run.py's circuit
# dispatch + num-data lookup and api._TEMPLATES all read from this registry, so the
# family list can never drift between the builder and the /templates payload.
#
# This is a low leaf: it imports only the numpy-only builders (codes / color, which
# pull lattice / circuit), never the decoders or the server, so the server imports
# it and not the other way round.

# Pauli DEM decoders every graphlike family offers (matching default + dense
# fallbacks). Non-Pauli / coherent channels route to `coherent` (see decoder.py).
PAULI_DECODERS = (
    "mwpm",
    "bposd",
    "mld",
    "tn",
)


@dataclass(frozen=True)
class CodeFamily:
    """
    One canonical code family: its wire `name`, UI `label`, `min_distance`, a
    uniform circuit `builder` over the surface knobs, a `num_data` sizer, the
    `default_decoders` the UI offers, the `variant_axes` (patterns/starts/edges the
    family supports along each axis; empty => no selector), and whether its DEM is
    `graphlike` (informational -- hex_color is the lone non-graphlike family, hence
    it omits MWPM from its decoders).
    """

    name: str
    label: str
    min_distance: int
    builder: Callable[..., Circuit]
    num_data: Callable[[int], int]
    default_decoders: tuple[str, ...]
    variant_axes: dict[str, list[str]] = field(default_factory=dict)
    graphlike: bool = True


def _plain(fn: Callable[..., Circuit]) -> Callable[..., Circuit]:
    """
    Adapt a qec.codes builder that ignores the surface knobs to the uniform builder
    signature (distance, rounds, p, channel, pattern, start, edge).
    """

    def build(distance, rounds, p, channel, pattern, start, edge):
        return fn(distance, rounds, p, channel=channel)

    return build


def _variant(fn: Callable[..., Circuit]) -> Callable[..., Circuit]:
    """
    Adapt a surface builder that honours the (pattern, start, edge) knobs.
    """

    def build(distance, rounds, p, channel, pattern, start, edge):
        return fn(
            distance,
            rounds,
            p,
            channel=channel,
            pattern=pattern,
            start=start,
            edge=edge,
        )

    return build


def _rotated_variant(fn: Callable[..., Circuit]) -> Callable[..., Circuit]:
    """
    Adapt rotated_surface_code (rows, cols, ...) to the uniform single-`distance`
    builder signature -- the server/Studio still offer one distance slider (a square
    rows=cols patch); rectangular (rows != cols) patches are only reachable by
    calling qec.codes.rotated_surface_code directly.
    """

    def build(distance, rounds, p, channel, pattern, start, edge):
        return fn(
            distance,
            distance,
            rounds,
            p,
            channel=channel,
            pattern=pattern,
            start=start,
            edge=edge,
        )

    return build


def _color(family: str) -> Callable[..., Circuit]:
    """
    Adapt qec.color.color_code for one triangular-axis family (surface knobs unused).
    """

    def build(distance, rounds, p, channel, pattern, start, edge):
        return color_code(family, distance, rounds, p, channel=channel)

    return build


# The canonical families, in the exact order /templates offers them. Every family
# dispatched by the server lives here -- adding one is a single record.
FAMILIES: dict[str, CodeFamily] = {
    "repetition": CodeFamily(
        name="repetition",
        label="Repetition code",
        min_distance=2,
        builder=_plain(repetition_code),
        num_data=lambda d: d,
        default_decoders=PAULI_DECODERS,
    ),
    "rotated_surface": CodeFamily(
        name="rotated_surface",
        label="Rotated surface code",
        min_distance=2,
        builder=_rotated_variant(rotated_surface_code),
        num_data=lambda d: d * d,
        default_decoders=PAULI_DECODERS,
        variant_axes={
            "patterns": ["css", "xzzx"],
            "starts": ["Z", "X"],
            "edges": ["even", "odd"],
        },
    ),
    "unrotated_surface": CodeFamily(
        name="unrotated_surface",
        label="Unrotated surface code",
        min_distance=2,
        builder=_variant(unrotated_surface_code),
        num_data=lambda d: d * d + (d - 1) * (d - 1),
        default_decoders=PAULI_DECODERS,
        variant_axes={
            "patterns": ["css", "xzzx"],
            "starts": ["Z", "X"],
            "edges": ["even"],
        },
    ),
    "toric": CodeFamily(
        name="toric",
        label="Toric code",
        min_distance=2,
        builder=_plain(toric_code),
        num_data=lambda d: 2 * d * d,
        default_decoders=PAULI_DECODERS,
    ),
    # Triangular-axis families. hex_color is a genuine 6.6.6 color code -- its DEM has
    # weight-3 hyperedges, so it is non-graphlike (MWPM omitted) and offers the
    # dedicated "color" decoder alongside the dense fallbacks. triangular / kagome are
    # graphlike surface codes, so they keep MWPM. Their num_data resolves from the
    # validated layout (patch size is auto-searched, not a closed form of d).
    "hex_color": CodeFamily(
        name="hex_color",
        label="Hexagonal color code",
        min_distance=2,
        builder=_color("hex_color"),
        num_data=lambda d: hex_color_layout(d)[0],
        default_decoders=(
            "bposd",
            "mld",
            "tn",
            "color",
        ),
        graphlike=False,
    ),
    "triangular": CodeFamily(
        name="triangular",
        label="Triangular surface code",
        min_distance=2,
        builder=_color("triangular"),
        num_data=lambda d: triangular_layout(d)[0],
        default_decoders=PAULI_DECODERS,
    ),
    "kagome": CodeFamily(
        name="kagome",
        label="Kagome code",
        min_distance=2,
        builder=_color("kagome"),
        num_data=lambda d: kagome_layout(d)[0],
        default_decoders=PAULI_DECODERS,
    ),
}


def circuit_factory(
    family: str,
    distance: int,
    rounds: int,
    channel: str,
    pattern: str,
    start: str,
    edge: str,
) -> Callable[[float], Circuit]:
    """
    A p -> Circuit factory for a canonical `family` at `distance` under `channel`
    noise. Surface families honour the (pattern, start, edge) knobs; the others
    ignore them. Raises on an unknown family (mirrors the old dispatch).
    """
    fam = FAMILIES.get(family)
    if fam is None:
        raise ValueError(f"unknown template family {family!r}")

    return lambda p: fam.builder(distance, rounds, p, channel, pattern, start, edge)


def num_data(family: str, distance: int) -> int:
    """
    Data-qubit count for `family` at `distance`, or 0 if the family is unknown.
    """
    fam = FAMILIES.get(family)
    if fam is None:
        return 0

    return fam.num_data(distance)
