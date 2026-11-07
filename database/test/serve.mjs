// Serve a migrated PGlite over the Postgres wire protocol, for the Python integration tests:
//   npm run serve            (then: IWW_TEST_DB_URL=postgresql://postgres@127.0.0.1:5544/postgres pytest -m db)
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';
import { PGlite } from '@electric-sql/pglite';
import { freshDb } from './db.mjs';

const port = Number(process.env.PORT ?? 5544);
// EMPTY=1 serves a database with only Supabase's roles, for testing tools/migrate.py.
const db = process.env.EMPTY ? new PGlite() : await freshDb();
if (process.env.EMPTY) await db.exec('create role anon nologin; create role authenticated nologin;');
const server = new PGLiteSocketServer({ db, port, host: '127.0.0.1' });
await server.start();
console.log(`PGlite (${process.env.EMPTY ? 'empty' : 'migrated'}): postgresql://postgres@127.0.0.1:${port}/postgres`);
process.on('SIGINT', async () => { await server.stop(); process.exit(0); });
