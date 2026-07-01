// Custom VitePress theme = the default theme + one global component, <SvelteIsland>,
// which lets any markdown route mount a Svelte 5 explainer (see ./SvelteIsland.vue).
// KaTeX CSS and the explainer theme (scoped to `.qtut`) are imported once here.
import DefaultTheme from 'vitepress/theme';
import type { Theme } from 'vitepress';

import 'katex/dist/katex.min.css';
import '../../_tut/theme.css';
// Pure-CSS component library (q-fig / q-legend / q-bars / q-cells / q-gauge /
// q-chip): lets static figures be authored as plain HTML in markdown -- no
// Svelte island -- and gives the interactive islands shared figure styling.
import '../../../shared/qui/components.css';

import SvelteIsland from './SvelteIsland.vue';

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('SvelteIsland', SvelteIsland);
  },
} satisfies Theme;
