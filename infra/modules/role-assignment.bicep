// Generic role assignment scoped to a resource id within the current RG.
param principalId string
param roleDefinitionId string
param resourceId string

var scopeName = last(split(resourceId, '/'))

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: scopeName
}

resource ra 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceId, principalId, roleDefinitionId)
  scope: acr
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}
