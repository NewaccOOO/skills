# install.ps1 — Install claude-code-ctf-skills into ~/.claude/skills/

$SkillsDir = Join-Path $env:USERPROFILE ".claude\skills"
$SourceDir = Join-Path $PSScriptRoot "skills"

Write-Host "Installing CTF skills to $SkillsDir ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null

$skills = Get-ChildItem -Path $SourceDir -Directory
foreach ($skill in $skills) {
    $dest = Join-Path $SkillsDir $skill.Name
    $exists = Test-Path $dest

    if ($exists) {
        Write-Host "  [update]  $($skill.Name)" -ForegroundColor Yellow
    } else {
        Write-Host "  [install] $($skill.Name)" -ForegroundColor Green
    }

    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item -Path (Join-Path $skill.FullName "SKILL.md") -Destination $dest -Force
}

Write-Host ""
Write-Host "Done! $($skills.Count) skills installed." -ForegroundColor Cyan
Write-Host "Restart Claude Code and use /ctf-recon <IP> to get started." -ForegroundColor White
