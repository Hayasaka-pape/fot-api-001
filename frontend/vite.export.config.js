import { defineConfig } from 'vite';

export default defineConfig({
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: 'dist/export',
    emptyOutDir: true,
    lib: { entry: 'src/export-entry.jsx', name: 'FotOverlayExport', formats: ['iife'], fileName: () => 'overlay-export.js' },
    cssCodeSplit: false,
    rollupOptions: { output: { assetFileNames: 'style.css' } },
  },
});
