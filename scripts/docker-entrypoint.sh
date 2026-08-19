#!/usr/bin/env sh
set -e

if [ "${DB_ENGINE}" = "mysql" ]; then
  echo "Waiting for MySQL at ${DB_HOST:-mysql}:${DB_PORT:-3306}..."
  until nc -z "${DB_HOST:-mysql}" "${DB_PORT:-3306}"; do
    sleep 1
  done
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${WAIT_FOR_MIGRATIONS:-0}" = "1" ]; then
  echo "Waiting for Django migrations to finish..."
  until python manage.py migrate --check >/dev/null 2>&1; do
    sleep 2
  done
fi

if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
