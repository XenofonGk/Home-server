# home-server

Configuration for a personal home server running on an old Ubuntu 20.04
laptop. Monitoring, a handful of self-hosted services, a local LLM, and
alerting to my phone over Telegram.

This repository is the server. Everything that runs on the machine is
defined here — compose files, systemd units, the bridge daemon, the backup
scripts — so the box can be rebuilt from a clone plus a USB stick rather
than from memory.

## Why it looks like this

The machine is a laptop with 5.7GB of RAM on home wifi. Two constraints
shaped nearly every decision:

**Memory is the binding constraint.** Every container has a `mem_limit`.
Ollama unloads its model after five idle minutes instead of holding ~2.5GB
resident around the clock. There is no web chat UI for the model — the
Telegram bot does that job for about 60MB instead of Open WebUI's several
hundred. The running total is tracked in `server-setup-log.md`, and the
ceiling is ~4.5GB so the OS and an SSH session always have room.

**This machine has broken before.** A previous attempt at setting it up
pinned a static IP in NetworkManager and took the laptop off the network
entirely — on a headless box, that means walking over with a monitor. So
nothing here touches network configuration. The IP is whatever DHCP hands
out. UFW is the only networking change, and it is applied allow-rules-first
so an SSH session can't be cut off mid-command.

The same instinct explains the rest: services get claimed immediately rather
than sitting unauthenticated on the LAN, the USB backup mount uses `nofail`
so a missing stick can never make the machine unbootable, and the backup is
verified by actually restoring from it.

## What runs on it

| Service | Port | What it does |
|---|---|---|
| Uptime Kuma | 3001 | Monitors everything else, alerts to Telegram |
| Portainer | 9000 | Docker management UI |
| Nginx | 80 | Static landing page listing the services |
| n8n | 5678 | Automation workflows, behind basic auth |
| Ollama | 127.0.0.1:11434 | Local LLM (llama3.2), loopback only |
| Telegram bridge | — | Relays Telegram messages to Ollama |

Everything is LAN-only. Nothing is exposed to the internet. Remote access is
via Tailscale, which adds its own interface and does not touch the wifi
config.

## Architecture

```
  phone (Telegram)
        |
        |  alerts          chat
        |  <------+        <------>
        v         |                 
  Telegram Bot API                  
        ^         ^                 
        |         |                 
   Uptime Kuma    |   telegram-ollama-bridge (systemd, user foe)
   (container)    +---- long-polls getUpdates -----+
        |                                          |
        | monitors                                 v
        |                                   Ollama (127.0.0.1:11434)
        v                                   llama3.2, unloads after 5m idle
  nginx / portainer / n8n
  (containers, mem_limit each)

  USB stick -> restic repo, nightly, verified by test restore
```

One Telegram bot serves both purposes. Uptime Kuma only *sends* through the
Bot API; the bridge is the only process that *polls*. That combination is
fine, but two pollers on one token would steal each other's updates — so if
you extend this, send freely and do not add a second consumer of
`getUpdates`.

### The bridge

`bridge/` is a small Python daemon, standard library only. No pip install,
no virtualenv to keep alive, nothing to break when unattended-upgrades runs.

It is split so the interesting parts are testable without a network:

- `config.py` — environment parsing and the allowlist check
- `text.py` — splitting replies to Telegram's 4096-character limit
- `retry.py` — exponential backoff, with the sleep function injected
- `clients.py` — the only two things that touch the network
- `main.py` — the poll loop and `handle_update`, which takes its clients as
  arguments so tests can pass fakes

The allowlist is the security-critical piece. A bot token is one URL away
from anyone who obtains it, and Ollama has no authentication of its own, so
an unrestricted bridge would hand free inference on my hardware to whoever
found it. The daemon **refuses to start** if `TELEGRAM_ALLOWED_CHAT_IDS` is
empty rather than defaulting to allow-all, and messages from other chat IDs
are logged and dropped without a reply — replying would confirm the bot is
live to whoever is probing.

## Setup from a fresh clone

