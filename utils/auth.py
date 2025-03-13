import os
import json
import time
import base64
import requests
import streamlit as st
import logging
import sys
import socket
from dotenv import load_dotenv

# Set up logger with explicit console handler for Azure Web App logs
logger = logging.getLogger('auth')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - AUTH - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Load environment variables
load_dotenv(override=True)

# Get auth URL from environment variable - never hardcode in the source
AUTH_URL = os.getenv("VITE_AUTH_URL")
AUTH_ENABLED = os.getenv("VITE_AUTH_ENABLED", "true").lower() == "true"

# Get application name from environment or default to directory name
APP_NAME = os.environ.get("APP_NAME") or os.path.basename(os.path.abspath(os.curdir))
logger.info(f"Using application name: {APP_NAME}")

# Log all environment variables related to auth
logger.info(f"AUTH_URL: {AUTH_URL}")
logger.info(f"AUTH_ENABLED: {AUTH_ENABLED}")

def initialize_auth():
    """Initialize authentication state variables if they don't exist."""
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    if "auth_expiry" not in st.session_state:
        st.session_state.auth_expiry = 0
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

def encode_token(data):
    """Encode data to base64 (equivalent to btoa in JavaScript)"""
    return base64.b64encode(json.dumps(data).encode()).decode()

def decode_token(token):
    """Decode base64 token (equivalent to atob in JavaScript)"""
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception as e:
        logger.error(f"Token decode error: {str(e)}")
        return None

def redirect_to_signin():
    """Redirect to authentication service signin page"""
    encoded_info = encode_token(FRONTEND_INFO)
    signin_url = f"{AUTH_URL}/signin/?v={encoded_info}"
    
    # Decode for logging to see exactly what we're sending
    decoded = json.dumps(json.loads(base64.b64decode(encoded_info)))
    logger.info(f"Auth redirect with encoded info: {encoded_info}")
    logger.info(f"Auth redirect with decoded info: {decoded}")
    logger.info(f"Full signin URL: {signin_url}")
    
    # Enhanced redirect with both meta refresh and JavaScript
    st.markdown(f"""
    <meta http-equiv="refresh" content="0;URL='{signin_url}'" />
    <script>
        window.location.href = "{signin_url}";
    </script>
    <p>If you are not redirected automatically, <a href="{signin_url}">click here</a>.</p>
    """, unsafe_allow_html=True)
    st.stop()

def parse_token_from_url():
    """Check if there's a token in the URL parameters."""
    token = st.query_params.get("t", None)
    
    if token:
        logger.info("Found token in URL parameters")
        # Remove token from URL to prevent issues on refresh
        st.query_params.clear()
        return token
    
    return None

def check_auth(token):
    """Verify if the token is valid by calling the authentication API."""
    if not token:
        return False
    
    try:
        # Decode token to get expiry
        token_data = json.loads(base64.b64decode(token))
        
        # Check if token is expired
        if time.time() * 1000 > token_data.get('expiry', 0):
            logger.info("Token expired, verifying with API")
            # Call API to check if token is still valid
            response = requests.get(
                f"{AUTH_URL}/auth/check/",
                headers={"x-token": token_data.get('token', '')},
                timeout=10
            )
            
            if not response.ok:
                logger.warning("API auth check failed")
                return False
            
            logger.info("API auth check successful")
            # Update token in session state
            st.session_state.auth_token = token
            st.session_state.auth_user = token_data.get('user', {})
            st.session_state.auth_expiry = token_data.get('expiry', 0)
            st.session_state.authenticated = True
            return True
        else:
            logger.info("Token still valid")
            # Store token info in session state
            st.session_state.auth_token = token
            st.session_state.auth_user = token_data.get('user', {})
            st.session_state.auth_expiry = token_data.get('expiry', 0)
            st.session_state.authenticated = True
            return True
    
    except Exception as e:
        logger.error(f"Auth check error: {str(e)}")
        return False

