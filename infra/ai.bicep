// P08.1: Charie AI services. Deploys into the existing rg-charie group.
// No secrets here: keys are read from the portal into .env after deploy.
// Deployment itself needs owner approval (P08.1 Task 4).
targetScope = 'resourceGroup'

@description('Azure region for Document Intelligence (data stays in India).')
param diLocation string = 'centralindia'

@description('Azure region for the OpenAI embeddings account.')
param openAiLocation string = 'southeastasia'

@description('Pinned text-embedding-3-large model version.')
param embedModelVersion string = '1'

@description('Standard SKU capacity (thousands of TPM) for embeddings.')
param embedCapacity int = 50

resource di 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'di-charie'
  location: diLocation
  sku: {
    name: 'S0'
  }
  kind: 'FormRecognizer'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    project: 'charie'
    phase: '08'
  }
}

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'aoai-charie'
  location: openAiLocation
  sku: {
    name: 'S0'
  }
  kind: 'OpenAI'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    project: 'charie'
    phase: '08'
  }
}

resource embedDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  name: 'embed-3-large'
  parent: aoai
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: embedModelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  sku: {
    name: 'Standard'
    capacity: embedCapacity
  }
}

// Endpoints and names only; keys stay out of templates and outputs.
output diEndpoint string = di.properties.endpoint
output openAiEndpoint string = aoai.properties.endpoint
output diName string = di.name
output openAiName string = aoai.name
output embedDeploymentName string = embedDeployment.name
