// The Container Apps environment and the two deployables.

@description('Where everything goes.')
param location string

@description('Environment discriminator — dev or prod.')
param env string

@description('Tags applied to every resource.')
param tags object

@description('The subnet from network.bicep that this environment is injected into.')
param infrastructureSubnetId string

@description('The Log Analytics workspace resource id. A diagnostic setting routes the environment logs there; the environment itself is told nothing about the workspace, which is what keeps this template free of a shared key.')
param logAnalyticsWorkspaceId string

@description('Where the identity provider publishes its discovery document. Required whenever AUTH_MODE is entra, which in a deployment it always is.')
param oidcAuthority string

@description('The audience every accepted token must carry. Comma-separated when one API is known by more than one name.')
param oidcAudience string

@description('Application Insights connection string, for OTel.')
param insightsConnectionString string

@description('Resource id of the user-assigned identity everything runs as.')
param identityId string

@description('Client id of that identity, which the app needs to pick it up from DefaultAzureCredential.')
param identityClientId string

@description('Registry hostname, e.g. crchariedev0000.azurecr.io.')
param registryLoginServer string

@description('Key Vault URI, for secret references.')
param keyVaultUri string

@description('Image tag to deploy. A git sha in the pipeline; a placeholder until WP12.2 pushes one.')
param imageTag string

@description('Postgres hostname, from postgres.bicep.')
param postgresHost string

@description('The platform database name.')
param postgresDatabase string

@description('The owner/migration login. Only the migration job is given it; the API connects as charie_app and owns nothing.')
param postgresAdminLogin string

@description('Blob endpoint, for the artifact store.')
param blobEndpoint string

@description('Minimum replicas. Zero is the point of Container Apps for a dev environment; prod may want one to avoid a cold start.')
@minValue(0)
param minReplicas int

@description('Maximum replicas, so a runaway cannot scale into a bill.')
@minValue(1)
param maxReplicas int

@description('Deploy the two container apps. False for the first pass of a deploy, before the vault has been seeded and before the migration has run — an app revision cannot start without its secrets, and must not start before its schema.')
param deployApps bool = true

@description('Deploy the migration job. Separated from deployApps so a deploy can create the job, run it, and only then roll the apps — which is the ordering the plan requires and the one a single flag cannot express.')
param deployJobs bool = true

// Named here rather than inline, so the set of secrets the platform expects is one readable list.
var secretNames = {
  metaApiKey: 'meta-api-key'
  appDatabasePassword: 'app-database-password'
  databasePassword: 'database-password'
}

// Unconditional, and it belongs in phase 1 after all.
resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-charie-${env}'
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      // The environment is not internal: `web` needs a public hostname.
      internal: false
    }
    // `azure-monitor`, not `log-analytics`, and the difference is a credential.
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Shared by both apps: the registry they pull from, the identity they use.
var registryConfig = [
  {
    server: registryLoginServer
    identity: identityId
  }
]

var commonEnv = [
  {
    name: 'ENV'
    value: env
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: insightsConnectionString
  }
  {
    // What `DefaultAzureCredential` needs in order to pick the user-assigned identity rather...
    name: 'AZURE_CLIENT_ID'
    value: identityClientId
  }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'ca-charie-api-${env}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      // External, and the previous `false` made the product unusable.
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: registryConfig
      secrets: [
        {
          name: secretNames.metaApiKey
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.metaApiKey}'
          identity: identityId
        }
        {
          name: secretNames.appDatabasePassword
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.appDatabasePassword}'
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${registryLoginServer}/charie-api:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnv, [
            {
              // Built here rather than stored, so the password is the only part that comes from...
              name: 'APP_DATABASE_URL'
              value: 'postgresql+asyncpg://charie_app@${postgresHost}:5432/${postgresDatabase}?ssl=require'
            }
            {
              name: 'APP_DB_PASSWORD'
              secretRef: secretNames.appDatabasePassword
            }
            {
              name: 'META_API_KEY'
              secretRef: secretNames.metaApiKey
            }
            {
              // The model configuration, which this template did not have and the product...
              name: 'LLM_PROVIDERS'
              value: 'meta'
            }
            {
              name: 'LLM_MODELS'
              value: '{"meta":{"small":"muse-spark-1.3","mid":"muse-spark-1.3","strong":"muse-spark-1.3"}}'
            }
            {
              // Composing is the long generation and the cheapest place to save.
              name: 'LLM_ROLE_MAP'
              value: '{"compose":"small"}'
            }
            {
              // A model absent from this map is recorded with a NULL cost, which means unpriced.
              name: 'LLM_PRICES'
              value: '{"muse-spark-1.3":{"input":1.25,"output":4.25},"muse-wonder-1.0":{"input":4.00,"output":20.00}}'
            }
            {
              // Half of what a developer's `.env` sets, on purpose.
              name: 'LLM_RUN_COST_LIMIT_USD'
              value: '1.00'
            }
            {
              // Key Vault is the secrets backend in Azure.
              name: 'SECRETS_BACKEND'
              value: 'keyvault'
            }
            {
              // These names are the `Settings` field names.
              name: 'KEY_VAULT_URL'
              value: keyVaultUri
            }
            {
              name: 'ARTIFACTS_BACKEND'
              value: 'blob'
            }
            {
              name: 'ARTIFACTS_ACCOUNT_URL'
              value: blobEndpoint
            }
            {
              name: 'AUTH_MODE'
              value: 'entra'
            }
            {
              // Set here or the mode above is a promise the API cannot keep.
              name: 'OIDC_AUTHORITY'
              value: oidcAuthority
            }
            {
              // Not a secret and not derivable from the authority.
              name: 'OIDC_AUDIENCE'
              value: oidcAudience
            }
            {
              // Never set before, so the API defaulted to `http://localhost:3000` and would...
              name: 'CORS_ORIGINS'
              value: 'https://ca-charie-web-${env}.${environment.properties.defaultDomain}'
            }
          ])
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

