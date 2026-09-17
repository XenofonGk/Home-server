# Rebuilding this server

For when the disk dies, the laptop is replaced, or something is corrupted
badly enough that starting over beats debugging.

## What you need

1. The USB stick with the restic repository
2. **The restic repository password** — kept off this machine, because the
   copy on the machine died with it
3. This repository
4. The Telegram bot token (recoverable from @BotFather if lost)

Without item 2 the backup is unreadable. Check now that you still have it.

## Full rebuild

### 1. Base system

Install Ubuntu, create the user `foe`, install your SSH key, confirm key-based
login works from the Mac. Then work through `docs/INSTALL.md` phases 1.1–1.4 —
updates, SSH hardening, Docker, clone this repo to `/home/foe/server`.

### 2. Mount the stick and open the repo

```bash
sudo apt install -y restic
sudo mkdir -p /mnt/backup
lsblk -f                                    # find the UUID
sudo mount /dev/sdX1 /mnt/backup            # or add the fstab line first

export RESTIC_REPOSITORY=/mnt/backup/restic
export RESTIC_PASSWORD_FILE=/path/to/password/file
restic snapshots                            # confirms the password works
```

If `restic snapshots` fails, stop. Nothing below will work and the problem is
the password or the stick, not the procedure.

### 3. Restore

```bash
sudo systemctl stop docker
sudo restic restore latest --target /
sudo systemctl start docker
```

This puts back `/var/lib/docker/volumes`, `/home/foe/server`, and
`/home/foe/server-setup-log.md`.

To restore somewhere safe first and inspect before committing:

```bash
restic restore latest --target /tmp/restored
```

### 4. Secrets

The `.env` files and `.restic-password` are inside `/home/foe/server` and come
back with the restore. Confirm their permissions survived:

```bash
chmod 600 /home/foe/server/bridge/.env \
          /home/foe/server/services/n8n/.env \
          /home/foe/server/.restic-password
```

If you are rebuilding *without* a backup, recreate them from the `.env.example`
files and re-issue the credentials.

### 5. Bring services back up

```bash
cd /home/foe/server
for s in uptime-kuma portainer nginx n8n; do
  docker compose -f services/$s/docker-compose.yml up -d
done
```

Accounts and monitors come back with the volumes — you should not need to
re-claim Portainer or reconfigure Uptime Kuma. If you get a fresh setup screen
instead, the volume did not restore; check `docker volume ls` before clicking
through it, because claiming it again on top of a failed restore loses the old
data for good.

### 6. Ollama, bridge, Tailscale

Ollama and the model are **not** in the backup — the model is a
multi-gigabyte public download, not data worth storing. Reinstall per
`docs/INSTALL.md` 2.3, including the keep-alive drop-in and the loopback
binding check.

Then 2.4 for the bridge service, 3.3 for cron, 3.4 for logrotate, 3.5 for
Tailscale (the new machine needs re-authorizing in the Tailscale admin).

### 7. Verify

Run the final check block at the bottom of `docs/INSTALL.md`, then the two
that prove the parts you cannot see:

```bash
./scripts/notify.sh "restore complete"      # alerting works
./scripts/restore-verify.sh                 # backups work on the new machine
```

A rebuilt server that cannot back itself up is halfway to the same problem.

## Restoring one thing

```bash
restic snapshots                                    # pick a snapshot ID
restic ls <snapshot-id>                             # browse it
restic restore <snapshot-id> --target /tmp/scratch \
  --include /var/lib/docker/volumes/n8n_n8n-data
```

Then stop the service, copy the files into place, start it again. Restoring
into a running container's volume is how you get a corrupted database.
