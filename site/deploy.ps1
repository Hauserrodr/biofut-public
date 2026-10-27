# Deploy the BioFut site to the Oracle A1 as https://biofut.h-brain.org.
# Run:   powershell -ExecutionPolicy Bypass -File D:\dev\BDSMA\site\deploy.ps1
# Check: ... deploy.ps1 -Check   (prints the server-side script, changes nothing)
# Re-running is safe: it re-uploads the code and keeps the PIN and data/ (sign-ups, photos, wiki reports).
# -Wiki also uploads the BioWiki built by ..\wiki\wiki.py site (data\wiki json; photos only the ones the server lacks),
#   and the game nights' photos from ..\wiki\jogos.py (data\wiki\jogos.json) when built.
# -Data also uploads data\radio\*.mp3 (the playlist of #/radio, replacing the server's) and data\phones.json and data\mensagens.json (phones.py: number -> name for logins and lists, members'
#   own group messages for #/eu). Only from the worktree with the latest phones.py build: a stale copy renames people
#   (10-09: a 10-07 phones.json made Leo Saul "Victor" on the live site). List stats go through the review queue: listas.py --send.
# The admin key for /admin (review queue) is made once in /etc/biofut.env as BIOFUT_ADMIN; read it with
#   ssh -i $env:BIOFUT_SSH_KEY ubuntu@$env:BIOFUT_HOST_IP sudo grep BIOFUT_ADMIN /etc/biofut.env
param([switch]$Check, [switch]$Wiki, [switch]$Data)
$ErrorActionPreference = 'Stop'

$Key    = $env:BIOFUT_SSH_KEY  # path to the server's ssh key
$HostIp = $env:BIOFUT_HOST_IP
$Target = "ubuntu@$HostIp"
$Json   = "$PSScriptRoot\biofut.json"  # built by build_data.py: history, BioBet GLM coefficients, lexicon, Pix

# Everything on the server runs as one bash script. It is sent base64-encoded because
# Windows PowerShell 5.1 mangles double quotes in native args and pipes CRLF to stdin.
$Remote = @'
set -euo pipefail

# BioBet runs the Poisson GLM (glm.py) since 2026-10-23: a biofut.json with the old logistic block would break the odds.
# Stop before the restart (the running server keeps the old code): rebuild it with build_data.py (--refit) and deploy it.
grep -q '"kind":"poisson_glm"' /srv/biofut/biofut.json || { echo 'biofut.json on the server has no GLM model: python build_data.py --refit biofut.json, then deploy again from here'; exit 1; }

# Group PIN, made once. Every save (sign-up, draft, photo, new match) needs it.
sudo test -f /etc/biofut.env || {
  printf 'BIOFUT_PIN=%06d\nHOST=127.0.0.1\nPORT=8013\n' "$(shuf -i 0-999999 -n1)" | sudo tee /etc/biofut.env >/dev/null
  sudo chmod 600 /etc/biofut.env
}
# Admin key for /admin (approve / edit / reject what the pipelines make), made once, never printed here.
sudo grep -q '^BIOFUT_ADMIN=' /etc/biofut.env || echo "BIOFUT_ADMIN=$(openssl rand -hex 16)" | sudo tee -a /etc/biofut.env >/dev/null
# Older deploys pointed at biofut_data.json; the server now defaults to /srv/biofut/biofut.json.
sudo sed -i '/^BIOFUT_DATA=/d' /etc/biofut.env

# systemd service on 127.0.0.1:8013 (8000-8004 Rotas compose, 8010-8012 other APIs).
sudo tee /etc/systemd/system/biofut.service >/dev/null <<'EOF'
[Unit]
Description=BioFut site (history, draft, BioBet, cards) - stdlib Python
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/srv/biofut
EnvironmentFile=/etc/biofut.env
ExecStart=/usr/bin/python3 /srv/biofut/server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable biofut
sudo systemctl restart biofut
sleep 2
systemctl is-active biofut
curl -s -o /dev/null -w 'service %{http_code}\n' http://127.0.0.1:8013/

# Daily backup at 03:00 BRT (backup.sh): 14 days here and on the BioFut Drive. rclone's Drive login is
# ~ubuntu/.config/rclone/rclone.conf, made once by hand (2026-10-10); without it only the local copy is made.
command -v rclone >/dev/null || sudo apt-get install -y -qq rclone >/dev/null
sudo tee /etc/systemd/system/biofut-backup.service >/dev/null <<'EOF'
[Unit]
Description=BioFut daily backup to /srv/biofut-backup and the BioFut Drive

[Service]
Type=oneshot
User=ubuntu
ExecStartPre=+/usr/bin/install -d -o ubuntu -g ubuntu /srv/biofut-backup
ExecStart=/bin/sh /srv/biofut/backup.sh
EOF
sudo tee /etc/systemd/system/biofut-backup.timer >/dev/null <<'EOF'
[Unit]
Description=BioFut daily backup at 03:00 BRT

