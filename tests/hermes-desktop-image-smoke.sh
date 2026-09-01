#!/bin/bash
set -Eeuo pipefail

for command_name in \
    dbus-launch gnome-keyring-daemon hermes-desktop pelagian-layoutd \
    pelagian-shellctl secret-tool wlrctl; do
    command -v "$command_name" >/dev/null
done

test -x /usr/local/bin/grotto-hermes-desktop-session
test -r /usr/share/grotto/hermes-desktop-source-revision
test "$(cat /usr/share/grotto/hermes-desktop-source-revision)" = \
    5fc308a70719a83cccdbba4c0e39c23f5a8239d5
test "${HERMES_DESKTOP_USER_DATA_DIR:-}" = /config/hermes-desktop
test "${HERMES_DESKTOP_PASSWORD_STORE:-}" = gnome-libsecret
pelagian-shellctl status >/dev/null
pelagian-shellctl config show >/dev/null
pelagian-layoutd status >/dev/null
for path in /config /workspace /tools /home/linuxbrew/.linuxbrew /cache; do
    test -d "$path"
done
