"""
Gunicorn configuration for Sports Prop Projections
Optimized for player props API endpoints with longer processing times
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"  # Use "gevent" for async if needed
worker_connections = 1000
max_requests = 500  # Restart workers after N requests to prevent memory leaks
max_requests_jitter = 50
timeout = 120  # 2 minutes — props are cache-only now so requests should be fast
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "sports_prop_projections"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = "/path/to/key.pem"
# certfile = "/path/to/cert.pem"

# Preload app for better memory usage
preload_app = True

# Restart workers gracefully on code change
reload = False  # Set to True for development


def on_starting(server):
    """Called just before the master process is initialized."""
    print(f"[gunicorn] Starting with {workers} workers, {timeout}s timeout")


def worker_int(worker):
    """Called when a worker receives a SIGINT or SIGQUIT signal."""
    print(f"[gunicorn] Worker {worker.pid} received INT/QUIT signal")


def worker_abort(worker):
    """Called when a worker times out."""
    print(f"[gunicorn] Worker {worker.pid} ABORTED (timeout > {timeout}s)")
