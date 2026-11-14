# NWC Ads: Operations Guide

Copyright 2026 Archdiocese of Seattle. Author: Kevin F Benz.

This guide describes how to run the production system: deploying updates, configuration, user access, certificates, backups, the Access cutover, and troubleshooting. [architecture.md](architecture.md) explains the design, and [developer-guide.md](developer-guide.md) explains how to change the code.

> **Status (November 2026):** NWC Ads is deployed but not yet the system of record. Access remains in use until cutover. Sign-in still runs in `dev` mode behind the IP allow list, while IT completes the Entra registration. Database backups are **not yet confirmed**. [backlog.md](backlog.md) tracks these items.

## 1. Production at a glance

| Item | Value |
|---|---|
| URL | https://nwcads.archseattle.org |
| Host | Azure VM `NWC-Ads`, Debian 12, public IP 4.242.48.163 |
| SSH user | `azureuser` |
| Application folder | `/opt/aos_nwc_ads` (a Git clone of the repository; owner `azureuser:www-data`) |
| Python environment | `/opt/aos_nwc_ads/.venv` (Python 3.11) |
| Configuration | `/opt/aos_nwc_ads/.env` (group `www-data`, mode `640`) |
| Service | systemd unit `aosnwcads`: Gunicorn, 3 workers, `127.0.0.1:8000`, runs as `www-data` |
| Web server | Nginx, site `/etc/nginx/sites-available/aosnwcads` |
| IP allow list | `/etc/nginx/snippets/aosnwcads-allow.conf` |
| TLS certificate | Let's Encrypt, `/etc/letsencrypt/live/nwcads.archseattle.org/`, webroot `/var/www/letsencrypt` |
| Database | MariaDB on the same VM; database `aos_nwc_ads`, user `nwcads@localhost` |
| Azure network security group | Inbound 22 (SSH), 80, and 443 allowed from any address |
| Health check | `https://nwcads.archseattle.org/healthz` returns `ok` without sign-in (from an allow-listed address) |

> The templates in `deploy/` predate the production setup. They use the path `/opt/aosnwcads`, and the Nginx template has no TLS or allow list. Treat the server as authoritative until the backlog item that aligns them is done.

## 2. Connecting to the server

```bash
ssh azureuser@4.242.48.163
```

Use the SSH key registered on the VM. If the key is lost, reset it in the Azure portal under the VM's **Reset password** blade.

## 3. Deploying an update

### 3.1 Standard update (code, templates, styles, help)

On a workstation, run the tests and push to `main` (see [developer-guide.md](developer-guide.md) section 7). Then, on the server:

```bash
cd /opt/aos_nwc_ads
git pull
sudo systemctl restart aosnwcads
curl -s https://nwcads.archseattle.org/healthz      # Expect: ok
```

A restart takes a few seconds. Users stay signed in, because sessions live in their browser cookies.

### 3.2 Update with new Python packages

When `requirements.txt` changes, install before restarting:

```bash
cd /opt/aos_nwc_ads
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart aosnwcads
```

### 3.3 Update with a database migration

When the update adds a file under `migrations/versions/`, back up first (section 7), then:

```bash
cd /opt/aos_nwc_ads
git pull
sudo -u www-data .venv/bin/flask --app run.py db upgrade
sudo systemctl restart aosnwcads
```

`db upgrade` reads the database settings from `.env`. Running it as `www-data` gives it permission to read that file. To see the current revision, run `sudo -u www-data .venv/bin/flask --app run.py db current`.

### 3.4 Rolling back

To return to the previous version of the code:

```bash
cd /opt/aos_nwc_ads
git log --oneline -5                 # Find the commit to return to
git checkout <commit>                # The folder is now on a "detached HEAD"
sudo systemctl restart aosnwcads
```

When the problem is fixed and pushed, return to normal with `git checkout main && git pull`.

If the bad version included a migration, run `flask db downgrade` **before** checking out the older code. If the migration changed data, restore the backup taken before the update (section 7.3) instead.

## 4. Service management

