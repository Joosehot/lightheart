# Asks for the Anthropic API key (hidden while you type) and keeps it in .env next to the app.
# .env is in .gitignore; the key never goes to the browser.
$root = Split-Path -Parent $PSScriptRoot
$secure = Read-Host "Anthropic API key" -AsSecureString
$key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
if (-not $key) { Write-Host "Nothing entered; nothing changed."; exit 1 }
$model = Read-Host "Model (Enter for the default, claude-sonnet-5-5)"
$lines = @("ANTHROPIC_API_KEY=$key")
if ($model) { $lines += "LIGHTHEART_MODEL=$model" }
Set-Content -Path (Join-Path $root ".env") -Value $lines -Encoding utf8
Write-Host "Saved to .env. Restart the server."
