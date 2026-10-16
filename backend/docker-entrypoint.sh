#!/bin/sh
# Make /data writable by the app user, then drop root and run the command.
# A host's persistent disk (Render, Railway) is usually mounted root-owned,
# which the image's own chown can't reach because the mount happens later.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    if [ "$(stat -c %U /data)" != "gazelens" ]; then
        chown -R gazelens:gazelens /data
    fi
    export HOME=/home/gazelens
    exec setpriv --reuid=gazelens --regid=gazelens --init-groups "$@"
fi

exec "$@"
