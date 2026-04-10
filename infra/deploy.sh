#!/usr/bin/env bash
# infra/deploy.sh — Full Sapphire stack deploy
#
# Prerequisites:
#   az login
#   gh auth login
#   Copy infra/params.example.json → infra/params.json and fill in secrets
#
# Usage:
#   chmod +x infra/deploy.sh && ./infra/deploy.sh

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

RG="rg-sapphire-prod"
SUB="cfcbaf7b-b9ac-4233-bc3d-37e94a074d92"
CA_NAME="ca-sapphire-prod"
ACS_NAME="acs-sapphire-prod"
EG_SUB_NAME="acs-inbound-calls"
ACS_RESOURCE_ID="/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.Communication/communicationServices/${ACS_NAME}"

# Detect GitHub repo from git remote (e.g. okekedev/sapphire)
GH_REPO=$(git remote get-url origin 2>/dev/null | sed -E 's|.*github\.com[:/]||;s|\.git$||' || echo "")

# ── Helpers ───────────────────────────────────────────────────────────────────

log() { echo ""; echo "==> $*"; }
ok()  { echo "   ✓ $*"; }

require_file() {
  if [ ! -f "$1" ]; then
    echo "ERROR: $1 not found. Copy infra/params.example.json → infra/params.json and fill in secrets."
    exit 1
  fi
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

require_file "infra/params.json"
az account show &>/dev/null || { echo "ERROR: Run 'az login' first."; exit 1; }

log "Starting Sapphire infrastructure deployment"
echo "   Resource group : $RG"
echo "   Subscription   : $SUB"
echo "   GitHub repo    : ${GH_REPO:-not detected}"

# ── 1. Bicep deployment ───────────────────────────────────────────────────────

log "1. Deploying infrastructure via Bicep (this takes ~5 minutes)..."
OUTPUTS=$(az deployment group create \
  --resource-group "$RG" \
  --subscription "$SUB" \
  --template-file infra/main.bicep \
  --parameters @infra/params.json \
  --query "properties.outputs" \
  --output json)

CA_URL=$(echo "$OUTPUTS"    | python3 -c "import json,sys; print(json.load(sys.stdin)['containerAppUrl']['value'])")
SWA_URL=$(echo "$OUTPUTS"   | python3 -c "import json,sys; print(json.load(sys.stdin)['staticWebAppUrl']['value'])")
SWA_TOKEN=$(echo "$OUTPUTS" | python3 -c "import json,sys; print(json.load(sys.stdin)['staticWebAppDeployToken']['value'])")
KV_URI=$(echo "$OUTPUTS"    | python3 -c "import json,sys; print(json.load(sys.stdin)['keyVaultUri']['value'])")

ok "Container App : $CA_URL"
ok "Static Web App: $SWA_URL"
ok "Key Vault     : $KV_URI"

# ── 2. Wait for Container App to be healthy ───────────────────────────────────

log "2. Waiting for Container App to pass health check..."
HEALTH_URL="${CA_URL}/api/v1/health"
for i in $(seq 1 40); do
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
  if [ "$HTTP" = "200" ]; then
    ok "Container App healthy (${HEALTH_URL})"
    break
  fi
  if [ "$i" -eq 40 ]; then
    echo "   WARNING: Container App not responding after 200s. Continuing anyway."
    echo "   Check logs: az containerapp logs show --name $CA_NAME --resource-group $RG --follow"
  fi
  echo "   HTTP ${HTTP} — retrying in 5s... ($i/40)"
  sleep 5
done

# ── 3. Event Grid subscription ────────────────────────────────────────────────

log "3. Creating Event Grid subscription for ACS inbound calls..."
EG_ENDPOINT="${CA_URL}/api/v1/acs/incoming"

if az eventgrid event-subscription show \
    --name "$EG_SUB_NAME" \
    --source-resource-id "$ACS_RESOURCE_ID" &>/dev/null; then

  az eventgrid event-subscription update \
    --name "$EG_SUB_NAME" \
    --source-resource-id "$ACS_RESOURCE_ID" \
    --endpoint "$EG_ENDPOINT" \
    --output none
  ok "Event Grid subscription updated → $EG_ENDPOINT"
else
  az eventgrid event-subscription create \
    --name "$EG_SUB_NAME" \
    --source-resource-id "$ACS_RESOURCE_ID" \
    --endpoint "$EG_ENDPOINT" \
    --endpoint-type webhook \
    --event-delivery-schema cloudeventschemav1_0 \
    --included-event-types "Microsoft.Communication.IncomingCall" \
    --output none
  ok "Event Grid subscription created → $EG_ENDPOINT"
fi

# ── 4. GitHub Actions secrets ─────────────────────────────────────────────────

log "4. Updating GitHub Actions secrets..."
if [ -n "$GH_REPO" ] && gh auth status &>/dev/null; then
  gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN --body "$SWA_TOKEN" --repo "$GH_REPO"
  ok "AZURE_STATIC_WEB_APPS_API_TOKEN set"

  # Optionally update subscription/tenant if they changed
  gh secret set AZURE_SUBSCRIPTION_ID --body "$SUB" --repo "$GH_REPO"
  ok "AZURE_SUBSCRIPTION_ID set"
else
  echo "   SKIP: gh not authenticated or repo not detected."
  echo "   Manually set AZURE_STATIC_WEB_APPS_API_TOKEN in GitHub Actions secrets:"
  echo "   ${SWA_TOKEN:0:20}..."
fi

# ── 5. Summary ────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Deployment complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Backend  : $CA_URL"
echo "  Frontend : $SWA_URL"
echo "  Key Vault: $KV_URI"
echo ""
echo "  Database : tables auto-created on first Container App start"
echo "  AI models: gpt-5 + gpt-5-mini deployed via Bicep"
echo "  Phones   : purchase numbers in Azure Portal → ACS → Phone Numbers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
