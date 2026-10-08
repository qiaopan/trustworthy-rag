#!/usr/bin/env bash
set -euo pipefail

# Pinned reference sources. Keep these unmodified; project contributions live in src/.
mkdir -p third_party
if [[ ! -d third_party/BIPIA/.git ]]; then
  git clone --depth 1 https://github.com/microsoft/BIPIA.git third_party/BIPIA
fi
if [[ ! -d third_party/PIGuard/.git ]]; then
  git clone --depth 1 https://github.com/leolee99/PIGuard.git third_party/PIGuard
fi

printf 'BIPIA: '
git -C third_party/BIPIA rev-parse --short HEAD
printf 'PIGuard: '
git -C third_party/PIGuard rev-parse --short HEAD
