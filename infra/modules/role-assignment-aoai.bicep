// Role assignment scoped to an existing Cognitive Services account in another RG.
param principalId string
param accountName string
param roleDefinitionId string

resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: accountName
}

resource ra 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aoai.id, principalId, roleDefinitionId)
  scope: aoai
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}
