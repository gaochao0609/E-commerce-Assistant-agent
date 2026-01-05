/*
 * File: lib/config.js
 * Purpose: Loads and validates runtime configuration for the AI dashboard.
 * Flow: reads JSON config from configs/ and caches parsed values.
 * Created: 2026-01-05
 */
import fs from 'fs/promises';
import path from 'path';
import { z } from 'zod';
import { logger } from './logger.js';

const ConfigSchema = z.object({
  appName: z.string().min(1),
  provider: z.string().min(1),
  model: z.string().min(1),
  maxInputChars: z.number().int().positive(),
  maxFileSizeMb: z.number().int().positive(),
  maxRows: z.number().int().positive(),
  maxColumns: z.number().int().positive(),
  reportFormat: z.enum(['xlsx', 'csv']),
  chartType: z.enum(['bar', 'line', 'area']).default('bar'),
  allowedFileTypes: z.array(z.string()).min(1),
  systemPrompt: z.string().min(1)
});

let cachedConfig;

const resolveConfigPath = () => {
  if (process.env.AI_DASHBOARD_CONFIG_PATH) {
    return path.resolve(process.env.AI_DASHBOARD_CONFIG_PATH);
  }
  return path.resolve(process.cwd(), '..', '..', 'configs', 'ai_dashboard.json');
};

export const getRuntimeConfig = async () => {
  if (cachedConfig) {
    return cachedConfig;
  }

  const configPath = resolveConfigPath();

  try {
    const rawConfig = await fs.readFile(configPath, 'utf-8');
    const parsed = ConfigSchema.parse(JSON.parse(rawConfig));
    cachedConfig = parsed;
    return parsed;
  } catch (error) {
    logger.error('Failed to load AI dashboard config.', { configPath, error });
    throw error;
  }
};
