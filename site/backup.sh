#!/bin/sh
# Daily BioFut backup (biofut-backup.timer from deploy.ps1): the data the sheet and the repo can't rebuild, gzipped,
# kept 14 days in /srv/biofut-backup and in "BioFut backups" on the BioFut Drive (rclone remote "biofut":
# biofutufrgs@gmail.com, scope drive.file, so rclone sees only its own files). Never the secret, the phone maps,
# the members' messages, or what deploy.ps1 -Wiki/-Data re-uploads.
set -eu
d=/srv/biofut-backup
f=$d/biofut-$(date -u +%F).tar.gz
mkdir -p $d
# tar exit 1 = a file changed while it read it (the site saved): the archive is still whole
tar -czf $f -C /srv/biofut/data --exclude=secret --exclude=phones.json --exclude=mensagens.json \
  --exclude=avatars --exclude=media --exclude=sheet.csv . || [ $? = 1 ]
find $d -name 'biofut-*.tar.gz' -mtime +13 -delete
rclone copy $f "biofut:BioFut backups"
rclone delete "biofut:BioFut backups" --min-age 14d