[Timer]
OnCalendar=*-*-* 03:00 America/Sao_Paulo
Persistent=true

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now biofut-backup.timer
systemctl list-timers biofut-backup.timer --no-pager | sed -n 2p

# SQL copy of the JSON files (db.py) every 5 minutes: Postgres db biofut owned by ubuntu, peer auth on the local socket
# (no password), pgvector on. It is rebuilt from the files, so backup.sh needs nothing from it.
dpkg -s python3-pil fonts-dejavu-core >/dev/null 2>&1 || sudo apt-get install -y -qq python3-pil fonts-dejavu-core >/dev/null  # conferir.py: the tabela check pictures
dpkg -s postgresql postgresql-18-pgvector python3-psycopg >/dev/null 2>&1 || sudo apt-get install -y -qq postgresql postgresql-18-pgvector python3-psycopg >/dev/null  # not psql: the client can be there alone
(cd /tmp
 [ "$(sudo -u postgres psql -Atc "select 1 from pg_roles where rolname = 'ubuntu'")" = 1 ] || sudo -u postgres createuser ubuntu
 [ "$(sudo -u postgres psql -Atc "select 1 from pg_database where datname = 'biofut'")" = 1 ] || sudo -u postgres createdb -O ubuntu biofut
 sudo -u postgres psql -q -d biofut -c 'create extension if not exists vector')
python3 /srv/biofut/db.py schema
sudo tee /etc/systemd/system/biofut-db.service >/dev/null <<'EOF'
[Unit]
Description=BioFut JSON files to the biofut Postgres db (db.py)
After=postgresql.service

[Service]
Type=oneshot
User=ubuntu
ExecStart=/usr/bin/python3 /srv/biofut/db.py
EOF
sudo tee /etc/systemd/system/biofut-db.timer >/dev/null <<'EOF'
[Unit]
Description=BioFut JSON files to Postgres every 5 minutes

[Timer]
OnCalendar=*:0/5

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now biofut-db.timer
psql -d biofut -Atc "select 'db: ' || count(*) || ' files, ' || (select count(*) from game_players) || ' player rows, ' || (select count(*) from balances) || ' balances, vector ' || (select extversion from pg_extension where extname = 'vector') from docs"

