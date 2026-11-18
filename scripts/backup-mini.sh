#!/usr/bin/env bash
# Backup deployment it-tools trên mini PC trước khi update.
# Chạy trên mini PC trong /home/mini/Software/it-tools:
#   ./backup.sh
set -euo pipefail

APP_DIR="/home/mini/Software/it-tools"
BACKUP_ROOT="/home/mini/Software/it-tools-backup"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"

mkdir -p "$DEST"
echo "[backup] $DEST"

# 1. File compose + env
for f in docker-compose.yml docker-compose.yaml compose.yml compose.yaml .env .env.example; do
  [ -f "$APP_DIR/$f" ] && cp -v "$APP_DIR/$f" "$DEST/"
done

# 2. Trạng thái container + image đang chạy
{
  echo "=== docker ps ==="
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  echo
  echo "=== images ==="
  docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}' | grep -iE 'tool|convert|stirling|omni' || true
} | tee "$DEST/docker-state.txt"

# 3. Inspect từng container liên quan
for c in it-tools-fork it-tools-converter it-tools Stirling-PDF omni-tools; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
    docker inspect "$c" > "$DEST/inspect-$c.json"
    echo "[backup] inspect $c OK"
  fi
done

# 4. Backup volumes của các container trên (nếu có)
for c in it-tools-fork it-tools-converter Stirling-PDF omni-tools; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
    vols="$(docker inspect -f '{{ range .Mounts }}{{ if eq .Type "volume" }}{{ .Name }} {{ end }}{{ end }}' "$c")"
    for v in $vols; do
      echo "[backup] volume $v (container $c)"
      docker run --rm -v "$v:/data:ro" -v "$DEST:/out" alpine \
        tar -czf "/out/volume-$v.tar.gz" -C /data . || echo "[warn] backup volume $v thất bại"
    done
  fi
done

echo "[backup] xong: $DEST"
ls -la "$DEST"
