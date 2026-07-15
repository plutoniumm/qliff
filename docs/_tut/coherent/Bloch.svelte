<script lang="ts">
  // The star of the page: a real WebGL Bloch sphere (Three.js). It renders ONE
  // persistent scene -- a translucent sphere, the X/Y/Z axes + equator/meridian
  // rings, the state-vector arrow, and a faint "sweep" ring showing the current
  // RZ(theta) rotation from the pre-rotation vector to the live one. The parent
  // owns the physics: it passes in the current Bloch vector `vec` (already through
  // whatever gates/rotation), an optional `ghost` (the vector before the live
  // rotation) and `sweep` (theta) so we can draw the arc. We only UPDATE the
  // existing meshes on reactive change -- we never rebuild the scene per tick, and
  // we keep a single WebGL context, disposed cleanly on unmount.
  import { onMount, onDestroy } from "svelte";
  import * as THREE from "three";
  import { C } from "$lib/colors";
  import type { Vec3 } from "./bloch";

  let {
    vec,
    ghost = null,
    sweep = 0,
    label = "",
  }: {
    vec: Vec3;
    ghost?: Vec3 | null;
    sweep?: number;
    label?: string;
  } = $props();

  let host: HTMLDivElement;

  let renderer: THREE.WebGLRenderer | undefined;
  let scene: THREE.Scene | undefined;
  let camera: THREE.PerspectiveCamera | undefined;
  let arrow: THREE.Group | undefined;
  let ghostArrow: THREE.Group | undefined;
  let sweepArc: THREE.Line | undefined;
  let raf = 0;
  let ro: ResizeObserver | undefined;
  const disposables: { dispose: () => void }[] = [];

  // Camera orbit state (a tiny hand-rolled orbit controller -- no extra import
  // path, no momentum surprises). az = azimuth, el = elevation, both radians.
  let az = 0.9;
  let el = 0.5;
  const RADIUS = 3.4;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  const SPHERE_R = 1;

  // Colors arrive as CSS expressions (e.g. "var(--accent)"); WebGL/canvas can't
  // read CSS vars, so resolve them to a concrete color via a hidden probe under
  // `host` (which inherits the .qtut tokens). Re-resolved on theme toggle below.
  let probe: HTMLSpanElement | undefined;
  function resolveCss(expr: string): string {
    if (!host) {
      return expr;
    }
    if (!probe) {
      probe = document.createElement("span");
      probe.style.display = "none";
    }
    probe.style.color = "";
    probe.style.color = expr;
    host.appendChild(probe);
    const rgb = getComputedStyle(probe).color;
    host.removeChild(probe);

    return rgb || expr;
  }

  function hex(c: string): THREE.Color {
    return new THREE.Color(resolveCss(c));
  }

  // Materials/labels whose color tracks a CSS var, repainted when the docs toggle
  // light/dark (the RAF loop then shows the new colors on the next frame).
  const tinted: (() => void)[] = [];
  let themeObs: MutationObserver | undefined;

  function paint<M extends THREE.Material & { color: THREE.Color }>(mat: M, expr: string): M {
    const apply = () => mat.color.copy(hex(expr));
    apply();
    tinted.push(apply);

    return mat;
  }

  function track<T extends { dispose: () => void }>(o: T): T {
    disposables.push(o);

    return o;
  }

  // A unit "lat/long" ring in a chosen plane, as a thin line loop.
  function ring(plane: "xy" | "xz" | "yz", color: string, opacity: number): THREE.Line {
    const pts: THREE.Vector3[] = [];
    const N = 96;
    for (let i = 0; i <= N; i++) {
      const t = (i / N) * Math.PI * 2;
      const c = Math.cos(t);
      const s = Math.sin(t);
      if (plane === "xy") {
        pts.push(new THREE.Vector3(c, s, 0));
      } else if (plane === "xz") {
        pts.push(new THREE.Vector3(c, 0, s));
      } else {
        pts.push(new THREE.Vector3(0, c, s));
      }
    }
    const geo = track(new THREE.BufferGeometry().setFromPoints(pts));
    const mat = track(
      paint(new THREE.LineBasicMaterial({ transparent: true, opacity }), color),
    );

    return new THREE.Line(geo, mat);
  }

  // A labelled axis: a line from -L..+L and a small sprite at the +end.
  function axis(dir: Vec3, color: string, text: string): THREE.Group {
    const g = new THREE.Group();
    const L = 1.32;
    const v = new THREE.Vector3(dir[0], dir[1], dir[2]);
    const geo = track(
      new THREE.BufferGeometry().setFromPoints([
        v.clone().multiplyScalar(-L),
        v.clone().multiplyScalar(L),
      ]),
    );
    const mat = track(paint(new THREE.LineBasicMaterial({ transparent: true, opacity: 0.55 }), color));
    g.add(new THREE.Line(geo, mat));
    g.add(makeLabel(text, color, v.clone().multiplyScalar(L + 0.18)));

    return g;
  }

  // A text sprite (canvas texture) floating at a world position.
  function makeLabel(text: string, color: string, at: THREE.Vector3): THREE.Sprite {
    const cv = document.createElement("canvas");
    cv.width = 128;
    cv.height = 128;
    const tex = track(new THREE.CanvasTexture(cv));
    const draw = () => {
      const ctx = cv.getContext("2d");
      if (ctx) {
        ctx.clearRect(0, 0, 128, 128);
        ctx.fillStyle = resolveCss(color);
        ctx.font = "bold 64px ui-monospace, monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, 64, 64);
      }
      tex.needsUpdate = true;
    };
    draw();
    tinted.push(draw);
    const mat = track(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
    const sp = new THREE.Sprite(mat);
    sp.position.copy(at);
    sp.scale.set(0.34, 0.34, 0.34);

    return sp;
  }

  // An arrow group (shaft + cone head) pointing along +z by default; we orient and
  // scale it to the live vector each update via setVec().
  function makeArrow(color: string, headColor: string): THREE.Group {
    const g = new THREE.Group();
    const shaftGeo = track(new THREE.CylinderGeometry(0.022, 0.022, 1, 16));
    const shaftMat = track(paint(new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0.1 }), color));
    const shaft = new THREE.Mesh(shaftGeo, shaftMat);
    shaft.position.y = 0.5;
    g.add(shaft);
    const headGeo = track(new THREE.ConeGeometry(0.072, 0.18, 20));
    const headMat = track(paint(new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.1 }), headColor));
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 1;
    g.add(head);
    g.userData.shaft = shaft;
    g.userData.head = head;

    return g;
  }

  // Point an arrow group along Bloch vector v (length = |v|, so damping shrinks it).
  function setVec(g: THREE.Group, v: Vec3) {
    const len = Math.hypot(v[0], v[1], v[2]);
    const target = new THREE.Vector3(v[0], v[1], v[2]);
    if (len < 1e-6) {
      g.visible = false;

      return;
    }
    g.visible = true;
    const dir = target.clone().normalize();
    // base orientation is +y; rotate +y onto dir.
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    g.quaternion.copy(q);
    const shaft = g.userData.shaft as THREE.Mesh;
    const head = g.userData.head as THREE.Mesh;
    // shaft spans 0..len-headLen along local y; head sits at len.
    const headLen = 0.18;
    const shaftLen = Math.max(0.001, len - headLen);
    shaft.scale.y = shaftLen;
    shaft.position.y = shaftLen / 2;
    head.position.y = shaftLen + headLen / 2;
  }

  function updateCamera() {
    if (!camera) {
      return;
    }
    el = Math.max(-1.45, Math.min(1.45, el));
    camera.position.set(
      RADIUS * Math.cos(el) * Math.cos(az),
      RADIUS * Math.sin(el),
      RADIUS * Math.cos(el) * Math.sin(az),
    );
    camera.up.set(0, 1, 0);
    camera.lookAt(0, 0, 0);
  }

  function resize() {
    if (!renderer || !camera || !host) {
      return;
    }
    const w = host.clientWidth;
    const h = host.clientHeight;
    if (w === 0 || h === 0) {
      return;
    }
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  function onPointerDown(e: PointerEvent) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    host.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: PointerEvent) {
    if (!dragging) {
      return;
    }
    az -= (e.clientX - lastX) * 0.008;
    el += (e.clientY - lastY) * 0.008;
    lastX = e.clientX;
    lastY = e.clientY;
    updateCamera();
  }

  function onPointerUp(e: PointerEvent) {
    dragging = false;
    if (host.hasPointerCapture(e.pointerId)) {
      host.releasePointerCapture(e.pointerId);
    }
  }

  onMount(() => {
    // NOTE: Bloch convention maps z (qubit) -> three.js Y (up). We feed vectors as
    // (x, y, z) but rotate the whole frame so "up" is the |0> pole. Simpler: build
    // the scene in a frame where qubit-z is world-Y by relabelling axes when we
    // construct rings/axes. We use the natural mapping (qx->X, qy->Z, qz->Y) so the
    // north pole points up. setVec/updateSweep also use this mapping via remap().
    scene = new THREE.Scene();

    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    updateCamera();

    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    host.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";

    // lighting.
    const amb = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(amb);
    const key = new THREE.DirectionalLight(0xffffff, 0.7);
    key.position.set(2, 3, 2);
    scene.add(key);

    // translucent sphere shell.
    const sphGeo = track(new THREE.SphereGeometry(SPHERE_R, 48, 32));
    const sphMat = track(
      paint(
        new THREE.MeshStandardMaterial({
          transparent: true,
          opacity: 0.08,
          roughness: 0.6,
          metalness: 0,
          side: THREE.FrontSide,
        }),
        C.accent,
      ),
    );
    scene.add(new THREE.Mesh(sphGeo, sphMat));
    // faint wireframe for depth.
    const wireGeo = track(new THREE.SphereGeometry(SPHERE_R * 1.001, 24, 16));
    const wireMat = track(
      paint(new THREE.MeshBasicMaterial({ wireframe: true, transparent: true, opacity: 0.16 }), C.line),
    );
    scene.add(new THREE.Mesh(wireGeo, wireMat));

    // remap qubit axes -> three world: qx->X(world), qy->Z(world), qz->Y(world).
    const frame = new THREE.Group();
    scene.add(frame);

    // equator (qubit xy-plane) -> world xz ring; meridians.
    frame.add(ring("xz", C.line, 0.32)); // equator (z=0)
    frame.add(ring("xy", C.line, 0.16));
    frame.add(ring("yz", C.line, 0.16));

    // axes in WORLD coords already remapped: qz(up)=Y, qx=X, qy=Z.
    frame.add(axis([0, 1, 0], C.fg, "|0⟩")); // +z qubit
    frame.add(axis([0, -1, 0], C.muted, "|1⟩"));
    frame.add(axis([1, 0, 0], C.x, "x"));
    frame.add(axis([0, 0, 1], C.z, "y"));

    // sweep arc (built empty, updated reactively).
    const arcGeo = track(new THREE.BufferGeometry());
    arcGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3 * 65), 3));
    const arcMat = track(paint(new THREE.LineBasicMaterial({ transparent: true, opacity: 0.9 }), C.accent2));
    sweepArc = new THREE.Line(arcGeo, arcMat);
    frame.add(sweepArc);

    // ghost arrow (pre-rotation), faint.
    ghostArrow = makeArrow(C.muted, C.muted);
    frame.add(ghostArrow);

    // state arrow (live).
    arrow = makeArrow(C.accent, C.accent2);
    frame.add(arrow);

    pushUpdate();

    ro = new ResizeObserver(() => resize());
    ro.observe(host);
    resize();

    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (renderer && scene && camera) {
        renderer.render(scene, camera);
      }
    };
    raf = requestAnimationFrame(loop);

    // repaint every tracked color when the docs flip light/dark (.dark on <html>).
    themeObs = new MutationObserver(() => {
      for (const apply of tinted) {
        apply();
      }
    });
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  });

  // qubit (x,y,z) -> world (x, z, y) so the |0> pole points up.
  function remap(v: Vec3): Vec3 {
    return [v[0], v[2], v[1]];
  }

  function pushUpdate() {
    if (!arrow || !ghostArrow) {
      return;
    }
    setVec(arrow, remap(vec));
    if (ghost) {
      ghostArrow.visible = true;
      setVec(ghostArrow, remap(ghost));
    } else {
      ghostArrow.visible = false;
    }
    updateSweepRemapped();
  }

  // sweep arc, computed in qubit coords then remapped to world.
  function updateSweepRemapped() {
    if (!sweepArc) {
      return;
    }
    const g = ghost;
    if (!g || Math.abs(sweep) < 1e-3) {
      sweepArc.visible = false;

      return;
    }
    sweepArc.visible = true;
    const N = 64;
    const arr = new Float32Array((N + 1) * 3);
    const rxy = Math.hypot(g[0], g[1]);
    const z = g[2];
    const phi0 = Math.atan2(g[1], g[0]);
    const arcR = Math.max(rxy, 0.001);
    for (let i = 0; i <= N; i++) {
      const t = phi0 + (i / N) * sweep;
      const q: Vec3 = [arcR * Math.cos(t) * 0.99, arcR * Math.sin(t) * 0.99, z * 0.99];
      const w = remap(q);
      arr[i * 3] = w[0];
      arr[i * 3 + 1] = w[1];
      arr[i * 3 + 2] = w[2];
    }
    const pos = sweepArc.geometry.getAttribute("position") as THREE.BufferAttribute;
    if (pos && pos.count === N + 1) {
      pos.copyArray(arr);
      pos.needsUpdate = true;
    } else {
      sweepArc.geometry.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    }
  }

  // React to prop changes -- update existing meshes only, never rebuild the scene.
  $effect(() => {
    // read the reactive props so the effect re-runs when they change.
    void vec;
    void ghost;
    void sweep;
    pushUpdate();
  });

  onDestroy(() => {
    cancelAnimationFrame(raf);
    ro?.disconnect();
    themeObs?.disconnect();
    for (const d of disposables) {
      try {
        d.dispose();
      } catch {
        // ignore disposal of already-freed resources.
      }
    }
    if (renderer) {
      renderer.dispose();
      renderer.forceContextLoss?.();
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    }
    renderer = undefined;
    scene = undefined;
    camera = undefined;
  });
</script>

<div
  class="bloch"
  bind:this={host}
  role="img"
  aria-label={label || "Bloch sphere"}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointerleave={onPointerUp}
></div>

<style>
  .bloch {
    width: 100%;
    /* Fill the host <div> the parent sizes (an explicit ~340-360px), and never
       grow past it -- the canvas tracks this box via the ResizeObserver. */
    height: 100%;
    min-height: 0;
    max-height: 100%;
    cursor: grab;
    touch-action: none;
  }

  .bloch:active {
    cursor: grabbing;
  }
</style>
