#!/usr/bin/env bash
set -euo pipefail
INSTANCE="marketplace-sql"
echo "Deleting Cloud SQL instance ${INSTANCE}..."
gcloud sql instances delete "${INSTANCE}" --quiet
echo "Done."
