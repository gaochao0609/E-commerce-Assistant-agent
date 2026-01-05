/*
 * File: tests/ai_dashboard/unit/intent.test.js
 * Purpose: Confirms report intent detection behavior.
 * Flow: checks keyword detection on the latest user message.
 * Created: 2026-01-05
 */
import { describe, expect, it } from 'vitest';
import { shouldGenerateReport } from 'ai-dashboard/lib/intent.js';

describe('shouldGenerateReport', () => {
  it('returns true when user requests a report', () => {
    const result = shouldGenerateReport([
      { role: 'assistant', content: 'Hello.' },
      { role: 'user', content: 'Please export a report.' }
    ]);

    expect(result).toBe(true);
  });

  it('returns false when no report keywords are present', () => {
    const result = shouldGenerateReport([{ role: 'user', content: 'Show KPIs.' }]);

    expect(result).toBe(false);
  });
});
