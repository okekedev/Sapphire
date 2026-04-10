// infra/main.bicep
// Provisions all Sapphire infrastructure from scratch.
//
// Deploy:
//   az deployment group create \
//     --resource-group rg-sapphire-prod \
//     --template-file infra/main.bicep \
//     --parameters @infra/params.json
//
// First-time only — grant the deploying principal KV Secrets Officer so it
// can write secrets during deployment:
//   az role assignment create \
//     --role "Key Vault Secrets Officer" \
//     --assignee <your-object-id> \
//     --scope /subscriptions/<sub>/resourceGroups/rg-sapphire-prod/providers/Microsoft.KeyVault/vaults/kv-sapphire-okeke

targetScope = 'resourceGroup'

// ── Parameters ───────────────────────────────────────────────────────────────

@description('Azure region. Defaults to resource group location.')
param location string = resourceGroup().location

// Public Azure AD values (safe as plain params / env vars)
@description('Azure AD tenant ID for user authentication.')
param azureAdTenantId string

@description('Azure AD app registration client ID (Sapphire app).')
param azureAdClientId string

@description('Object ID of the Sapphire Users group. Empty = skip group check.')
param azureAdGroupId string = ''

@description('OAuth redirect URI for Azure AD (frontend callback page).')
param azureAdRedirectUri string = 'https://swa-sapphire-prod.azurestaticapps.net/auth/callback'

@description('Frontend public URL — used for CORS and redirect URIs.')
param frontendUrl string = 'https://swa-sapphire-prod.azurestaticapps.net'

// Secrets
@secure()
@description('AES-256-GCM encryption key for credentials at rest. Generate: python3 -c "import secrets; print(secrets.token_urlsafe(32))"')
param encryptionKey string

@secure()
@description('FastAPI session secret key.')
param secretKey string

@secure()
@description('JWT HS256 signing secret.')
param jwtSecretKey string

@secure()
@description('Azure AD app client secret (user-facing OAuth flows). Can be eliminated once federated credentials are implemented.')
param azureAdClientSecret string

@secure()
@description('Google OAuth client secret (Business Profile, Ads).')
param googleClientSecret string

@secure()
@description('Google AI API key (Imagen / Gemini).')
param googleAiApiKey string

@secure()
@description('Meta app secret (Facebook Pages, Instagram, Ads).')
param metaAppSecret string

@secure()
@description('Microsoft OAuth client secret (Bing Ads).')
param microsoftClientSecret string

@secure()
@description('LinkedIn OAuth client secret.')
param linkedinClientSecret string

@secure()
@description('Twitter/X OAuth client secret.')
param twitterClientSecret string

@secure()
@description('TikTok OAuth client key (functions as a secret).')
param tiktokClientSecret string

@secure()
@description('Applyra API key.')
param applyraApiKey string

// Container registry (ghcr.io)
@description('GitHub username for pulling the backend image from ghcr.io.')
param ghcrUsername string = 'okekedev'

@secure()
@description('GitHub PAT with read:packages scope for ghcr.io.')
param ghcrToken string

// ── Resource names ────────────────────────────────────────────────────────────

var uamiName  = 'uami-sapphire-prod'
var kvName    = 'kv-sapphire-okeke'
var pgName    = 'pg-sapphire-prod'
var redisName = 'redis-sapphire-prod'
var acsName   = 'acs-sapphire-prod'
var aiName    = 'ai-sapphire-prod'
var caeName   = 'cae-sapphire-prod'
var caName    = 'ca-sapphire-prod'
var swaName   = 'swa-sapphire-prod'
var logName   = 'log-sapphire-prod'

// ── User-Assigned Managed Identity ────────────────────────────────────────────

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
}

// ── Log Analytics ─────────────────────────────────────────────────────────────

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── Key Vault ─────────────────────────────────────────────────────────────────

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true   // RBAC model, not legacy access policies
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enabledForDeployment: false
    enabledForTemplateDeployment: false
  }
}

