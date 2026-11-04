// The platform database: Flexible Server, B-series, pgvector, private.

@description('Where everything goes.')
param location string

@description('Environment discriminator — dev or prod.')
param env string

@description('Tags applied to every resource.')
param tags object

@description('Compute tier. B-series for dev per the owner, and the parameter is what lets prod differ without a second template.')
param skuName string

@description('Burstable, GeneralPurpose or MemoryOptimized — must match the family skuName belongs to.')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param skuTier string

@description('Data disk size. 32 GB is the smallest Flexible Server offers.')
@minValue(32)
param storageGb int

@description('Days of point-in-time restore. WP12.4 drills a restore, so this has to be long enough to drill against.')
@minValue(7)
@maxValue(35)
param backupRetentionDays int

@description('The administrator login. Not a secret by itself, and never the identity the application connects as.')
param administratorLogin string

@description('The administrator password, supplied at deploy time and never stored in a tracked file.')
@secure()
param administratorPassword string

@description('The delegated subnet from network.bicep.')
param subnetId string

@description('The private DNS zone the server registers its hostname in.')
param privateDnsZoneId string

@description('The database the application uses.')
param databaseName string

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'psql-charie-${env}'
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: '16'
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    storage: {
      storageSizeGB: storageGb
      // Growing the disk by hand is a 3am job.
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      // Local rather than geo-redundant: a dev environment.
      geoRedundantBackup: 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: subnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      // Redundant with the delegated subnet — Azure refuses both.
      publicNetworkAccess: 'Disabled'
    }
    highAvailability: {
      // Off for a B-series dev server: the tier does not support it.
      mode: 'Disabled'
    }
    maintenanceWindow: {
      customWindow: 'Enabled'
      // Sunday 18:00 UTC — small hours in southeastasia.
      dayOfWeek: 0
      startHour: 18
      startMinute: 0
    }
    authConfig: {
      // Both, deliberately. Entra authentication is how a person or a pipeline reaches the server.
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled'
      tenantId: subscription().tenantId
    }
  }
}

// An extension is not installed by creating it.
resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'azure.extensions'
  properties: {
    value: 'PGCRYPTO,VECTOR'
    source: 'user-override'
  }
}

// Connections are TLS-only. Off by default on some tiers, and B-013's rule for customer databases.
resource requireSsl 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'require_secure_transport'
  properties: {
    value: 'on'
    source: 'user-override'
  }
  dependsOn: [extensions]
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output id string = server.id
output name string = server.name
output fullyQualifiedDomainName string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
