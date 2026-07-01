// Re-export shim -- the deterministic PRNG helpers now live in the cross-codebase
// toolkit at shared/qui, shared with the studio SPA. Import via `$lib/rng` (docs)
// or `$shared/rng` (either build); both land here.
export * from '$shared/rng';
