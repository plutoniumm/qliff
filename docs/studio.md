# Studio

`qliff studio` is a local web UI for **drawing** stabilizer-code lattices and
**running** them to measure a logical error rate (LER). It ships in the wheel and
launches with one command:

```bash
pip install "qliff[studio]"
qliff                       # opens http://127.0.0.1:8731 in your browser
```

From a source checkout you can run it without installing:

```bash
./do serve                  # = python -m qliff
./do serve --port 9000 --no-browser
```

The `[studio]` extra pulls the web server (FastAPI + uvicorn) and the decoders
(`pymatching`, `ldpc`). The core library stays dependency-light — `import qliff`
never imports any of these.

## Part A — diagram generator

A passive, frontend-only generator for the three lattice families, each rendered
as SVG and exportable to SVG or PNG:

- **Square** — the rotated/unrotated surface code: data qubits on grid corners,
  a checkerboard of X/Z plaquettes, boundary half-circle stabilizers.
- **Triangular** — a triangular lattice of up/down triangles, with a **Kagome**
  (medial-lattice) variant.
- **Hexagonal** — the honeycomb color code, 3-colored so every shared edge takes
  the third color of its two faces.

## Part B — builder + runner

An interactive canvas for assembling larger codes and measuring their
performance:

- **Build** — drag tiles from the palette onto the grid; select (click or
  marquee, Finder-style), move, rotate, copy/paste, undo/redo, snap-to-grid, and
  save/load the design as JSON.
- **Configure** — pick a built-in template (repetition, rotated/unrotated
  surface, toric) or use your free-form drawing; set the noise model + strength
  (or a sweep), rounds, shots, and decoder (**MWPM** default, **BP+OSD** for
  non-graphlike codes).
- **Run** — the server compiles the lattice to a circuit, samples noisy
  trajectories, decodes, and streams the logical error rate back to a live plot
  of LER vs. physical error rate.

## API

The server is a thin REST + WebSocket layer over the engine, so you can drive it
without the UI:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/templates` | the code families the builder offers |
| `POST /api/compile` | static circuit summary (qubit/detector counts) for a request |
| `POST /api/run` | run a full LER sweep, return the curve |
| `WS /api/run` | the same sweep, streamed one point at a time |

A request carries either a `template` (`{family, distance}`) or an explicit
`spec` (the builder's resolved lattice), plus a `noise` model, `shots`, and a
`decoder`. See `qliff/server/schema.py` for the full contract.
