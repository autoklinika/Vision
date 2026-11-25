import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';
export default defineConfig({
  base: '/design/',
  plugins: [react()],
  build: {rollupOptions: {input: {
    carbon: fileURLToPath(new URL('./carbon.html', import.meta.url)),
    fluent: fileURLToPath(new URL('./fluent.html', import.meta.url)),
  }}},
});
