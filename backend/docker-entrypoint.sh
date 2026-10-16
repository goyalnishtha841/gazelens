#!/bin/sh
# Make /data writable by the app user, then drop root and run the command.
# A host's persistent disk (Render, Railway) is usually mounted root-owned,
# which the image's own chown can't reach because the mount happens later.
# Hosts that already start the container as uid 1000 (Hugging Face Spaces)
# skip straight to the command.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    if [ "$(stat -c %U /data)" != "gazelens" ]; then
        chown -R gazelens:gazelens /data
    fi
    exec setpriv --reuid=gazelens --regid=gazelens --init-groups "$@"
fi

exec "$@"
