#!/bin/sh
# Starts as root only long enough to make the data folder writable by the app user,
# then drops privileges. So a fresh TrueNAS dataset works without setting permissions by hand.
set -e
APP_UID="${PUID:-568}"
APP_GID="${PGID:-568}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  chown -R "$APP_UID:$APP_GID" "$DATA_DIR" 2>/dev/null \
    || echo "warning: couldn't take ownership of $DATA_DIR; it must be writable by uid $APP_UID"
  exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups "$@"
fi
exec "$@"
