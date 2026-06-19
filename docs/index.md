---
layout: home

hero:
  name: "qliff"
  text: "Clifford + noisy stabilizer simulator"
  tagline: "Native Rust core. Stim-style Python API."
  actions:
    - theme: brand
      text: Getting Started
      link: /getting-started
    - theme: alt
      text: Simulator API
      link: /api
    - theme: alt
      text: GitHub
      link: https://github.com/plutoniumm/qliff

features:
  - title: "Clifford simulation"
    details: "Noise-free stabilizer simulation on the CHP / Aaronson-Gottesman tableau, with a stim-style uppercase gate API (H, S, CX, CZ, M, R, ...)."
    icon: "&#x269B;"
  - title: "General noise, cheaply"
    details: "Pauli, coherent and amplitude-damping channels via importance-sampled stabilizer trajectories with stratified variance reduction (arXiv:2512.07304)."
    icon: "&#x1F300;"
  - title: "Decoder-ready QEC"
    details: "Detectors, observables, detector error models and ready-made repetition / rotated surface codes. Feed MWPM, BP or ML decoders directly; none bundled."
    icon: "&#x1F6E1;"
  - title: "Native core, Python surface"
    details: "The tableau is a Rust crate exposed through PyO3: the hot path is compiled, every extension seam stays Pythonic."
    icon: "&#x1F680;"
---
