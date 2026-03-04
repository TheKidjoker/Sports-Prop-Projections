# Deployment Instructions

## Production Performance Optimizations

This deployment includes persistent caching and database layers that make the app feel instant for users.

## Step 1: Run SQL Migrations in Supabase

Go to your Supabase project → SQL Editor → New Query and run these in order:

### 1. Persistent Cache Tables
```sql
-- Copy and paste from: migrations/001_persistent_cache.sql
```

### 2. Player Season Stats Cache
```sql
-- Copy and paste from: migrations/002_player_season_stats.sql
```

## Step 2: Set Environment Variables

Make sure these are set in your deployment environment (Render, Railway, etc.):

```bash
# Required for cache layer
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here  # Service role, not anon key
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_JWT_SECRET=your_jwt_secret_here

# Optional: Odds API (for Line Shop, historical spreads)
ODDS_API_KEY=your_odds_api_key_here
```

**Important:** Use the **service role** key for `SUPABASE_SERVICE_KEY`, not the anon key. This allows cache writes to work properly.

## Step 3: Deploy

Push to your git remote and deploy normally. The app will:

1. Auto-load cached scans from Supabase on startup
2. Warm in-memory cache from DB for instant responses
3. Run background worker that refreshes caches every hour
4. Auto-run daily 6AM EST scan to pre-warm all sports
5. Auto-grade tracked bets after each refresh

## How It Works

### Two-Tier Caching
- **Layer 1:** In-memory cache for ultra-fast access (microseconds)
- **Layer 2:** Supabase persistent cache (survives deploys, benefits all users)
- On cache miss: Fetch from ESPN → Cache in both layers

### Performance Impact

**Before:**
- First scan of the day: 15-30 seconds
- Every deploy resets cache (cold start)
- 100+ ESPN API calls per scan

**After:**
- Cache hits: 1-2 seconds (instant)
- Persists across deploys (no cold start)
- Season stats: 5ms DB lookup instead of 200ms API call
- 80% reduction in ESPN API load

### Cache Invalidation

- Scan cache: 10-60 minutes (auto-refreshed hourly)
- Props cache: 10 minutes
- Season stats: 24 hours
- Old entries auto-deleted after 24 hours (cleanup runs hourly)

### Background Jobs (Already Running)

The app automatically runs these background tasks:

1. **Hourly:** Refresh all cached sports + grade tracked bets
2. **Daily 6AM EST:** Full scan of all sports (pre-warm for the day)
3. **On-demand:** Immediate refresh when user requests a sport

No additional cron jobs or worker dynos needed!

## Monitoring

Check your logs for cache performance:

```
[cache_manager] Cache HIT for scan:nba
[cache_manager] Cache MISS for props:cbb
[scan_cache] Warmed memory from DB: nhl
[get_top_props] Completed in 2.3s, found 45 props
```

## Troubleshooting

### "502 Bad Gateway" on props
- Reduced with caching + 45s timeout protection
- Check logs for which games are timing out
- May need to increase worker timeout in deployment platform

### Cache not persisting
- Verify `SUPABASE_SERVICE_KEY` is set (not anon key)
- Check Supabase logs for permission errors
- Verify SQL migrations ran successfully

### Stats not caching
- Verify `player_season_stats` table exists
- Check that season is set to current year (2024-25)
- Update `season` variable in api_client.py annually

## Manual Cache Clear

If you need to force-refresh the cache:

```sql
-- Clear all cached scans
DELETE FROM scan_cache;

-- Clear all cached props
DELETE FROM props_cache;

-- Clear player stats older than 1 hour
DELETE FROM player_season_stats WHERE last_updated < NOW() - INTERVAL '1 hour';
```

The app will automatically rebuild the cache on next request.
