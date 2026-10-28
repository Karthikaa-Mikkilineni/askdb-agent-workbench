// Restricted-environment fallback. Single-connection PostgreSQL WASM, not native PG.
import {PGlite} from '@electric-sql/pglite';
import {PGLiteSocketServer} from '@electric-sql/pglite-socket';
import {spawn} from 'node:child_process';
const db=await PGlite.create();
const version=await db.query('SELECT version()');
console.log('Mode: PGlite single underlying connection, multiplexed sequential clients; '+version.rows[0].version);
const setup=spawn(process.env.ASKDB_PYTHON||'python3',['-c',
 'import sys;sys.path.insert(0,"backend");from agentic.store import DDL;print(DDL)'],{cwd:new URL('..',import.meta.url)});
let ddl='';setup.stdout.on('data',chunk=>ddl+=chunk);
await new Promise(resolve=>setup.on('exit',resolve));
await db.exec(ddl);
await db.exec("CREATE ROLE askdb_reader LOGIN PASSWORD 'local-test-only'; GRANT USAGE ON SCHEMA public TO askdb_reader; GRANT SELECT ON ALL TABLES IN SCHEMA public TO askdb_reader;");
const server=new PGLiteSocketServer({db,host:'127.0.0.1',port:55439,maxConnections:16});
await server.start();
const child=spawn(process.env.ASKDB_PYTHON||'python3',['-m','pytest','agent_tests/test_postgres.py','-q'],{
 cwd:new URL('..',import.meta.url),stdio:'inherit',env:{...process.env,
 ASKDB_TEST_DSN:'postgresql://askdb_reader:local-test-only@127.0.0.1:55439/postgres?sslmode=disable'}});
const code=await new Promise(resolve=>child.on('exit',resolve));
await server.stop();await db.close();process.exit(code??1);
