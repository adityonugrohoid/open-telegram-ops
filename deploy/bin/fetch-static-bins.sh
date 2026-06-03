#!/usr/bin/env bash
# Fetch the official static x86_64 binaries that the OpenClaw `session-logs`
# skill needs (jq + ripgrep), into this directory. They are bind-mounted into
# the stock gateway container at /usr/local/bin (see docker-compose.yml), so the
# skill resolves to R/eligible without baking a custom gateway image.
#
# Pinned, official upstream sources only (no third-party taps). Re-run after a
# version bump. Binaries are gitignored; this script is the tracked source.
set -euo pipefail
cd "$(dirname "$0")"

JQ_VERSION="1.7.1"
RG_VERSION="14.1.1"

JQ_URL="https://github.com/jqlang/jq/releases/download/jq-${JQ_VERSION}/jq-linux-amd64"
RG_URL="https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl.tar.gz"

# sha256 of the fetched artifacts; verified on first download (2026-06-05).
JQ_SHA256="5942c9b0934e510ee61eb3e30273f1b3fe2590df93933a93d7c58b81d19c8ff5"
RG_SHA256="f401154e2393f9002ac77e419f9ee5521c18f4f8cd3e32293972f493ba06fce7"

echo "Fetching jq ${JQ_VERSION}..."
curl -fsSL -o jq "$JQ_URL"
echo "${JQ_SHA256}  jq" | sha256sum -c -
chmod +x jq

echo "Fetching ripgrep ${RG_VERSION}..."
curl -fsSL -o /tmp/rg.tar.gz "$RG_URL"
tar -xzf /tmp/rg.tar.gz -C /tmp
cp "/tmp/ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl/rg" ./rg
echo "${RG_SHA256}  rg" | sha256sum -c -
chmod +x rg
rm -rf /tmp/rg.tar.gz "/tmp/ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl"

echo "Done. Versions:"
./jq --version
./rg --version | head -1
