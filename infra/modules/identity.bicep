// The one identity everything runs as.

@description('Where everything goes.')
param location string

@description('Environment discriminator — dev or prod.')
param env string

@description('Tags applied to every resource.')
param tags object

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-charie-${env}'
  location: location
  tags: tags
}

output id string = identity.id
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
