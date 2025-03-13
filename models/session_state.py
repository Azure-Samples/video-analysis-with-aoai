import streamlit as st
import os
from config import DEFAULT_SEGMENT_INTERVAL, DEFAULT_FRAMES_PER_SECOND, RESIZE_OF_FRAMES, DEFAULT_TEMPERATURE, VIDEO_ANALYSIS_SYSTEM_PROMPT, VIDEO_ANALYSIS_USER_PROMPT, CHAT_SYSTEM_PROMPT

def initialize_session_state():
    """Initialize all session state variables."""
    
    # Navigation state
    if "current_phase" not in st.session_state:
        st.session_state.current_phase = "Upload"
    
    # Make sure the current_phase is valid (handles added phases after app has been run before)
    valid_phases = ["Upload", "Analyze", "Chat", "Readme"]
    if st.session_state.current_phase not in valid_phases:
        st.session_state.current_phase = "Upload"
    
    # Video source state
    if "video_file" not in st.session_state:
        st.session_state.video_file = None
    if "video_url" not in st.session_state:
        st.session_state.video_url = ""
    if "file_or_url" not in st.session_state:
        st.session_state.file_or_url = "File"
    
    # Analysis state
    if "analyses" not in st.session_state:
        st.session_state.analyses = []
    if "current_analyses" not in st.session_state:
        st.session_state.current_analyses = []
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Configuration state
    if "config" not in st.session_state:
        st.session_state.config = {
            "audio_transcription": True,
            "show_transcription": True,
            "segment_interval": DEFAULT_SEGMENT_INTERVAL,
            "frames_per_second": float(DEFAULT_FRAMES_PER_SECOND),
            "resize": RESIZE_OF_FRAMES,
            "save_frames": False,
            "temperature": DEFAULT_TEMPERATURE,
            "video_analysis_system_prompt": VIDEO_ANALYSIS_SYSTEM_PROMPT,
            "video_analysis_user_prompt": VIDEO_ANALYSIS_USER_PROMPT,
            "chat_system_prompt": CHAT_SYSTEM_PROMPT,
            "enable_range": False,
            "start_time": 0,
            "end_time": 0
        }
    
    # Chat configuration state
    if "chat_config" not in st.session_state:
        st.session_state.chat_config = {
            "model": "gpt-4o",
            "temperature": 0.7,
            "summarize_first": False,
            "include_transcription": True,
            "max_context": 5,
            "expert_mode": False
        }
    
    # API configuration state
    if "api_config" not in st.session_state:
        st.session_state.api_config = {
            "azure_endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            "azure_api_key": os.environ.get("AZURE_OPENAI_API_KEY", ""),
            "azure_api_version": os.environ.get("AZURE_OPENAI_API_VERSION", ""),
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", ""),
            "whisper_endpoint": os.environ.get("WHISPER_ENDPOINT", ""),
            "whisper_api_key": os.environ.get("WHISPER_API_KEY", ""),
            "whisper_api_version": os.environ.get("WHISPER_API_VERSION", ""),
            "whisper_deployment": os.environ.get("WHISPER_DEPLOYMENT_NAME", "")
        }

def get_analysis_count():
    """Get the number of analyses."""
    return len(st.session_state.analyses)

def clear_chat_history():
    """Clear chat history."""
    st.session_state.chat_history = []

def add_chat_message(role, content):
    """Add a message to chat history."""
    st.session_state.chat_history.append({"role": role, "content": content})

def add_analysis(analysis_data):
    """Add an analysis to the analyses list."""
    st.session_state.current_analyses.append(analysis_data)
