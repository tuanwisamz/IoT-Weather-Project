-- 0004_rls.sql: weather data is public and read-only; writes come only from the jobs (architecture §7.9).
-- The jobs connect as `postgres` through the session pooler, which bypasses RLS.

do $$ declare t text; begin
  foreach t in array array['locations','sources','forecast_models','ingestion_runs','observations',
                           'forecasts','forecasts_daily','satellite_features','ml_models','predictions'] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy %I on %I for select to anon, authenticated using (true)', t || '_read', t);
  end loop;
end $$;
alter table raw_responses enable row level security;           -- no policy = no anon access

-- Explicit grants rather than relying on Supabase's default privileges (they have changed between
-- releases). Readers get SELECT and EXECUTE only; RLS is the second line of defence.
grant usage on schema public to anon, authenticated;
revoke insert, update, delete, truncate on all tables in schema public from anon, authenticated;
grant select on all tables in schema public to anon, authenticated;
revoke select on raw_responses from anon, authenticated;
grant execute on all functions in schema public to anon, authenticated;

-- Read-only role for FastAPI (least privilege). Not needed until FastAPI is in scope (P1).
-- Set the password in the Supabase dashboard rather than committing it.
-- create role api_reader login password '<set-in-dashboard>' noinherit;
-- grant usage on schema public to api_reader;
-- grant select on all tables in schema public to api_reader;
-- grant execute on all functions in schema public to api_reader;
