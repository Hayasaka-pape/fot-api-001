import { defineConfig } from 'vite';

export default defineConfig({
  // Library mode may leave Node env references; OBS file:// needs a fully browser-ready production React bundle.
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: 'dist/export',
    emptyOutDir: true,
    // IIFE works from an OBS local file without an ESM loader or a separate web server.
    lib: { entry: 'src/export-entry.jsx', name: 'FotOverlayExport', formats: ['iife'], fileName: () => 'overlay-export.js' },
    cssCodeSplit: false,
    rollupOptions: { output: { assetFileNames: 'style.css' } },
  },
});
