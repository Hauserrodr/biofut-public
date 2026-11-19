#!/bin/bash
# Once on the server (ubuntu, sudo), from the folder with mediamtx.yml and yt.sh. Safe to run again.
# Then: put YT_KEY=... in /etc/biofut-stream.env and BIOFUT_STREAM_PIN=... in /etc/biofut.env, restart both services.
set -euo pipefail
V=v1.21.4
T=mediamtx_${V}_linux_arm64.tar.gz
cd "$(dirname "$0")"

command -v ffmpeg >/dev/null || sudo apt-get install -y ffmpeg
if ! /usr/local/bin/mediamtx --version 2>/dev/null | grep -q "$V"; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/$T" "https://github.com/bluenviron/mediamtx/releases/download/$V/$T"
  curl -fsSL -o "$tmp/sums" "https://github.com/bluenviron/mediamtx/releases/download/$V/checksums.sha256"
  (cd "$tmp" && grep " $T\$" sums | sha256sum -c -)
  tar -xzf "$tmp/$T" -C "$tmp" mediamtx
  sudo install -m 755 "$tmp/mediamtx" /usr/local/bin/mediamtx
  rm -rf "$tmp"
fi

sudo install -D -m 644 mediamtx.yml /etc/mediamtx/biofut.yml
sudo install -m 755 yt.sh /usr/local/bin/biofut-yt.sh
sudo mkdir -p /srv/biofut-stream/rec
sudo chown -R ubuntu:ubuntu /srv/biofut-stream
if [ ! -f /etc/biofut-stream.env ]; then
  echo 'YT_KEY=' | sudo tee /etc/biofut-stream.env >/dev/null
  sudo chmod 600 /etc/biofut-stream.env
fi

sudo tee /etc/systemd/system/mediamtx-biofut.service >/dev/null <<'EOF'
[Unit]
Description=BioFut camera relay (mediamtx)
After=network-online.target biofut.service

[Service]
User=ubuntu
EnvironmentFile=-/etc/biofut-stream.env
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx/biofut.yml
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# WebRTC media: 8189 UDP and TCP, before the REJECT rule. The OCI security list needs the same ingress.
for p in udp tcp; do
  sudo iptables -C INPUT -p "$p" --dport 8189 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p "$p" --dport 8189 -j ACCEPT
done
sudo netfilter-persistent save >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable mediamtx-biofut >/dev/null
sudo systemctl restart mediamtx-biofut
sleep 2
systemctl is-active mediamtx-biofut
curl -fsS 127.0.0.1:9997/v3/paths/list
echo
df -h /srv | tail -1
