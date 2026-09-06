#!/bin/sh
set -eu

python -m drumscribe_api.model_bundle install --root /app
exec "$@"
