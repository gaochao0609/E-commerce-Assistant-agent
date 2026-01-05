/*
 * File: tests/ai_dashboard/vitest.config.mjs
 * Purpose: Vitest configuration for AI dashboard unit tests.
 * Flow: defines node environment and module alias resolution.
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
      'ai-dashboard': path.resolve(__dirname, '../../src/ai_dashboard')
    }
  },
  test: {
    environment: 'node',
    include: ['tests/ai_dashboard/**/*.test.js']
  }
});
