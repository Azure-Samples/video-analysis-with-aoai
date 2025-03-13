import streamlit as st
import json
import logging
from utils.api_clients import update_api_clients
from utils.analysis import chat_with_video_analysis
from config import CHAT_SYSTEM_PROMPT
from utils.logging_utils import log_session_state, TimerLog

# Set up logger for this component
logger = logging.getLogger('chat')

def show_chat_page():
    """Display the chat interface."""
    logger.info("Rendering chat page")
    
    # Log current session state
    log_session_state(logger, st.session_state, "CHAT: ")
    
    # Chat configuration sidebar
    with st.sidebar:
        logger.debug("Rendering sidebar configuration")
        st.title("Chat Settings")
        
        # Model selection (limited to models that can understand the analysis)
        model_options = ["gpt-4o"]
        selected_model = st.selectbox(
            "Model",
            options=model_options,
            index=model_options.index(st.session_state.chat_config.get("model", "gpt-4o")) if st.session_state.chat_config.get("model") in model_options else 0
        )
        st.session_state.chat_config["model"] = selected_model
        
        # Temperature slider with info tooltip
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.chat_config.get("temperature", 0.7),
            step=0.1,
            help="Higher values make output more random, lower values more deterministic"
        )
        st.session_state.chat_config["temperature"] = temperature
        
        # Context handling options
        st.subheader("Context Settings")
        
        st.session_state.chat_config["summarize_first"] = st.checkbox(
            "Generate summary first",
            value=st.session_state.chat_config.get("summarize_first", True),
            help="Create a high-level summary of all segments before answering questions"
        )
        
        st.session_state.chat_config["include_transcription"] = st.checkbox(
            "Include transcriptions in context",
            value=st.session_state.chat_config.get("include_transcription", True),
            help="Include audio transcriptions as part of the analysis context"
        )
        
        max_context = st.slider(
            "Max context length (segments)",
            min_value=1,
            max_value=len(st.session_state.analyses) if st.session_state.analyses else 5,
            value=st.session_state.chat_config.get("max_context", len(st.session_state.analyses) if st.session_state.analyses else 5),
            help="Maximum number of analysis segments to include in context"
        )
        st.session_state.chat_config["max_context"] = max_context
        
        # Action buttons
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Clear Chat History", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()
        with col2:
            if st.button("Return to Analysis", use_container_width=True):
                st.session_state.current_phase = "Analyze" 
                st.rerun()
        
        st.markdown("---")
        expert_mode = st.toggle(
            "Advanced Options", 
            value=st.session_state.chat_config.get("expert_mode", False),
            help="Show advanced options and technical details"
        )
        st.session_state.chat_config["expert_mode"] = expert_mode
        
        # Show additional expert options if enabled
        if expert_mode:
            # System prompt customization
            chat_system_prompt = st.text_area(
                "System Prompt",
                value=st.session_state.chat_config.get("chat_system_prompt", CHAT_SYSTEM_PROMPT),
                height=100
            )
            st.session_state.chat_config["chat_system_prompt"] = chat_system_prompt
            
            # Model parameters
            st.session_state.chat_config["max_tokens"] = st.number_input(
                "Max Response Tokens",
                min_value=100,
                max_value=4096,
                value=st.session_state.chat_config.get("max_tokens", 1000),
                step=50
            )
            
            # API Configuration Section
            show_api_configuration()
        
        # Log configuration changes
        old_config = getattr(st.session_state, '_previous_chat_config', None)
        # Store current config for comparison next time
        st.session_state._previous_chat_config = st.session_state.chat_config.copy()
        
        if old_config:
            for key, value in st.session_state.chat_config.items():
                if key in old_config and old_config[key] != value:
                    logger.info(f"Chat config changed: {key} = {value} (was {old_config[key]})")
    
    # Main chat container
    st.header("💬 Chat about the video analysis")
    
    # Display chat interface
    logger.debug("Rendering chat interface")
    show_chat_interface()

