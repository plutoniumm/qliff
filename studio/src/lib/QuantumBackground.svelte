<script lang="ts">
  // Decorative backdrop behind the whole app: drifting CSS phase-field blobs plus
  // a faint "entanglement graph" of nodes and links on a canvas. Purely cosmetic
  // (fixed, behind everything, pointer-events off, aria-hidden). The canvas web is
  // skipped entirely under prefers-reduced-motion; requestAnimationFrame pauses on
  // its own while the tab is backgrounded.
  import { onMount } from "svelte";

  interface Node {
    x: number;
    y: number;
    vx: number;
    vy: number;
  }

  let canvas: HTMLCanvasElement | null = $state(null);

  onMount(() => {
    const el = canvas;

    if (el === null) {
      return;
    }

    const ctx = el.getContext("2d");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (ctx === null || reduce) {
      return;
    }

    const c = ctx;
    const cnv = el;
    const maxDist = 132;
    const maxDist2 = maxDist * maxDist;

    let raf = 0;
    let width = 0;
    let height = 0;
    let nodes: Node[] = [];

    function seed(): void {
      const count = Math.min(56, Math.round((width * height) / 28000));
      nodes = [];

      for (let i = 0; i < count; i++) {
        nodes.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.16,
          vy: (Math.random() - 0.5) * 0.16,
        });
      }
    }

    function resize(): void {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      width = window.innerWidth;
      height = window.innerHeight;
      cnv.width = Math.floor(width * dpr);
      cnv.height = Math.floor(height * dpr);
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function loop(): void {
      c.clearRect(0, 0, width, height);

      for (const n of nodes) {
        n.x = (n.x + n.vx + width) % width;
        n.y = (n.y + n.vy + height) % height;
      }

      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];

        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;

          if (d2 < maxDist2) {
            const alpha = (1 - Math.sqrt(d2) / maxDist) * 0.2;
            c.strokeStyle = `rgba(139, 108, 255, ${alpha})`;
            c.beginPath();
            c.moveTo(a.x, a.y);
            c.lineTo(b.x, b.y);
            c.stroke();
          }
        }
      }

      c.fillStyle = "rgba(190, 205, 255, 0.5)";

      for (const n of nodes) {
        c.beginPath();
        c.arc(n.x, n.y, 1.3, 0, Math.PI * 2);
        c.fill();
      }

      raf = requestAnimationFrame(loop);
    }

    resize();
    raf = requestAnimationFrame(loop);
    window.addEventListener("resize", resize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  });
</script>

<div class="qbg" aria-hidden="true">
  <div class="blob b1"></div>
  <div class="blob b2"></div>
  <div class="blob b3"></div>
  <div class="grid"></div>
  <canvas bind:this={canvas} class="web"></canvas>
</div>

<style>
  .qbg {
    position: fixed;
    inset: 0;
    z-index: -1;
    overflow: hidden;
    pointer-events: none;
  }
  .blob {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.45;
    mix-blend-mode: screen;
  }
  .b1 {
    width: 46vw;
    height: 46vw;
    top: -12vw;
    left: 56vw;
    background: radial-gradient(circle, var(--accent), transparent 70%);
    animation: drift1 27s var(--ease-out) infinite alternate;
  }
  .b2 {
    width: 40vw;
    height: 40vw;
    bottom: -14vw;
    left: -8vw;
    background: radial-gradient(circle, var(--accent-2), transparent 70%);
    animation: drift2 33s var(--ease-out) infinite alternate;
  }
  .b3 {
    width: 32vw;
    height: 32vw;
    top: 28vh;
    left: 32vw;
    opacity: 0.3;
    background: radial-gradient(circle, var(--accent-3), transparent 70%);
    animation: drift3 39s var(--ease-out) infinite alternate;
  }
  .grid {
    position: absolute;
    inset: 0;
    background-image: radial-gradient(
      circle at 1px 1px,
      rgba(150, 170, 235, 0.1) 1px,
      transparent 0
    );
    background-size: 38px 38px;
    mask: radial-gradient(125% 120% at 50% 0%, #000 32%, transparent 78%);
    -webkit-mask: radial-gradient(125% 120% at 50% 0%, #000 32%, transparent 78%);
    opacity: 0.5;
  }
  .web {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0.55;
  }
  @keyframes drift1 {
    to {
      transform: translate(-9vw, 11vh) scale(1.16);
    }
  }
  @keyframes drift2 {
    to {
      transform: translate(8vw, -9vh) scale(1.12);
    }
  }
  @keyframes drift3 {
    to {
      transform: translate(-6vw, -7vh) scale(1.2);
    }
  }
</style>
