# PostgreSQL production proof

On 22 July 2026, Restock was exercised against a disposable local PostgreSQL
instance using the production database path.

- Alembic upgraded a blank database through revision `20260719_03`.
- `RestockRepository` wrote and read a real user row through psycopg.
- The API started with `RESTOCK_ENV=production`, PostgreSQL, demo mode disabled,
  and a high-entropy temporary session secret.
- `/health`, `/ready`, `/capabilities`, `/metrics`, and the PWA returned success.
- Protected endpoints returned `401` without a signed session.
- `pg_dump` created a custom-format backup without placing the database password
  in process arguments.
- `pg_restore` restored that backup into a fresh database.
- The restored database contained Alembic revision `20260719_03` and the expected
  user row.

The drill exposed and fixed two failure modes: incomplete dump files are now removed
after backup failure, and restore rejects missing or empty inputs. Operators may use
`PG_DUMP_BIN` and `PG_RESTORE_BIN` to select client binaries compatible with the
managed PostgreSQL server version.

This proves the application and recovery path locally. A final restore drill against
the chosen managed service remains an external launch gate.
