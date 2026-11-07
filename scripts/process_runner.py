"""Bound subprocess duration, log size and cleanup for local build commands."""

import hashlib
import os
import subprocess
import time


def stop_tree(process):
    """Terminate only the child PID and its descendants after failure/timeout."""
    if process.poll() is not None:
        return "already_exited"
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
            cleanup = "tree_terminated" if result.returncode == 0 else "tree_cleanup_failed"
        else:
            process.kill()
            cleanup = "child_terminated"
    except (OSError, subprocess.SubprocessError):
        cleanup = "tree_cleanup_failed"
    try:
        if cleanup == "tree_cleanup_failed":
            process.kill()
        process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
            process.wait(timeout=5)
            cleanup = "child_terminated_tree_unconfirmed"
        except (OSError, subprocess.SubprocessError):
            cleanup = "cleanup_unconfirmed"
    return cleanup


def run_command(step, log, env, deadline, *, root, log_limit, terminate=stop_tree):
    started = time.monotonic()
    result = dict(status="failed", exit_code=None, cleanup="not_needed")
    process = None
    try:
        with log.open("wb") as output:
            process = subprocess.Popen(
                step["argv"],
                cwd=root / step["cwd"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            end = min(deadline, started + step["timeout_seconds"])
            while process.poll() is None:
                if time.monotonic() >= end:
                    result.update(status="timed_out", reason="command_or_total_deadline")
                    result["cleanup"] = terminate(process)
                    break
                if log.stat().st_size > log_limit:
                    result.update(reason="log_limit_exceeded")
                    result["cleanup"] = terminate(process)
                    break
                time.sleep(0.1)
            else:
                result["status"] = "passed" if process.returncode == 0 else "failed"
            result["exit_code"] = process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        result.update(status="unavailable", reason=type(exc).__name__)
        if process is not None:
            result["cleanup"] = terminate(process)
    except KeyboardInterrupt:
        result.update(status="cancelled", reason="interrupted")
        if process is not None:
            result["cleanup"] = terminate(process)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if log.exists():
        result["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
        result["log_bytes"] = log.stat().st_size
        if result["log_bytes"] > log_limit:
            result.update(status="failed", reason="log_limit_exceeded")
    return result


