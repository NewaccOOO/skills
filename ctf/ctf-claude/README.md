# Claude Code CTF Skills

> Automated pentesting & CTF attack skills for [Claude Code](https://claude.ai/code), powered by a Kali Linux MCP server.

A collection of **9 specialized skills** that transform Claude Code into an interactive pentesting assistant. Based on industry-standard methodologies covering a wide range of CTF challenges and lab machines.

---

## How it works

Each skill is a structured prompt loaded into Claude Code that:
- Guides Claude through a **phase-by-phase attack methodology**
- Executes real commands via a **Kali Linux MCP server**
- **Auto-hands off** to the next skill when a new attack vector is confirmed

```
You: /ctf-recon 10.10.11.45
        │
        ▼
  [ctf-recon] nmap → gobuster → enum4linux → ...
        │
        ├─ HTTP found ──────► [ctf-web]
        ├─ AD/SMB found ────► [ctf-ad] ──► [ctf-adcs]
        ├─ SQLi found ──────► [ctf-sqli]
        ├─ Docker exposed ──► [ctf-docker-escape]
        └─ Shell obtained ──► [ctf-privesc-linux] or [ctf-privesc-windows]
```

---

## Prerequisites

### 1. Claude Code

Install the CLI:
```bash
npm install -g @anthropic-ai/claude-code
```

### 2. mcp-kali-server

These skills require [mcp-kali-server](https://github.com/heverin/mcp-kali-server) — an MCP server that gives Claude Code access to a Kali Linux instance with pentesting tools.

Configure it in `~/.claude/claude.json` (or via `claude mcp add`):
```json
{
  "mcpServers": {
    "mcp-kali-server": {
      "command": "...",
      "args": ["..."]
    }
  }
}
```

> Refer to the mcp-kali-server documentation for setup details.

---

## Installation

### Linux / macOS

```bash
git clone https://github.com/YOUR_USERNAME/claude-code-ctf-skills.git
cd claude-code-ctf-skills
chmod +x install.sh
./install.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/YOUR_USERNAME/claude-code-ctf-skills.git
cd claude-code-ctf-skills
.\install.ps1
```

### Manual

Copy each folder inside `skills/` to `~/.claude/skills/`:

```
~/.claude/skills/
├── ctf-recon/
│   └── SKILL.md
├── ctf-web/
│   └── SKILL.md
├── ctf-ad/
│   └── SKILL.md
... (and so on)
```

---

## Available Skills

| Skill | Trigger command | Description |
|-------|----------------|-------------|
| **ctf-recon** | `/ctf-recon <IP>` | Initial recon: nmap, gobuster, enum4linux, service-specific enumeration. Auto-hands off to specialized skills. |
| **ctf-web** | `/ctf-web <URL>` | Web exploitation: LFI, SSRF, SSTI, SQLi, upload bypass, JWT, deserialization, CMS CVEs. |
| **ctf-ad** | `/ctf-ad <DC_IP>` | Active Directory: RID cycling, Kerberoasting, AS-REP, BloodHound, RBCD, shadow credentials, DCSync. |
| **ctf-adcs** | `/ctf-adcs <DC_IP>` | ADCS exploitation: ESC1–ESC9, certipy, NTLM relay to LDAPS, golden certificates. |
| **ctf-sqli** | `/ctf-sqli <URL>` | SQL Injection: sqlmap, blind/time-based, stacked queries, xp_cmdshell, gRPC/WebSocket SQLi. |
| **ctf-bof** | `/ctf-bof <binary>` | Binary exploitation: BOF, ROP chains, format string, ret2libc, pwntools, GDB workflow. |
| **ctf-privesc-linux** | `/ctf-privesc-linux` | Linux privesc: sudo, SUID, cron, capabilities, linpeas, GTFObins, PYTHONPATH hijack. |
| **ctf-privesc-windows** | `/ctf-privesc-windows` | Windows privesc: token abuse, DLL hijack, SeImpersonate, DPAPI, UAC bypass, winpeas. |
| **ctf-docker-escape** | `/ctf-docker-escape` | Container escape: privileged containers, Docker socket, cgroup release_agent, LXC, K8s. |

---

## Usage Examples

### Start from scratch with just an IP

```
/ctf-recon 10.10.11.45
```

Claude will:
1. Check Kali connectivity
2. Run nmap (fast + full port scan in background)
3. Enumerate each discovered service
4. Present an attack surface table
5. Auto-invoke the relevant specialized skill

### Jump directly to a specific phase

```
/ctf-web http://10.10.11.45
/ctf-ad 10.10.11.45 domain.local
/ctf-privesc-linux
```

### Typical full flow

```
/ctf-recon 10.10.11.45
    → discovers SMB + HTTP
    → auto-invokes /ctf-ad
        → gets user credentials
        → auto-invokes /ctf-adcs (ESC1 found)
            → forges certificate as Administrator
            → DCSync → NTLM hash
            → /ctf-privesc-windows (if needed)
```

---

## Skill Detail

### ctf-recon
Systematic initial enumeration methodology:
- **Phase 1**: Connectivity check + fast nmap
- **Phase 2**: Full port scan (background)
- **Phase 3**: Service-specific enumeration (HTTP, SMB, LDAP, FTP, Docker, Redis, WinRM...)
- **Phase 4**: DNS enumeration + vhost discovery
- **Phase 5**: Attack surface summary table + automatic handoff

### ctf-ad
Active Directory attack phases:
- **Phase 1**: Unauthenticated (RID cycling, null sessions, AS-REP roasting, LDAP anonymous)
- **Phase 2**: With credentials (BloodHound, Kerberoasting, GMSA, LAPS, password spray)
- **Phase 3**: ACL abuse (GenericWrite, ForceChangePassword, WriteDACL, Shadow Credentials)
- **Phase 4**: NTLM Relay + coercion (PetitPotam, DFSCoerce, RemotePotato0)
- **Phase 5**: RBCD delegation abuse
- **Phase 6**: Unconstrained/Constrained delegation
- **Phase 7**: DCSync
- **Phase 8**: Lateral movement (evil-winrm, psexec, Pass-the-Ticket)
- **Phase 9**: Memory dump analysis (memprocfs)
- **Phase 10**: Cross-forest trust abuse

### ctf-adcs
Certificate Services exploitation (Certify/Certipy):
- ESC1: Enrollee supplies SAN
- ESC2: Any purpose EKU
- ESC3: Enrollment agent abuse
- ESC4: Template write access
- ESC7: Manage CA + Manage Certificates
- ESC8: NTLM relay to HTTP enrollment endpoint
- ESC9/ESC10: No security extension / weak certificate mapping

---

## Methodology

These skills implement a structured attack methodology suitable for CTFs and laboratory environments. The checklist-driven approach ensures consistent, thorough enumeration before moving to exploitation.

Key principles:
- Enumerate before exploiting
- Prefer stealthy techniques (shadow credentials over password resets)
- BloodHound first, then targeted attacks
- Document findings at each phase

---

## Disclaimer

These skills are intended for **authorized security testing** only:
- CTF platforms and laboratory environments
- Penetration testing engagements with written authorization
- Security research in controlled lab environments

Do not use against systems you don't have permission to test.

---

## Credits

- Runtime: [Claude Code](https://claude.ai/code) by Anthropic
- Kali integration: [mcp-kali-server](https://github.com/heverin/mcp-kali-server)
