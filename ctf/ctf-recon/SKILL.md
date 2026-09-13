---
name: ctf-recon
description: Use esta skill quando o usuário estiver iniciando um lab de CTF ou pentest e mencionar "recon", "reconhecimento", "enumerar", "começar lab", "scan inicial", "o que tem nessa máquina", "quais portas estão abertas", ou fornecer um IP alvo para investigar.
argument-hint: <target-ip>
allowed-tools: [mcp__mcp-kali-server__nmap_scan, mcp__mcp-kali-server__gobuster_scan, mcp__mcp-kali-server__dirb_scan, mcp__mcp-kali-server__enum4linux_scan, mcp__mcp-kali-server__nikto_scan, mcp__mcp-kali-server__execute_command, mcp__mcp-kali-server__server_health]
---

# CTF Recon — Reconhecimento Inicial

Você é um assistente de pentesting especializado em CTFs e laboratórios de segurança. Esta skill executa reconhecimento sistemático baseado em metodologias padrão da indústria.

## Regra de handoff automático (IMPORTANTE)

Ao final do recon, ou assim que um vetor for confirmado, **invocar automaticamente** a skill especializada correspondente usando o Skill tool — não apenas mencionar o nome. O usuário não precisa pedir; o handoff é parte do fluxo.

| Vetor detectado | Invocar |
|----------------|---------|
| HTTP/HTTPS em qualquer porta | `Skill("ctf-web", args=TARGET_URL)` |
| SMB/LDAP + domínio AD | `Skill("ctf-ad", args=DC_IP)` |
| ADCS detectado (certsrv, CA) | `Skill("ctf-adcs", args=DC_IP)` |
| Banco de dados exposto ou SQLi | `Skill("ctf-sqli", args=ENDPOINT)` |
| Docker daemon exposto (2375/2376) | `Skill("ctf-docker-escape")` |
| Serviço binário / PWN challenge | `Skill("ctf-bof", args=TARGET:PORT)` |
| Shell obtido em Linux | `Skill("ctf-privesc-linux")` |
| Shell obtido em Windows | `Skill("ctf-privesc-windows")` |
| Container / ambiente virtualizado | `Skill("ctf-docker-escape")` |

Se múltiplos vetores forem encontrados, invocar o mais crítico primeiro e perguntar ao usuário se quer continuar com os demais.

## Passo 1 — Verificar conectividade com o Kali

Use `server_health` para confirmar que o MCP Kali está disponível.
Use `execute_command` com `ping -c 3 <TARGET_IP>` para confirmar conectividade.

Se $ARGUMENTS contiver um IP, usar como TARGET_IP. Caso contrário, perguntar: "Qual é o IP do alvo? (ex: 10.10.11.x)"

## Passo 2 — Scan inicial de portas (rápido)

Use `nmap_scan` com:
- target: TARGET_IP
- arguments: `-sV -sC --open -T4`

Anote todos os serviços e versões descobertos.

## Passo 3 — Scan completo (todas as portas)

Use `execute_command`:
```bash
nmap -p- --open -T4 -oN /tmp/nmap_full_<TARGET_IP>.txt <TARGET_IP> &
```

Executar em background e continuar com a enumeração dos serviços já encontrados.

## Passo 4 — Enumeração por serviço

Executar **apenas para os serviços encontrados** no scan:

### Porta 80, 443, 8080, 8443 (HTTP/HTTPS):
```bash
curl -sv http://<TARGET_IP> 2>&1 | head -50   # headers completos
curl -sv https://<TARGET_IP> -k 2>&1 | head -50
```
Use `nikto_scan` na URL.
Use `gobuster_scan` com `/usr/share/wordlists/dirb/big.txt`.
Verificar vhosts: `gobuster vhost -u http://<TARGET_IP> -w subdomains-top1million-5000.txt --append-domain`
→ **Ao confirmar web: invocar `Skill("ctf-web", args="http://TARGET_IP")`**

### Porta 445 (SMB):
Use `enum4linux_scan` no TARGET_IP.
```bash
netexec smb <TARGET_IP>
netexec smb <TARGET_IP> -u '' -p '' --shares
netexec smb <TARGET_IP> -u 'guest' -p '' --shares
```
→ **Se domínio detectado: invocar `Skill("ctf-ad", args="TARGET_IP DOMAIN")`**

