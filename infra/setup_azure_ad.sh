#!/usr/bin/env bash
# infra/setup_azure_ad.sh
#
# Provisions the Azure AD app registration and security group for Sapphire.
#
# What this does:
#   1. Creates a user-assigned Managed Identity (id-sapphire-prod)
#   2. Creates the "Sapphire" app registration (single-tenant)
#   3. Adds a client secret and stores it in Key Vault
#   4. Creates the "Sapphire Users" security group
#   5. Grants the Managed Identity GroupMember.Read.All on Microsoft Graph
#      so the app can check group membership without a user-delegated token
#
# Run once:
#   az login
#   bash infra/setup_azure_ad.sh
#
# After running, add these to your .env (printed at the end):
#   AZURE_AD_TENANT_ID, AZURE_AD_CLIENT_ID, AZURE_AD_GROUP_ID

set -euo pipefail

RESOURCE_GROUP="rg-sapphire-prod"
LOCATION="eastus2"
APP_NAME="Sapphire"
GROUP_NAME="Sapphire Users"
IDENTITY_NAME="id-sapphire-prod"
KEYVAULT_NAME="kv-sapphire-okeke"
REDIRECT_URI="http://localhost:8000/api/v1/auth/microsoft/callback"

TENANT_ID=$(az account show --query tenantId -o tsv)
echo "Tenant: $TENANT_ID"

# ── 1. Managed Identity ────────────────────────────────────────────────────────
echo ""
echo "==> Creating managed identity: $IDENTITY_NAME"
az identity create \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

IDENTITY_PRINCIPAL_ID=$(az identity show \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv)
IDENTITY_CLIENT_ID=$(az identity show \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query clientId -o tsv)
echo "    principal ID : $IDENTITY_PRINCIPAL_ID"
echo "    client ID    : $IDENTITY_CLIENT_ID"

# ── 2. App Registration ────────────────────────────────────────────────────────
echo ""
echo "==> Creating app registration: $APP_NAME"
APP_ID=$(az ad app create \
  --display-name "$APP_NAME" \
  --sign-in-audience "AzureADMyOrg" \
  --web-redirect-uris "$REDIRECT_URI" \
  --query appId -o tsv)
echo "    App (client) ID: $APP_ID"

echo "==> Creating service principal for app"
az ad sp create --id "$APP_ID" --output none

# ── 3. Client Secret → Key Vault ──────────────────────────────────────────────
echo ""
echo "==> Creating client secret (2 years)"
CLIENT_SECRET=$(az ad app credential reset \
  --id "$APP_ID" \
  --years 2 \
  --query password -o tsv)

echo "==> Storing client secret in Key Vault: $KEYVAULT_NAME"
az keyvault secret set \
  --vault-name "$KEYVAULT_NAME" \
  --name "azure-ad-client-secret" \
  --value "$CLIENT_SECRET" \
  --output none
echo "    Stored as: azure-ad-client-secret"

# ── 4. Security Group ──────────────────────────────────────────────────────────
echo ""
echo "==> Creating security group: $GROUP_NAME"
GROUP_ID=$(az ad group create \
  --display-name "$GROUP_NAME" \
  --mail-nickname "SapphireUsers" \
  --query id -o tsv)
echo "    Group object ID: $GROUP_ID"

# ── 5. Grant Managed Identity GroupMember.Read.All on Microsoft Graph ──────────
echo ""
echo "==> Granting GroupMember.Read.All to managed identity on Microsoft Graph"

# Microsoft Graph service principal (well-known ID)
GRAPH_SP_ID=$(az ad sp show --id "00000003-0000-0000-c000-000000000000" --query id -o tsv)
ROLE_ID=$(az ad sp show \
  --id "00000003-0000-0000-c000-000000000000" \
  --query "appRoles[?value=='GroupMember.Read.All'].id" -o tsv)
echo "    Graph SP     : $GRAPH_SP_ID"
echo "    Role ID      : $ROLE_ID"

az rest \
  --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${IDENTITY_PRINCIPAL_ID}/appRoleAssignments" \
  --body "{
    \"principalId\": \"${IDENTITY_PRINCIPAL_ID}\",
    \"resourceId\":  \"${GRAPH_SP_ID}\",
    \"appRoleId\":   \"${ROLE_ID}\"
  }" \
  --output none
echo "    Permission granted (no admin consent required for app roles)"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo " Done. Add these to your .env:"
echo "=========================================="
echo "AZURE_AD_TENANT_ID=$TENANT_ID"
echo "AZURE_AD_CLIENT_ID=$APP_ID"
echo "AZURE_AD_GROUP_ID=$GROUP_ID"
echo "AZURE_AD_REDIRECT_URI=$REDIRECT_URI"
echo ""
echo "AZURE_AD_CLIENT_SECRET is in Key Vault (azure-ad-client-secret)."
echo "Managed identity $IDENTITY_NAME has GroupMember.Read.All on Graph."
echo ""
echo "Next steps:"
echo "  1. Add users to the '$GROUP_NAME' group:"
echo "     az ad group member add --group $GROUP_ID --member-id <user-object-id>"
echo "  2. Assign the managed identity to your Container App on deploy."
echo "  3. For local dev, 'az login' is used — set AZURE_AD_GROUP_ID='' to skip group check."
