/*
 * File: playwright.config.mjs
 * Purpose: Playwright configuration for AI dashboard E2E checks.
 * Flow: targets tests under tests/ai_dashboard with configurable base URL.
 * Created: 2026-01-05
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3001'
  }
});
