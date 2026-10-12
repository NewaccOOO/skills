import collections

from collect import scan

CASES = [
    ("dsn", "DATABASE_URL=postgresql+asyncpg://app:s3cretP4ss@db:5432/guild", "postgresql+asyncpg://app:s3cretP4ss@db:5432/guild", True),
    ("dsn", "mysql+pymysql://app:p4ss@mysql/db и mongodb+srv://a:b9@cluster/x", "mongodb+srv://a:b9@cluster/x", True),
    ("dsn", "jdbc:postgresql://h:5432/db?user=a&password=b1", "jdbc:postgresql://h:5432/db?user=a&password=b1", True),
    ("db_kv", "host=db port=5432 user=app password=S3cret dbname=x", "password=S3cret", True),
    ("db_kv", "Server=sql;Database=x;User Id=a;Password=b1x;", "Password=b1x", True),
    ("db_cli", "PGPASSWORD=x1y2 psql -h db -U app -d guild", "psql -h db -U app -d guild", True),
    ("high_entropy", "tracker:Qk9GQUtFMTIzNDU2Nzg5OkZha2VUb2tlbjk4NzY1", "Qk9GQUtFMTIzNDU2Nzg5OkZha2VUb2tlbjk4NzY1", True),
    ("high_entropy", "ветка feature/AIAGENTS-3236-precondition-deeplink", "feature/AIAGENTS-3236-precondition-deeplink", False),
    ("high_entropy", "коммит 0123456789abcdef0123456789abcdef01234567", "0123456789abcdef0123456789abcdef01234567", False),
    ("value_keyword", "RkFLRTk4NzY1NDMyMTpBYmNEZWYxMjM0NTY3ODlY вот токен конфлюенса", "RkFLRTk4NzY1NDMyMTpBYmNEZWYxMjM0NTY3ODlY", True),
    ("uuid", '"service_token": "1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d"', "1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d", True),
    ("config_secret", 'password: "Fk[]pw1999zz"', "Fk[]pw1999zz", True),
    ("config_secret", "token = settings.SERVICE_TOKEN", "settings.SERVICE_TOKEN", False),
    ("ssh", "ssh farm.user@10.0.0.5\nFk[]pw1999zz пингани", "Fk[]pw1999zz", True),
    ("basic_decoded", "Authorization: Basic ZGVtbzpkZW1vMTIz", "demo:demo123", True),
    ("high_entropy", "путь /Users/someone/.npm/_npx/0a1b2c3d4e5f6a7b/node_modules", "/Users/someone", False),
    ("high_entropy", "модель unsloth/gemma-4-31B-it", "unsloth/gemma-4-31B-it", False),
    ("high_entropy", "atl_token=ABCD-EFGH-IJKL-MNOP_0123456789abcdef0123456789abcd", "atl_token", False),
    ("high_entropy", "BBDC-RmFrZTEyMzQ1Njc4OTpYeVo5OGFCY0Rl/Qz вот", "BBDC-RmFrZTEyMzQ1Njc4OTpYeVo5OGFCY0Rl/Qz", True),
]

failed = 0
for kind, text, expected, should_find in CASES:
    stats = collections.defaultdict(lambda: {"U": set(), "other": set(), "ctx": ""})
    scan(stats, text, "U", "test")
    found = any(name == kind and expected in value for name, value in stats)
    status = "ok  " if found == should_find else "FAIL"
    failed += status == "FAIL"
    print(f"{status} {kind}: {'находит' if should_find else 'не находит'} {expected[:40]}")
raise SystemExit(failed)
