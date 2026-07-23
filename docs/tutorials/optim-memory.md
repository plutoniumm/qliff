---
title: "Optimisations: Memory"
outline: 2
prev:
  text: "Optimisations: Physics"
  link: /tutorials/optim-physics
next: false
---

# Optimisations: Memory <Badge type="info" text="Tutorial 10 of 10" />

<script setup>
import LayoutGrid from '../_tut/optim-memory/LayoutGrid.svelte'
import ScalingPlot from '../_tut/optim-memory/ScalingPlot.svelte'
import ChunkGrid from '../_tut/optim-memory/ChunkGrid.svelte'
</script>

## The running example: a wall of bits {#running}

The [Physics page](./optim-physics) made each shot cheaper. This page makes the shot's data structure cheaper. Everything below lives in one Rust file, `src/tableau.rs`, and one object, `ColTableau`.

The Aaronson-Gottesman tableau for $n$ qubits has $2n+1$ Pauli rows: $n$ destabilizers, $n$ stabilizers, and one measurement scratch. Each row is a pair of bit-vectors (an X-part and a Z-part) plus a sign. Pack the bits 64 to a machine word and the whole state is a few `Vec<u64>`. State-vector simulation cannot reach the qubit counts a surface-code experiment needs; a tableau can, but only if the bit-shuffling stays off the critical path. At $n = 65536$ the tableau is $131073$ rows, and every gate and every measurement touches it. Where the bits sit decides everything.

## Two layouts for one tableau {#dual-layout}

Take a single-qubit gate on qubit $q$. Whatever the gate, it reads and writes $q$'s bit in **every** row, all $2n+1$ of them. There are two ways to store those bits, and they are not equal.

Store the tableau **row-major**, row after row with each row's $n$ qubits packed left to right, and $q$'s bits land one cell per row, `w = ceil(n/64)` words apart. A gate is then $2n+1$ strided scalar touches, each in a different cache line. Once the tableau outgrows cache, that stride costs a cache miss per row and gate throughput falls off a cliff. We call that cliff Wall 1, and it made large-$n$ runs unusable.

Store the tableau **column-major**, with qubit $q$'s bits as one contiguous bit-plane over the $2n+1$ rows (`rw = ceil(rows/64)` words), and the same gate becomes a single sweep over `rw` whole words per plane. That is $O(\text{rows}/64)$ contiguous word operations instead of $O(\text{rows})$ scattered ones: about a 64x drop in distinct cache lines, and the sweep vectorises. `ColTableau` calls these planes `xc`, `zc`, and a `signc` sign plane.

But measurement wants the other layout. `do_measure` and `rowsum` walk a whole Pauli row at once, and the bit-parallel core `word_g` sums the phase contribution over 64 qubit-lanes packed into one **row** word. That is naturally row-major. So `ColTableau` keeps **both**: a proven row-major engine (`inner`, a `RowTableau`) that owns measurement, the RNG, and the record, plus the column-major planes that own gates. A one-bit `layout` flag says which side is authoritative. The tableau transposes lazily: only when the operation kind switches at the gate-to-measure boundary, not per gate.

**Which words a gate touches**

<SvelteIsland :component="LayoutGrid" />

Legend:
- blue cells = qubit $q$'s bits (what the gate touches)
- faint bands = destabilizer, stabilizer, and scratch rows
- `column-major` / `row-major` = the two memory orders

<figure class="q-fig">
  <div class="q-fig-title">Who owns which operation</div>
  <ul class="q-legend">
    <li style="--c:var(--accent)">column-major planes (xc / zc / signc)</li>
    <li style="--c:var(--accent-3)">row-major engine (inner)</li>
  </ul>
  <table>
    <thead>
      <tr><th>operation</th><th>authoritative layout</th><th>cost per call</th></tr>
    </thead>
    <tbody>
      <tr><td>1- and 2-qubit gates</td><td style="color:var(--accent)">column-major</td><td>ceil(rows/64) word ops per plane</td></tr>
      <tr><td>measure / reset / expectation</td><td style="color:var(--accent-3)">row-major</td><td>proven CHP path, word_g phase sums</td></tr>
      <tr><td>gate -&gt; measure switch</td><td>transpose</td><td>one blocked 64x64 transpose</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">The layout flag makes the transpose lazy: a run of gates stays column-major and pays nothing, and a run of measurements stays row-major. Only the boundary between the two kinds costs a transpose, so a d-round memory experiment transposes about once per round, not once per gate.</div>
</figure>

Measured, the column layout does what it promises: gate cost per plane-word stays flat as the plane grows past cache.

**Gate throughput across sizes**

<SvelteIsland :component="ScalingPlot" />

Legend:
- purple `ns per plane-word` = time per word of a plane (the cache-cliff test)
- red `ns per gate` = whole-gate time, $O(\text{rows}/64)$ word ops
- dashed line = the ~14 ns/word bandwidth floor

## The transpose, made cheap {#transpose}

The dual layout only pays if the transpose between the two is nearly free. It is, for three reasons.