| Task | Command |
|---|---|
| Status | `sudo systemctl status aosnwcads` |
| Restart | `sudo systemctl restart aosnwcads` |
| Application log (live) | `sudo journalctl -u aosnwcads -f` |
| Application log (last hour) | `sudo journalctl -u aosnwcads --since "1 hour ago"` |
| Nginx test and reload | `sudo nginx -t && sudo systemctl reload nginx` |
| Nginx logs | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| MariaDB console | `sudo mariadb aos_nwc_ads` |
| Disk space | `df -h /` |

systemd restarts the service automatically 5 seconds after a crash (`Restart=always`).

## 5. Configuration (`.env`)

| Setting | Production value | Notes |
|---|---|---|
| `SECRET_KEY` | A long random value | Signs session cookies. Changing it signs everyone out. Generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | `localhost`, `3306`, `aos_nwc_ads`, `nwcads`, (secret) | |
| `AUTH_MODE` | `entra` after cutover; `dev` until then | The app refuses to start in `entra` mode without the three Entra values, or with the default `SECRET_KEY`. |
| `DEV_ROLE` | Not set | Used only in `dev` mode. |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` | From IT | See section 6. |
| `ENTRA_REDIRECT_URI` | `https://nwcads.archseattle.org/auth/callback` | Optional; set it if sign-in redirects to the wrong address. |
| `PROXY_COUNT` | `1` (default) | The number of proxies in front of the app (Nginx). |

After editing `.env`, restart the service. Keep the file's permissions, so that `www-data` can read it and other users cannot:

```bash
sudo chgrp www-data /opt/aos_nwc_ads/.env
sudo chmod 640 /opt/aos_nwc_ads/.env
```

An editor that replaces the file (for example `sed -i`) resets its group. The service then fails at startup with `PermissionError` on `.env`.

## 6. Sign-in and user access (Microsoft Entra ID)

### 6.1 App registration (one-time, done by IT)

IT creates an app registration in the Archdiocese tenant with these settings:

| Setting | Value |
|---|---|
| Supported account types | This organization only (single tenant) |
| Redirect URI (Web) | `https://nwcads.archseattle.org/auth/callback` |
| Front-channel logout URL | `https://nwcads.archseattle.org/auth/frontchannel-logout` |
| ID tokens | Enabled |
| API permission | Microsoft Graph `User.Read` (delegated) |
| App roles (allowed member types: Users/Groups) | Values `NWCAds.Viewer`, `NWCAds.Editor`, `NWCAds.Admin` |
| Client secret | Created; IT sends the value securely and records its **expiry date** |
| Enterprise application › Properties › Assignment required | Yes, so that only assigned people can sign in |

IT then sends the tenant ID, the client (application) ID, and the client secret. Put them in `.env`, set `AUTH_MODE=entra`, and restart the service. Then sign in with an Admin account to confirm.

### 6.2 Granting, changing, and removing access

In the Entra admin center, open **Enterprise applications › NWC Ads › Users and groups**:

- **Grant:** select **Add user/group**, choose the person (or a group), and choose the role.
- **Change:** remove the assignment, and add it again with the new role.
- **Remove:** remove the assignment.

Changes take effect the next time the person signs in. To apply a change sooner, ask the person to select **Sign out** and sign in again. Otherwise, the change applies when their session expires, at most 8 hours later.

Assign roles to Entra groups when possible (for example "NWC Ads Editors"), so that access follows group membership.

### 6.3 Client secret renewal

Entra client secrets expire, usually after 6 to 24 months. When the secret expires, **nobody can sign in**, and the sign-in page shows "Sign-in failed". Before the expiry date:

1. IT creates a new secret on the same app registration.
2. Replace `ENTRA_CLIENT_SECRET` in `.env`, and restart the service.
3. Sign in to confirm, and then IT deletes the old secret.

Record the expiry date in a shared calendar with a reminder one month ahead.

## 7. Backups and restore

> **Not yet in place.** [backlog.md](backlog.md) item C-02 tracks this. Complete it before cutover.

### 7.1 Recommended setup

