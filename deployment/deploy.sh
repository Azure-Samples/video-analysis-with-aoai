#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status

# Configure Azure CLI to allow preview extensions without prompting
echo "Configuring Azure CLI to allow preview extensions..."
az config set extension.dynamic_install_allow_preview=true

# Auto-install application-insights extension silently
echo "Installing required extensions..."
az extension add --name application-insights --yes || echo "Failed to install application-insights extension"

# Default paths
ENV_FILE_PATH=".env"
DOCKERFILE_PATH="deployment/Dockerfile"
DOCKER_CONTEXT="."  # The root directory containing all files to include in the image
ENTRY_FILE="start_app.py"  # The specific Python file that runs when the container starts

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env-file)
            ENV_FILE_PATH="$2"
            shift 2
            ;;
        --dockerfile)
            DOCKERFILE_PATH="$2"
            shift 2
            ;;
        --context)
            DOCKER_CONTEXT="$2"
            shift 2
            ;;
        --entry-file)
            ENTRY_FILE="$2"
            shift 2
            ;;
        *)
            APP_NAME="$1"
            shift
            ;;
    esac
done

# Check for .env file
echo "Looking for environment variables..."
if [ ! -f "$ENV_FILE_PATH" ]; then
    echo "Error: Environment file $ENV_FILE_PATH not found."
    echo "Please create an .env file or specify one with --env-file"
    exit 1
fi

# Load environment variables
echo "Loading environment variables from $ENV_FILE_PATH"
set -a
source "$ENV_FILE_PATH"
set +a

# Check if the app name is provided
if [ -z "$APP_NAME" ]; then
    echo "Usage: $0 [--env-file path/to/env] [--dockerfile path/to/Dockerfile] [--context path/to/context] [--entry-file app_entry_point.py] <app_name>"
    echo "Example: $0 video-analysis-app"
    echo "All parameters are optional except for app_name, which must be specified last"
    echo "Default values:"
    echo "  --env-file .env"
    echo "  --dockerfile deployment/Dockerfile"
    echo "  --context ."
    echo "  --entry-file start_app.py"
    exit 1
fi

# Check if Dockerfile exists
if [ ! -f "$DOCKERFILE_PATH" ]; then
    echo "Error: Dockerfile not found at $DOCKERFILE_PATH"
    exit 1
fi

# Check if required environment variables are set
REQUIRED_VARS=("AZURE_RESOURCE_GROUP" "AZURE_LOCATION" "AZURE_ACR_NAME" 
              "AZURE_APP_SERVICE_PLAN" "AZURE_KEY_VAULT" "AZURE_LOG_ANALYTICS")
              
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required environment variable $var is not set in $ENV_FILE_PATH"
        exit 1
    fi
done

# Use environment variables for resources (with defaults for backward compatibility)
RESOURCE_GROUP=${AZURE_RESOURCE_GROUP}
LOCATION=${AZURE_LOCATION:-"eastus"}
ACR_NAME=${AZURE_ACR_NAME}
APP_SERVICE_PLAN=${AZURE_APP_SERVICE_PLAN}
KEY_VAULT=${AZURE_KEY_VAULT}
LOG_ANALYTICS=${AZURE_LOG_ANALYTICS}
APP_SERVICE_SKU=${AZURE_APP_SERVICE_SKU:-"P1V3"}
DOCKER_IMAGE_TAG=${AZURE_DOCKER_IMAGE_TAG:-"latest"}

# App-specific resources
WEB_APP_NAME="app-${APP_NAME}"
IMAGE_NAME="${APP_NAME}"
APP_INSIGHTS_NAME="${WEB_APP_NAME}-ai"

# Set up retry function for Azure commands
function retry {
  local n=1
  local max=5
  local delay=15
  while true; do
    "$@" && break || {
      if [[ $n -lt $max ]]; then
        ((n++))
        echo "Command failed. Attempt $n/$max in $delay seconds:"
        sleep $delay;
      else
        echo "The command has failed after $n attempts."
        return 1
      fi
    }
  done
}

echo "Starting deployment for app: $APP_NAME"
echo "Using environment file: $ENV_FILE_PATH"
echo "Using Dockerfile: $DOCKERFILE_PATH"
echo "Using Docker context: $DOCKER_CONTEXT"
echo "Using entry file: $ENTRY_FILE"
echo "RESOURCE_GROUP: $RESOURCE_GROUP"
echo "LOCATION: $LOCATION"
echo "ACR_NAME: $ACR_NAME"
echo "APP_SERVICE_PLAN: $APP_SERVICE_PLAN"
echo "WEB_APP_NAME: $WEB_APP_NAME"
echo "IMAGE_NAME: $IMAGE_NAME"
echo "APP_SERVICE_SKU: $APP_SERVICE_SKU"