// UAMI → Key Vault Secrets User (read secrets at runtime)
resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, uami.id, '4633458b-17de-408a-b874-0445c86b69e0')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e0')
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Key Vault Secrets ─────────────────────────────────────────────────────────
// App reads all of these at startup via _load_from_keyvault() using UAMI.

resource kvSecretEncryption 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'encryption-key'
  properties: { value: encryptionKey }
}

resource kvSecretSecretKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'secret-key'
  properties: { value: secretKey }
}

resource kvSecretJwtKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'jwt-secret-key'
  properties: { value: jwtSecretKey }
}

resource kvSecretAzureAdClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'azure-ad-client-secret'
  properties: { value: azureAdClientSecret }
}

resource kvSecretGoogleClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'google-client-secret'
  properties: { value: googleClientSecret }
}

resource kvSecretGoogleAiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'google-ai-api-key'
  properties: { value: googleAiApiKey }
}

resource kvSecretMetaAppSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'meta-app-secret'
  properties: { value: metaAppSecret }
}

resource kvSecretMicrosoftClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'microsoft-client-secret'
  properties: { value: microsoftClientSecret }
}

resource kvSecretLinkedinClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'linkedin-client-secret'
  properties: { value: linkedinClientSecret }
}

resource kvSecretTwitterClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'twitter-client-secret'
  properties: { value: twitterClientSecret }
}

resource kvSecretTiktokClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'tiktok-client-secret'
  properties: { value: tiktokClientSecret }
}

resource kvSecretApplyraApiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'applyra-api-key'
  properties: { value: applyraApiKey }
}

// ── Azure Cache for Redis (replaces Upstash) ──────────────────────────────────
// Standard C0 = 250 MB, SLA, no data loss. SSL only (port 6380).

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: redisName
  location: location
  properties: {
    sku: {
      name: 'Standard'
      family: 'C'
      capacity: 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisConfiguration: {}
  }
}

// Write Redis connection strings to KV so app picks them up via _load_from_keyvault()
var redisConnString = 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:6380'

resource kvSecretRedisUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'redis-url'
  properties: { value: redisConnString }
}

resource kvSecretCeleryBroker 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'celery-broker-url'
  properties: { value: '${redisConnString}/0' }
}

resource kvSecretCeleryBackend 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'celery-result-backend'
  properties: { value: '${redisConnString}/1' }
}

// ── PostgreSQL Flexible Server (Entra-only auth) ───────────────────────────────

resource pgServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: pgName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenant().tenantId
    }
    storage: { storageSizeGB: 32 }
    version: '16'
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
  }
}

// UAMI as PostgreSQL Entra administrator
resource pgAdmin 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2023-12-01-preview' = {
  parent: pgServer
  name: uami.properties.principalId
  properties: {
    principalType: 'ServicePrincipal'
    principalName: uamiName
    tenantId: tenant().tenantId
  }
  dependsOn: [pgServer]
}

resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: pgServer
  name: 'workforce'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// ── Azure Communication Services ──────────────────────────────────────────────
// Phone numbers are purchased separately and are NOT managed by this Bicep.
// Re-deploying this Bicep is safe — existing numbers are preserved.

resource acs 'Microsoft.Communication/communicationServices@2023-06-01-preview' = {
  name: acsName
  location: 'global'
  properties: {
    dataLocation: 'United States'
  }
}

// UAMI → Contributor on ACS (allows phone number provisioning + SMS)
resource acsContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acs.id, uami.id, 'b24988ac-6180-42a0-ab88-20f7382dd24c')
  scope: acs
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Azure AI Services (OpenAI) ────────────────────────────────────────────────
// Provisions the account and both model deployments.
// Deploy sequentially (dependsOn) — simultaneous deployments on the same account fail.

resource aiServices 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: aiName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: aiName
    publicNetworkAccess: 'Enabled'
  }
}

resource gpt5Mini 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: aiServices
  name: 'gpt-5-mini'
  sku: { name: 'GlobalStandard', capacity: 50 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: '2025-08-07'
    }
  }
}

