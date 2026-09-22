#!/bin/bash
set -Eeuo pipefail
exec "$(dirname "$0")/smoke-desktop.sh" hermes "${GROTTO_HERMES_DESKTOP_IMAGE:-grotto-hermes-desktop:dev}"