def get_username():
    """Get username from token if available"""
    if st.session_state.auth_user and 'name' in st.session_state.auth_user:
        return st.session_state.auth_user['name']
    return "User"
    
def logout():
    """Clear auth session data and redirect to sign-in"""
    logger.info("Logging out user")
    
    # Preserve auth-related keys but set to None/False
    st.session_state.auth_token = None
    st.session_state.auth_user = None
    st.session_state.auth_expiry = 0
    st.session_state.authenticated = False
    
    # Clear all non-auth session state to reset the app
    for key in list(st.session_state.keys()):
        if key not in ["auth_token", "auth_user", "auth_expiry", "authenticated"]:
            del st.session_state[key]
    
    # Force redirect to signin page after clearing session
    redirect_to_signin()

def is_authenticated():
    """Check if user is authenticated"""
    return st.session_state.get("authenticated", False)

def require_auth():
    """Main authentication function to be used in Streamlit apps"""
    logger.info("Starting authentication check")
    
    if not AUTH_ENABLED:
        logger.info("Authentication is disabled, proceeding without auth")
        return True
        
    # Initialize authentication state
    initialize_auth()
    
    # Check if already authenticated in this session
    if st.session_state.authenticated:
        logger.info("User is already authenticated in session")
        return True
        
    # Check for token in query params
    token_from_url = parse_token_from_url()
    
    if token_from_url:
        logger.info("Found token in URL, validating...")
        # Validate token
        is_valid = check_auth(token_from_url)
        if is_valid:
            logger.info("Token from URL is valid")
            st.session_state.auth_token = token_from_url
            st.session_state.authenticated = True
            return True
        else:
            logger.warning("Token from URL is invalid, redirecting to sign-in")
            redirect_to_signin()
            
    # Check for token in session state
    elif "auth_token" in st.session_state and st.session_state.auth_token:
        logger.info("Found token in session state, validating...")
        is_valid = check_auth(st.session_state.auth_token)
        if is_valid:
            logger.info("Token from session state is valid")
            st.session_state.authenticated = True
            return True
        else:
            logger.warning("Token from session state is invalid, redirecting to sign-in")
            st.session_state.auth_token = None
            redirect_to_signin()
    
    # No token found
    else:
        logger.info("No token found, redirecting to sign-in")
        redirect_to_signin()
        
    return False

# Function to detect if running locally
def is_running_locally():
    """Check if the app is running on localhost"""
    # Check for common environment variables that indicate cloud deployment
    if os.environ.get('WEBSITE_SITE_NAME') or os.environ.get('KUBERNETES_SERVICE_HOST'):
        logger.info("Cloud deployment environment variables detected")
        return False
    
    # Check if we're in a container
    if os.path.exists('/.dockerenv'):
        logger.info("Docker container environment detected")
        return False
    
    # Check for macOS or common development hostnames
    hostname = socket.gethostname()
    if hostname.lower() == 'localhost' or hostname.startswith('127.0.0.1'):
        logger.info(f"Standard localhost hostname detected: {hostname}")
        return True
    
    # Check for macOS or other typical dev environment patterns
    if '.local' in hostname.lower() or 'macbook' in hostname.lower() or 'mbp' in hostname.lower():
        logger.info(f"Development machine hostname detected: {hostname}")
        return True
        
    # Try to determine if Streamlit is running in "local" mode
    streamlit_server_port = os.environ.get("STREAMLIT_SERVER_PORT")
    if streamlit_server_port and streamlit_server_port in ["8501", "8502", "8503"]:
        logger.info(f"Streamlit appears to be running locally on port {streamlit_server_port}")
        return True
        
    # As a final check, see if we can reach the loopback interface
    try:
        socket.create_connection(("localhost", int(os.environ.get("STREAMLIT_SERVER_PORT", 8501))), timeout=1)
        logger.info("Successfully connected to localhost, assuming local development environment")
        return True
    except (socket.error, socket.timeout):
        logger.info(f"Could not connect to localhost:{os.environ.get('STREAMLIT_SERVER_PORT', 8501)}")
        pass
    
    # Default assumption - if no cloud environments detected, assume it's local
    # This is safer than assuming cloud when we're uncertain
    logger.info("No definitive cloud markers detected, assuming local environment")
    return True

