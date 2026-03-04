#!/usr/bin/env sh
set -e

npm run db:generate
npm run start -- -p "${PORT:-8080}"
