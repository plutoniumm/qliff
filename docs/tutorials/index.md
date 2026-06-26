---
title: Interactive Tutorials
layout: home

hero:
  name: qliff explainers
  text: How a QEC qubit stays alive
  tagline: Seven interactive walkthroughs of the qliff stack -- the decoders that clean up errors, the noise they fight, and the logical error rate that scores it all. Drag the sliders. Watch it happen.
  actions:
    - theme: brand
      text: Start -- Gates & CX
      link: /tutorials/gates
    - theme: alt
      text: Getting started
      link: /getting-started

features:
  - icon: "⚛️"
    title: Gates & CX
    details: Cliffords don't move amplitudes -- they conjugate Pauli operators. See why CX makes X copy forward and Z copy backward.
    link: /tutorials/gates
    linkText: Tutorial 01
  - icon: "🧩"
    title: Minimum-Weight Perfect Matching
    details: Turn a syndrome into a graph, then pair up the defects as cheaply as possible.
    link: /tutorials/mwpm
    linkText: Tutorial 02
  - icon: "🔁"
    title: Belief Propagation
    details: Let qubits and checks exchange probabilities until they agree on the likeliest error.
    link: /tutorials/bp
    linkText: Tutorial 03
  - icon: "🕸️"
    title: Tensor-Network Decoder
    details: Sum over every possible error at once by contracting a factor graph -- exact maximum likelihood.
    link: /tutorials/tn
    linkText: Tutorial 04
  - icon: "🌀"
    title: Coherent Noise
    details: Rotations and damping aren't Pauli errors -- represent them as signed quasiprobabilities over Cliffords.
    link: /tutorials/coherent
    linkText: Tutorial 05
  - icon: "🎲"
    title: Noise Sampling
    details: How one stabilizer trajectory is drawn, and why importance weights make non-Pauli noise honest.
    link: /tutorials/noise
    linkText: Tutorial 06
  - icon: "📉"
    title: Logical Error Rate
    details: Sample, decode, compare -- and read the threshold off a sweep with honest error bars.
    link: /tutorials/ler
    linkText: Tutorial 07
---

The pipeline these explainers walk, end to end: **noise** corrupts the qubits, **stabilizers** flag what changed, a **decoder** infers the most likely error, and you read off whether the **logical** qubit survived. Written for a second-year physics student -- no prior QEC assumed. Read top to bottom.
