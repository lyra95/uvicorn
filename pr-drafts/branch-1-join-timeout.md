# PR draft — `fix/windows-reload-join-timeout`

**Title:** Do not block forever when the reload child never receives the shutdown signal

**Base:** `Kludex/uvicorn:main` ← **Head:** `lyra95/uvicorn:fix/windows-reload-join-timeout`

---

## Summary

On Windows `BaseReload.restart()` stops the child with `os.kill(pid, CTRL_C_EVENT)`
and then calls `self.process.join()` with no timeout. That is a console control
event: it targets a process group, not a single process, and the spawned child is
not a group leader. When the event does not reach the child — no console attached,
or the child not in the targeted group — `join()` blocks forever.

Two consequences:

- The reloader logs `Reloading...` and stops there. Edits silently have no effect
  while the old child keeps serving the previous version of the code.
- `shutdown()` has the same problem, so the child survives as an orphan still bound
  to the port. Windows allows the rebind, so the next run starts with no error and
  two servers end up listening on the same port — requests can land on the stale one.

This change joins with a timeout and kills the child if it is still alive, which is
what `Multiprocess` already does for worker processes (`process.kill()` once the
healthcheck fails). The existing signalling is left untouched, so a child that does
receive the event still shuts down gracefully.

```python
def _join_or_kill(self) -> None:
    self.process.join(GRACEFUL_TIMEOUT)
    if self.process.is_alive():
        logger.warning("Child process [%s] did not exit, killing it.", self.process.pid)
        self.process.kill()
        self.process.join()
```

## Relationship to existing work

**#3081 (`Use IPC for graceful Windows reloads`) is the better fix**, and I would
rather see that land than this. It drops the console event entirely, so shutdown
stays graceful instead of becoming a kill. I checked that branch out and verified it
on Windows 11 / Python 3.13.5 against the repro below — it resolves this case
completely. It currently conflicts with `main` and has not moved since 2026-08-18.
Treat this PR as a stop-gap for as long as #3081 is blocked, and close it if #3081
is moving again.

**#2947 was closed in favour of `--timeout-graceful-shutdown`.** That reasoning
holds for its scenario — a child draining long-lived connections is already shutting
down, and the option bounds the wait. It does not transfer here: the child never
learns that it should shut down at all, because the signal does not reach it, so no
timeout inside the child can fire. The bound has to sit on the parent's `join()`.

## Reproduce

Run any app under `--reload` from a process with no console attached — `pythonw.exe`,
a debugger, or with stdout/stderr redirected — then edit a watched file:

```
WARNING:  WatchFiles detected changes in 'app.py'. Reloading...
<nothing further; the old code keeps serving>
```

Verified on Windows 11, Python 3.13.5, uvicorn 0.54.0.

## Testing

- `pytest tests/supervisors/` — 38 passed, 11 skipped on Windows
- Four new tests: an unresponsive child is killed; a child that exits on its own is
  not; `shutdown()` completes and closes its sockets; `restart()` still starts a
  replacement after a kill
- Manually confirmed against the repro above, before and after the change
