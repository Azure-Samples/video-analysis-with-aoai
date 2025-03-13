param (
    [Parameter(Mandatory=$true)]
    [string]$Prefix,
    [string]$PythonScript = "video_shot_analysis.py" # Default to video_shot_analysis.py if not provided
)

$ErrorActionPreference = "Stop"  # Exit immediately if a command exits with a non-zero status

$PrefixLower = $Prefix.ToLower()

$ResourceGroup = "${Prefix}ResourceGroup"
$AcrName = "${PrefixLower}acr"
$AppServicePlan = "${Prefix}AppServicePlan"
$WebAppName = "${PrefixLower}app"
$Location = "eastus"
$ImageName = "${AcrName}.azurecr.io/${PrefixLower}-demo"
$DockerImageTag = "latest"

Write-Output "Starting deployment with the following parameters:"
Write-Output "PREFIX: $Prefix"
Write-Output "RESOURCE_GROUP: $ResourceGroup"
Write-Output "ACR_NAME: $AcrName"
Write-Output "APP_SERVICE_PLAN: $AppServicePlan"
Write-Output "WEB_APP_NAME: $WebAppName"
Write-Output "LOCATION: $Location"
Write-Output "IMAGE_NAME: $ImageName"
Write-Output "DOCKER_IMAGE_TAG: $DockerImageTag"
Write-Output "PYTHON_SCRIPT: $PythonScript"

try {
    # Check if already logged in to Azure
    try {
        az account show -o none
        Write-Output "Already logged in to Azure."
    } catch {
        Write-Output "Logging in to Azure..."
        az login
    }

    # Set the subscription
    $SubscriptionId = (az account show --query 'id' -o tsv).Trim()
    Write-Output "Using subscription ID: $SubscriptionId"
    az account set --subscription $SubscriptionId

    # Create a resource group
    Write-Output "Creating resource group: $ResourceGroup in $Location"
    az group create --name $ResourceGroup --location $Location

    # Create an Azure Container Registry
    Write-Output "Creating Azure Container Registry: $AcrName"
    az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true

    # Login to the Azure Container Registry
    Write-Output "Logging in to Azure Container Registry: $AcrName"
    az acr login --name $AcrName

    # Debug output to verify variable values
    Write-Output "Debug: ACR_NAME=${AcrName}"
    Write-Output "Debug: IMAGE_NAME=${ImageName}"
    Write-Output "Debug: DOCKER_IMAGE_TAG=${DockerImageTag}"
    Write-Output "Debug: PYTHON_SCRIPT=${PythonScript}"

    # Build the Docker image
    Write-Output "Building Docker image: ${ImageName}:${DockerImageTag}"
    docker build --platform linux/amd64 --build-arg PYTHON_SCRIPT=$PythonScript -t ${ImageName}:${DockerImageTag} .

    # Verify if the Docker image was built successfully
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed. Exiting."
        exit 1
    }

    # Push the Docker image to the Azure Container Registry
    Write-Output "Pushing Docker image to Azure Container Registry: ${ImageName}:${DockerImageTag}"
    docker push ${ImageName}:${DockerImageTag}

    # The P1V3 tier (Premium v3 - P1v3) provides more CPU and memory resources for production workloads
    # Create an App Service plan
    Write-Output "Creating App Service plan: $AppServicePlan"
    az appservice plan create --name $AppServicePlan --resource-group $ResourceGroup --sku P1V3 --is-linux

    # Create a Web App for Containers
    Write-Output "Creating Web App for Containers: $WebAppName"
    az webapp create --resource-group $ResourceGroup --plan $AppServicePlan --name $WebAppName --deployment-container-image-name ${ImageName}:${DockerImageTag}

    # Configure the Web App to use the Azure Container Registry
    Write-Output "Configuring Web App to use Azure Container Registry: ${ImageName}:${DockerImageTag}"
    az webapp config container set --name $WebAppName --resource-group $ResourceGroup --container-image-name ${ImageName}:${DockerImageTag} --container-registry-url https://${AcrName}.azurecr.io

    # Load environment variables from .env file
    Write-Output "Checking if .env file exists..."
    if (Test-Path -Path .env -PathType Leaf) {
        Write-Output ".env file found. Loading environment variables..."
        $envVars = Get-Content -Path .env | ForEach-Object {
            if ($_ -match "=") {
                $name, $value = $_ -split '=', 2
                [PSCustomObject]@{ Name = $name.Trim(); Value = $value.Trim('"') }
            }
        }
        Write-Output "Loaded environment variables:"
        $envVars | ForEach-Object { Write-Output "$($_.Name)=$($_.Value)" }
    } else {
        Write-Error ".env file not found."
        exit 1
    }

    # Set environment variables in Azure Web App
    Write-Output "Setting environment variables in Azure Web App: $WebAppName"
    $settings = @{}
    foreach ($envVar in $envVars) {
        $settings[$envVar.Name] = $envVar.Value
    }
    
    $settingsArray = $settings.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
    az webapp config appsettings set --resource-group $ResourceGroup --name $WebAppName --settings $settingsArray
    
    Write-Output "Deployment completed. You can access your Streamlit app at https://$WebAppName.azurewebsites.net"
} catch {
    Write-Error "An error occurred during deployment: $_"
    exit 1
}