# Check if already logged in to Azure
if ! az account show &>/dev/null; then
    echo "Logging in to Azure..."
    az login
else
    echo "Already logged in to Azure."
fi

# Set the subscription
SUBSCRIPTION_ID="$(az account show --query 'id' -o tsv)"
echo "Using subscription ID: $SUBSCRIPTION_ID"
az account set --subscription "$SUBSCRIPTION_ID"

# Create resource group if it doesn't exist
if ! az group show --name $RESOURCE_GROUP &>/dev/null; then
    echo "Creating resource group: $RESOURCE_GROUP in $LOCATION"
    az group create --name $RESOURCE_GROUP --location $LOCATION
else
    echo "Resource group $RESOURCE_GROUP already exists."
fi

# Register necessary resource providers
echo "Registering necessary Azure resource providers..."
az provider register --namespace Microsoft.Insights
az provider register --namespace Microsoft.OperationalInsights

# Create Azure Container Registry if it doesn't exist
if ! az acr show --name $ACR_NAME &>/dev/null; then
    echo "Creating Azure Container Registry: $ACR_NAME"
    az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --admin-enabled true
else
    echo "Azure Container Registry $ACR_NAME already exists."
fi

# Create Key Vault if it doesn't exist
if ! az keyvault show --name $KEY_VAULT &>/dev/null; then
    echo "Creating Key Vault: $KEY_VAULT"
    az keyvault create --name $KEY_VAULT --resource-group $RESOURCE_GROUP --location $LOCATION
else
    echo "Key Vault $KEY_VAULT already exists."
fi

# Create Log Analytics workspace if it doesn't exist
if ! az monitor log-analytics workspace show --workspace-name $LOG_ANALYTICS --resource-group $RESOURCE_GROUP &>/dev/null; then
    echo "Creating Log Analytics workspace: $LOG_ANALYTICS"
    az monitor log-analytics workspace create --resource-group $RESOURCE_GROUP --workspace-name $LOG_ANALYTICS
    
    # Wait for Log Analytics workspace to be fully provisioned
    echo "Waiting for Log Analytics workspace to be fully provisioned..."
    sleep 30
else
    echo "Log Analytics workspace $LOG_ANALYTICS already exists."
fi

# Create App Service Plan if it doesn't exist
if ! az appservice plan show --name $APP_SERVICE_PLAN --resource-group $RESOURCE_GROUP &>/dev/null; then
    echo "Creating App Service plan: $APP_SERVICE_PLAN"
    az appservice plan create --name $APP_SERVICE_PLAN --resource-group $RESOURCE_GROUP --sku $APP_SERVICE_SKU --is-linux
else
    echo "App Service plan $APP_SERVICE_PLAN already exists."
fi

# Login to the Azure Container Registry
echo "Logging in to Azure Container Registry: $ACR_NAME"
az acr login --name $ACR_NAME

# Build the Docker image with timestamp for uniqueness
echo "Building Docker image: $ACR_NAME.azurecr.io/$IMAGE_NAME:$DOCKER_IMAGE_TAG"
BUILD_TIMESTAMP=$(date +%Y%m%d%H%M%S)
UNIQUE_IMAGE_TAG="${DOCKER_IMAGE_TAG}-${BUILD_TIMESTAMP}"
echo "Using unique image tag: $UNIQUE_IMAGE_TAG"

# Build with platform specification for better compatibility
# Passes the entry file name and other environment args
docker build --platform linux/amd64 \
  -f $DOCKERFILE_PATH \
  --build-arg ENTRY_FILE=$ENTRY_FILE \
  --build-arg VITE_AUTH_URL="$VITE_AUTH_URL" \
  --build-arg VITE_AUTH_ENABLED="$VITE_AUTH_ENABLED" \
  -t $ACR_NAME.azurecr.io/$IMAGE_NAME:$DOCKER_IMAGE_TAG \
  -t $ACR_NAME.azurecr.io/$IMAGE_NAME:$UNIQUE_IMAGE_TAG \
  $DOCKER_CONTEXT

# Push the Docker image to the Azure Container Registry
echo "Pushing Docker image to Azure Container Registry: $ACR_NAME.azurecr.io/$IMAGE_NAME:$DOCKER_IMAGE_TAG"
docker push $ACR_NAME.azurecr.io/$IMAGE_NAME:$DOCKER_IMAGE_TAG
docker push $ACR_NAME.azurecr.io/$IMAGE_NAME:$UNIQUE_IMAGE_TAG

