# Examples

Copy-paste recipes for the things people actually run with `aaronson`. Each
example is a single runnable block — imports at the top, one line of intent, one
line on what to expect. They build only on the documented API, so they keep
working as you mix and match.

- [Circuits](/examples/circuits) — Bell and GHZ states, sampling bitstrings,
  mid-circuit measurement and reset, classical feedback, and reading
  $\langle P\rangle$ without collapse.
- [Noise](/examples/noise) — Pauli channels sampled with `Sampler`, coherent
  rotations estimated with flat and stratified importance sampling, and a custom
  `Channel`.
- [Error Correction](/examples/qec) — repetition- and surface-code memory
  experiments, detector sampling, exporting a detector error model, and decoding
  with pymatching.
