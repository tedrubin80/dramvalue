#!/bin/bash
# =============================================================================
# Generate private Feed API key and write FTP-only documentation
# =============================================================================
set -euo pipefail

REPO_DIR="/var/www/wtracker"
DOCS_DIR="$REPO_DIR/docs/api"
ENV_FILE="$REPO_DIR/.env"
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

mkdir -p "$DOCS_DIR"

# Write key file
echo "$API_KEY" > "$DOCS_DIR/API_KEY.txt"
chmod 600 "$DOCS_DIR/API_KEY.txt"

# Write connection guide with live key
cat > "$DOCS_DIR/CONNECTION.md" << EOF
# DramValue Private Feed API

Generated: $(date -u '+%Y-%m-%d %H:%M UTC')

## Base URL

\`\`\`
https://dramvalue.com/api/v1/feed
\`\`\`

Local (server only):

\`\`\`
http://localhost:8002/api/v1/feed
\`\`\`

## API Key

\`\`\`
$API_KEY
\`\`\`

Also saved in \`API_KEY.txt\` in this folder.

## Authentication

\`\`\`
X-API-Key: $API_KEY
\`\`\`

or

\`\`\`
Authorization: Bearer $API_KEY
\`\`\`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | \`/\` | Feed index |
| GET | \`/stats\` | Database summary counts |
| GET | \`/prices\` | Paginated prices (\`?days=30&page=1&page_size=100\`) |
| GET | \`/prices/recent\` | New prices since timestamp |
| GET | \`/bottles\` | Bottle catalog with aggregates |
| GET | \`/market\` | Monthly auction market stats |

## Quick test

\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" https://dramvalue.com/api/v1/feed/stats | jq .
\`\`\`

## Poll new prices (for JSON feed publishing)

\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  "https://dramvalue.com/api/v1/feed/prices/recent?limit=100" | jq .
\`\`\`

Use \`meta.generated_at\` from the response as the \`since\` parameter on the next poll.

## Rate limits

- Most endpoints: 120 req/hour
- \`/prices/recent\`: 300 req/hour
EOF

chmod 600 "$DOCS_DIR/CONNECTION.md"
chmod 700 "$DOCS_DIR"

# Update .env
if grep -q '^FEED_API_KEY=' "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^FEED_API_KEY=.*|FEED_API_KEY=$API_KEY|" "$ENV_FILE"
else
    echo "FEED_API_KEY=$API_KEY" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "[+] Feed API key generated"
echo "[+] Key file:    $DOCS_DIR/API_KEY.txt"
echo "[+] Docs:        $DOCS_DIR/CONNECTION.md"
echo "[+] .env updated with FEED_API_KEY"
echo ""
echo "Restart API to apply: docker compose restart api"
