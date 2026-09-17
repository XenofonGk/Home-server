# Install checklist

Ordered, with a verification step per phase. Do not move to the next phase
until the current one verifies. Record each system-level change in
`~/server-setup-log.md` as you go.

Run everything as `foe`. Nothing here needs a root shell; the `sudo` calls
are individual and named.

---

## Phase 1 — Foundation

### 1.1 System update

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

Security patches only. Check `/etc/apt/apt.conf.d/50unattended-upgrades` has
only the `-security` origin uncommented.

**Verify:** `cat /etc/apt/apt.conf.d/20auto-upgrades`

### 1.2 SSH hardening

Confirm key auth works *before* disabling passwords. Keep your current
session open throughout.

```bash
ls -la ~/.ssh                       # want 700 on .ssh, 600 on authorized_keys
grep -c . ~/.ssh/authorized_keys    # non-zero
```

From the Mac, in a *second* terminal: `ssh foe@10.0.0.46` — must succeed with
no password prompt. Only then:

```bash
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak-$(date +%F)
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sshd -t && sudo systemctl reload ssh
```

`reload`, not `restart` — do not pull the service out from under yourself.

**Verify:** `sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin'`
and open a *third* SSH session to confirm you can still get in.

### 1.3 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker foe
newgrp docker
```

Log it: **docker group membership is root-equivalent.** Anyone in it can
mount the host filesystem into a container. That is an accepted trade here,
not an oversight.

**Verify:** `docker run --rm hello-world`

### 1.4 Clone this repo

```bash
git clone <repo> /home/foe/server
cd /home/foe/server && mkdir -p logs
```

### 1.5 Uptime Kuma — monitoring first

```bash
docker compose -f services/uptime-kuma/docker-compose.yml up -d
```

**Verify:** `curl -sI http://localhost:3001 | head -1` and open
`http://10.0.0.46:3001` to create the admin account **now**.

### 1.6 Telegram bot — alerting

1. `@BotFather` → `/newbot` → copy the token.
2. `@userinfobot` → copy your numeric chat ID.
3. `cp bridge/.env.example bridge/.env`, fill both in, `chmod 600 bridge/.env`
4. Test it:

```bash
./scripts/notify.sh "test from the home server"
```

**Verify:** the message arrives on your phone. Do not continue until it does.

5. In Uptime Kuma: Settings → Notifications → Telegram, same token and chat
   ID, "Test" button.
6. Add monitors for each service you're about to install.

**Verify the alerting actually works**, which is not the same as configuring
it:

```bash
docker stop nginx     # once nginx exists
# wait for the down alert on your phone
docker start nginx
# wait for the recovery alert
```

### 1.7 Fail2ban

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
```

**Verify:** `sudo fail2ban-client status sshd`

### 1.8 UFW

Allow rules first, *then* enable. Enabling with an empty ruleset over SSH
locks you out.

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 3001/tcp
sudo ufw allow 5678/tcp
sudo ufw allow 9000/tcp
sudo ufw status numbered          # confirm 22 is there BEFORE the next line
sudo ufw enable
```

Note 3000 is absent — there is no Open WebUI.

**Verify:** `sudo ufw status verbose`, and confirm your SSH session survived.

---

## Phase 2 — Services

### 2.1 Nginx

```bash
docker compose -f services/nginx/docker-compose.yml up -d
```

**Verify:** `curl -s http://localhost | head -5`

### 2.2 Portainer

```bash
docker compose -f services/portainer/docker-compose.yml up -d
```

**STOP.** Open `http://10.0.0.46:9000` and claim the admin account right now.
Portainer holds the Docker socket; an unclaimed instance lets whoever reaches
it first set the password, and that is a root shell on this machine.

### 2.3 Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo cp systemd/ollama-keepalive.conf /etc/systemd/system/ollama.service.d/
sudo systemctl daemon-reload && sudo systemctl restart ollama
ollama pull llama3.2
```

**Verify loopback binding** — this one matters, Ollama has no auth:

```bash
ss -tlnp | grep 11434        # must show 127.0.0.1:11434, NOT 0.0.0.0
```

**Verify keep-alive actually works** (three measurements for the log):

```bash
free -m                                        # 1. idle, no model loaded
ollama run llama3.2 "say hello" </dev/null     # trigger a load
free -m                                        # 2. during/just after inference
sleep 360 && free -m                           # 3. six minutes later
```

Measurement 3 should be back near measurement 1. If the model is still
resident, keep-alive is configured but not working — that is a bug to fix,
not a footnote.

### 2.4 Telegram bridge

```bash
sudo cp systemd/telegram-ollama-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-ollama-bridge
```

**Verify:**

```bash
systemctl status telegram-ollama-bridge
journalctl -u telegram-ollama-bridge -f
```

Send a message from your phone. You should get a model reply back. Then add
the bridge itself as an Uptime Kuma monitor — it is infrastructure now.

### 2.5 n8n

```bash
cp services/n8n/.env.example services/n8n/.env   # set user + a real password
chmod 600 services/n8n/.env
docker compose -f services/n8n/docker-compose.yml up -d
```

**Check the RAM budget before you commit to this one:**

```bash
docker stats --no-stream
free -m
```

If the total is pressing against ~4.5GB, n8n is the thing to drop. It is the
largest non-Ollama consumer and the one that executes arbitrary code.

---

## Phase 3 — Resilience

### 3.1 USB mount

```bash
lsblk -f                      # find the stick, note its UUID
sudo mkdir -p /mnt/backup
echo 'UUID=<uuid> /mnt/backup ext4 defaults,nofail,x-systemd.device-timeout=10 0 2' | sudo tee -a /etc/fstab
sudo mount -a
```

`nofail` is not optional. Without it, booting with the stick unplugged can
drop the machine to an emergency prompt — on a headless server that means
carrying a monitor over to find out.

**Verify:** `mountpoint /mnt/backup && df -h /mnt/backup`

### 3.2 restic

```bash
sudo apt install -y restic
openssl rand -base64 32 > /home/foe/server/.restic-password
chmod 600 /home/foe/server/.restic-password
cat /home/foe/server/.restic-password    # SAVE THIS OFF-MACHINE. Now.
sudo chown -R foe:foe /mnt/backup
./scripts/backup.sh
```

**Verify the restore, not just the backup:**

```bash
./scripts/restore-verify.sh
```

### 3.3 Cron

```bash
crontab -e
```

Add the two lines from the README. **Verify:** `crontab -l`, then run each
script by hand once and confirm the Telegram message arrives.

### 3.4 logrotate

```bash
sudo cp logrotate/home-server /etc/logrotate.d/home-server
sudo logrotate -d /etc/logrotate.d/home-server     # dry run
```

### 3.5 Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up            # prints an auth URL; open it in your browser
```

**Verify the wifi is untouched:** `ip addr` — still DHCP, still 10.0.0.46.

---

## Final check

```bash
ip addr | grep 'inet '                  # network unchanged
sudo ufw status verbose
sudo sshd -T | grep -E 'passwordauth|permitroot'
ss -tlnp | grep 11434                   # loopback only
docker ps --format 'table {{.Names}}\t{{.Status}}'
docker stats --no-stream
free -m
systemctl is-enabled docker ollama telegram-ollama-bridge fail2ban
```

Everything enabled, nothing unclaimed, total RAM under ~4.5GB, and both the
down-alert and the restore verified by having actually watched them happen.
