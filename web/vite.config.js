// O.R.I.O.N. window — build settings.
// app.py opens ../ui/index.html straight from disk (file://). WebView2 blocks ES modules there
// (the origin is “null”), so the bundle is one classic script (IIFE) with relative paths.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const classicScript = {
  name: 'orion-classic-script',
  enforce: 'post',
  transformIndexHtml(html) {
    return html
      .replace(/<script type="module" crossorigin/g, '<script defer')
      .replace(/<link rel="stylesheet" crossorigin/g, '<link rel="stylesheet"');
  },
};

export default defineConfig({
  base: './',
  plugins: [react(), classicScript],
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test-setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
  },
  build: {
    outDir: '../ui',
    emptyOutDir: true,
    modulePreload: false,
    cssCodeSplit: false,
    assetsInlineLimit: 0,        // fonts stay files next to the page
    rollupOptions: {
      output: {
        format: 'iife',
        entryFileNames: 'assets/orion.js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
});
