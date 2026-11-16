-- Execute no SQL Editor do seu projeto Supabase.
-- Segurança: leitores autenticados, escrita de notícias APENAS com service_role.
create table if not exists public.radar_articles (
  id text primary key,
  entity_id text not null,
  title text not null,
  url text not null,
  category text not null,
  source text not null,
  status text not null default 'official_domain',
  published_at timestamptz,
  priority integer not null default 3,
  first_seen timestamptz not null default now()
);
create index if not exists radar_articles_seen_idx on public.radar_articles(first_seen desc);
create table if not exists public.radar_sources (
  id text primary key,
  checked_at timestamptz,
  ok boolean not null default false,
  error text,
  seen_links integer not null default 0,
  relevant_links integer not null default 0
);
create table if not exists public.radar_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  prefs jsonb not null default '{}'::jsonb
);
create table if not exists public.radar_marks (
  user_id uuid not null references auth.users(id) on delete cascade,
  article_id text not null references public.radar_articles(id) on delete cascade,
  saved boolean not null default false,
  hidden boolean not null default false,
  primary key(user_id,article_id)
);
create index if not exists radar_marks_user_idx on public.radar_marks(user_id);
alter table public.radar_articles enable row level security;
alter table public.radar_sources enable row level security;
alter table public.radar_settings enable row level security;
alter table public.radar_marks enable row level security;
revoke all on public.radar_articles,public.radar_sources,public.radar_settings,public.radar_marks from anon,authenticated;
grant select on public.radar_articles,public.radar_sources to authenticated;
grant select,insert,update on public.radar_settings,public.radar_marks to authenticated;
drop policy if exists "Read official candidates" on public.radar_articles;
create policy "Read official candidates" on public.radar_articles for select to authenticated using (true);
drop policy if exists "Read source diagnostics" on public.radar_sources;
create policy "Read source diagnostics" on public.radar_sources for select to authenticated using (true);
drop policy if exists "Read personal settings" on public.radar_settings;
create policy "Read personal settings" on public.radar_settings for select to authenticated using ((select auth.uid())=user_id);
drop policy if exists "Insert personal settings" on public.radar_settings;
create policy "Insert personal settings" on public.radar_settings for insert to authenticated with check ((select auth.uid())=user_id);
drop policy if exists "Update personal settings" on public.radar_settings;
create policy "Update personal settings" on public.radar_settings for update to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
drop policy if exists "Read personal marks" on public.radar_marks;
create policy "Read personal marks" on public.radar_marks for select to authenticated using ((select auth.uid())=user_id);
drop policy if exists "Insert personal marks" on public.radar_marks;
create policy "Insert personal marks" on public.radar_marks for insert to authenticated with check ((select auth.uid())=user_id);
drop policy if exists "Update personal marks" on public.radar_marks;
create policy "Update personal marks" on public.radar_marks for update to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