def show_api_configuration():
    """Display API configuration UI."""
    logger.debug("Rendering API configuration")
    st.subheader("API Configuration")
    
    # OpenAI API Configuration Section
    with st.expander("Azure OpenAI API Settings", expanded=False):
        # Azure OpenAI settings
        azure_api_key = st.text_input(
            "Azure OpenAI API Key", 
            type="password",
            value=st.session_state.api_config["azure_api_key"],
            placeholder="your-azure-openai-api-key"
        )
        st.session_state.api_config["azure_api_key"] = azure_api_key
        
        azure_endpoint = st.text_input(
            "Azure OpenAI Endpoint", 
            value=st.session_state.api_config["azure_endpoint"],
            placeholder="https://your-azure-openai-endpoint.openai.azure.com/"
        )
        st.session_state.api_config["azure_endpoint"] = azure_endpoint
        
        azure_deployment = st.text_input(
            "Azure Deployment Name", 
            value=st.session_state.api_config["azure_deployment"],
            placeholder="gpt-4o",
            help="This is your deployment name, e.g., gpt-4o"
        )
        st.session_state.api_config["azure_deployment"] = azure_deployment
        
        azure_api_version = st.text_input(
            "Azure API Version", 
            value=st.session_state.api_config["azure_api_version"],
            placeholder="2024-08-01-preview"
        )
        st.session_state.api_config["azure_api_version"] = azure_api_version
        
        st.markdown("[Get Azure OpenAI access](https://azure.microsoft.com/en-us/products/cognitive-services/openai-service)")
    
    # Whisper API Configuration Section
    with st.expander("Azure Whisper API Settings", expanded=False):
        # Whisper settings
        whisper_api_key = st.text_input(
            "Whisper API Key", 
            type="password",
            value=st.session_state.api_config["whisper_api_key"],
            placeholder="your-whisper-api-key"
        )
        st.session_state.api_config["whisper_api_key"] = whisper_api_key
        
        whisper_endpoint = st.text_input(
            "Whisper Endpoint", 
            value=st.session_state.api_config["whisper_endpoint"],
            placeholder="https://your-whisper-endpoint.openai.azure.com/"
        )
        st.session_state.api_config["whisper_endpoint"] = whisper_endpoint
        
        whisper_deployment = st.text_input(
            "Whisper Deployment Name", 
            value=st.session_state.api_config["whisper_deployment"],
            placeholder="whisper",
            help="This is your whisper deployment name"
        )
        st.session_state.api_config["whisper_deployment"] = whisper_deployment
        
        whisper_api_version = st.text_input(
            "Whisper API Version", 
            value=st.session_state.api_config["whisper_api_version"],
            placeholder="2023-09-01-preview"
        )
        st.session_state.api_config["whisper_api_version"] = whisper_api_version
    
    # Apply Changes button
    if st.button("Apply API Changes", use_container_width=True):
        logger.info("Applying API configuration changes")
        if update_api_clients():
            st.rerun()
    
    # Test Connection button
    if st.button("Test Connection", use_container_width=True):
        from utils.api_clients import test_api_connection
        success, message = test_api_connection(st.session_state.aoai_client)
        if success:
            st.success(f"Azure OpenAI API connection working: {message}")
        else:
            st.error(f"Azure OpenAI API connection error: {message}")
        
        whisper_initialized = hasattr(st.session_state, 'whisper_client') and st.session_state.whisper_client is not None
        if whisper_initialized:
            st.success("Whisper client initialized")
        else:
            st.error("Whisper client not initialized")
    
    # Debug button to check environment variables
    if st.button("Debug API Settings", use_container_width=True):
        st.write("Current API Configuration:")
        for key, value in st.session_state.api_config.items():
            if value and "api_key" in key:
                # Mask API keys for security
                masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                st.write(f"{key}: {masked}")
            else:
                st.write(f"{key}: {value}")
    
    # Debug information
    if st.checkbox("Show Context Statistics", value=False):
        st.subheader("Context Statistics")
        
        # Count total tokens in context
        max_context = st.session_state.chat_config.get("max_context", len(st.session_state.analyses))
        context_size = sum(len(analysis.get("analysis", "").split()) for analysis in st.session_state.analyses[:max_context])
        st.write(f"Analysis segments: {len(st.session_state.analyses[:max_context])}")
        st.write(f"Approximate context size: ~{context_size} words")
        
        # Show most recent chat history entries
        if st.session_state.chat_history:
            st.write(f"Chat history entries: {len(st.session_state.chat_history)}")
            if len(st.session_state.chat_history) > 0:
                last_msg = next((m for m in reversed(st.session_state.chat_history) if m["role"] == "user"), None)
                if last_msg:
                    st.write(f"Latest user query: '{last_msg['content'][:50]}...' ({len(last_msg['content'].split())} words)")

