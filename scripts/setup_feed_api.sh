#!/bin/bash
# =============================================================================
# Generate private Feed API key and write secure documentation
# =============================================================================
set -euo pipefail

REPO_DIR="/var/www/wtracker"
DOCS_DIR="$REPO_DIR/docs/api"
SECURE_DIR="$REPO_DIR/docs/secure"
ENV_FILE="$REPO_DIR/.env"
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
GENERATED=$(date -u '+%Y-%m-%d %H:%M UTC')
BASE_PROD="https://dramvalue.com/api/v1/feed"
BASE_LOCAL="http://localhost:8002/api/v1/feed"

mkdir -p "$DOCS_DIR" "$SECURE_DIR"

# ---------------------------------------------------------------------------
# API_KEY.txt
# ---------------------------------------------------------------------------
echo "$API_KEY" > "$DOCS_DIR/API_KEY.txt"
chmod 600 "$DOCS_DIR/API_KEY.txt"

# ---------------------------------------------------------------------------
# CONNECTION.md (short card)
# ---------------------------------------------------------------------------
cat > "$DOCS_DIR/CONNECTION.md" << EOF
# DramValue Private Feed API

Generated: $GENERATED

## Base URL

\`\`\`
$BASE_PROD
\`\`\`

Local (server only):

\`\`\`
$BASE_LOCAL
\`\`\`

## API Key

\`\`\`
$API_KEY
\`\`\`

Also saved in \`API_KEY.txt\` and \`docs/secure/keychain.md\`.

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
| GET | \`/search?q=\` | Search bottles by name / brand |
| GET | \`/bottles/{id}\` | Bottle detail + trends + promo hints |
| GET | \`/bottles/{id}/prices\` | Bottle price history |
| GET | \`/bottles\` | Bottle catalog with aggregates |
| GET | \`/trending\` | Hot bottles for promo content |
| GET | \`/movers\` | Biggest 90d price gainers / losers |
| GET | \`/prices\` | Paginated prices (\`?days=30&page=1\`) |
| GET | \`/prices/recent\` | New prices since timestamp |
| GET | \`/market\` | Monthly auction market stats |

## Quick test

\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" $BASE_PROD/stats | jq .
\`\`\`

## Docs

- Full reference (no secrets): \`docs/api/API.md\`
- Keychain + OpenClaw: \`docs/secure/keychain.md\`
- Secure API copy: \`docs/secure/API.md\`

## Rate limits

- Most endpoints: 120 req/hour
- \`/prices/recent\`: 300 req/hour
- Catalog / market: 60 req/hour
EOF
chmod 600 "$DOCS_DIR/CONNECTION.md"

# ---------------------------------------------------------------------------
# docs/secure/keychain.md
# ---------------------------------------------------------------------------
cat > "$SECURE_DIR/keychain.md" << EOF
# DramValue — Private API Keychain

**CONFIDENTIAL** — Do not commit, share publicly, or paste into public chats.  
Generated / last verified: $GENERATED

---

## API key

\`\`\`
$API_KEY
\`\`\`

Also mirrored in:
- \`docs/api/API_KEY.txt\`
- Server \`.env\` as \`FEED_API_KEY\`

---

## Base URLs

| Env | Base |
|-----|------|
| Production | \`$BASE_PROD\` |
| Local | \`$BASE_LOCAL\` |

Site (for promo links): \`https://dramvalue.com\`

---

## Auth headers

\`\`\`
X-API-Key: $API_KEY
\`\`\`

or

\`\`\`
Authorization: Bearer $API_KEY
\`\`\`

---

## OpenClaw env

\`\`\`bash
export DRAMVALUE_API_KEY="$API_KEY"
export DRAMVALUE_API_BASE="$BASE_PROD"
\`\`\`

In \`~/.openclaw/openclaw.json\` skill entry (example):

\`\`\`json5
{
  skills: {
    entries: {
      "dramvalue-promo": {
        enabled: true,
        env: {
          DRAMVALUE_API_KEY: "$API_KEY",
          DRAMVALUE_API_BASE: "$BASE_PROD"
        }
      }
    }
  }
}
\`\`\`

---

## Quick curls (promo workflows)

### Health / stats
\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  $BASE_PROD/stats | jq .
\`\`\`

### Trending bottles (content ideas)
\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  "$BASE_PROD/trending?limit=10" | jq .
\`\`\`

### Price movers (gainers / losers)
\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  "$BASE_PROD/movers?direction=both&limit=5" | jq .
\`\`\`

### Search a specific bottle
\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  --get --data-urlencode "q=Macallan 18" \\
  "$BASE_PROD/search" | jq .
\`\`\`

### Bottle detail + trends (use id from search)
\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  "$BASE_PROD/bottles/123" | jq .
\`\`\`

### Recent prices poll
\`\`\`bash
curl -s -H "X-API-Key: $API_KEY" \\
  "$BASE_PROD/prices/recent?limit=50" | jq .
\`\`\`

---

## Full API documentation

See:
- **\`docs/api/API.md\`** — complete endpoint reference (safe to commit, no secrets)
- **\`docs/secure/API.md\`** — same docs + live-key examples
- **\`docs/api/CONNECTION.md\`** — short connection card (gitignored)

---

## Rotate key

\`\`\`bash
cd /var/www/wtracker
./scripts/setup_feed_api.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api
\`\`\`
EOF
chmod 600 "$SECURE_DIR/keychain.md"

# ---------------------------------------------------------------------------
# docs/secure/API.md — full docs + live examples
# ---------------------------------------------------------------------------
{
  echo "# DramValue Private Feed API — Full Documentation (secure copy)"
  echo ""
  echo "> Live credentials copy. Safe reference: \`docs/api/API.md\`. Key: \`docs/secure/keychain.md\`."
  echo ""
  cat "$DOCS_DIR/API.md"
  cat << EOF

---

## Live examples (this key)

\`\`\`bash
KEY="$API_KEY"
BASE="$BASE_PROD"

curl -s -H "X-API-Key: \$KEY" "\$BASE/" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/stats" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/trending?limit=10" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/movers?direction=both&limit=5" | jq .
curl -s -H "X-API-Key: \$KEY" --get --data-urlencode "q=Yamazaki" "\$BASE/search" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/bottles/1" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/bottles/1/prices?days=180" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/prices/recent?limit=50" | jq .
curl -s -H "X-API-Key: \$KEY" "\$BASE/market?months=12" | jq .
\`\`\`
EOF
} > "$SECURE_DIR/API.md"
chmod 600 "$SECURE_DIR/API.md"
chmod 700 "$SECURE_DIR"
chmod 700 "$DOCS_DIR"

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
if grep -q '^FEED_API_KEY=' "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^FEED_API_KEY=.*|FEED_API_KEY=$API_KEY|" "$ENV_FILE"
else
    echo "FEED_API_KEY=$API_KEY" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "[+] Feed API key generated"
echo "[+] Key file:     $DOCS_DIR/API_KEY.txt"
echo "[+] Connection:   $DOCS_DIR/CONNECTION.md"
echo "[+] Keychain:     $SECURE_DIR/keychain.md"
echo "[+] Secure API:   $SECURE_DIR/API.md"
echo "[+] Public API:   $DOCS_DIR/API.md"
echo "[+] .env updated with FEED_API_KEY"
echo ""
echo "Restart API to apply: docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api"
