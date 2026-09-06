# Obsidian client setup (desktop + mobile)

End-to-end walkthrough for connecting Obsidian clients to your self-hosted CouchDB LiveSync server.

## Pre-flight (server side, do this FIRST)

```bash
# 1. Confirm nginx → CouchDB chain works from internet
curl -sk https://<server-ip>:8443/_up
# expect: {"status":"ok","seeds":{}}

# 2. Confirm your user is registered
curl -sk -u <USERNAME>:<USER_PASS> https://<server-ip>:8443/<VAULT_NAME>
# expect: {"db_name":"<VAULT_NAME>","doc_count":0,...}
# If 401 → see references/couchdb-troubleshooting.md chain 4
# If 404 → PUT the DB (see SKILL.md step 6)

# 3. Pull the cert locally if you want to pre-import it
ssh root@<server-ip> 'cat /opt/couchdb/certs/fullchain.pem' > /tmp/obsidian-cert.pem
# Optional — Obsidian LiveSync has an "accept self-signed certs" toggle, so you
# usually don't need to import. But importing silences HTTPS warnings.
```

## Desktop — Obsidian app

### Install + create vault

1. Download Obsidian from https://obsidian.md/download (Linux / macOS / Windows)
2. First launch → "Create new vault" → choose a folder on your disk (e.g. `~/Documents/ObsidianVault`)
3. Vault name: anything (this is just the display name)

### Enable Community Plugins

Settings → Community plugins → toggle "Community plugins: ON" → confirm the warning.
(This is needed because Self-hosted LiveSync is a community plugin, not bundled.)

### Install Self-hosted LiveSync

1. Community plugins → Browse
2. Search "Self-hosted LiveSync" by Voronouch
3. Install → Enable
4. **DO NOT confuse with "Remotely Save"** — different plugin, different protocol

### Install Obsidian Git (optional, for git remote backup)

Community plugins → Browse → "Obsidian Git" by denyskovalev → Install → Enable

