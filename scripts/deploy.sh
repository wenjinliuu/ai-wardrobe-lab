#!/usr/bin/env bash
set -euo pipefail
release="${1:?Usage: deploy.sh COMMIT_SHA [--prebuilt]}"
mode="${2:-}"
[[ -z "$mode" || "$mode" == --prebuilt ]] || { echo 'Invalid deployment mode'; exit 1; }
[[ "$release" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid revision'; exit 1; }
base=/opt/wardrobe-lab
target="$base/releases/$release"
env_file="$base/shared/.env"
[[ -f "$env_file" ]] || { echo 'Missing shared/.env'; exit 1; }
[[ -d "$target" ]] || { echo 'Missing release'; exit 1; }
exec 9>"$base/deploy.lock"
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
previous=$(readlink -f "$base/current" || true)
cd "$target"
export LAB_APP_IMAGE="wardrobe-lab:$release"
if [[ "$mode" == --prebuilt ]]; then
    [[ -f images.tar.gz ]] || { echo 'Missing prebuilt image bundle'; exit 1; }
    docker load -i images.tar.gz
    docker image inspect "$LAB_APP_IMAGE" caddy:2-alpine >/dev/null
else
    docker compose --env-file "$env_file" -p wardrobe-lab build app
fi
rollback() {
    echo 'Deployment health check failed; restoring previous release.'
    if [[ -n "$previous" && "$previous" != "$target" ]]; then
        export LAB_APP_IMAGE="wardrobe-lab:$(basename "$previous")"
        cd "$previous"
        docker compose --env-file "$env_file" -p wardrobe-lab up -d --no-build --pull never --force-recreate
        ln -sfn "$previous" "$base/current"
    fi
}
trap rollback ERR
docker compose --env-file "$env_file" -p wardrobe-lab up -d --no-build --pull never --force-recreate
for attempt in $(seq 1 30); do
    if docker compose --env-file "$env_file" -p wardrobe-lab exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)" >/dev/null 2>&1; then
        ln -sfn "$target" "$base/current"
        trap - ERR
        rm -f "$target/images.tar.gz"
        echo "Deployment healthy: $release"
        exit 0
    fi
    sleep 2
done
false