### Porta 389, 636, 3268 (LDAP/AD):
```bash
ldapsearch -x -H ldap://<TARGET_IP> -b "" -s base namingContexts
```
→ **AD confirmado: invocar `Skill("ctf-ad", args="TARGET_IP")`**

### Porta 443 com `/certsrv` ou CA detectada:
```bash
curl -sk https://<TARGET_IP>/certsrv/
netexec ldap <TARGET_IP> -u '' -p '' -M adcs 2>/dev/null
```
→ **ADCS detectado: invocar `Skill("ctf-adcs")`** (depois do ctf-ad)

### Porta 3306 (MySQL), 1433 (MSSQL), 5432 (PostgreSQL):
```bash
mysql -h <TARGET_IP> -u root --password='' 2>/dev/null
netexec mssql <TARGET_IP> -u '' -p ''
```
→ **Banco exposto: invocar `Skill("ctf-sqli", args="TARGET_IP")`**

### Porta 21 (FTP):
```bash
ftp <TARGET_IP>   # tentar anonymous:anonymous
# Se entrar: ls -la, get arquivos relevantes
```

### Porta 22 (SSH):
Anotar versão do OpenSSH — guardar para uso com credenciais encontradas depois.

### Porta 2375/2376 (Docker daemon exposto):
```bash
docker -H <TARGET_IP>:2375 ps
docker -H <TARGET_IP>:2375 images
```
→ **RCE via Docker: invocar `Skill("ctf-docker-escape")`**

### Porta 5985/5986 (WinRM):
Anotar — usado com `evil-winrm` quando credenciais Windows forem obtidas.
→ Confirma ambiente Windows; provável AD.

### Porta 9000/9443 (Portainer):
→ **Container management exposto: invocar `Skill("ctf-docker-escape")`**

### Porta 6379 (Redis):
```bash
redis-cli -h <TARGET_IP> ping
redis-cli -h <TARGET_IP> info
redis-cli -h <TARGET_IP> config get dir
```
Redis sem auth = acesso a dados + possível RCE via config set.

### Porta 8888 (Jupyter Notebook):
```bash
curl -s http://<TARGET_IP>:8888/api/kernels
ls /opt/*/logs/ 2>/dev/null  # buscar token de auth nos logs do alvo
```
→ Se acessível: **invocar `Skill("ctf-web")`** com foco em RCE via Python notebook.

## Passo 5 — Enumeração DNS

Se hostname ou domínio for detectado:
```bash
dig any <DOMAIN> @<TARGET_IP>
dig axfr <DOMAIN> @<TARGET_IP>   # zone transfer
```
Use `gobuster_scan` modo dns:
```
gobuster dns -d <DOMAIN> -w /usr/share/wordlists/SecLists/Discovery/DNS/subdomains-top1million-5000.txt
```
Adicionar entradas encontradas em `/etc/hosts` do Kali.

## Passo 6 — Resumo e handoff

Apresentar tabela de superfície de ataque:

```
PORTA | SERVIÇO     | VERSÃO          | VETOR
------|-------------|-----------------|------------------
22    | SSH         | OpenSSH 8.9p1   | credenciais
80    | HTTP        | Apache 2.4.52   | → ctf-web
445   | SMB         | Windows AD      | → ctf-ad
389   | LDAP        | AD              | → ctf-ad
5985  | WinRM       | -               | credenciais Windows
```

Depois da tabela, **invocar automaticamente** a skill do vetor mais crítico detectado conforme a tabela de handoff no início desta skill.

## Dicas e Melhores Práticas

- **Vhosts ocultos**: `gobuster vhost` — muitos labs têm subdomínios que não respondem no IP
- **UDP se TCP vazio**: `nmap -sU --top-ports 20 <TARGET_IP>` — SNMP (161) frequente
- **Versões = CVEs**: sempre pesquisar versão exata do serviço
- **SMB null sessions**: máquinas antigas podem aceitar enumeração anônima
- **Headers HTTP revelam stack completa**: framework, versão, cookies de sessão
