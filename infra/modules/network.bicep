// The network private Postgres needs, and nothing more.

@description('Where everything goes. Passed rather than defaulted so a module cannot silently land in a second region.')
param location string

@description('Environment discriminator — dev or prod. Names derive from it.')
param env string

@description('Tags applied to every resource, so cost and ownership are answerable.')
param tags object

// /16 for the VNet with /24s inside it: far more address space than this will use.
var vnetPrefix = '10.20.0.0/16'
var postgresPrefix = '10.20.1.0/24'

// Container Apps wants a /23 at minimum for a consumption environment.
var appsPrefix = '10.20.4.0/23'

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-charie-${env}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [vnetPrefix]
    }
    subnets: [
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: postgresPrefix
          // Delegation is what makes this subnet Postgres's and nothing else's.
          delegations: [
            {
              name: 'postgres-flexible'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-apps'
        properties: {
          addressPrefix: appsPrefix
          delegations: [
            {
              name: 'container-apps'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
    ]
  }
}

// The private DNS zone that makes the server's hostname resolve inside the VNet.
resource dns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'charie-${env}.private.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dns
  name: 'link-${env}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

output vnetId string = vnet.id
output postgresSubnetId string = vnet.properties.subnets[0].id
output appsSubnetId string = vnet.properties.subnets[1].id
output privateDnsZoneId string = dns.id
// Named so `main.bicep` can depend on the link rather than on the zone.
output privateDnsLinkId string = dnsLink.id
