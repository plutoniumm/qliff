// Client-side export of a rendered <svg> to a file. SVG is a straight
// serialise; PNG rasterises the SVG onto a canvas via an <img>. Both trigger a
// browser download with no server round-trip.

function serialize(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;

  // Ensure the namespace survives standalone serialisation.
  if (!clone.getAttribute("xmlns")) {
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  }

  return new XMLSerializer().serializeToString(clone);
}

function trigger(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadSVG(svg: SVGSVGElement, filename: string): void {
  const blob = new Blob([serialize(svg)], { type: "image/svg+xml;charset=utf-8" });
  trigger(blob, filename);
}

// Rasterise at `scale`x the SVG's viewBox extent so PNGs stay crisp.
export function downloadPNG(svg: SVGSVGElement, filename: string, scale = 2): void {
  const source = serialize(svg);
  const box = svg.viewBox.baseVal;
  const w = box && box.width > 0 ? box.width : svg.clientWidth || 512;
  const h = box && box.height > 0 ? box.height : svg.clientHeight || 512;
  const img = new Image();
  const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    const ctx = canvas.getContext("2d");

    if (ctx) {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (blob) trigger(blob, filename);
        URL.revokeObjectURL(url);
      }, "image/png");
    } else {
      URL.revokeObjectURL(url);
    }
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}

// Wrapper matching the surfacepro `download(...)` signature. `name` is the bare
// stem; the extension is appended from `mode`.
export function download(name: string, svg: SVGSVGElement, mode: "svg" | "png" = "svg"): void {
  if (mode === "png") {
    downloadPNG(svg, `${name}.png`);
  } else {
    downloadSVG(svg, `${name}.svg`);
  }
}
