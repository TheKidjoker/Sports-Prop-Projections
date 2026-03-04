# Production Deployment Guide

## Gunicorn Configuration

Use the included `gunicorn.conf.py` for production deployments:

```bash
gunicorn -c gunicorn.conf.py app:app
```

### Key Settings
- **Timeout**: 90 seconds (for slow player props endpoints)
- **Workers**: CPU_COUNT * 2 + 1 (auto-scaled)
- **Worker Class**: sync (change to gevent for async)
- **Max Requests**: 1000 (workers restart to prevent memory leaks)

### Environment Variables for Production

```bash
# Scanner performance tuning (REDUCE THESE FOR LOW MEMORY)
SCAN_GAME_WORKERS=2    # Concurrent game scans (default: 4)
SCAN_API_WORKERS=2     # API threads per request (default: 4)
GUNICORN_WORKERS=2     # Gunicorn workers (default: auto)
```

## Memory Optimization

### For Render.com Free Tier (512MB RAM)
```bash
export SCAN_GAME_WORKERS=2
export SCAN_API_WORKERS=2
export GUNICORN_WORKERS=2
```

### Worker Timeout Errors
If you see `[CRITICAL] WORKER TIMEOUT`, increase timeout in gunicorn.conf.py or reduce SCAN_API_WORKERS.

### Out of Memory Errors
If workers are killed with SIGKILL, reduce SCAN_API_WORKERS=1 and GUNICORN_WORKERS=2.
