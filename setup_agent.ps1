$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $projectDir ".env"

Write-Host ""
Write-Host "INTOPIA DSS - Connect Decision Agent to OpenAI"
Write-Host "The key is stored only in the local .env file, which is excluded from GitHub."
Write-Host ""

$secureKey = Read-Host "Paste OPENAI_API_KEY" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "No API key was entered."
}

$existing = @()
if (Test-Path $envFile) {
    $existing = Get-Content -LiteralPath $envFile |
        Where-Object {
            $_ -notmatch '^\s*OPENAI_API_KEY=' -and
            $_ -notmatch '^\s*OPENAI_MODEL=' -and
            $_ -notmatch '^\s*OPENAI_AGENT_ENABLED='
        }
}

$updated = @($existing) + @(
    "OPENAI_AGENT_ENABLED=true",
    "OPENAI_API_KEY=$apiKey",
    "OPENAI_MODEL=gpt-5.6-sol"
)

$updated | Set-Content -LiteralPath $envFile -Encoding UTF8
$apiKey = $null

Write-Host ""
Write-Host "The Agent connection was saved successfully."
Write-Host "Close the demo if it is open, then start run_demo.bat again."
Write-Host ""
