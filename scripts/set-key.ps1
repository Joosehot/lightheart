# Asks for an API key (hidden while you type) and keeps it in .env next to the app, changing only
# that key's line. .env is in .gitignore; keys never go to the browser.
#   powershell -File scripts/set-key.ps1                  # the Anthropic key (the chat)
#   powershell -File scripts/set-key.ps1 OPENAI_API_KEY   # pictures (and OpenAI voice)
#   powershell -File scripts/set-key.ps1 GEMINI_API_KEY   # voice mode on Gemini Live
param([string]$Name = "ANTHROPIC_API_KEY")
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$secure = Read-Host "$Name" -AsSecureString
$key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
if (-not $key) { Write-Host "Nothing entered; nothing changed."; exit 1 }
$lines = @()
if (Test-Path $envFile) { $lines = @(Get-Content $envFile | Where-Object { $_ -notmatch "^$Name=" }) }
$lines += "$Name=$key"
Set-Content -Path $envFile -Value $lines -Encoding utf8
Write-Host "Saved $Name to .env. Restart the server."
