# Client TLS certificate warning — fix reference

When Self-hosted LiveSync in Obsidian can't reach your CouchDB, you sometimes see:

> Failed to connect to the server: Error: Request failed. 此服务器的证书无效。你可能正在连接一个伪装成 "<your-ip>" 的服务器,这会威胁到你的机密信息的安全。

This is **Obsidian's network layer (Capacitor HTTPS handling on mobile, Node TLS on desktop) rejecting your self-signed cert**, not a CouchDB bug. The TLS handshake completes — the server is fine — but the cert isn't in the OS trust store.

## Quick fix: tell LiveSync to skip cert verification

In the LiveSync plugin settings, look under **Remote Settings → Advanced** (label varies by LiveSync version):

| LiveSync version | English label | 中文 label |
|---|---|---|
| 0.x – 1.0.x | Allow insecure endpoint | 允许不安全端点 |
| any | Trust self-signed certificates | 信任自签证书 |
| any | Disable TLS verification | 关闭 TLS 验证 |
| any | Insecure mode | 不安全模式 |

Set it ON, save, **Test Connection** again — should succeed. This only relaxes LiveSync's own TLS check; other plugins and Obsidian's core still verify HTTPS.

## Proper fix: install the cert as a trusted root CA

Better long-term, and the only reliable fix on iOS where Capacitor's ATS is strict.

### 1. Get the cert onto the device

```bash
# Server cert is at /opt/couchdb/certs/fullchain.pem
# Pull it to your local machine:
scp root@<server-ip>:/opt/couchdb/certs/fullchain.pem ./aeglx-couchdb-ca.pem
# Then AirDrop / email / Google Drive / iCloud / USB to the device
```

### 2. Install it

- **macOS**: double-click `.pem` → Keychain Access → "Get Info" on the cert → "Trust → Always Trust" → restart Obsidian
- **Windows**: `certmgr.msc` → Trusted Root Certification Authorities → right-click → All Tasks → Import → `.pem`
- **iOS**: tap `.pem` file → "Install Profile" → then **Settings → 通用 → VPN 与设备管理 → 信任** → then **Settings → 通用 → 关于本机 → 证书信任设置 → 对根证书启用完全信任 (toggle ON)**
- **Android 7+**: Settings → Security → Encryption & credentials → Install a certificate → CA certificate → pick `.pem` → restart browser/Obsidian

### 3. Verify

After install + Obsidian restart, click **Test Connection** in LiveSync — no red banner. LiveSync's "Allow insecure endpoint" toggle can stay OFF.

## When neither fix works

- **Wrong port**: client URI must be `https://...:8443/` (CouchDB), not the `:8444/` plugin download port
- **Cert CN doesn't match**: cert was generated for a different IP/hostname — regenerate with `-subj '/CN=<current-ip>/' -addext 'subjectAltName=IP:<current-ip>,DNS:localhost'`
- **Cloud firewall still blocking**: `curl -sk https://<server-ip>:8443/_up` from outside the server fails → check security group / iptables rules
- **Old CouchDB version**: `0.x` has different cert handling; upgrade to `3.x`