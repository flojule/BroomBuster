# User Database — Options and Rationale

BroomBuster needs to persist a small amount of per-user data: saved cars (name, color, last-known location), and a preferred region. This is a single table with one row per user, updated on every "save" action.

---

## Current choice: Supabase PostgreSQL

Supabase provides a managed PostgreSQL database alongside its Auth service. Since Supabase is already used for authentication, using its database avoids a second external dependency.

**Schema:**

```sql
CREATE TABLE user_prefs (
    user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    home_lat         DOUBLE PRECISION,
    home_lon         DOUBLE PRECISION,
    preferred_region TEXT DEFAULT 'bay_area',
    notify_email     BOOLEAN DEFAULT FALSE,
    cars             JSONB DEFAULT '[]',
    updated_at       TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE user_prefs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own row" ON user_prefs
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
```

The `cars` column stores a JSON array of car objects. Each car has a name, color, last lat/lon, and preferred region. No location history is stored.

**Pros:**
- Already integrated — one less service to set up and manage.
- Row-level security ensures users cannot read or modify each other's data.
- Full SQL available if the schema needs to grow.
- Free tier: 500 MB database, unlimited API calls, no row limits.

**Cons:**
- Supabase free projects pause after 1 week of inactivity (the database becomes unavailable until manually unpaused via the dashboard). This is the main risk for a prototype with intermittent use.
- Vendor lock-in to Supabase's hosting. Migrating requires an export and re-import.

**Verdict**: the right choice for this prototype. The pause-on-inactivity behavior is annoying but manageable.

---

## Alternative: Firebase Firestore

Google's NoSQL document database. A document per user, stored in a `users/{uid}` path.

**Pros:**
- Generous free tier (1 GB storage, 50k reads/day, 20k writes/day).
- Real-time sync (useful if multiple devices show the same car simultaneously).
- Does not pause on inactivity.
- Firebase Auth is a viable alternative to Supabase Auth.

**Cons:**
- Requires replacing Supabase Auth with Firebase Auth — both the frontend (Supabase JS SDK) and backend (JWT verification) would need rewriting.
- NoSQL: no relational integrity, no row-level security in the same sense (Firestore security rules are more verbose).
- Google ecosystem; a second vendor relationship.

**Verdict**: not worth the migration cost for this prototype. Could be reconsidered if Supabase pausing becomes a persistent problem.

---

## Alternative: Neon (serverless Postgres)

A serverless PostgreSQL provider with a free tier.

**Pros:**
- Standard PostgreSQL; schema is identical to the current Supabase setup.
- Does not pause on inactivity (free tier has compute auto-suspend but resumes on first query, typically in under 1 s).
- Easy to migrate to from Supabase (same SQL, `psycopg2` / `asyncpg` compatible).

**Cons:**
- No built-in auth; would still need Supabase Auth (or an alternative) to issue JWTs.
- One more service to manage.
- Free tier: 0.5 GB storage, 191 compute-hours/month.

**Verdict**: a reasonable fallback if Supabase's database pause behavior becomes intolerable, but requires keeping Supabase (or adding another service) for auth.

---

## Alternative: localStorage only (no server-side persistence)

Store all car data in the browser's `localStorage`. Nothing is sent to a server.

**Pros:**
- Zero setup, zero cost, no dependency on any database.
- No privacy concerns around storing location data.
- Works offline.

**Cons:**
- Data is tied to a single browser/device. Switching phones or clearing browser data loses everything.
- Cannot share state between a phone and a desktop.
- No recovery path if localStorage is cleared.

**Verdict**: acceptable for a single-user, single-device prototype, but defeats the purpose of having user accounts. Not recommended once accounts are in use.
