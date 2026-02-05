#!/bin/sh
set -e

TOKEN="$1"

if [ -z "$TOKEN" ]; then
    echo "Error: Token required."
    echo "Usage: fetch-nord-key <YOUR_TOKEN>"
    exit 1
fi

echo "Fetching Credentials for Token..."
# Using curl -u "token:VALUE" as requested
OUTPUT=$(curl -s -u "token:$TOKEN" "https://api.nordvpn.com/v1/users/services/credentials")

# Check for error in output (simple check)
if echo "$OUTPUT" | grep -q "Invalid authorization"; then
    echo "Error: Invalid authorization token."
    exit 1
fi

KEY=$(echo "$OUTPUT" | jq -r .nordlynx_private_key)

if [ "$KEY" = "null" ] || [ -z "$KEY" ]; then
    echo "Error: Could not retrieve private key. Response:"
    echo "$OUTPUT"
    exit 1
fi

echo ""
echo "============================================================"
echo "FOUND NORDVPN PRIVATE KEY:"
echo "$KEY"
echo "============================================================"
echo "Use this key as NORD_PRIVATE_KEY for the config generator."
echo ""
