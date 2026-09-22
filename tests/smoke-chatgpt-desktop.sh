#!/bin/bash
set -Eeuo pipefail
exec "$(dirname "$0")/smoke-desktop.sh" chatgpt "${GROTTO_CHATGPT_DESKTOP_IMAGE:-grotto-chatgpt-desktop:dev}"
