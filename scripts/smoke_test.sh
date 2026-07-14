#!/usr/bin/env bash

set -u

if [[ $# -ne 1 || -z "${1}" ]]; then
  echo "Usage: $0 <base-url>" >&2
  exit 2
fi

base_url="${1%/}"
failed=0

for path in / /health /audit-log /notifications/pending; do
  if curl --fail --silent --show-error --max-time 15 \
    --output /dev/null "${base_url}${path}"; then
    echo "PASS ${path}"
  else
    echo "FAIL ${path}" >&2
    failed=1
  fi
done

exit "${failed}"
