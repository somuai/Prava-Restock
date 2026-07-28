#!/bin/sh
set -eu

# This verifies the image-local executable boundary only. It performs no npm
# operation, does not pass a remote URL, and cannot start OAuth or call Zepto.
version="$(python -c 'from merchant.zepto_mcp import MCP_REMOTE_VERSION; print(MCP_REMOTE_VERSION)')"
binary="$(python -c 'from merchant.zepto_mcp import MCP_REMOTE_BINARY; print(MCP_REMOTE_BINARY)')"

printf 'Node: '
node --version

if [ ! -x "${binary}" ]; then
    echo "FAIL: image-local mcp-remote executable is missing" >&2
    exit 1
fi
installed="$(node -p "require('/opt/zepto-mcp/node_modules/mcp-remote/package.json').version")"
if [ "${installed}" != "${version}" ]; then
    echo "FAIL: image contains mcp-remote ${installed}; expected ${version}" >&2
    exit 1
fi
echo "PASS: image-local mcp-remote@${version} is executable (offline check)"
