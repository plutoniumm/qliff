import { defineConfig } from 'vitepress';
import { readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const isDev = process.env.NODE_ENV === 'development';
const here = dirname(fileURLToPath(import.meta.url));

// "Exam" report mechanism (mirrors plutoniumm/qudit):
//   MDR_OUT=docs/tests ./do test
// drops one markdown report per test file into docs/tests/. We discover them at
// config-eval time so the sidebar stays in sync without hand-editing. The dir is
// gitignored and may be empty on a fresh clone, so guard for that.
function testReports() {
  const dir = join(here, '..', 'tests');
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.md') && f !== 'index.md')
    .sort()
    .map((f) => {
      const slug = f.replace(/\.md$/, '');
      const text = slug.charAt(0).toUpperCase() + slug.slice(1);
      return { text, link: `/tests/${slug}` };
    });
}

export default defineConfig({
  base: isDev ? '/' : '/aaronson/',
  title: 'aaronson',
  description: 'Clifford + noisy stabilizer simulator with a native Rust core.',
  markdown: {
    math: true,
    lineNumbers: true,
  },
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Getting Started', link: '/getting-started' },
      { text: 'API', link: '/api' },
    ],

    sidebar: [
      {
        text: 'Usage',
        items: [
          { text: 'Getting Started', link: '/getting-started' },
          { text: 'Simulator', link: '/api' },
          { text: 'Circuit', link: '/circuit' },
          { text: 'Observables & Metrics', link: '/observables' },
          { text: 'Noise', link: '/noise' },
          { text: 'Error Correction', link: '/qec' },
        ],
      },
      {
        text: 'Testing',
        items: [{ text: 'Overview', link: '/tests/' }, ...testReports()],
      },
    ],

    search: {
      provider: 'local',
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/plutoniumm/aaronson' },
    ],
  },
  vite: {
    server: {
      port: 3000,
      fs: {
        strict: false,
      },
    },
  },
});
