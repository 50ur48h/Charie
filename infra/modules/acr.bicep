// The private registry, Basic tier per architecture 9.1's table.

@description('Where everything goes.')
param location string

@description('Environment discriminator — dev or prod.')
param env string

@description('Tags applied to every resource.')
param tags object

@description('Globally-unique suffix, derived from the resource group.')
param suffix string

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  // Alphanumeric only, globally unique: no hyphens available.
  name: take('crcharie${env}${suffix}', 50)
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    // Off, deliberately. The admin user is a username and password that grants push and pull.
    adminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

output id string = registry.id
output name string = registry.name
output loginServer string = registry.properties.loginServer
