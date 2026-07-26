-- Non-superuser application role so Postgres RLS actually enforces tenant
-- isolation (a superuser / BYPASSRLS role silently ignores every policy).
--
-- Run once per database as a superuser (or a role with CREATEROLE), passing the
-- password as a psql variable, then point DATABASE_URL at this role:
--
--   psql "$ADMIN_DATABASE_URL" -v app_password="'<secret>'" -f create_app_role.sql
--   DATABASE_URL=postgresql+asyncpg://llamatrade_app:<secret>@host:5432/llamatrade
--
-- Migrations still run as the owner/migrator role; the app services connect as
-- llamatrade_app, which the startup guard (llamatrade_db.rls.assert_rls_capable)
-- verifies is not superuser/BYPASSRLS.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llamatrade_app') THEN
    CREATE ROLE llamatrade_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

ALTER ROLE llamatrade_app PASSWORD :app_password;

GRANT CONNECT ON DATABASE llamatrade TO llamatrade_app;
GRANT USAGE ON SCHEMA public TO llamatrade_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO llamatrade_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO llamatrade_app;

-- Future tables/sequences created by the migrator inherit the same grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO llamatrade_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO llamatrade_app;
