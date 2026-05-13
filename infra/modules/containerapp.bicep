param location string
param tags object
param name string
param environmentId string
param registryServer string
param imageName string
param targetPort int = 8501
param cpu string = '1.0'
param memory string = '2.0Gi'
param minReplicas int = 1
param maxReplicas int = 3

param aoaiEndpoint string
param aoaiDeploymentName string

param useWhisper bool = false
param whisperEndpoint string = ''
param whisperDeploymentName string = ''
@secure()
param whisperApiKey string = ''

var baseEnv = [
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: aoaiEndpoint
  }
  {
    name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
    value: aoaiDeploymentName
  }
  {
    name: 'USE_WHISPER'
    value: string(useWhisper)
  }
]

var whisperEnv = useWhisper ? [
  {
    name: 'WHISPER_ENDPOINT'
    value: whisperEndpoint
  }
  {
    name: 'WHISPER_DEPLOYMENT_NAME'
    value: whisperDeploymentName
  }
  {
    name: 'WHISPER_API_KEY'
    secretRef: 'whisper-api-key'
  }
] : []

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: 'system'
        }
      ]
      secrets: useWhisper && !empty(whisperApiKey) ? [
        {
          name: 'whisper-api-key'
          value: whisperApiKey
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'app'
          image: imageName
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(baseEnv, whisperEnv)
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output id string = app.id
output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output principalId string = app.identity.principalId
