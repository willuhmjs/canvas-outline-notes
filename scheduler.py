#!/usr/bin/env python3
"""Scheduler for canvas-sync and canvas-outline-notes.

Runs both scripts on their respective schedules in a single long-running process.
"""
import os
import sys
import time
import logging
from datetime import datetime
from threading import Thread, Event
import importlib.util

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load scripts as modules
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

stop_event = Event()

def run_task(name, func, interval_minutes):
    """Run a task on a fixed interval."""
    next_run = time.time()
    while not stop_event.is_set():
        if time.time() >= next_run:
            logger.info(f"Running {name}...")
            try:
                func()
                logger.info(f"{name} completed successfully")
            except Exception as e:
                logger.error(f"{name} failed: {e}", exc_info=True)
            next_run = time.time() + (interval_minutes * 60)

        # Sleep in small increments so we can check stop_event
        stop_event.wait(min(60, max(1, next_run - time.time())))

def main():
    logger.info("Starting canvas scheduler...")

    # Load the scripts
    sync_module = load_module("canvas_sync", "/scripts/sync.py")
    notes_module = load_module("canvas_notes", "/scripts/notes.py")

    # Get schedule from environment or use defaults
    sync_interval = int(os.environ.get("SYNC_INTERVAL_MINUTES", "15"))
    notes_interval = int(os.environ.get("NOTES_INTERVAL_MINUTES", "60"))

    logger.info(f"Sync interval: {sync_interval} minutes")
    logger.info(f"Notes interval: {notes_interval} minutes")

    # Start both tasks in separate threads
    sync_thread = Thread(
        target=run_task,
        args=("canvas-sync", sync_module.main, sync_interval),
        daemon=True
    )
    notes_thread = Thread(
        target=run_task,
        args=("canvas-outline-notes", notes_module.main, notes_interval),
        daemon=True
    )

    sync_thread.start()
    notes_thread.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        stop_event.set()
        sync_thread.join(timeout=5)
        notes_thread.join(timeout=5)

if __name__ == "__main__":
    main()
