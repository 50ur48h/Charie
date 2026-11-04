// Log Analytics and Application Insights, capped on purpose.

@description('Where everything goes.')
param location string

@description('Environment discriminator — dev or prod.')
param env string

@description('Tags applied to every resource.')
param tags object

@description('Daily ingestion ceiling in GB. Past this the workspace stops taking data until the next day.')
@minValue(1)
param dailyCapGb int

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-charie-${env}'
  location: location
  tags: tags
  properties: {
    sku: {
      // Pay-as-you-go with a cap, rather than a commitment tier.
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: dailyCapGb
    }
    features: {
      // Local auth off, so telemetry is written with the managed identity like everything else.
      disableLocalAuth: true
    }
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-charie-${env}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    // Workspace-based, which is the only mode still offered — classic App Insights is retired.
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    DisableLocalAuth: true
  }
}

output workspaceId string = workspace.id
output workspaceCustomerId string = workspace.properties.customerId
output insightsId string = insights.id
output insightsConnectionString string = insights.properties.ConnectionString
