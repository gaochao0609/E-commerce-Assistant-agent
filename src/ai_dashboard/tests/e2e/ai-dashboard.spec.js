/*
 * File: tests/e2e/ai-dashboard.spec.js
 * Purpose: Basic end-to-end checks for the AI dashboard UI.
 * Flow: verifies key UI elements load in the browser.
 * Created: 2026-01-05
 */
import { expect, test } from '@playwright/test';

test.describe('AI dashboard', () => {
  test.skip(!process.env.E2E_BASE_URL, 'E2E_BASE_URL is not set.');

  test('loads the main interface', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: 'Operations AI Assistant' })
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send request' })).toBeVisible();
    await expect(page.getByText('Data Upload')).toBeVisible();
  });
});
