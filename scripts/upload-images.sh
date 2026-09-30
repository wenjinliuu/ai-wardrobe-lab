#!/usr/bin/env bash
set -euo pipefail
bundle="${1:?Usage: upload-images.sh BUNDLE COMMIT_SHA}"
revision="${2:?Missing commit SHA}"
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid revision'; exit 1; }
remote="/opt/wardrobe-lab/releases/$revision/images.tar.gz"
total=$(stat -c %s "$bundle")
[[ "$total" -gt 0 ]] || { echo 'Empty bundle'; exit 1; }
poll="${UPLOAD_POLL_INTERVAL:-30}"
stall="${UPLOAD_STALL_SECONDS:-180}"
[[ "$poll" =~ ^[1-9][0-9]*$ && "$stall" =~ ^[1-9][0-9]*$ ]] || exit 1
printf 'Image bundle: %s bytes (%s MiB). Reporting progress every %ss.\n' "$total" "$((total / 1048576))" "$poll"
# Remove only the previous incomplete bundle for this exact revision.
ssh lighthouse "df -h /opt/wardrobe-lab; rm -f '$remote'"
setsid scp "$bundle" "lighthouse:$remote" &
upload_pid=$!
cleanup() { kill -- "-$upload_pid" 2>/dev/null || true; wait "$upload_pid" 2>/dev/null || true; }
trap cleanup EXIT
started=$SECONDS
last_change=$SECONDS
previous=0
probe_failures=0
while kill -0 "$upload_pid" 2>/dev/null; do
    sleep "$poll"
    if ! kill -0 "$upload_pid" 2>/dev/null; then break; fi
    if ! bytes=$(timeout 25s ssh lighthouse "stat -c %s '$remote' 2>/dev/null || echo 0"); then
        probe_failures=$((probe_failures + 1))
        echo "Progress probe failed ($probe_failures/3); upload result is not yet known."
        [[ "$probe_failures" -lt 3 ]] || exit 1
        continue
    fi
    probe_failures=0
    [[ "$bytes" =~ ^[0-9]+$ ]] || { echo 'Invalid progress response'; exit 1; }
    elapsed=$((SECONDS - started))
    printf 'Uploaded %s / %s bytes (%s%%); elapsed %ss; average %s KiB/s.\n' "$bytes" "$total" "$((bytes * 100 / total))" "$elapsed" "$((bytes / 1024 / (elapsed + 1)))"
    if [[ "$bytes" -gt "$previous" ]]; then
        previous=$bytes
        last_change=$SECONDS
    elif [[ "$((SECONDS - last_change))" -ge "$stall" ]]; then
        echo "Upload stalled: remote file has not grown for ${stall}s. Stopping without starting services."
        exit 1
    fi
done
wait "$upload_pid"
trap - EXIT
echo 'Image transfer completed; workflow will verify SHA256 next.'
