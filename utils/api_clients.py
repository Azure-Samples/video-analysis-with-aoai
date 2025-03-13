import os
import streamlit as st
from openai import AzureOpenAI
import logging

# Configure logging
logger = logging.getLogger(__name__)

def initialize_api_clients():
    """Initialize API clients if they don't exist in session state."""
    if 'api_clients_initialized' not in st.session_state:
        try:
            # Configure API clients
            aoai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
            aoai_apikey = os.environ["AZURE_OPENAI_API_KEY"]
            aoai_apiversion = os.environ["AZURE_OPENAI_API_VERSION"]
            aoai_model_name = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
            
            # Create AOAI client for answer generation
            st.session_state.aoai_client = AzureOpenAI(
                azure_deployment=aoai_model_name,
                api_version=aoai_apiversion,
                azure_endpoint=aoai_endpoint,
                api_key=aoai_apikey
            )
            st.session_state.aoai_model_name = aoai_model_name
            
            # Configure Whisper client
            whisper_endpoint = os.environ["WHISPER_ENDPOINT"]
            whisper_apikey = os.environ["WHISPER_API_KEY"]
            whisper_apiversion = os.environ["WHISPER_API_VERSION"]
            whisper_model_name = os.environ["WHISPER_DEPLOYMENT_NAME"]
            
            st.session_state.whisper_client = AzureOpenAI(
                api_version=whisper_apiversion,
                azure_endpoint=whisper_endpoint,
                api_key=whisper_apikey
            )
            st.session_state.whisper_model_name = whisper_model_name
            
            st.session_state.api_clients_initialized = True
            logger.info("API clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize API clients: {str(e)}")
            st.error(f"Failed to initialize API clients: {str(e)}")
            # Create empty placeholders so we don't crash
            st.session_state.aoai_client = None
            st.session_state.whisper_client = None
            st.session_state.api_clients_initialized = False

def validate_azure_endpoint(endpoint):
    """Validate Azure endpoint format."""
    if not endpoint:
        return False
    if not endpoint.startswith("https://"):
        return False
    if not endpoint.endswith(".openai.azure.com/"):
        # Add trailing slash if missing
        if endpoint.endswith(".openai.azure.com"):
            return endpoint + "/"
    return endpoint

def test_api_connection(client, is_aoai=True):
    """Test API connection."""
    try:
        if is_aoai:
            # Simple test API call to check connection
            response = client.chat.completions.create(
                model=st.session_state.api_config["azure_deployment"],
                messages=[{"role": "user", "content": "Hello, this is a connection test"}],
                max_tokens=10
            )
            return True, "Connection successful"
        else:
            # No easy way to test Whisper without audio file, so we'll just check the client
            if client:
                return True, "Client initialized"
            else:
                return False, "Failed to initialize client"
    except Exception as e:
        return False, str(e)

def update_api_clients():
    """Update API clients with new configuration."""
    try:
        # Get values from session state
        azure_endpoint = st.session_state.api_config["azure_endpoint"]
        azure_api_key = st.session_state.api_config["azure_api_key"]
        azure_deployment = st.session_state.api_config["azure_deployment"]
        azure_api_version = st.session_state.api_config["azure_api_version"]
        
        whisper_endpoint = st.session_state.api_config["whisper_endpoint"]
        whisper_api_key = st.session_state.api_config["whisper_api_key"]
        whisper_deployment = st.session_state.api_config["whisper_deployment"]
        whisper_api_version = st.session_state.api_config["whisper_api_version"]
        
        # Validate endpoints
        valid_azure = validate_azure_endpoint(azure_endpoint)
        valid_whisper = validate_azure_endpoint(whisper_endpoint)
        
        api_updated = False
        whisper_updated = False
        
        # Update Azure OpenAI client if configuration is valid
        if valid_azure and azure_api_key and azure_deployment and azure_api_version:
            try:
                # Create new client
                new_aoai_client = AzureOpenAI(
                    azure_deployment=azure_deployment,
                    api_version=azure_api_version,
                    azure_endpoint=azure_endpoint,
                    api_key=azure_api_key
                )
                
                # Test the new client
                success, message = test_api_connection(new_aoai_client)
                
                if success:
                    # If successful, update the client
                    st.session_state.aoai_client = new_aoai_client
                    st.session_state.aoai_model_name = azure_deployment
                    api_updated = True
                    st.success(f"Azure OpenAI API settings updated successfully: {message}")
                else:
                    st.error(f"Failed to connect to Azure OpenAI API: {message}")
            except Exception as e:
                st.error(f"Failed to update Azure OpenAI client: {str(e)}")
        else:
            if not valid_azure:
                st.error("Invalid Azure OpenAI endpoint format. Should be: https://YOUR_RESOURCE_NAME.openai.azure.com/")
        
        # Update Whisper client if configuration is valid
        if valid_whisper and whisper_api_key and whisper_deployment and whisper_api_version:
            try:
                # Create new client
                new_whisper_client = AzureOpenAI(
                    api_version=whisper_api_version,
                    azure_endpoint=whisper_endpoint,
                    api_key=whisper_api_key
                )
                
                # Test the new client (basic validation only)
                success, message = test_api_connection(new_whisper_client, is_aoai=False)
                
                if success:
                    # If successful, update the client
                    st.session_state.whisper_client = new_whisper_client
                    st.session_state.whisper_model_name = whisper_deployment
                    whisper_updated = True
                    st.success(f"Whisper API settings updated successfully: {message}")
                else:
                    st.error(f"Failed to initialize Whisper client: {message}")
            except Exception as e:
                st.error(f"Failed to update Whisper client: {str(e)}")
        else:
            if not valid_whisper:
                st.error("Invalid Whisper endpoint format. Should be: https://YOUR_RESOURCE_NAME.openai.azure.com/")
        
        # Update session state to indicate that clients have been updated
        if api_updated or whisper_updated:
            # Also update the environment variables (optional, for persistence)
            if api_updated:
                os.environ["AZURE_OPENAI_ENDPOINT"] = azure_endpoint
                os.environ["AZURE_OPENAI_API_KEY"] = azure_api_key
                os.environ["AZURE_OPENAI_API_VERSION"] = azure_api_version
                os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"] = azure_deployment
            
            if whisper_updated:
                os.environ["WHISPER_ENDPOINT"] = whisper_endpoint
                os.environ["WHISPER_API_KEY"] = whisper_api_key
                os.environ["WHISPER_API_VERSION"] = whisper_api_version
                os.environ["WHISPER_DEPLOYMENT_NAME"] = whisper_deployment
            
            return True
        
        return False
        
    except Exception as e:
        st.error(f"Error updating API clients: {str(e)}")
        logger.error(f"Error updating API clients: {str(e)}")
        return False