Assumes Ubuntu 20.04+, a user named `foe`, and a USB stick for backups.
Python 3.8 or newer (20.04 ships 3.8; the code targets it).

Work through `docs/INSTALL.md` — it is the ordered checklist, with the
verification step for each phase. The short version:

```bash
git clone <this repo> /home/foe/server
cd /home/foe/server

cp bridge/.env.example bridge/.env       # fill in, then chmod 600
cp services/n8n/.env.example services/n8n/.env
```

### Credentials you need

- **Telegram bot token** — message [@BotFather](https://t.me/botfather),
  send `/newbot`, follow the prompts. It hands you the token.
- **Your Telegram chat ID** — message `@userinfobot`; it replies with your
  numeric ID. This goes in `TELEGRAM_ALLOWED_CHAT_IDS`.
- **n8n basic auth** — a username and password you choose. n8n can execute
  shell commands, so pick a real password.
- **restic repository password** — generate one, store it in
  `/home/foe/server/.restic-password` (chmod 600), **and keep a copy
  somewhere off this machine**. A backup you cannot decrypt is not a backup.
- **Claude / Anthropic API key** — not needed. The model here is local.

None of these are in the repository and none are logged.

### Scheduled jobs

Both run as `foe`, never root (`crontab -e`):

```cron
# Nightly backup to the USB stick at 03:00
0 3 * * * /home/foe/server/scripts/backup.sh >> /home/foe/server/logs/backup.log 2>&1

# Daily health report to Telegram at 08:00
0 8 * * * /home/foe/server/scripts/health-report.sh >> /home/foe/server/logs/health.log 2>&1
```

## Running the tests

No dependencies, no test runner to install:

```bash
cd /home/foe/server
python3 -m unittest discover -s bridge/tests -t .
```

37 tests covering message splitting, backoff timing, config parsing, and the
full `handle_update` path against fake Telegram and Ollama clients — including
that a non-allowlisted sender gets no reply and never reaches the model.

To exercise the bridge by hand without cron or systemd:

```bash
set -a; source bridge/.env; set +a
python3 -m bridge.main
```

It logs to stdout as well as its log file, so you can watch a message arrive.

## Backups

`scripts/backup.sh` runs restic nightly to the USB stick at `/mnt/backup`,
covering Docker volumes, this repository, and the setup log. It:

- refuses to run if `/mnt/backup` isn't mounted, rather than quietly writing
  to the root filesystem and looking like it worked
- stops Uptime Kuma and n8n for the few seconds it takes to copy their data
- prunes on a 7 daily / 4 weekly / 6 monthly policy
- runs `restic check` on a 5% data subset each night
- alerts over Telegram on any failure, and touches a stamp file on success
  so `health-report.sh` notices if backups silently stop

`scripts/restore-verify.sh` restores one volume into a scratch directory and
diffs it against the live copy. Run it after the first backup. `RESTORE.md`
documents rebuilding the whole machine.

## What this deliberately does not do

- **No public exposure.** No Cloudflare tunnel, no port forwarding. Remote
  access is Tailscale only.
- **No static IP.** DHCP, deliberately. See above.
- **No web UI for the model.** Open WebUI was dropped to save the RAM.
- **No conversation memory in the bridge.** Each message is an independent
  prompt. Adding history means storing message content on disk, which is a
  bigger decision than this daemon should quietly make.
- **No automatic HTTPS.** Everything is plain HTTP on the LAN. Fine for a
  home network with Tailscale for remote access; not fine if any of this is
  ever exposed.

## Attribution

The bulk of this — the compose files, the bridge daemon and its tests, the
backup and health scripts, and this README — was written by Claude (Claude
Code) in a session where I described what I wanted and pushed back on the
parts I disagreed with. The architecture decisions are mine: dropping Open
WebUI for the Telegram bridge, leaving networking alone, monitoring before
services rather than after.

I reviewed everything here before running it on the machine. That was the
point of building it as a repository instead of letting an agent configure
the server directly — an earlier unattended attempt granted itself
passwordless sudo and left services unauthenticated on the LAN, which is
exactly the failure mode that reading a diff first prevents.