def show_chat_interface():
    """Display the chat interface with message history and input."""
    logger.debug(f"Rendering chat interface with {len(st.session_state.chat_history)} messages")
    
    # Chat interface with fixed scrolling region
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    # Messages area (scrollable)
    st.markdown('<div class="messages-container">', unsafe_allow_html=True)
    
    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
    st.markdown('</div>', unsafe_allow_html=True)  # Close messages container
    
    # Chat input area (fixed at bottom)
    st.markdown('<div class="chat-input-container">', unsafe_allow_html=True)
    
    # Chat input with prompt
    placeholder_text = "Ask a question about the video analysis..."
    prompt = st.chat_input(placeholder_text)
    
    if prompt:
        handle_chat_input(prompt)
    
    st.markdown('</div>', unsafe_allow_html=True)  # Close input container

def handle_chat_input(prompt):
    """Handle user chat input."""
    logger.info(f"New chat input received: {prompt[:50]}..." + ("" if len(prompt) <= 50 else ""))
    logger.debug(f"Full user prompt: {prompt}")
    
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Get settings from session state
        logger.debug(f"Using model settings: temp={st.session_state.chat_config.get('temperature')}, summarize={st.session_state.chat_config.get('summarize_first')}, max_context={st.session_state.chat_config.get('max_context')}")
        temperature = st.session_state.chat_config.get("temperature", 0.7)
        summarize_first = st.session_state.chat_config.get("summarize_first", False)
        max_context = st.session_state.chat_config.get("max_context", len(st.session_state.analyses))
        
        # Make sure clients are properly initialized before use
        if not hasattr(st.session_state, 'aoai_client') or st.session_state.aoai_client is None:
            error_msg = "Azure OpenAI client is not properly configured. Please check API settings."
            message_placeholder.error(error_msg)
            logger.error("Azure OpenAI client is not initialized")
            full_response = error_msg
        else:
            try:
                logger.debug("Starting chat request")
                with TimerLog(logger, "Processing chat request"):
                    # Limit context to max_context segments
                    limited_analyses = st.session_state.analyses[:max_context] if max_context < len(st.session_state.analyses) else st.session_state.analyses
                    
                    # Get chat history formatted for API
                    api_messages = []
                    for msg in st.session_state.chat_history:
                        if msg["role"] in ["user", "assistant"]:
                            api_messages.append({"role": msg["role"], "content": msg["content"]})
                    
                    # Get streaming response
                    response = chat_with_video_analysis(
                        query=prompt,
                        analyses=limited_analyses,
                        chat_history=api_messages,
                        temperature=temperature,
                        summarize_first=summarize_first
                    )
                    
                    # Process streaming response
                    if isinstance(response, str):  # Error message returned
                        full_response = response
                        message_placeholder.error(full_response)
                    else:  # Stream the response
                        for chunk in response:
                            if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                                full_response += chunk.choices[0].delta.content
                                message_placeholder.markdown(full_response + "▌")
                        
                        # Display final response without cursor
                        message_placeholder.markdown(full_response)
                
                logger.info(f"Chat response generated, length: {len(full_response)}")
                preview_length = 500
                logger.debug(f"Response preview: {full_response[:preview_length]}..." + 
                            ("" if len(full_response) <= preview_length else f" [truncated, total length: {len(full_response)}]"))
                
                # For complete analysis, still log the full response at TRACE level if needed
                if logger.isEnabledFor(logging.DEBUG):  # Only gather this string if we're actually in DEBUG mode
                    logger.debug(f"Full model response: {full_response}")
                
            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                logger.exception("Chat error")
                message_placeholder.error(error_msg)
                full_response = error_msg
                logger.error(f"Chat error: {str(e)}")
        
    # Update chat history
    logger.debug("Updating chat history")
    from models.session_state import add_chat_message
    add_chat_message("user", prompt)
    add_chat_message("assistant", full_response)
    
    # Log the chat interaction ID or sequence number for correlation
    logger.info(f"Chat interaction #{len(st.session_state.chat_history)//2} completed")