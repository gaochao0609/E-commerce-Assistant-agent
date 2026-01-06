/*
 * File: lib/storage.js
 * Purpose: Handles temporary storage for uploads and generated reports.
 * Flow: persists files under OS temp and stores JSON metadata for lookup.
 * Created: 2026-01-05
 */
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import crypto from 'crypto';

const UPLOAD_DIR = path.join(os.tmpdir(), 'ai-dashboard-uploads');
const REPORT_DIR = path.join(os.tmpdir(), 'ai-dashboard-reports');
const UPLOAD_TTL_HOURS = Number(process.env.AI_DASHBOARD_UPLOAD_TTL_HOURS || 24);
const REPORT_TTL_HOURS = Number(process.env.AI_DASHBOARD_REPORT_TTL_HOURS || 168);
const ID_PATTERN = /^[0-9a-fA-F-]{36}$/;

const ensureDir = async (dir) => {
  await fs.mkdir(dir, { recursive: true });
};

const safeName = (name) => {
  return name.replace(/[^a-zA-Z0-9._-]/g, '_');
};

const isValidId = (id) => {
  return typeof id === 'string' && ID_PATTERN.test(id);
};

const isWithinDir = (dir, targetPath) => {
  const resolvedDir = path.resolve(dir);
  const resolvedTarget = path.resolve(targetPath);
  return resolvedTarget === resolvedDir || resolvedTarget.startsWith(`${resolvedDir}${path.sep}`);
};

const cleanupDir = async (dir, maxAgeHours) => {
  if (!Number.isFinite(maxAgeHours) || maxAgeHours <= 0) {
    return;
  }

  const maxAgeMs = maxAgeHours * 60 * 60 * 1000;
  const now = Date.now();

  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    await Promise.all(
      entries.map(async (entry) => {
        if (!entry.isFile()) {
          return;
        }
        const filePath = path.join(dir, entry.name);
        try {
          const stat = await fs.stat(filePath);
          if (now - stat.mtimeMs > maxAgeMs) {
            await fs.unlink(filePath);
          }
        } catch {
          // Ignore cleanup errors to avoid breaking uploads.
        }
      })
    );
  } catch {
    // Ignore cleanup errors to avoid breaking uploads.
  }
};

const writeMetadata = async (dir, id, metadata) => {
  const metaPath = path.join(dir, `${id}.json`);
  await fs.writeFile(metaPath, JSON.stringify(metadata, null, 2));
};

const removeMetadata = async (dir, id) => {
  const metaPath = path.join(dir, `${id}.json`);
  if (!isWithinDir(dir, metaPath)) {
    return;
  }
  try {
    await fs.unlink(metaPath);
  } catch {
    // Ignore cleanup errors to avoid masking the original issue.
  }
};

const readMetadata = async (dir, id) => {
  if (!isValidId(id)) {
    return null;
  }

  const metaPath = path.join(dir, `${id}.json`);
  if (!isWithinDir(dir, metaPath)) {
    return null;
  }
  try {
    const raw = await fs.readFile(metaPath, 'utf-8');
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.id !== id) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

const ensureFileExists = async (dir, metadata) => {
  if (!metadata || !metadata.filePath) {
    return null;
  }
  if (!isWithinDir(dir, metadata.filePath)) {
    await removeMetadata(dir, metadata.id);
    return null;
  }
  try {
    await fs.stat(metadata.filePath);
  } catch {
    await removeMetadata(dir, metadata.id);
    return null;
  }
  return metadata;
};

export const saveUpload = async (buffer, file) => {
  await ensureDir(UPLOAD_DIR);
  await cleanupDir(UPLOAD_DIR, UPLOAD_TTL_HOURS);
  const id = crypto.randomUUID();
  const filename = safeName(file.name || 'upload');
  const extension = path.extname(filename) || '.bin';
  const storedName = `${id}${extension}`;
  const filePath = path.join(UPLOAD_DIR, storedName);

  await fs.writeFile(filePath, buffer);

  const metadata = {
    id,
    filePath,
    filename,
    size: buffer.length,
    mimeType: file.type || 'application/octet-stream',
    createdAt: new Date().toISOString()
  };

  await writeMetadata(UPLOAD_DIR, id, metadata);
  return metadata;
};

export const getUpload = async (id) => {
  const metadata = await readMetadata(UPLOAD_DIR, id);
  return await ensureFileExists(UPLOAD_DIR, metadata);
};

export const saveReport = async (buffer, format) => {
  await ensureDir(REPORT_DIR);
  await cleanupDir(REPORT_DIR, REPORT_TTL_HOURS);
  const id = crypto.randomUUID();
  const extension = format === 'csv' ? '.csv' : '.xlsx';
  const filename = `report-${id}${extension}`;
  const filePath = path.join(REPORT_DIR, filename);
  const mimeType =
    format === 'csv'
      ? 'text/csv'
      : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

  await fs.writeFile(filePath, buffer);

  const metadata = {
    id,
    filePath,
    filename,
    mimeType,
    createdAt: new Date().toISOString()
  };

  await writeMetadata(REPORT_DIR, id, metadata);
  return metadata;
};

export const getReport = async (id) => {
  const metadata = await readMetadata(REPORT_DIR, id);
  return await ensureFileExists(REPORT_DIR, metadata);
};
