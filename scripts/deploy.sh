#!/usr/bin/env bash
set -euo pipefail
release="${1:?Usage: deploy.sh COMMIT_SHA}"
[[ "$release" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid revision'; exit 1; }
base=/opt/wardrobe-lab
target="$base/releases/$release"
env_file="$base/shared/.env"
[[ -f "$env_file" ]] || { echo 'Missing shared/.env'; exit 1; }
[[ -d "$target" ]] || { echo 'Missing release'; exit 1; }
exec 9>"$base/deploy.lock"
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
# A configuration edited as root may keep mode 600 but lose deploy ownership.
# Use the already-running trusted image to repair only this file's owner/mode.
# Never read or print credentials, pull an image, or grant world access.
if [[ ! -r "$env_file" ]]; then
    [[ ! -L "$env_file" ]] || { echo 'Refusing redirected configuration'; exit 1; }
    repair_image=$(docker inspect --format '{{.Config.Image}}' wardrobe-lab-app-1)
    [[ "$repair_image" =~ ^wardrobe-lab:[a-f0-9]{40}$ ]] || { echo 'No trusted running app image for configuration permission repair'; exit 1; }
    echo 'Restoring configuration ownership for deployment account (values unchanged)'
    docker run --rm --pull never --network none --read-only --user 0 \
        --cap-drop ALL --cap-add CHOWN --cap-add FOWNER \
        --mount "type=bind,src=$env_file,dst=/repair.env" \
        --entrypoint python "$repair_image" -c \
        'import os,stat,sys; p="/repair.env"; assert stat.S_ISREG(os.stat(p,follow_symlinks=False).st_mode); os.chown(p,int(sys.argv[1]),int(sys.argv[2])); os.chmod(p,0o600)' \
        "$(id -u)" "$(id -g)"
    [[ -r "$env_file" ]] || { echo 'Configuration remains unreadable; stopped before service changes'; exit 1; }
fi
previous=$(readlink -f "$base/current" || true)
cd "$target"
export LAB_APP_IMAGE="wardrobe-lab:$release"
export LAB_USE_TENCENT_MIRRORS=true
echo 'Building on Lighthouse using Tencent Debian and PyPI mirrors'
docker compose --progress plain --env-file "$env_file" -p wardrobe-lab build app
# Caddy still uses Docker's existing registry configuration; download before updating services.
docker compose --env-file "$env_file" -p wardrobe-lab pull caddy
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
        echo "Deployment healthy: $release"
        exit 0
    fi
    sleep 2
done
false
