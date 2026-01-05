/*
 * File: vitest.config.mjs
 * Purpose: Vitest configuration for the AI dashboard unit tests.
 * Flow: resolves aliases and targets test files under tests/ai_dashboard.
 * Created: 2026-01-05
 */
import { defineConfig } from 'vitest/config';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  resolve: {
    alias: {
      'ai-dashboard': path.resolve(__dirname)
    }
  },
  test: {
    environment: 'node',
    include: ['../../tests/ai_dashboard/**/*.test.js']
  }
});
