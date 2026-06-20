import { tick } from "svelte";

// Wrap a Svelte state mutation in the View Transitions API so the swapped DOM
// cross-fades (see ::view-transition rules in app.css). Falls back to a plain
// update when the API is missing or the user prefers reduced motion. The
// callback returns tick() so Svelte has flushed the DOM before the new snapshot
// is captured.
type VtDocument = Document & {
  startViewTransition?: (cb: () => Promise<void>) => unknown;
};

export function viewTransition(update: () => void): void {
  const doc = document as VtDocument;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (typeof doc.startViewTransition !== "function" || reduce) {
    update();

    return;
  }

  doc.startViewTransition(async () => {
    update();
    await tick();
  });
}
