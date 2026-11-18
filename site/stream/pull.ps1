# Cup day, on the PC: every 10 minutes, move the finished recordings off the server (its disk is small).
# A segment is removed on the server only after the copy here has the same size. The marks file is copied, never removed.
# Needs $env:BIOFUT_SSH_KEY and $env:BIOFUT_HOST_IP, like deploy.ps1. Stop with Ctrl+C.
param([string]$Dest = 'L:\BioFut\stream', [int]$Minutes = 10)
$ErrorActionPreference = 'Continue'  # PS 5.1: native stderr must not abort the loop
$Key = $env:BIOFUT_SSH_KEY
$Target = "ubuntu@$($env:BIOFUT_HOST_IP)"
if (-not $Key -or -not $env:BIOFUT_HOST_IP) { throw 'set BIOFUT_SSH_KEY and BIOFUT_HOST_IP first' }
New-Item -ItemType Directory -Force $Dest | Out-Null

while ($true) {
    # path|size of every segment untouched for 11 minutes (a segment is 10 minutes long)
    $list = & ssh -o BatchMode=yes -i $Key $Target "find /srv/biofut-stream/rec -name '*.mp4' -mmin +11 -printf '%P|%s\n'"
    if ($LASTEXITCODE) { Write-Warning "ssh failed ($LASTEXITCODE), trying again later" }
    foreach ($line in @($list | Where-Object { $_ })) {
        $rel, $size = $line.Split('|')
        $local = Join-Path $Dest ($rel -replace '/', '\')
        New-Item -ItemType Directory -Force (Split-Path $local) | Out-Null
        & scp -q -i $Key "${Target}:/srv/biofut-stream/rec/$rel" $local
        if ($LASTEXITCODE -or -not (Test-Path $local) -or (Get-Item $local).Length -ne [long]$size) {
            Write-Warning "copy of $rel incomplete: kept on the server"
            continue
        }
        & ssh -o BatchMode=yes -i $Key $Target "rm -- '/srv/biofut-stream/rec/$rel'"
        "{0:HH:mm} moved {1} ({2:N0} MB)" -f (Get-Date), $rel, ([long]$size / 1MB)
    }
    & scp -q -i $Key "${Target}:/srv/biofut/data/lances.jsonl" (Join-Path $Dest 'lances.jsonl') 2>$null
    $free = & ssh -o BatchMode=yes -i $Key $Target "df -h /srv | tail -1"
    "{0:HH:mm} server disk: {1}" -f (Get-Date), $free
    Start-Sleep -Seconds ($Minutes * 60)
}
