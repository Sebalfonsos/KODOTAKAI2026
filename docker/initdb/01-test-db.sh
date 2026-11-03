#!/bin/sh
# Base de datos aislada para las pruebas automáticas (make test).
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE ${POSTGRES_DB}_test OWNER $POSTGRES_USER;"
