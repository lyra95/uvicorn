# Comment draft — on upstream PR #3081

**Where:** https://github.com/Kludex/uvicorn/pull/3081 (`Use IPC for graceful Windows reloads`)

**Why this instead of a new PR:** #3081 already fixes this properly — it drops the
console control event in favour of a shared `multiprocessing.Event`, so shutdown
stays graceful rather than becoming a kill. It is approved by review bots, has
maintainer comments, and has not moved since 2026-08-18; it currently conflicts with
`main`. Fresh Windows verification plus an offer to rebase is worth more than a
competing stop-gap PR.

---

I verified this branch on Windows 11 (Python 3.13.5) against the windowless case,
and it fixes it completely.

**Repro on `main`** — a reloader with no console attached (launched with
`pythonw.exe`, which is also how it behaves under a debugger or with the output
redirected):

```
WARNING:  WatchFiles detected changes in 'app.py'. Reloading...
<nothing further>
```

`restart()` logs `Reloading...`, then blocks in `self.process.join()` forever. The
old child keeps serving the previous code, so an edit silently has no effect. On
shutdown the child survives as an orphan still bound to the port, and because
Windows allows the rebind, the next run starts without an error — two servers end up
listening on the same port and requests can land on the stale one.

The cause is that `os.kill(pid, CTRL_C_EVENT)` is a console control event: it targets
a process group, and the spawned child is not a group leader. I also tried swapping
it for `CTRL_BREAK_EVENT` to match `Multiprocess`, which does not work either:

- with no console: `OSError: [WinError 6] The handle is invalid`, which kills the
  reloader outright and orphans the child
- with a console: the event reaches every process in the console group, taking down
  siblings sharing the terminal — `pytest tests/supervisors/` dies partway through
  because the test runner itself is signalled

Making the child a group leader would need `CREATE_NEW_PROCESS_GROUP`, and
`multiprocessing` hardcodes `dwCreationFlags` to `0` in
`popen_spawn_win32.Popen.__init__`, so there is no seam for it. The IPC event in this
PR is the right call.

**On this branch**, same repro, no console:

```
WARNING:  WatchFiles detected changes in 'app.py'. Reloading...
INFO:     Shutting down
INFO:     Finished server process [21260]
INFO:     Started server process [25052]
```

The edit is picked up, and the child shuts down gracefully instead of being killed.

The branch currently conflicts with `main`. Happy to rebase it and re-run the Windows
verification if that would help it land.
