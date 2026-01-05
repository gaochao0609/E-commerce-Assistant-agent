/*
 * File: tests/ai_dashboard/playwright.config.mjs
 * Purpose: Playwright configuration for AI dashboard E2E checks.
 * Flow: uses an optional base URL and a focused test directory.
 * Created: 2026-01-05
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/ai_dashboard/e2e',
  timeout: 30000,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3001'
  }
});