Settings:
- **Auto commit interval**: 5 (minutes; don't go lower, races with LiveSync)
- **Auto push on startup**: ON
- **Auto pull on startup**: ON
- **Commit message**: `vault: auto {{date}} {{time}}`
- **Backup remote URL**: `ssh://root@<server-ip>/opt/<vault-name>.git`

---

## ⚠️ If you can't reach the Obsidian plugin marketplace

**Symptoms**: `Browse` tab opens but shows a blank list, hangs on load, or returns errors. This is the standard failure mode for users in mainland China (CDN blocked) or behind strict corporate firewalls.

**Do NOT keep retrying** — switch to offline install. The server already hosts the two required plugins (see SKILL.md pitfall #11 for setup). Just pull the files straight into your vault's plugin directory:

```bash
# Linux / macOS
cd ~/Documents/<vault>/.obsidian/plugins
mkdir -p obsidian-git && cd obsidian-git
curl -kO https://<server-ip>:8444/obsidian-git/main.js \
     -kO https://<server-ip>:8444/obsidian-git/manifest.json \
     -kO https://<server-ip>:8444/obsidian-git/styles.css
cd ..
mkdir -p self-hosted-livesync && cd self-hosted-livesync
curl -kO https://<server-ip>:8444/self-hosted-livesync/main.js \
     -kO https://<server-ip>:8444/self-hosted-livesync/manifest.json \
     -kO https://<server-ip>:8444/self-hosted-livesync/styles.css
```

```powershell
# Windows PowerShell
cd $HOME\Documents\<vault>\.obsidian\plugins
New-Item -ItemType Directory -Force -Path obsidian-git | Out-Null
cd obsidian-git
curl.exe -kO https://<server-ip>:8444/obsidian-git/main.js `
          -kO https://<server-ip>:8444/obsidian-git/manifest.json `
          -kO https://<server-ip>:8444/obsidian-git/styles.css
cd ..
New-Item -ItemType Directory -Force -Path self-hosted-livesync | Out-Null
cd self-hosted-livesync
curl.exe -kO https://<server-ip>:8444/self-hosted-livesync/main.js `
          -kO https://<server-ip>:8444/self-hosted-livesync/manifest.json `
          -kO https://<server-ip>:8444/self-hosted-livesync/styles.css
```

Restart Obsidian → 第三方插件 → click "启用" next to each plugin. `-k` skips the self-signed cert check (only for this download; HTTPS itself is still used).

---

## 中文版 Obsidian UI 对照

If you're using the Chinese localization, the English instructions above won't match the menu names exactly. Translation table:

| English UI | 中文 UI |
|---|---|
| Settings | 设置 |
| Community plugins | 第三方插件 |
| Browse (plugin marketplace) | 浏览 |
| Install | 安装 |
| Enable | 启用 |
| Restricted mode is on | 受限模式已启用 |
| Turn off restricted mode | 关闭受限模式 |
| Turn on restricted mode | 启用受限模式 |

**The single most-skipped step in 中文版**: ⚙️ 设置 → 第三方插件 → click **"关闭受限模式"**. Until you do this, NO community plugins appear — not even ones already in your `.obsidian/plugins/` folder. This is the first thing to check if "I installed the plugin but it doesn't show up".

### Configure LiveSync

Open the plugin settings:

- **URI**: `https://<server-ip>:8443/`  ← include the trailing slash + https
- **Username**: the one you PUT into CouchDB `_users`
- **Password**: from `~/.config/couchdb_user_pass` (or whatever you saved)
- **Database**: `<VAULT_NAME>` (matches what you PUT in step 6 of SKILL.md)

Click **Test Connection** — should say "Connection success" or similar.

### Set the encryption passphrase (CRITICAL)

In the plugin settings:
- Look for "Setup passphrase" or "Encryption passphrase"
- Enter a STRONG passphrase (20+ chars, ideally generated)
- **SAVE THIS PASSPHRASE TO YOUR PASSWORD MANAGER** — losing it = losing your vault (no recovery)
- This passphrase encrypts your notes client-side; the server only sees ciphertext

### Choose sync mode

In the plugin settings → Sync:
- Recommended: **LiveSync** (real-time, see edits within seconds on other devices)
- Alternative: Periodic Sync (every N seconds, less battery on mobile)

Restart Obsidian after first sync setup.

### Install Obsidian Git (optional, for git remote backup)

Community plugins → Browse → "Obsidian Git" by denyskovalev → Install → Enable

Settings:
- **Auto commit interval**: 5 (minutes; don't go lower, races with LiveSync)
- **Auto push on startup**: ON
- **Auto pull on startup**: ON
- **Commit message**: `vault: auto {{date}} {{time}}`
- **Backup remote URL**: `ssh://root@<server-ip>/opt/<vault-name>.git`

## Desktop — first-sync verification

1. Create a note `00-Inbox/test.md` with content "hello world"
2. Wait 5-10 seconds
3. Open the LiveSync plugin panel — should show "synced" or similar
4. Edit the note, save, observe sync log

## Mobile — Obsidian app (iOS / Android)

### Install + vault setup

1. Install Obsidian from App Store / Play Store
2. Open → "Create new vault" OR "Open folder as vault" if you have iCloud/Drive sync
3. Recommended: pick "Open folder as vault" → choose iCloud Drive / Google Drive folder so mobile has local backup even if LiveSync server goes down

### Install Self-hosted LiveSync

1. Settings → Community plugins → enable community plugins
2. Browse → search "Self-hosted LiveSync" → install + enable

### Configure LiveSync (same as desktop)

- URI: `https://<server-ip>:8443/`
- Username: same
- Password: same
- Database: same
- **Passphrase**: SAME as desktop (this is what decrypts your notes)

### What mobile does NOT need

- Skip Obsidian Git — mobile Obsidian can't run shell commands, git push won't work
- Just rely on LiveSync + iCloud/Drive local backup

## Multi-device sanity test

1. Desktop: create `test-desktop.md` in vault
2. Mobile: within 5s, the note should appear
3. Mobile: edit it
4. Desktop: within 5s, the edit should appear

If sync doesn't propagate:
- Both clients must be open (Obsidian closes connections when backgrounded on mobile)
- Check the LiveSync log on both — errors will name the issue
- Verify URI/password/database are identical on both clients

## Security checklist before going public

- [ ] SSH key on server uses ED25519 or RSA 4096
- [ ] Server firewall restricts 22 (SSH), 80 (HTTP), 8443 (LiveSync) to your IPs only
- [ ] nginx reverse proxy is the ONLY public-facing entry — CouchDB binds 127.0.0.1 only
- [ ] CouchDB admin password is 32+ random hex chars (openssl rand -hex 16)
- [ ] CouchDB user password is separate from admin
- [ ] Encryption passphrase is in your password manager
- [ ] No notes contain passwords/secrets that aren't also in your password manager
- [ ] CouchDB data volume `/opt/couchdb/data` is in a daily backup (see references/security-checklist.md)