// Where the environment's logs actually go.
resource environmentDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-log-analytics'
  scope: environment
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
  }
}

// The migration job (WP12.2). A one-off Container Apps job rather than a step in the pipeline.
resource selfcheck 'Microsoft.App/jobs@2024-03-01' = if (deployJobs) {
  name: 'cj-charie-selfcheck-${env}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      // Two minutes. Four round trips to two Azure services.
      replicaTimeout: 120
      // One retry, unlike the migration job's zero.
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfig
    }
    template: {
      containers: [
        {
          name: 'selfcheck'
          image: '${registryLoginServer}/charie-api:${imageTag}'
          command: ['sh', '-c']
          args: ['python -m charie.ops.selfcheck']
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          // The app's storage configuration and nothing else.
          env: concat(commonEnv, [
            {
              name: 'SECRETS_BACKEND'
              value: 'keyvault'
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVaultUri
            }
            {
              name: 'ARTIFACTS_BACKEND'
              value: 'blob'
            }
            {
              name: 'ARTIFACTS_ACCOUNT_URL'
              value: blobEndpoint
            }
          ])
        }
      ]
    }
  }
}

resource migrate 'Microsoft.App/jobs@2024-03-01' = if (deployJobs) {
  name: 'cj-charie-migrate-${env}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      // Ten minutes, matching what `ops/scripts/deploy_migrate.sh` waits for.
      replicaTimeout: 600
      // No retries. Alembic is not idempotent mid-failure.
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: registryConfig
      secrets: [
        {
          name: secretNames.databasePassword
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.databasePassword}'
          identity: identityId
        }
        {
          name: secretNames.appDatabasePassword
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.appDatabasePassword}'
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: '${registryLoginServer}/charie-api:${imageTag}'
          // Two steps, in this order, and the second is not optional.
          command: ['sh', '-c']
          args: ['alembic upgrade head && python -m charie.db.grant_app_login']
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              // The owner DSN, password-less here and rejoined by `_with_password` in config.py.
              name: 'DATABASE_URL'
              value: 'postgresql+asyncpg://${postgresAdminLogin}@${postgresHost}:5432/${postgresDatabase}?ssl=require'
            }
            {
              name: 'DB_PASSWORD'
              secretRef: secretNames.databasePassword
            }
            {
              // The password this job is about to give `charie_app`.
              name: 'APP_DB_PASSWORD'
              secretRef: secretNames.appDatabasePassword
            }
            {
              name: 'ENV'
              value: env
            }
          ]
        }
      ]
    }
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'ca-charie-web-${env}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      // **External.** The one public surface.
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
      }
      registries: registryConfig
    }
    template: {
      containers: [
        {
          name: 'web'
          image: '${registryLoginServer}/charie-web:${imageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: commonEnv
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output environmentId string = environment.id

@description('The environment domain every app hostname is built from. The web build needs the API hostname before either app exists, and this is where it comes from.')
output defaultDomain string = environment.properties.defaultDomain
output apiFqdn string = api.?properties.?configuration.?ingress.?fqdn ?? ''
output webFqdn string = web.?properties.?configuration.?ingress.?fqdn ?? ''
output secretNames object = secretNames