1. **Nightly database dump on the VM**, keeping 14 days:

   ```bash
   sudo mkdir -p /var/backups/aosnwcads && sudo chmod 700 /var/backups/aosnwcads
   sudo tee /etc/cron.d/aosnwcads-backup > /dev/null <<'EOF'
   30 2 * * * root mariadb-dump --single-transaction --routines aos_nwc_ads | gzip > /var/backups/aosnwcads/aos_nwc_ads_$(date +\%F).sql.gz && find /var/backups/aosnwcads -name '*.sql.gz' -mtime +14 -delete
   EOF
   ```

2. **A copy off the VM.** Dumps on the VM are lost with the VM. Enable **Azure Backup** for the VM (daily, with at least 30 days' retention), or copy the dumps to an Azure Storage account.
3. **A restore test every quarter**, into a scratch database (section 7.3). An untested backup is not a backup.

### 7.2 Manual backup (before risky changes)

Take one before migrations, large merges, imports, and the cutover:

```bash
sudo sh -c 'mariadb-dump --single-transaction --routines aos_nwc_ads | gzip > /var/backups/aosnwcads/aos_nwc_ads_$(date +%F_%H%M).sql.gz'
sudo ls -lh /var/backups/aosnwcads/
```

### 7.3 Restore

To test a backup, restore it into a scratch database:

```bash
sudo mariadb -e "CREATE DATABASE aos_nwc_ads_restore"
gunzip -c /var/backups/aosnwcads/<file>.sql.gz | sudo mariadb aos_nwc_ads_restore
sudo mariadb aos_nwc_ads_restore -e "SELECT COUNT(*) FROM accounts; SELECT COUNT(*) FROM ad_placements;"
sudo mariadb -e "DROP DATABASE aos_nwc_ads_restore"
```

To replace production with a backup, which loses every change made since the backup:

```bash
sudo systemctl stop aosnwcads
gunzip -c /var/backups/aosnwcads/<file>.sql.gz | sudo mariadb aos_nwc_ads
sudo systemctl start aosnwcads
```

## 8. Nginx, the allow list, and TLS

### 8.1 IP allow list

Nginx admits only the addresses in `/etc/nginx/snippets/aosnwcads-allow.conf`, and refuses all others with 403. The file holds one `allow` line per address or range, followed by `deny all;`. It currently admits the Archdiocese offices' public addresses and the developer's address.

To add an address, for example for a staff member who works from home:

```bash
sudo nano /etc/nginx/snippets/aosnwcads-allow.conf     # Add: allow 203.0.113.10;  (before "deny all;")
sudo nginx -t && sudo systemctl reload nginx
```

Home internet addresses can change without notice. Once Entra sign-in is on, decide whether to keep the allow list (backlog item C-08).

The Let's Encrypt challenge path (`/.well-known/acme-challenge/`) must stay reachable from any address, or certificate renewal fails. It has its own `location` block that serves files from `/var/www/letsencrypt`. Keep the `include snippets/aosnwcads-allow.conf;` line inside the application's `location /` block, not at the `server` level, so that the challenge path stays outside the allow list. `sudo certbot renew --dry-run` confirms that renewal still works.

### 8.2 Certificate renewal

The Debian `certbot` package renews certificates automatically through the `certbot.timer` systemd timer. The certificate lasts 90 days, and renewal starts 30 days before expiry. To check:

```bash
systemctl list-timers certbot.timer
sudo certbot certificates                  # Shows the expiry date
sudo certbot renew --dry-run               # Tests renewal without changing anything
grep renew_hook /etc/letsencrypt/renewal/nwcads.archseattle.org.conf
```

The last command should show `renew_hook = systemctl reload nginx`. Without a reload hook, Nginx keeps serving the old certificate until its next reload, and browsers warn when it expires. If the line is missing, add a hook script that certbot runs after every renewal:

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

## 9. Importing data from Access, and the cutover

### 9.1 The import pipeline

1. On a Windows workstation, export the two Access tables to CSV with `scripts/export_access_csv.ps1` (see [developer-guide.md](developer-guide.md) section 1.1).
2. Copy the CSV files to the server, into `/opt/aos_nwc_ads/exports/access_csv/` (mode `700` folder, `600` files).
3. Load them with `sql/002_staging_import.sql`, using `mariadb --local-infile=1`. The script loads the staging tables, upserts accounts, and inserts ads.

> **The committed `sql/002_staging_import.sql` is missing three fixes** that were applied by hand on the server for the November 2026 import (backlog item C-04):
> - `LINES TERMINATED BY '\r\n'` instead of `'\n'`, because the Access export uses Windows line endings.
> - `ESCAPED BY ''` instead of `ESCAPED BY '"'`. The original value merged fields, which caused the error "Data too long for column 'city'".
> - A guard on `commission_percent`: `CASE WHEN value BETWEEN 0 AND 1 THEN value ELSE NULL END`. One Access row holds 3717, which is out of range.

### 9.2 Running the import again

The import is **not safe to run twice** on the same database:

- Accounts are **upserted**, so the Access values overwrite any edits made in NWC Ads.
- Ads are **inserted without duplicate checks**, so every ad is added a second time.

For the final cutover import, empty the tables first (section 9.3). Any cleanup done in NWC Ads before then, such as merges, orphan fixes, and test edits, is discarded. Lookup lists and the normalization map survive, because the import does not touch them.

### 9.3 Cutover runbook (outline)

The full runbook is backlog item C-05. The outline:

1. **Before the day:** backups in place (section 7); Entra sign-in tested; staff have their roles; the business owner has signed off on the reports.
2. **Freeze Access:** staff stop using Access at an agreed time. Make the `.accdb` read-only.
3. **Export** the final CSVs from Access, and copy them to the server.
4. **Back up** MariaDB (section 7.2).
5. **Reload:** `DELETE FROM ad_placements; DELETE FROM accounts; DELETE FROM audit_log;`, then run the corrected import (section 9.1).
6. **Reconcile:** compare the counts and totals with Access: the number of accounts, the number of ads, the number of orphan ads, and `SUM(amount)` per year. They must match exactly.
7. **Switch on:** set `AUTH_MODE=entra` (if not already), restart the service, and sign in as each role.
8. **Announce** the switch to staff, with a link to Help › Getting started.
9. **After cutover:** do the data cleanup (merges, lookup lists, orphans) in NWC Ads. Keep the final `.accdb` as a read-only archive.

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser: "502 Bad Gateway" | The service is not running. | `sudo systemctl status aosnwcads`, then `sudo journalctl -u aosnwcads -n 50` for the error. |
| Service fails; log shows `PermissionError` on `.env` | `.env` lost its `www-data` group. | Section 5: `chgrp` and `chmod 640`. |
| Service fails; log says "refuses to start" or `RuntimeError` | Missing or invalid configuration (Entra IDs, default `SECRET_KEY`, unknown `AUTH_MODE`). | Fix `.env`. The message names the setting. |
| "Internal Server Error"; log shows `Access denied for user` | Wrong database credentials. | Check the `DB_*` settings in `.env`. |
| "Internal Server Error"; log shows MariaDB error 1064 | SQL that MariaDB does not support (for example `NULLS LAST`). | A code bug: fix it and deploy (see [developer-guide.md](developer-guide.md) section 6). |
| Browser: "403 Forbidden" from Nginx (plain page) | The user's IP address is not on the allow list. | Section 8.1. |
| App page "Not allowed" | The user's role is too low for that page. | Section 6.2. |
| App page "No access yet" | The user signed in but has no NWC Ads role. | Section 6.2. |
| App page "Sign-in failed" | Expired client secret, wrong Entra IDs, or wrong redirect URI. | Section 6.3; check `ENTRA_*` and the redirect URI in the registration. |
| Site unreachable (time-out) | The VM is stopped, or the network security group blocks the port. | Azure portal: VM status and inbound rules. |
| Browser certificate warning | The certificate expired or Nginx was not reloaded. | Section 8.2. |

## 11. Routine maintenance

| How often | Task |
|---|---|
| Daily (automatic) | Database dump; Azure Backup |
| Monthly | Apply Debian updates: `sudo apt update && sudo apt upgrade`, then restart the service. Check `df -h`. |
| Quarterly | Test a restore (section 7.3). Check `certbot renew --dry-run`. Review Entra role assignments, and remove people who have left. Check `pip list --outdated` for security fixes. |
| Before expiry | Renew the Entra client secret (section 6.3). |
| After each release | Spot-check the changed pages; skim `journalctl -u aosnwcads` for errors. |