First, the transpose itself. `transpose64` flips a 64x64 bit matrix held as 64 `u64` rows in place, using the Hacker's Delight divide-and-conquer: six mask-and-shift passes, halving the block size each time, each output word written once. That is $O(64 \log 64)$ word operations instead of $64 \times 64$ individual bit moves. `to_col` and `to_row` tile the whole tableau into 64x64 blocks and transpose each once. The earlier bit-by-bit transpose took more than 8 seconds at $n = 65536$, and this replaced it. One correctness subtlety remains: Hacker's Delight transposes an MSB-column matrix, and `ColTableau` stores LSB-column (bit $b$ of word $r$ is column $b$), so the shifted operand is flipped to get the LSB form. The unit tests verify this against a naive transpose.

Second, initialization skips the transpose entirely. `ColTableau::new` builds $|0\ldots0\rangle$ **directly in the column planes** and starts in `Layout::Col`, so a pure-gate circuit is already in place and never pays a row-to-column transpose to get going.

Third, the gate kernels are written to vectorise. Each kernel (`k_h`, `k_s`, `k_sdag`, `k_x`, `k_y`, `k_z`, `k_cx`, `k_cz`) takes plain `&mut [u64]` slices and iterates them with `zip`, so LLVM proves the bounds and drops the checks, then auto-vectorises the loop and emits NEON. The two-qubit kernels get their two disjoint planes from a `split_at_mut` helper (`planes_mut`) so they stay bounds-check-free like the one-qubit ones. This is the SIMD path the source notes pulls large-$n$ gates ahead of stim; no hand-written intrinsics are involved, and the section below explains why we left it that way.

<figure class="q-fig">
  <div class="q-fig-title">transpose64: six divide-and-conquer passes</div>
  <ul class="q-legend">
    <li style="--c:var(--accent)">block size j, halving each pass</li>
    <li style="--c:var(--muted)">each pass swaps j x j block pairs across the diagonal</li>
  </ul>
  <table>
    <thead>
      <tr><th>pass</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th><th>6</th></tr>
    </thead>
    <tbody>
      <tr><td>block size j</td><td>32</td><td>16</td><td>8</td><td>4</td><td>2</td><td>1</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">Six passes total, O(64 log 64) word ops, and each of the 64 output words is written once. The kernels below are what run between transposes: one whole-plane sweep each.</div>
</figure>

<figure class="q-fig">
  <div class="q-fig-title">The column-major gate kernels (all bounds-check-free, autovectorised)</div>
  <ul class="q-legend">
    <li style="--c:var(--accent)">whole-plane word sweep over ceil(rows/64) words</li>
    <li style="--c:var(--z)">writes the sign plane</li>
  </ul>
  <table>
    <thead>
      <tr><th>kernel</th><th>gate</th><th>per-word op</th></tr>
    </thead>
    <tbody>
      <tr><td>k_h</td><td>H</td><td><code>sign ^= x &amp; z</code><br><code>swap x, z</code></td></tr>
      <tr><td>k_s / k_sdag</td><td>S / S†</td><td><code>sign ^= x &amp; z (or x &amp; !z)</code><br><code>z ^= x</code></td></tr>
      <tr><td>k_x / k_y / k_z</td><td>Pauli</td><td><code>sign ^= z / x^z / x</code></td></tr>
      <tr><td>k_cx</td><td>CX a-&gt;b</td><td><code>x_b ^= x_a</code><br><code>z_a ^= z_b</code><br><code>sign update</code></td></tr>
      <tr><td>k_cz</td><td>CZ</td><td><code>z_a ^= x_b</code><br><code>z_b ^= x_a</code><br><code>sign update</code></td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">SWAP is three CX kernels. Each op is one pass over the plane's words, so a gate's whole cost is the ceil(rows/64) factor and nothing else. The kernels are #[inline], so the batched run() folds them straight into its loop with no per-gate call.</div>
</figure>

::: info One transpose per round is the floor
The lazy transpose already collapses a whole syndrome round to a single flush. Going below that, coalescing several rounds into fewer transposes, is blocked by ancilla reuse: the next round's CX ladder touches the ancillas the previous round measured, which forces a flush. So one transpose per gate-to-measure boundary, about one per round, is as far as this goes.
:::

## Zero-copy output {#zero-copy}

Once a batch of shots is sampled, the results have to cross back into Python. The batched samplers (`sample_batch`, `frame_run`) return a single flat `Vec<u8>` of `shots * num_meas` record bytes plus the `num_meas` width. Python does not iterate it. It views it in place:

```python
return np.frombuffer(buf, dtype=np.uint8).reshape(shots, num_meas)
```

No copy, no per-element boxing. The earlier design returned a nested Python structure, which forced one PyO3 Python-integer allocation per measurement per shot. That is on the order of `shots * num_meas` small allocations, which, measured at $n = 1024$ in the June 2026 profiling run, came to about 40% of per-shot time. `np.frombuffer` over one contiguous buffer erases all of it: the bytes the Rust chunks wrote shot-major are the array's memory.

