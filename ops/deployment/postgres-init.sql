-- Runs once, on first initialisation of an empty Postgres data directory
-- (mounted into /docker-entrypoint-initdb.d by docker-compose.yml).
-- The app database (POSTGRES_DB, default `ieqops`) is created by the image;
-- here we add LangFuse's own database so observability data stays isolated
-- from incident/checkpoint data.
CREATE DATABASE langfuse;