# Get frontend URL using smart detection
def determine_frontend_url():
    """Smart detection of frontend URL based on environment"""
    # First check if explicitly set in environment variables
    frontend_url = os.environ.get("FRONTEND_URL")
    
    if frontend_url:
        logger.info(f"Using FRONTEND_URL from environment: {frontend_url}")
    else:
        # If running locally, use localhost
        local_env = is_running_locally()
        if local_env:
            # Try multiple ways to detect the actual running port
            
            # 1. First check for Streamlit server port from environment
            port = os.environ.get("STREAMLIT_SERVER_PORT")
            
            # 2. If not set in environment, try to detect from STREAMLIT_CONFIG
            if not port and 'STREAMLIT_CONFIG' in os.environ:
                try:
                    import json
                    config = json.loads(os.environ['STREAMLIT_CONFIG'])
                    if 'server' in config and 'port' in config['server']:
                        port = config['server']['port']
                except:
                    pass
                    
            # 3. If Python is running in Streamlit's process, try to find port in sys.argv
            if not port:
                import sys
                for i, arg in enumerate(sys.argv):
                    if arg == "--server.port" and i+1 < len(sys.argv):
                        port = sys.argv[i+1]
                        break
                        
            # 4. Check common ports to see which one might be open
            if not port:
                # Try to detect active port by checking common Streamlit ports
                for test_port in ["8501", "8502", "8503", "8504", "8505", "8500"]:
                    try:
                        # Simple URL request to check if a Streamlit server responds
                        import urllib.request
                        urllib.request.urlopen(f"http://localhost:{test_port}", timeout=0.5)
                        port = test_port
                        logger.info(f"Detected active Streamlit server on port {port}")
                        break
                    except:
                        continue
            
            # Default to 8501 if we couldn't detect the port
            if not port:
                port = "8501"
                logger.warning(f"Could not detect Streamlit port, using default: {port}")
            else:
                logger.info(f"Using detected Streamlit port: {port}")
                
            frontend_url = f"http://localhost:{port}"
            logger.info(f"Using localhost URL for local environment: {frontend_url}")
        else:
            # Try to get from .env file as fallback
            frontend_url = os.getenv("FRONTEND_URL")
            logger.info(f"Using FRONTEND_URL from .env file: {frontend_url}")
            
            # Last resort fallback for Azure deployment
            if not frontend_url:
                # Check for Azure Web App name
                site_name = os.environ.get('WEBSITE_SITE_NAME')
                if site_name:
                    frontend_url = f"https://app-{APP_NAME}.azurewebsites.net"
                    logger.info(f"Derived FRONTEND_URL from Azure site name: {frontend_url}")
                else:
                    # No hardcoded fallbacks - let admin know config is missing
                    logger.error("FRONTEND_URL not found in any configuration source")
                    # For local development, still provide a working URL
                    if local_env:
                        frontend_url = "http://localhost:8501"
                        logger.info(f"Using default localhost URL: {frontend_url}")
                    else:
                        frontend_url = "FRONTEND_URL_NOT_CONFIGURED"
    
    # Ensure the URL doesn't have trailing slashes
    if frontend_url and frontend_url.endswith('/'):
        frontend_url = frontend_url[:-1]
        logger.info(f"Removed trailing slash from FRONTEND_URL: {frontend_url}")
        
    return frontend_url

# Get frontend URL with smart detection
frontend_url = determine_frontend_url()

# Frontend info for authentication
FRONTEND_INFO = {
    "app": APP_NAME,
    "url": frontend_url
}

# Log the frontend info for debugging with explicit JSON serialization
frontend_info_json = json.dumps(FRONTEND_INFO)
logger.info(f"Using FRONTEND_INFO for auth redirection: {frontend_info_json}")
