# Database migrations

Schema is managed by Alembic (`backend/alembic/`). The ORM models in
`backend/app/models/` are the source of truth; migrations must keep
`alembic upgrade head` equivalent to `Base.metadata.create_all`.

## History note: the reconstructed baseline

The baseline migration `77ed50a58fed_initial_schema.py` was originally an
empty stub (`upgrade()`/`downgrade()` were `pass`), so `alembic upgrade head`
on a fresh database created only the tables added by later migrations — the
core tables (users, accounts, transactions, ...) existed only where
`Base.metadata.create_all` had been run (seed.py, test fixtures).

On 2026-07-07 the baseline was reconstructed from the models to contain
exactly the schema that existed at baseline time (everything in the models
except what later migrations add). Alembic never re-executes a revision a
database is already at or past, so this rewrite only affects databases that
have not yet run the baseline — i.e. fresh ones.

A drift-fix migration `e7a9c2d41f88_add_user_id_to_merchants.py` was added at
the same time: the `Merchant` model has a non-nullable `user_id` FK that no
migration ever created (`c8758d8d5e4b` created `merchants` without it). The
migration is guarded by runtime inspection so it is a no-op on databases that
already have the column (e.g. schemas that came from `create_all`).

## Which path applies to your database?

Check whether an `alembic_version` table exists and what it contains:

```sql
SELECT version_num FROM alembic_version;
```

### 1. Fresh / empty database

```bash
cd backend
alembic upgrade head
```

This now creates the complete schema. (The docker `api` container already
does this on boot.)

### 2. Existing database WITH an alembic_version row

This is the normal case for existing deployments — the api container has been
running `alembic upgrade head` on boot, so `alembic_version` is populated
(e.g. `3f9e1a7c2b4d` before this change). Just upgrade:

```bash
alembic upgrade head
```

The rewritten baseline will NOT re-run (your version is already past it); the
only new revision is the guarded merchants fix, which skips itself if
`merchants.user_id` already exists.

### 3. Existing database created via `create_all`, NO alembic_version table

The schema already matches the models, so tell Alembic it is at head without
running anything:

```bash
alembic stamp head
```

After stamping, future migrations apply normally with `alembic upgrade head`.
Do NOT run `upgrade head` without stamping first — the baseline would fail on
the already-existing tables.

## Verified equivalence

`alembic upgrade head` on a fresh Postgres 16 was compared against
`Base.metadata.create_all` (reflected via SQLAlchemy inspector: tables,
columns, types, nullability, defaults, PKs, FKs, unique constraints, indexes).
The schemas are identical except one known, pre-existing difference:

- `symbol_classifications`: migration `a1b2c3d4e5f6` creates a **unique**
  index `ix_symbol_classifications_user_symbol (user_id, symbol)` that the
  model does not declare. The index is intentional (the classifier upserts on
  first sighting), so migrated databases are stricter than `create_all` ones.
  If you add the index to the model, delete this bullet.

## Caveats

- The migration chain is Postgres-only from `b2c3d4e5f6a7` (pending_orders)
  onward: its `op.create_unique_constraint` uses ALTER, which SQLite does not
  support. SQLite databases (tests, local hacking) should use
  `Base.metadata.create_all`, as the test fixtures and seed.py already do.
- `e7a9c2d41f88` adds `merchants.user_id` as NOT NULL. On a database that has
  merchant rows but lacks the column (only possible if the schema came purely
  from the old migration chain), the migration fails loudly; backfill
  `user_id` manually in that case.
