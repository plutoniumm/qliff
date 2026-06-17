---
layout: home

hero:
  name: "aaronson"
  text: "Clifford + noisy stabilizer simulator"
  tagline: "A native Rust core with a stim-style uppercase Python API."
  actions:
    - theme: brand
      text: Getting Started
      link: /getting-started
    - theme: alt
      text: Simulator API
      link: /api
    - theme: alt
      text: GitHub
      link: https://github.com/plutoniumm/aaronson

features:
  - title: "Clifford simulation"
    details: "Noise-free stabilizer simulation via the CHP / Aaronson-Gottesman tableau, with a stim-style uppercase gate API (H, S, CX, CZ, M, R, ...)."
    icon: "&#x269B;"
  - title: "General noise, cheaply"
    details: "Pauli, coherent and non-unitary (amplitude-damping) channels via importance-sampled stabilizer trajectories with stratified variance reduction (arXiv:2512.07304)."
    icon: "&#x1F300;"
  - title: "Decoder-ready QEC"
    details: "Detectors, observables, detector error models and ready-made repetition / rotated surface codes that drop straight into MWPM, BP or ML decoders. No decoder bundled."
    icon: "&#x1F6E1;"
  - title: "Native core, Python surface"
    details: "The tableau lives in a Rust crate exposed through PyO3/maturin, so the hot path is compiled while every extension seam stays Pythonic."
    icon: "&#x1F680;"
---
