"""
Run log: rolling JSON file capturing what happened on each run.

A single file `runs.json` lives in the repo. Each run appends one entry.
We keep the last 60 entries and auto-trim older ones.

Public function:
    write_run_log(log_data: dict, path='runs.json', keep_last=60)
"""

import json
import os
from datetime import datetime, timezone


def append_run_log(log_data, path="runs.json", keep_last=60):
    """
    Append a run entry to the rolling log file. Trims old entries.

    Args:
      log_data: dict to append (will get a 'logged_at' timestamp added if missing)
      path: where to write
      keep_last: maximum number of historical entries to retain
    """
    if "logged_at" not in log_data:
        log_data["logged_at"] = datetime.now(timezone.utc).isoformat()

    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "runs" in data:
                    existing = data["runs"]
                elif isinstance(data, list):
                    existing = data
        except Exception as e:
            print(f"WARNING: could not parse existing runs.json ({e}); starting fresh.")

    existing.append(log_data)

    # Trim to keep_last (most recent)
    if len(existing) > keep_last:
        existing = existing[-keep_last:]

    payload = {
        "_format_version": 1,
        "_keep_last": keep_last,
        "runs": existing,
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Run log written: {len(existing)} entries in {path}")
    except Exception as e:
        print(f"WARNING: failed to write run log: {e}")


def estimate_cost(input_tokens, output_tokens, model="claude-sonnet-4-6"):
    """
    Rough cost estimate. Sonnet 4.x input ~$3/M, output ~$15/M.
    Web search tool ~$10 per 1000 searches.
    Returns USD float.
    """
    pricing = {
        "input_per_mtok": 3.0,
        "output_per_mtok": 15.0,
    }
    cost = (input_tokens / 1_000_000) * pricing["input_per_mtok"]
    cost += (output_tokens / 1_000_000) * pricing["output_per_mtok"]
    return round(cost, 4)
