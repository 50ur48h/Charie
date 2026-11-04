// What the application identity may do, and nothing else.

@description('The principal id of the user-assigned identity from identity.bicep.')
param principalId string

@description('Key Vault, from keyvault.bicep.')
param keyVaultName string

@description('Storage account, from storage.bicep.')
param storageAccountName string

@description('Container registry, from acr.bicep.')
param registryName string

// Key Vault Secrets Officer — read, write and delete a secret's value.
var keyVaultSecretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

// Storage Blob Data Contributor — read and write blobs within the account.
var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// AcrPull — pull images. There is no push here; the deploy workflow's own OIDC identity pushes.
var acrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' existing = {
  name: keyVaultName
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: registryName
}

// `guid()` over the scope, principal and role: deterministic.
resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, principalId, keyVaultSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      keyVaultSecretsOfficer
    )
    principalId: principalId
    // Stated explicitly. Without it, Azure resolves the principal type by lookup.
    principalType: 'ServicePrincipal'
  }
}

resource blobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, principalId, blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      blobDataContributor
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, principalId, acrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPull)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