# nginx: own vhost file, so a1-sites deploys can't revert it (2026-09-15 incident).
sudo tee /etc/nginx/sites-available/biofut >/dev/null <<'EOF'
# biofut.h-brain.org - BioFut group site (/srv/biofut, biofut.service on :8013).
server { listen 80; listen [::]:80; server_name biofut.h-brain.org; return 301 https://$host$request_uri; }
server {
    listen 443 ssl; listen [::]:443 ssl; http2 on;
    server_name biofut.h-brain.org;
    ssl_certificate     /etc/ssl/cloudflare/hbrain-origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/hbrain-origin.key;
    client_max_body_size 4m;  # photo upload: 1.5 MB JPEG as base64 JSON
    include /etc/nginx/snippets/deny-private.conf;
    location / {
        proxy_pass http://127.0.0.1:8013;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/biofut /etc/nginx/sites-enabled/biofut
sudo nginx -t
sudo systemctl reload nginx
curl -sk -o /dev/null -w 'nginx %{http_code}\n' --resolve biofut.h-brain.org:443:127.0.0.1 https://biofut.h-brain.org/api/state
sudo grep BIOFUT_PIN /etc/biofut.env
'@ -replace "`r", ''

if ($Check) { $Remote; return }

function Run-Ssh($cmd) {
    & ssh -o BatchMode=yes -i $Key $Target $cmd
    if ($LASTEXITCODE) { throw "ssh failed ($LASTEXITCODE): $cmd" }
}

# 1. Files.
Run-Ssh 'sudo mkdir -p /srv/biofut/data && sudo chown -R ubuntu:ubuntu /srv/biofut'
$Files = @("$PSScriptRoot\server.py", "$PSScriptRoot\index.html", "$PSScriptRoot\wiki.html", "$PSScriptRoot\transparencia.html", "$PSScriptRoot\entrar.html", "$PSScriptRoot\admin.html", "$PSScriptRoot\sumula.py", "$PSScriptRoot\glm.py", "$PSScriptRoot\costs.py", "$PSScriptRoot\sheet.py", "$PSScriptRoot\conferir.py", "$PSScriptRoot\lista.py", "$PSScriptRoot\backup.sh", "$PSScriptRoot\db.py",
  "$PSScriptRoot\site.css", "$PSScriptRoot\site.js", "$PSScriptRoot\og.png", "$PSScriptRoot\logo.png", "$PSScriptRoot\robots.txt", "$PSScriptRoot\sitemap.xml", "$PSScriptRoot\push.py", "$PSScriptRoot\sw.js", "$PSScriptRoot\copa_art.jpg", "$PSScriptRoot\truco-v03.jpg")
if (Test-Path $Json) { $Files += $Json } else { 'biofut.json not here: keeping the one on the server' }
& scp -q -i $Key @Files "${Target}:/srv/biofut/"
if ($LASTEXITCODE) { throw "scp failed ($LASTEXITCODE)" }
& python "$PSScriptRoot\og_copa.py"  # one countdown image per day left: /copa's preview + the group post, and the Instagram story (needs Pillow here)
if ($LASTEXITCODE) { 'og_copa.py failed: /copa keeps the images already on the server' } else {
    Run-Ssh 'mkdir -p /srv/biofut/og && rm -f /srv/biofut/og/copa-*.jpg /srv/biofut/og/story-*.jpg'
    & scp -q -i $Key @(Get-ChildItem "$PSScriptRoot\og\copa-*.jpg", "$PSScriptRoot\og\story-*.jpg" | ForEach-Object { $_.FullName }) "${Target}:/srv/biofut/og/"
    if ($LASTEXITCODE) { throw "scp og failed ($LASTEXITCODE)" }
}
$Extra =@(@('phones.json', 'mensagens.json') | Where-Object { $Data } | ForEach-Object { "$PSScriptRoot\data\$_" } | Where-Object { Test-Path $_ })  # @(): one file would splat as characters
if ($Extra) {
    & scp -q -i $Key @Extra "${Target}:/srv/biofut/data/"
    if ($LASTEXITCODE) { throw "scp data failed ($LASTEXITCODE)" }
}
$Songs = @(Get-ChildItem "$PSScriptRoot\data\radio\*.mp3" -ErrorAction SilentlyContinue | Where-Object { $Data })  # #/radio: the whole local folder is the playlist
if ($Songs) {
    Run-Ssh 'mkdir -p /srv/biofut/data/radio && rm -f /srv/biofut/data/radio/*.mp3'
    & scp -q -i $Key @($Songs | ForEach-Object { $_.FullName }) "${Target}:/srv/biofut/data/radio/"
    if ($LASTEXITCODE) { throw "scp radio failed ($LASTEXITCODE)" }
    "radio: $($Songs.Count) songs"
}
if ($Wiki) {  # members' feedback.jsonl and the review queue on the server are never touched
    # The local build is the source of truth: it replaces bits approved on the server since the last build.
    Run-Ssh 'mkdir -p /srv/biofut/data/wiki/media'
    $Have = @(& ssh -o BatchMode=yes -i $Key $Target 'ls /srv/biofut/data/wiki/media')
    $New = @(Get-ChildItem "$PSScriptRoot\data\wiki\media" -File | Where-Object { $Have -notcontains $_.Name } | ForEach-Object { $_.Name })
    $Tar = "$env:TEMP\biofut_wiki.tar"
    $List = "$env:TEMP\biofut_wiki.txt"
    @('public.json', 'member.json') + @(@('jogos.json') | Where-Object { Test-Path "$PSScriptRoot\data\wiki\$_" }) + @($New | ForEach-Object { "media/$_" }) | Set-Content -Encoding ascii $List
    # Windows' own bsdtar: under Git Bash (Claude Code's `!`) PATH finds GNU tar first, which reads C:\... as host "C"
    & "$env:SystemRoot\System32\tar.exe" -cf $Tar -C "$PSScriptRoot\data\wiki" -T $List
    if ($LASTEXITCODE) { throw "tar failed ($LASTEXITCODE)" }
    "wiki: 2 json + $($New.Count) new photos"
    & scp -q -i $Key $Tar "${Target}:/tmp/biofut_wiki.tar"
    if ($LASTEXITCODE) { throw "scp wiki failed ($LASTEXITCODE)" }
    Run-Ssh 'tar -xf /tmp/biofut_wiki.tar -C /srv/biofut/data/wiki && rm /tmp/biofut_wiki.tar && du -sh /srv/biofut/data/wiki'
    Remove-Item $Tar, $List
}

# 2-3. PIN, service, nginx (server-side script above).
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Remote))
Run-Ssh "echo $b64 | base64 -d | bash"

# 4. DNS: proxied A record biofut.h-brain.org -> A1 (same token file as C:\dev\_web\cf.sh).
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Token = (Get-Content $env:CF_TOKEN_FILE -Raw).Trim()
$Api   = "https://api.cloudflare.com/client/v4/zones/$env:CF_ZONE_ID/dns_records"
$H     = @{ Authorization = "Bearer $Token" }
$found = Invoke-RestMethod -Headers $H -Uri "${Api}?name=biofut.h-brain.org"
if ($found.result.Count -eq 0) {
    $body = @{ type = 'A'; name = 'biofut'; content = $HostIp; proxied = $true; ttl = 1 } | ConvertTo-Json
    $r = Invoke-RestMethod -Method Post -Headers $H -ContentType 'application/json' -Uri $Api -Body $body
    "DNS created: $($r.success)"
} else {
    'DNS record already exists'
}

# 5. Public check (DNS can take a minute).
Start-Sleep 20
try   { 'public ' + (Invoke-WebRequest -UseBasicParsing https://biofut.h-brain.org/).StatusCode }
catch { "public check failed (retry in a minute): $($_.Exception.Message)" }
