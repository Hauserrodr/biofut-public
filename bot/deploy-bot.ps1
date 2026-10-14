# Deploy the BioFut WhatsApp bot to the Oracle A1 as an always-on Docker container.
# First run:  powershell -ExecutionPolicy Bypass -File D:\dev\biofut\bot\deploy-bot.ps1 -Phone 5551XXXXXXXXX
#   then on the phone: WhatsApp > Linked devices > Link a device > Link with phone number, type the PAIRING CODE it prints.
# Later runs (code update): same command without -Phone; the session in /srv/biofut-bot/session is kept.
# Check: ... deploy-bot.ps1 -Check   (prints the server-side script, changes nothing)
# Logs:  ... deploy-bot.ps1 -Logs    (follows the live log; an unlinked bot prints a new PAIRING CODE every few minutes, type the newest)
param([string]$Phone = '', [switch]$Check, [switch]$Logs)
$ErrorActionPreference = 'Stop'

$Key    = $env:BIOFUT_SSH_KEY  # path to the server's ssh key
$Target = "ubuntu@$env:BIOFUT_HOST_IP"
$Digits = $Phone -replace '\D', ''

# Same pattern as site/deploy.ps1: one bash script, base64-encoded (PowerShell 5.1 mangles quotes and CRLF).
$Remote = @'
set -euo pipefail
# Env: webhook token made once; phone only when given (used to print a pairing code while unlinked).
sudo test -f /etc/biofut-bot.env || {
  printf 'BIOFUT_BOT_TOKEN=%s\nBIOFUT_BOT_SESSION=/session/auth\n' "$(openssl rand -hex 16)" | sudo tee /etc/biofut-bot.env >/dev/null
  sudo chmod 600 /etc/biofut-bot.env
}
if [ -n "__PHONE__" ]; then
  sudo sed -i '/^BIOFUT_BOT_PHONE=/d' /etc/biofut-bot.env
  echo 'BIOFUT_BOT_PHONE=__PHONE__' | sudo tee -a /etc/biofut-bot.env >/dev/null
fi

cd /srv/biofut-bot/app
sudo docker build -q -t biofut-bot . >/dev/null
sudo docker rm -f biofut-bot >/dev/null 2>&1 || true
# host network: the webhook listens on the A1's 127.0.0.1:8787, next to the site (biofut.service :8013)
sudo docker run -d --name biofut-bot --restart unless-stopped --network host \
  --env-file /etc/biofut-bot.env -v /srv/biofut-bot/session:/session biofut-bot >/dev/null
sleep 25
sudo docker logs biofut-bot 2>&1 | tail -20
echo "container: $(sudo docker inspect -f '{{.State.Status}}' biofut-bot)"
'@ -replace "`r", '' -replace '__PHONE__', $Digits

if ($Check) { $Remote; return }
if ($Logs) { & ssh -t -i $Key $Target 'sudo docker logs -f --tail 20 biofut-bot'; return }

function Run-Ssh($cmd) {
    & ssh -o BatchMode=yes -i $Key $Target $cmd
    if ($LASTEXITCODE) { throw "ssh failed ($LASTEXITCODE): $cmd" }
}

if (-not (Test-Path "$PSScriptRoot\config.json")) { throw 'bot\config.json missing (copy config.example.json, set groupJid)' }
Run-Ssh 'sudo mkdir -p /srv/biofut-bot/app /srv/biofut-bot/session && sudo chown -R ubuntu:ubuntu /srv/biofut-bot/app'
& scp -q -i $Key "$PSScriptRoot\bot.js" "$PSScriptRoot\package.json" "$PSScriptRoot\Dockerfile" "$PSScriptRoot\.dockerignore" "$PSScriptRoot\config.json" "${Target}:/srv/biofut-bot/app/"
if ($LASTEXITCODE) { throw "scp failed ($LASTEXITCODE)" }

$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Remote))
Run-Ssh "echo $b64 | base64 -d | bash"
'Look for "PAIRING CODE: XXXX-XXXX" above (first run) or "bot connected". Follow the log: deploy-bot.ps1 -Logs'
