/*
 * File: tests/ai_dashboard/smoke.mjs
 * Purpose: Lightweight smoke test for non-production environments.
 * Flow: hits the base URL and checks for the main header.
 * Created: 2026-01-05
 */

const baseUrl = process.env.SMOKE_BASE_URL;

if (!baseUrl) {
  console.log('SMOKE_BASE_URL not set. Skipping smoke test.');
  process.exit(0);
}

const response = await fetch(baseUrl);
if (!response.ok) {
  console.error(`Smoke test failed: ${response.status}`);
  process.exit(1);
}

const body = await response.text();
if (!body.includes('Operations AI Assistant')) {
  console.error('Smoke test failed: header not found.');
  process.exit(1);
}

console.log('Smoke test passed.');
