# Server setup log

Every system-level change to this machine, in order, with a reason and how to
undo it. Append as you work through `docs/INSTALL.md`; do not rewrite history
here — a wrong entry that was later fixed is more useful than a tidy one.

Format:

```
## YYYY-MM-DD HH:MM — what changed

Why: one line.
Command: the exact thing that ran.
Undo: the exact thing that reverses it.
Notes: RAM delta, surprises, anything that did not go as expected.
```

---

## Template entry (delete once there are real ones)

## 2026-01-01 00:00 — Example: enabled UFW

Why: firewall the LAN-facing ports; only the six services should be reachable.
Command: `sudo ufw allow 22/tcp … && sudo ufw enable`
Undo: `sudo ufw disable`
Notes: allow rules added before enabling so the SSH session survived.
Verified with `sudo ufw status verbose` and a fresh SSH login. RAM: no change.

---

## Running RAM total

Update after each service. Ceiling is ~4.5GB; the box has 5.7GB and the OS
plus an SSH session need the rest.

| Service | Expected | Measured | Running total |
|---|---|---|---|
| (baseline, no services) | — | | |
| uptime-kuma | ~150MB | | |
| portainer | ~100MB | | |
| nginx | ~20MB | | |
| n8n | ~250-400MB | | |
| ollama (idle, unloaded) | ~50MB | | |
| ollama (llama3.2 loaded) | ~2.5-3GB | | |
| telegram bridge | ~60MB | | |

The two Ollama rows are the whole reason for `OLLAMA_KEEP_ALIVE=5m`. Record
the third measurement — RAM six minutes after the last request — to prove the
model actually unloads rather than just being configured to.
