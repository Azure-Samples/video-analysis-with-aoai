import streamlit as st
import os
from dotenv import load_dotenv
import logging

# Import logging utility
from utils.logging_utils import setup_logging

# Import components
from components.upload import show_upload_page
from components.analyze import show_analyze_page
from components.chat import show_chat_page

# Import state management
from models.session_state import initialize_session_state

# Import API clients
from utils.api_clients import initialize_api_clients

# Import authentication functions
from utils.auth import require_auth, logout, is_authenticated, AUTH_ENABLED

# Configure page
st.set_page_config(
    page_title="Video Analysis and Chat with LLM's",
    layout="wide",
    initial_sidebar_state="auto",
)

def main():
    # Set up logging - will only initialize once regardless of how many times Streamlit reruns
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    
    # Load environment variables
    load_dotenv(override=True)
    logger.debug("Environment variables loaded")
    
    # Log key auth-related variables
    logger.info(f"AUTH_ENABLED: {os.getenv('VITE_AUTH_ENABLED', 'Not set')}")
    logger.info(f"FRONTEND_URL: {os.getenv('FRONTEND_URL', 'Not set')}")
    logger.info(f"AUTH_URL: {os.getenv('VITE_AUTH_URL', 'Not set')}")
    
    logger.info("Starting authentication process")
    
    # Check for logout action through query parameter
    if AUTH_ENABLED and "logout" in st.query_params:
        logger.info("Logout action detected in query parameters")
        st.query_params.clear()
        logout()
        # Don't call st.rerun() here, logout() will handle redirection
    
    # Check authentication before proceeding
    logger.info("Checking authentication status")
    if not require_auth():
        logger.info("Authentication failed, stopping app execution")
        st.stop()
    
    logger.info("Authentication successful, continuing with app")
    
    # Initialize session state
    initialize_session_state()
    logger.debug("Session state initialized")
    
    # Initialize API clients if not already done
    initialize_api_clients()
    logger.debug("API clients initialization attempted")
    
    # Header and navigation with authentication info
    header_cols = st.columns([3, 1])
    
    with header_cols[0]:
        st.image("media/microsoft.png", width=100)
        st.markdown(
            """
            <div style="margin-top: 5px;">
                <a href="https://github.com/john-carroll-sw/video-analysis-with-gpt-4o" target="_blank">
                    <img src="https://img.shields.io/badge/GitHub-View%20on%20GitHub-blue?logo=github" alt="GitHub Repository"/>
                </a>
            </div>
            """, 
            unsafe_allow_html=True
        )
        st.title('Video Analysis and Chat with LLM\'s')
    
    # Show user info and logout button if authenticated
    with header_cols[1]:
        if AUTH_ENABLED and is_authenticated():
            st.markdown(f"""
            <div style="display: flex; justify-content: flex-end; align-items: center; margin-top: 20px;">
                <a href="?logout=true" style="display: inline-flex; align-items: center; justify-content: center; 
                    padding: 5px 12px; border-radius: 4px; background: transparent; 
                    color: currentColor; border: none; cursor: pointer; transition: background 0.2s;
                    text-decoration: none;" 
                    onmouseover="this.style.background='rgba(0,0,0,0.05)'" 
                    onmouseout="this.style.background='transparent'">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" 
                stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                style="margin-right: 5px;">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                <polyline points="16 17 21 12 16 7"></polyline>
                <line x1="21" y1="12" x2="9" y2="12"></line>
                    </svg>
                    Logout
                </a>
            </div>
            """, unsafe_allow_html=True)
    
    # Define tab titles and corresponding phases
    tabs = [
        ("Upload", "Upload"),
        ("Analyze", "Analyze"),
        ("Chat", "Chat")
    ]
    
    # Create custom tabs using columns and buttons
    cols = st.columns(len(tabs))
    
    prev_phase = st.session_state.current_phase
    
    for i, (label, phase) in enumerate(tabs):
        with cols[i]:
            button_type = "primary" if st.session_state.current_phase == phase else "secondary"
            disabled = False
            if st.button(label, key=f"tab_{i}", type=button_type, disabled=disabled, use_container_width=True):
                logger.info(f"Navigation: Switching from {prev_phase} to {phase}")
                st.session_state.current_phase = phase
                st.rerun()
    
    st.divider()  # Separator below tabs
    
    # Show the current phase
    logger.debug(f"Rendering phase: {st.session_state.current_phase}")
    if st.session_state.current_phase == "Upload":
        show_upload_page()
    elif st.session_state.current_phase == "Analyze":
        show_analyze_page()
    elif st.session_state.current_phase == "Chat":
        show_chat_page()

if __name__ == "__main__":
    main()
