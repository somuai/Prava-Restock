#!/usr/bin/env bash

set -u

if [[ $# -ne 1 || -z "${1}" ]]; then
  echo "Usage: $0 <base-url>" >&2
  exit 2
fi

base_url="${1%/}"
failed=0

for path in / /app/ /health /ready /capabilities /metrics; do
  if curl --fail --silent --show-error --max-time 15 \
    --output /dev/null "${base_url}${path}"; then
    echo "PASS ${path}"
  else
    echo "FAIL ${path}" >&2
    failed=1
  fi
done

# Production behavioral endpoints require a signed session token. Accept one
# explicitly for a full smoke test; otherwise prove they are not public.
auth_token="${RESTOCK_SMOKE_AUTH_TOKEN:-}"
for path in /audit-log /notifications/pending; do
  if [[ -n "${auth_token}" ]]; then
    if curl --fail --silent --show-error --max-time 15 \
      --header "Authorization: Bearer ${auth_token}" \
      --output /dev/null "${base_url}${path}"; then
      echo "PASS ${path} (authenticated)"
    else
      echo "FAIL ${path} (authenticated)" >&2
      failed=1
    fi
    continue
  fi

  status_code="$(curl --silent --show-error --max-time 15 \
    --output /dev/null --write-out '%{http_code}' "${base_url}${path}")"
  if [[ "${status_code}" == "401" ]]; then
    echo "PASS ${path} (authentication required)"
  else
    echo "FAIL ${path} (expected 401, got ${status_code})" >&2
    failed=1
  fi
done

exit "${failed}"