resource gpt5 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: aiServices
  name: 'gpt-5'
  sku: { name: 'GlobalStandard', capacity: 30 }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5'
      version: '2025-08-07'
    }
  }
  dependsOn: [gpt5Mini]
}

// UAMI → Cognitive Services OpenAI User (allows inference API calls)
resource aiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, uami.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: aiServices
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Container App Environment ─────────────────────────────────────────────────

resource cae 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// ── Container App (backend) ───────────────────────────────────────────────────

resource ca 'Microsoft.App/containerApps@2023-11-02-preview' = {
  name: caName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  properties: {
    environmentId: cae.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        corsPolicy: {
          allowedOrigins: [frontendUrl]
          allowedMethods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
          allowCredentials: true
        }
      }
      registries: [
        {
          server: 'ghcr.io'
          username: ghcrUsername
          passwordSecretRef: 'ghcr-token'
        }
      ]
      secrets: [
        {
          name: 'ghcr-token'
          value: ghcrToken
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: 'ghcr.io/okekedev/sapphire-backend:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            // App
            { name: 'APP_ENV',               value: 'production' }
            { name: 'APP_NAME',              value: 'workforce' }
            { name: 'DEBUG',                 value: 'false' }
            // Identity — AZURE_CLIENT_ID tells DefaultAzureCredential which UAMI to use
            { name: 'AZURE_CLIENT_ID',       value: uami.properties.clientId }
            { name: 'UAMI_CLIENT_ID',        value: uami.properties.clientId }
            // Key Vault — app loads all secrets from KV at startup
            { name: 'AZURE_KEYVAULT_URL',    value: kv.properties.vaultUri }
            // Azure AD (public values, not secrets)
            { name: 'AZURE_AD_TENANT_ID',    value: azureAdTenantId }
            { name: 'AZURE_AD_CLIENT_ID',    value: azureAdClientId }
            { name: 'AZURE_AD_GROUP_ID',     value: azureAdGroupId }
            { name: 'AZURE_AD_REDIRECT_URI', value: azureAdRedirectUri }
            // AI Services
            { name: 'FOUNDRY_ENDPOINT',      value: 'https://${aiName}.cognitiveservices.azure.com' }
            { name: 'FOUNDRY_DEFAULT_MODEL', value: 'haiku' }
            // ACS — connection string empty; UAMI Contributor role used in production
            { name: 'ACS_ENDPOINT',          value: 'https://${acsName}.unitedstates.communication.azure.com' }
            // Database — Entra token auth; UAMI name is the PG principal
            { name: 'DATABASE_URL',          value: 'postgresql+asyncpg/${uamiName}@${pgServer.properties.fullyQualifiedDomainName}/workforce' }
            // Frontend
            { name: 'FRONTEND_URL',          value: frontendUrl }
            { name: 'CORS_ORIGINS',          value: '["${frontendUrl}"]' }
            // Email
            { name: 'EMAIL_PROVIDER',        value: 'sendgrid' }
            { name: 'EMAIL_FROM_ADDRESS',    value: 'outreach@seojames.io' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

// ── Static Web App (frontend) ─────────────────────────────────────────────────
// Deploy token output below — add as AZURE_STATIC_WEB_APPS_API_TOKEN in GitHub secrets.

resource swa 'Microsoft.Web/staticSites@2023-01-01' = {
  name: swaName
  location: location
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output containerAppUrl       string = 'https://${ca.properties.configuration.ingress.fqdn}'
output staticWebAppUrl       string = 'https://${swa.properties.defaultHostname}'
output staticWebAppDeployToken string = swa.listSecrets().properties.apiKey
output keyVaultName          string = kv.name
output keyVaultUri           string = kv.properties.vaultUri
output redisHostname         string = redis.properties.hostName
output postgresHost          string = pgServer.properties.fullyQualifiedDomainName
output uamiClientId          string = uami.properties.clientId
output uamiPrincipalId       string = uami.properties.principalId
