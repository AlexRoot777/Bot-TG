#!/usr/bin/env bash
set -euo pipefail

# Генератор секрета MTProto в формате dd + 32 hex символа.
# Можно использовать как PROXY_GEN_CMD.
printf 'dd%s\n' "$(openssl rand -hex 16)"