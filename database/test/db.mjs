// Shared helpers: a fresh in-memory Postgres (PGlite) with Supabase's reader roles and our migrations.
import { PGlite } from '@electric-sql/pglite';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const MIGRATIONS = join(dirname(fileURLToPath(import.meta.url)), '..', 'migrations');

// The order the live database receives them in: tables + RLS + seeds on D1, analytics later.
export const PHASED_ORDER = ['0001_core', '0004_rls', '0005_seed', '0002_views', '0003_rpc', '0006_retro_window', '0007_next_day', '0008_ml_live'];

export function migrationFiles(order = PHASED_ORDER) {
  const present = new Set(readdirSync(MIGRATIONS).filter((f) => f.endsWith('.sql')).map((f) => f.slice(0, -4)));
  return order.filter((name) => present.has(name)).map((name) => join(MIGRATIONS, `${name}.sql`));
}

export async function freshDb({ order = PHASED_ORDER } = {}) {
  const db = new PGlite();
  // Supabase creates these roles itself; PGlite needs stand-ins so grants and `set role anon` work.
  await db.exec(`create role anon nologin; create role authenticated nologin;`);
  for (const file of migrationFiles(order)) {
    try {
      await db.exec(readFileSync(file, 'utf8'));
    } catch (err) {
      err.message = `${file}: ${err.message}`;
      throw err;
    }
  }
  return db;
}

// Run `fn` with the session role switched to anon, the role the dashboard's key maps to.
export async function asAnon(db, fn) {
  await db.exec('set role anon');
  try {
    return await fn();
  } finally {
    await db.exec('reset role');
  }
}

export function hasMigration(name) {
  return existsSync(join(MIGRATIONS, `${name}.sql`));
}