# Create a Web App for Containers if it doesn't exist
if ! az webapp show --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP &>/dev/null; then
    echo "Creating Web App for Containers: $WEB_APP_NAME"
    az webapp create --resource-group $RESOURCE_GROUP --plan $APP_SERVICE_PLAN --name $WEB_APP_NAME \
        --deployment-container-image-name $ACR_NAME.azurecr.io/$IMAGE_NAME:$UNIQUE_IMAGE_TAG
    
    # Add configuration for the auth server port and frontend URL
    echo "Configuring port mappings and environment for authentication server..."
    az webapp config appsettings set --resource-group $RESOURCE_GROUP --name $WEB_APP_NAME \
        --settings WEBSITES_PORT=8501 \
        FRONTEND_URL="https://${WEB_APP_NAME}.azurewebsites.net" \
        WEBSITE_HOSTNAME="${WEB_APP_NAME}.azurewebsites.net"
else
    echo "Web App $WEB_APP_NAME already exists. Updating container image."
    # Use the unique tag to force an update
    az webapp config container set --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP \
        --docker-custom-image-name $ACR_NAME.azurecr.io/$IMAGE_NAME:$UNIQUE_IMAGE_TAG \
        --docker-registry-server-url https://$ACR_NAME.azurecr.io
    
    # Update frontend URL setting
    az webapp config appsettings set --resource-group $RESOURCE_GROUP --name $WEB_APP_NAME \
        --settings FRONTEND_URL="https://${WEB_APP_NAME}.azurewebsites.net" \
        WEBSITE_HOSTNAME="${WEB_APP_NAME}.azurewebsites.net"
fi

# Get all environment variable names from the specified .env file
echo "Reading environment variables from $ENV_FILE_PATH"
ENV_VARS=$(grep -v '^#' "$ENV_FILE_PATH" | grep -v '^AZURE_RESOURCE' | grep -v '^AZURE_LOCATION' \
          | grep -v '^AZURE_ACR' | grep -v '^AZURE_APP_SERVICE' | grep -v '^AZURE_KEY_VAULT' \
          | grep -v '^AZURE_LOG_ANALYTICS' | grep -v 'DOCKER_IMAGE_TAG' | grep '=' | cut -d '=' -f1)

# Build the appsettings command
APPSETTINGS_CMD="az webapp config appsettings set --resource-group $RESOURCE_GROUP --name $WEB_APP_NAME --settings"

# Add each environment variable to the command
for var in $ENV_VARS; do
    # Use indirect reference to get the value
    value=${!var}
    if [ -n "$value" ]; then  # Only add if value is not empty
        APPSETTINGS_CMD="$APPSETTINGS_CMD $var='$value'"
    fi
done

# Set environment variables in Azure Web App if we have any to set
if [ "$APPSETTINGS_CMD" != "az webapp config appsettings set --resource-group $RESOURCE_GROUP --name $WEB_APP_NAME --settings" ]; then
    echo "Setting environment variables in Azure Web App: $WEB_APP_NAME"
    eval $APPSETTINGS_CMD
else
    echo "No environment variables to set in Azure Web App."
fi

# Enable application logs
echo "Enabling application logs for Web App: $WEB_APP_NAME"
az webapp log config --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP \
    --application-logging filesystem --level information

# Set up Application Insights with ARM template approach
echo "Setting up Application Insights for Web App: $WEB_APP_NAME"

# Check if Application Insights exists
if az monitor app-insights component show --app $APP_INSIGHTS_NAME --resource-group $RESOURCE_GROUP --only-show-errors &>/dev/null; then
    echo "Found existing Application Insights: $APP_INSIGHTS_NAME"
    
    # Check its provisioning state
    PROVISION_STATE=$(az monitor app-insights component show \
        --app $APP_INSIGHTS_NAME \
        --resource-group $RESOURCE_GROUP \
        --query "provisioningState" -o tsv --only-show-errors 2>/dev/null || echo "Unknown")
    
    if [ "$PROVISION_STATE" != "Succeeded" ]; then
        echo "Existing Application Insights is in state: $PROVISION_STATE"
        echo "Removing and recreating Application Insights..."
        az monitor app-insights component delete \
            --app $APP_INSIGHTS_NAME \
            --resource-group $RESOURCE_GROUP \
            --yes --only-show-errors
        # Wait for deletion to complete
        sleep 30
    else
        echo "Application Insights is in a good state."
    fi
fi

