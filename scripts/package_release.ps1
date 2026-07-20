param([string]$Version = "v1.9.0")

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$folderName = "EMBA_TAU_Simulation_AI_Decision_OS_$Version`_$stamp"
$stage = Join-Path (Split-Path -Parent $repo) $folderName
$zip = "$stage.zip"

$files = @(
  ".env.example", ".gitignore", "agent_service.py", "analytics.py", "ARCHITECTURE.md",
  "AUDIT_IMPLEMENTATION_ROADMAP_HE.md", "backup_service.py", "cloud.py", "config.py", "db.py",
  "DEPLOYMENT_CHECKLIST_HE.md", "DEPLOY_v0.6_STEP_BY_STEP_HE.md", "DEPLOY_v1.0_STEP_BY_STEP_HE.md",
  "digital_twin.py", "Dockerfile", "evidence_engine.py", "group_governance.py", "import_service.py",
  "insights.py", "intopia_rules.py", "learning_engine.py", "logic.py", "main.py",
  "market_intelligence.py", "MIGRATION_v0.4_to_v0.5_HE.md", "MIGRATION_v0.5_to_v0.6_HE.md",
  "portfolio_optimizer.py", "README_HE.md", "render.yaml", "requirements-dev.txt", "requirements.txt",
  "reset_data.bat", "reset_data.py", "reset_data.sh", "rulebook.py", "RULEBOOK_SOURCES.md",
  "run_app.bat", "run_app.sh", "run_demo.bat", "seed_data.py", "setup_agent.bat", "setup_agent.ps1",
  "START_HERE.txt", "strategy_optimizer.py", "USER_GUIDE_HE.md"
)
$files += Get-ChildItem -LiteralPath $repo -File -Filter "RELEASE_NOTES_*.md" | Select-Object -ExpandProperty Name

New-Item -ItemType Directory -Path $stage | Out-Null
foreach ($name in ($files | Sort-Object -Unique)) {
  $source = Join-Path $repo $name
  if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $stage $name) }
}
foreach ($directory in @("static", "supabase", "tests")) {
  Copy-Item -LiteralPath (Join-Path $repo $directory) -Destination (Join-Path $stage $directory) -Recurse
}
New-Item -ItemType Directory -Path (Join-Path $stage "scripts") | Out-Null
Copy-Item -LiteralPath (Join-Path $repo "scripts\verify_cloud.py") -Destination (Join-Path $stage "scripts\verify_cloud.py")
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $stage "scripts\package_release.ps1")
Get-ChildItem -LiteralPath $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $stage -Recurse -File |
  Where-Object { $_.Extension -eq ".pyc" -or $_.Name -eq ".env" } |
  Remove-Item -Force
Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
Write-Output $zip
