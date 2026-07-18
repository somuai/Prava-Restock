#!/usr/bin/env bash

set -u

if [[ $# -ne 1 || -z "${1}" ]]; then
  echo "Usage: $0 <base-url>" >&2
  exit 2
fi

base_url="${1%/}"
failed=0

auth_token="${RESTOCK_API_TOKEN:-restock-local-demo-token}"

for path in / /app/ /health /ready /capabilities /metrics /audit-log /notifications/pending; do
  if curl --fail --silent --show-error --max-time 15 \
    --header "Authorization: Bearer ${auth_token}" \
    --output /dev/null "${base_url}${path}"; then
    echo "PASS ${path}"
  else
    echo "FAIL ${path}" >&2
    failed=1
  fi
done

exit "${failed}"
