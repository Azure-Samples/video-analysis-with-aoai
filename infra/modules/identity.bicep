param location string
param tags object
param name string

resource uai 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
  tags: tags
}

output id string = uai.id
output name string = uai.name
output principalId string = uai.properties.principalId
output clientId string = uai.properties.clientId
