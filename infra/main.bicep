targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used to generate unique resource names. Set by azd.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('Tags applied to all resources.')
param tags object = {
  'azd-env-name': environmentName
}

// ----- Azure OpenAI (existing) -----
@description('Resource group of the existing Azure OpenAI account.')
param aoaiResourceGroupName string

@description('Name of the existing Azure OpenAI account.')
param aoaiAccountName string

@description('Name of an existing chat-completions deployment in the AOAI account (e.g. gpt-4o).')
param aoaiDeploymentName string

// ----- Optional Whisper -----
@description('Enable Whisper transcription path in the app.')
param useWhisper bool = false

@description('Optional Whisper endpoint URL.')
param whisperEndpoint string = ''

@description('Optional Whisper deployment name.')
param whisperDeploymentName string = ''

@description('Optional Whisper API key (stored as Container App secret).')
@secure()
param whisperApiKey string = ''

// ----- Container sizing -----
param containerCpu string = '1.0'
param containerMemory string = '2.0Gi'
param minReplicas int = 1
param maxReplicas int = 3

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var serviceName = 'web'

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
  }
}

module env 'modules/containerapps-env.bicep' = {
  name: 'cae'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    logAnalyticsWorkspaceId: monitoring.outputs.id
  }
}

module app 'modules/containerapp.bicep' = {
  name: 'app'
  scope: rg
  params: {
    location: location
    tags: union(tags, { 'azd-service-name': serviceName })
    name: '${abbrs.appContainerApps}${serviceName}-${resourceToken}'
    environmentId: env.outputs.id
    registryServer: registry.outputs.loginServer
    // azd will replace this placeholder image on first deploy
    imageName: 'mcr.microsoft.com/k8se/quickstart:latest'
    // Initial port matches the placeholder image (port 80). After azd deploy
    // pushes the real Streamlit image, the deploy script updates ingress to 8501.
    targetPort: 80
    cpu: containerCpu
    memory: containerMemory
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    aoaiEndpoint: aoai.properties.endpoint
    aoaiDeploymentName: aoaiDeploymentName
    useWhisper: useWhisper
    whisperEndpoint: whisperEndpoint
    whisperDeploymentName: whisperDeploymentName
    whisperApiKey: whisperApiKey
  }
}

// Existing AOAI lookup (cross-RG)
resource aoaiRg 'Microsoft.Resources/resourceGroups@2023-07-01' existing = {
  name: aoaiResourceGroupName
  scope: subscription()
}

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aoaiAccountName
  scope: aoaiRg
}

// RBAC: AcrPull on the ACR
module acrPull 'modules/role-assignment.bicep' = {
  name: 'rbac-acrpull'
  scope: rg
  params: {
    principalId: app.outputs.principalId
    // AcrPull
    roleDefinitionId: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    resourceId: registry.outputs.id
  }
}

// RBAC: Cognitive Services OpenAI User on the AOAI account (cross-RG)
module aoaiUser 'modules/role-assignment-aoai.bicep' = {
  name: 'rbac-aoai-user'
  scope: aoaiRg
  params: {
    principalId: app.outputs.principalId
    accountName: aoaiAccountName
    // Cognitive Services OpenAI User
    roleDefinitionId: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name
output AZURE_CONTAINER_ENVIRONMENT_NAME string = env.outputs.name
output AZURE_CONTAINER_APP_NAME string = app.outputs.name
output AZURE_CONTAINER_APP_FQDN string = app.outputs.fqdn
output SERVICE_WEB_NAME string = app.outputs.name
output SERVICE_WEB_URI string = 'https://${app.outputs.fqdn}'
output AZURE_OPENAI_ENDPOINT string = aoai.properties.endpoint
output AZURE_OPENAI_DEPLOYMENT_NAME string = aoaiDeploymentName