<figure class="q-fig">
  <div class="q-fig-title">Crossing the FFI boundary, per batch of S shots x M measurements</div>
  <ul class="q-legend">
    <li style="--c:var(--bad)">old: nested Python ints</li>
    <li style="--c:var(--accent)">now: one flat buffer, viewed</li>
  </ul>
  <table>
    <thead>
      <tr><th></th><th style="color:var(--bad)">nested ints</th><th style="color:var(--accent)">flat buffer + frombuffer</th></tr>
    </thead>
    <tbody>
      <tr><td>Python allocations</td><td style="color:var(--bad)">~ S x M</td><td style="color:var(--accent)">0 (a view)</td></tr>
      <tr><td>bytes copied out</td><td style="color:var(--bad)">S x M boxed</td><td style="color:var(--accent)">0</td></tr>
      <tr><td>share of per-shot time</td><td style="color:var(--bad)">~40% (n=1024, June 2026)</td><td style="color:var(--accent)">negligible</td></tr>
    </tbody>
  </table>
  <div class="q-fig-note">Numbers attributed to the June 2026 profiling run, not re-measured here. The current samplers return (bytes, num_meas) and Python reshapes the buffer. The DetectorSampler then XOR-folds detectors against their noiseless reference directly on that uint8 array.</div>
</figure>

## Reproducible multicore {#multicore}

The samplers are parallel, and the parallelism is built so the answer does not depend on how many cores ran it. That invariance is a deliberate constraint, not an accident.

Each sampler splits `shots` into **fixed-size** chunks and hands them to rayon: `FRAME_CHUNK = 1024` for the frame engine, `BATCH_CHUNK = 256` for the per-shot tableau sampler, `EST_CHUNK = 256` for the importance estimator. The size is a compile-time constant, never derived from the core count. Each chunk then derives its own RNG seeds from its **index** through a splitmix64 mix (`chunk_seed`), so chunk 5 draws the same stream no matter which worker picks it up or how many workers exist. Same seed in, byte-identical bytes out, whether it runs on one core or eight. The source verifies this at 1 vs 8 threads.

**Fixed chunks, index-derived seeds**

<SvelteIsland :component="ChunkGrid" />

Legend:
- coloured left border = which core ran a chunk
- mono value = the chunk's splitmix64 seed, from its index
- `output digest` = a schedule-independent fold of the seeds

## The reference run, computed once {#reference}

The frame sampler needs one thing before it can run: the noiseless measurement record, the reference every shot's detection events are XORed against. `frame_reference` computes it by running the circuit with no noise and returning the deterministic measurement bits. It returns `None` if any measurement is a coin flip, and the code then falls back to the heavier per-shot `sample_batch`.

That reference depends only on the circuit, not on the seed or the shot count. So `CompiledSampler` computes it **once**, on the first `sample()` call, and caches it (`self._ref`) for every later call. Across a logical-error-rate sweep of many `sample()` calls on the same circuit, this is the difference between paying the serial reference pass once and paying it every time. In one sweep it had been roughly 85% of per-call cost. Caching it moves that to a one-time setup.

The reference run has its own memory lesson. It is a full circuit replay, so it must run on the fast layout. `frame_reference` builds a fresh `ColTableau` and replays the gates column-major, transposing to the row engine only for measurements. The source notes this runs about 20x faster than replaying on the old row-major path: the same cache cliff from the first section, now avoided in the one serial pass the parallel engine cannot hide behind.

<figure class="q-fig">
  <div class="q-fig-title">Where an LER sweep spends its time</div>
  <ul class="q-legend">
    <li style="--c:var(--bad)">serial reference, if recomputed every call</li>
    <li style="--c:var(--accent)">parallel frame_run over the shots</li>
  </ul>
  <ul class="q-bars">
    <li style="--v:.85;--c:var(--bad)"><b>reference</b><span class="q-track"></span><i>~85% / call</i></li>
    <li style="--v:.15;--c:var(--accent)"><b>frame_run</b><span class="q-track"></span><i>~15% / call</i></li>
  </ul>
  <div class="q-fig-note">Share attributed to the sweep profiled in the June 2026 run, not re-measured here. Caching the reference (it is circuit-only) turns the red bar into a one-time cost. Running it on the column-major layout keeps that one-time cost ~20x smaller than the old row-major replay would.</div>
</figure>

## Worked example {#worked-example}

Take $n = 1024$, one H gate, and follow the memory.

The tableau is $2n+1 = 2049$ rows. Column-major, qubit $q$'s plane is `ceil(2049/64) = 33` words, so the H kernel sweeps 33 words on each of the X, Z, and sign planes: 99 word operations, all contiguous. Row-major, the same H would touch $q$'s bit in every one of the 2049 rows, `w = ceil(1024/64) = 16` words apart, for 2049 strided scalar touches. The ratio is `2049 / 33 = 62`, so the column layout does about a 62nd of the distinct-cache-line work here, rising toward 64 as $n$ grows.

When this circuit next measures, `to_row` transposes the planes back into the row engine by walking `ceil(2049/64) x ceil(1024/64) = 33 x 16 = 528` blocks of 64x64 bits, each block six passes of `transpose64`. That one transpose is amortised over the whole round of gates that preceded it. A pure-gate circuit that never measures never transposes at all, because `ColTableau::new` started column-major.
