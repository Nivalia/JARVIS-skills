# Tool Index

- Generated at: 2026-08-06 02:02:31 +0800
- Platform: linux (Linux 6.1.0-18-amd64)
- Script: `skills/scripts/refresh-tool-index.sh`
- Note: This script detects tools only. It does not install tools.

| Tool | Skill | Purpose | Available | Path | Version | Source | Install hint |
|---|---|---|---|---|---|---|---|
| java | core-runtime | Java runtime for jadx/apktool/Burp/Ghidra | yes | /opt/jdk/jdk-21.0.12/bin/java | java version "21.0.12" 2026-07-21 LTS | command | apt: sudo apt install openjdk-17-jdk |
| python3 | core-runtime | Python runtime for helper scripts and pipx tools | yes | /usr/bin/python3 | Python 3.11.2 | command | apt: sudo apt install python3 python3-venv python3-pip pipx |
| pipx | core-runtime | Isolated Python CLI installer | yes | /usr/bin/pipx | 1.1.0 | command | see PLATFORMS.md and docs/platforms/linux.md |
| node | core-runtime | Node.js runtime for MCP bridges | yes | /root/.nvm/versions/node/v24.18.1/bin/node | v24.18.1 | command | apt/nvm: sudo apt install nodejs npm; prefer NodeSource or nvm for newer Node |
| npm | core-runtime | Node package manager | yes | /root/.nvm/versions/node/v24.18.1/bin/npm | 11.16.0 | command | see PLATFORMS.md and docs/platforms/linux.md |
| npx | core-runtime | Run npm MCP packages | yes | /root/.nvm/versions/node/v24.18.1/bin/npx | 11.16.0 | command | see PLATFORMS.md and docs/platforms/linux.md |
| jadx | apk-reverse | APK Java/Kotlin decompiler | yes | /usr/local/bin/jadx | 1.5.6 | command | GitHub release: download jadx ZIP to ~/tools/jadx |
| apktool | apk-reverse | APK decode and rebuild | yes | /usr/bin/apktool | 2.7.0-dirty | command | apt or jar: sudo apt install apktool; or official apktool.jar |
| adb | apk-reverse | Android device bridge | yes | /usr/bin/adb | Android Debug Bridge version 1.0.41 | command | apt or Android platform-tools: sudo apt install adb |
| frida | reverse-engineering | Dynamic instrumentation CLI | yes | /root/.local/bin/frida | 17.17.0 | command | pipx: pipx install frida-tools |
| frida-ps | reverse-engineering | Frida process listing | yes | /root/.local/bin/frida-ps | 17.17.0 | command | see PLATFORMS.md and docs/platforms/linux.md |
| r2 | radare2 | radare2 CLI analysis | yes | /usr/bin/r2 | radare2 6.1.8 +1 abi:110 @ linux-x86_64 | command | GitHub/source preferred; apt if available |
| rabin2 | radare2 | Binary metadata extraction | yes | /usr/bin/rabin2 | rabin2 6.1.8 +1 abi:110 @ linux-x86_64 | command | see PLATFORMS.md and docs/platforms/linux.md |
| ghidra | reverse-engineering | Ghidra reverse-engineering suite | yes | /usr/local/bin/ghidraRun | Exited with error.  Run in foreground (fg) mode for more details. | command | GitHub release ZIP or Flatpak; Java required |
| idapro | ida-reverse | IDA Pro commercial reverse-engineering suite | no | — | — | — | see PLATFORMS.md and docs/platforms/linux.md |
| burpsuite | burp-mcp | BurpSuite desktop application | yes | /usr/local/bin/burpsuite | 2025.6-39511 Burp Suite Community Edition | command | manual installer/jar; then load burp-mcp-full jar |
| graphviz | diagram-generator | Graphviz diagram rendering | yes | /usr/bin/dot | dot - graphviz version 2.43.0 (0) | command | see PLATFORMS.md and docs/platforms/linux.md |
| plantuml | diagram-generator | PlantUML diagram rendering | yes | /usr/bin/plantuml | PlantUML version 1.2020.02 (Sun Mar 01 18:22:07 CST 2020) | command | see PLATFORMS.md and docs/platforms/linux.md |
| nmap | pentest-tools | Network scanner | yes | /usr/bin/nmap | Nmap version 7.93 ( https://nmap.org ) | command | see PLATFORMS.md and docs/platforms/linux.md |
| sqlmap | pentest-tools | SQL injection testing tool | yes | /usr/bin/sqlmap | 1.7.2#stable | command | see PLATFORMS.md and docs/platforms/linux.md |
| ffuf | pentest-tools | Web fuzzer | yes | /usr/bin/ffuf | ffuf version: 1.1.0 | command | see PLATFORMS.md and docs/platforms/linux.md |
| hashcat | pentest-tools | Password recovery | no | — | — | — | see PLATFORMS.md and docs/platforms/linux.md |
| nuclei | pentest-tools | Template-based vulnerability scanner | no | — | — | — | GitHub release or go install; apt may be unavailable |
| binwalk | firmware-pentest | Firmware extraction and analysis | no | — | — | — | apt: sudo apt install binwalk |
| seclists | pentest-tools | Security wordlists | no | — | — | — | git clone https://github.com/danielmiessler/SecLists ~/tools/SecLists |
| jshookmcp | js-reverse | JS/CDP/Hook MCP runtime via npx | yes | /root/.nvm/versions/node/v24.18.1/bin/npx | 11.16.0 | command | npx: npx -y @jshookmcp/jshook@0.3.4 |
| reqable-mcp | pentest-tools | Reqable desktop MCP runtime via npx | yes | /root/.nvm/versions/node/v24.18.1/bin/npx | 11.16.0 | command | npx: npx -y reqable-mcp-server@1.0.1; install Reqable desktop separately |
| jeb-pro | apk-reverse | Commercial Android/ARM decompiler (manual licensed install) | no | — | — | — | manual licensed install: https://www.pnfsoftware.com/jeb/ |
| anything-analyzer | browser-automation | Browser/HTTP analyzer MCP project | no | — | — | — | git clone + pnpm install + pnpm dev |
| burp-mcp-full | burp-mcp | Local Burp MCP extension and stdio bridge | yes | /root/.hermes/skills/reverse-skill/burp-mcp-full/mcp-bridge.js | — | path-probe | see PLATFORMS.md and docs/platforms/linux.md |
| binwalk | firmware-pentest | Firmware extraction and analysis | no | — | — | — | apt: sudo apt install binwalk |
| yara | malware-analysis | Malware rule matching engine | no | — | — | — | apt: sudo apt install yara |
| pwntools | reverse-engineering | CTF pwn exploit development framework | no | — | — | — | pipx: pipx install pwntools |

---

## Next steps

- Read `docs/platforms/linux.md` for ordinary Linux setup.
- If the host is Kali, read `kali/README-kali.md` instead.
- Register MCP servers in your Agent client; tool availability does not imply MCP registration.

---

## 能力状态视图 (Capability Status)

| 能力 | 工具可用 | Ready | MCP 已注册 | 服务在线 | MCP HTTP | 可自动安装 | 安装方式 |
|------|---------|-------|-----------|---------|----------|-----------|---------|
| jadx | ✓ | ✓ | — | — | — | ✓ | github-release-zip |
| apktool | ✓ | ✓ | — | — | — | ✓ | github-release-jar-wrapper |
| jeb-pro | ✗ | ✗ | — | — | — | ✗ | manual |
| frida | ✓ | ✓ | — | — | — | ✓ | pip-package |
| frida-ps | ✓ | ✓ | — | — | — | ✓ | pip-package |
| idalib-mcp | ✗ | ✗ | — | — | — | ✓ | pip-package |
| reqable-mcp | ✓ | ✗ | — | — | — | ✓ | npm-mcp |
| jshookmcp | ✓ | ✗ | — | — | — | ✓ | npm-mcp |
| anything-analyzer | ✗ | ✗ | — | — | — | ✓ | local-http-mcp |
| idapro | ✗ | ✗ | — | — | — | ✓ | local-http-mcp |
| r2 | ✓ | ✓ | — | — | — | ✓ | github-release-zip |
| rabin2 | ✓ | ✓ | — | — | — | ✓ | github-release-zip |
| adb | ✓ | ✓ | — | — | — | ✓ | winget-package |
| agent-browser | ✗ | ✗ | — | — | — | ✓ | npm-global |
| ghidra-mcp | ✗ | ✗ | — | — | — | ✓ | github-release-zip |
| seclists | ✗ | ✗ | — | — | — | ✓ | git-clone |
| proxycat | ✗ | ✗ | — | — | — | ✓ | git-clone |
| burpsuite-mcp | ✗ | ✗ | — | — | — | ✗ | local-http-mcp |
| nmap | ✓ | ✓ | — | — | — | ✓ | winget-package |
| pentestswarm | ✗ | ✗ | — | — | — | ✓ | go-install |
| binwalk | ✗ | ✗ | — | — | — | ✓ | winget-package |
| yara | ✗ | ✗ | — | — | — | ✓ | winget-package |
| pwntools | ✗ | ✗ | — | — | — | ✓ | pip-package |
| bkcrack | ✗ | ✗ | — | — | — | ✓ | github-release-zip |

> ✓ = 是 | ✗ = 否 | — = 不适用或未检测

