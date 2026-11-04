// Key Vault, in RBAC mode and created empty.

@description('Where everything goes.')
param location string

@description('Environment discriminator — dev or prod.')
param env string

@description('Tags applied to every resource.')
param tags object

@description('Globally-unique suffix, derived from the resource group.')
param suffix string

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  // Vault names are globally unique and capped at 24 characters.
  name: take('kv-charie-${env}-${suffix}', 24)
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    // Soft delete is not optional on new vaults and is left at its default.
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      // Azure services and the deploy pipeline both reach this over the public endpoint.
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

output id string = vault.id
output name string = vault.name
output uri string = vault.properties.vaultUri
