# PR draft — `fix/windows-reload-process-group`

**Title:** Windows reload via `CTRL_BREAK_EVENT` — investigation, do not merge

**Base:** `Kludex/uvicorn:main` ← **Head:** `lyra95/uvicorn:fix/windows-reload-process-group`

> **This branch does not work.** It is written up as a negative result, because
> "why not just send `CTRL_BREAK_EVENT` like `Multiprocess` does?" is the obvious
> question to ask about the Windows reload path, and the answer is not obvious
> until you try it. Do not merge.

---

## What it does

The reloader stops its child on Windows with `os.kill(pid, CTRL_C_EVENT)`, while
`Multiprocess` sends `CTRL_BREAK_EVENT` to a child that converts SIGBREAK into
SIGTERM. This branch aligns the two:

- install the same SIGBREAK → SIGTERM handler in `subprocess_started()`
- send `CTRL_BREAK_EVENT` from the reloader instead of `CTRL_C_EVENT`
- drop the `is_restarting` flag and the `sys.stdout.write(" ")` workaround, which
  existed only to cope with the console-wide Ctrl+C

No tests; see the results below for why they were not worth writing.

## Results on Windows 11 / Python 3.13.5

**No console attached** (`pythonw.exe`; equivalent to running under a debugger or
with the output redirected) — the reloader dies:

```
File "uvicorn/supervisors/basereload.py", line 97, in _terminate_process
  os.kill(self.process.pid, signal.CTRL_BREAK_EVENT)
OSError: [WinError 6] The handle is invalid
```

The child is then orphaned and keeps serving the old code. This is the exact case
the change set out to fix, and it is made worse, not better.

**With a console** — it works, and gracefully:

```
WARNING:  WatchFiles detected changes in 'app.py'. Reloading...
INFO:     Shutting down
INFO:     Finished server process [24512]
INFO:     Started server process [9912]
```

but the event reaches **every process in the console group**, not just the child.
Siblings sharing the terminal are taken down with it; `pytest tests/supervisors/`
dies partway through because the test runner itself is signalled.

## Why it cannot be fixed on this branch

Both failures come from the same root: the child is not a process group leader, so
its pid is not a valid target for `GenerateConsoleCtrlEvent`. Making it one requires
`CREATE_NEW_PROCESS_GROUP` at creation time, and `multiprocessing` hardcodes
`dwCreationFlags` to `0`:

```python
# Lib/multiprocessing/popen_spawn_win32.py
hp, ht, pid, tid = _winapi.CreateProcess(
    python_exe, cmd,
    None, None, False, 0, env, None,          # <- dwCreationFlags
    STARTUPINFO(dwFlags=STARTF_FORCEOFFFEEDBACK))
```

There is no seam to pass the flag through, so this direction is closed without
replacing the spawn machinery entirely.

## Conclusion

Console control events are the wrong mechanism for stopping the reload child on
Windows. **#3081 (`Use IPC for graceful Windows reloads`) takes the right approach** —
a shared `multiprocessing.Event` instead of a console signal. I verified that branch
against the windowless repro above and it resolves the case cleanly and gracefully.