# Create Application Insights using ARM template approach if it doesn't exist or was deleted
if ! az monitor app-insights component show --app $APP_INSIGHTS_NAME --resource-group $RESOURCE_GROUP --only-show-errors &>/dev/null; then
    echo "Creating Application Insights using ARM template..."
    
    # Create a unique file for ARM template in the current directory with timestamp
    TIMESTAMP=$(date +%s)
    TEMPLATE_FILE="./appinsights_template_${APP_NAME}_${TIMESTAMP}.json"
    
    echo "Creating template file: $TEMPLATE_FILE"
    
    # Create ARM template for Application Insights
    cat > "$TEMPLATE_FILE" << EOL
{
    "\$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
    "contentVersion": "1.0.0.0",
    "resources": [
        {
            "type": "microsoft.insights/components",
            "apiVersion": "2020-02-02",
            "name": "${APP_INSIGHTS_NAME}",
            "location": "${LOCATION}",
            "kind": "web",
            "properties": {
                "Application_Type": "web",
                "WorkspaceResourceId": "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.OperationalInsights/workspaces/${LOG_ANALYTICS}",
                "publicNetworkAccessForIngestion": "Enabled",
                "publicNetworkAccessForQuery": "Enabled"
            }
        }
    ]
}
EOL
    
    # Verify template file was created
    if [ ! -f "$TEMPLATE_FILE" ]; then
        echo "Error: Failed to create template file. Check permissions and disk space."
        # Continue anyway - we can try to use the direct method
    else
        # Deploy the ARM template
        echo "Deploying ARM template..."
        az deployment group create \
          --name "deploy-appinsights-$APP_NAME" \
          --resource-group $RESOURCE_GROUP \
          --template-file "$TEMPLATE_FILE" \
          --only-show-errors
        
        # Clean up template file with error handling
        echo "Cleaning up template file..."
        if [ -f "$TEMPLATE_FILE" ]; then
            rm "$TEMPLATE_FILE" || echo "Warning: Could not remove template file: $TEMPLATE_FILE"
        else
            echo "Warning: Template file not found for cleanup: $TEMPLATE_FILE"
        fi
    fi
    
    echo "Waiting for Application Insights to be fully provisioned..."
    sleep 15
else
    echo "Application Insights already exists, using existing instance."
fi

# Get the instrumentation key with retries
echo "Getting instrumentation key..."
MAX_RETRIES=5
RETRY_COUNT=0
INSTRUMENTATION_KEY=""

while [ -z "$INSTRUMENTATION_KEY" ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    INSTRUMENTATION_KEY=$(az monitor app-insights component show \
        --app $APP_INSIGHTS_NAME \
        --resource-group $RESOURCE_GROUP \
        --query instrumentationKey \
        --output tsv --only-show-errors 2>/dev/null || echo "")
    
    if [ -z "$INSTRUMENTATION_KEY" ]; then
        RETRY_COUNT=$((RETRY_COUNT+1))
        echo "Retry $RETRY_COUNT/$MAX_RETRIES: Failed to get instrumentation key. Waiting 10 seconds..."
        sleep 10
    else
        echo "Successfully retrieved instrumentation key!"
    fi
done

if [ -n "$INSTRUMENTATION_KEY" ]; then
    # Add Application Insights to the Web App
    echo "Adding Application Insights to Web App..."
    az webapp config appsettings set --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP \
        --settings APPINSIGHTS_INSTRUMENTATIONKEY=$INSTRUMENTATION_KEY \
        APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=$INSTRUMENTATION_KEY \
        --only-show-errors
    
    echo "Application Insights successfully configured."
else
    # Try the direct approach if ARM template didn't work
    echo "Warning: Could not retrieve instrumentation key after $MAX_RETRIES attempts."
    echo "Trying direct creation of Application Insights..."
    
    # Direct creation approach
    az monitor app-insights component create \
        --app $APP_INSIGHTS_NAME \
        --location $LOCATION \
        --resource-group $RESOURCE_GROUP \
        --application-type web \
        --workspace $LOG_ANALYTICS \
        --only-show-errors
        
    # Get instrumentation key again
    INSTRUMENTATION_KEY=$(az monitor app-insights component show \
        --app $APP_INSIGHTS_NAME \
        --resource-group $RESOURCE_GROUP \
        --query instrumentationKey \
        --output tsv --only-show-errors 2>/dev/null || echo "")
    
    if [ -n "$INSTRUMENTATION_KEY" ]; then
        az webapp config appsettings set --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP \
            --settings APPINSIGHTS_INSTRUMENTATIONKEY=$INSTRUMENTATION_KEY \
            APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=$INSTRUMENTATION_KEY \
            --only-show-errors
        echo "Application Insights successfully configured using direct method."
    else
        echo "Warning: Could not configure Application Insights. You may need to do this manually."
    fi
fi

# Enable Always On for the web app to improve reliability
echo "Enabling 'Always On' for the Web App..."
az webapp config set --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP --always-on true

# Add a restart to ensure new container is used
echo "Restarting web app to ensure changes are applied..."
az webapp restart --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP

echo "==============================================================="
echo "Deployment completed successfully!"
echo "==============================================================="
echo "You can access your app at: https://$WEB_APP_NAME.azurewebsites.net"
echo "Application Insights dashboard: https://portal.azure.com/#resource/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/microsoft.insights/components/$APP_INSIGHTS_NAME/overview"
echo "==============================================================="
