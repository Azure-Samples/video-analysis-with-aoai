import streamlit as st
import os
import time
import logging
import io  # Add this import for BytesIO
from config import VIDEO_ANALYSIS_SYSTEM_PROMPT, VIDEO_ANALYSIS_USER_PROMPT
from utils.analysis_cache import check_video_analyzed, check_url_analyzed, load_previous_analysis
from utils.logging_utils import log_session_state, TimerLog

from utils.video_processing import get_video_file_info, get_video_url_info

# Set up logger for this component
logger = logging.getLogger('upload')

def show_upload_page():
    """Display the upload and configuration page."""
    logger.info("Rendering upload page")
    
    # Initialize upload status flags if they don't exist
    if "file_uploaded_success" not in st.session_state:
        logger.debug("Initializing file_uploaded_success flag")
        st.session_state.file_uploaded_success = False
    if "url_entered_success" not in st.session_state:
        logger.debug("Initializing url_entered_success flag")
        st.session_state.url_entered_success = False
    if "previous_analysis_path" not in st.session_state:
        logger.debug("Initializing previous_analysis_path")
        st.session_state.previous_analysis_path = None
    if "use_previous_analysis" not in st.session_state:
        logger.debug("Initializing use_previous_analysis flag")
        st.session_state.use_previous_analysis = False
    if "video_info" not in st.session_state:
        logger.debug("Initializing video_info")
        st.session_state.video_info = {}
    
    # Log current session state
    log_session_state(logger, st.session_state, "UPLOAD: ")
    
    # Show sidebar configuration
    with st.sidebar:
        logger.debug("Rendering sidebar configuration")
        
        st.header("Video Configuration")
        
        file_or_url = st.radio(
            "Video source:", 
            ["File", "URL"], 
            index=0 if st.session_state.file_or_url == "File" else 1,
            help="Choose whether to upload a local video file or analyze a video from URL (e.g., YouTube)"
        )
        st.session_state.file_or_url = file_or_url
        
        # Audio options
        st.session_state.config["audio_transcription"] = st.checkbox(
            'Transcribe audio', 
            value=st.session_state.config["audio_transcription"],
            help="Extract and transcribe the audio from the video using Azure Whisper for better analysis"
        )
        
        if st.session_state.config["audio_transcription"]:
            st.session_state.config["show_transcription"] = st.checkbox(
                'Show transcription', 
                value=st.session_state.config["show_transcription"],
                help="Display the transcribed audio text alongside the analysis results"
            )
        
        # Video segmentation and processing options
        st.session_state.config["segment_interval"] = int(st.number_input(
            'Segment interval (seconds)', 
            min_value=1, 
            value=int(st.session_state.config["segment_interval"]),
            help="Determines the length of video segments for analysis. A shorter interval (e.g., every 10 seconds) allows the AI model to capture more granular, context-rich details, which can be beneficial for spotting subtle changes or events. Conversely, a longer interval (e.g., every 60 seconds) offers a broader overview with less processing overhead. Adjust this setting based on the level of detail you require from the video footage."
        ))
        
        # Fix the frames_per_second input with consistent float types
        st.session_state.config["frames_per_second"] = float(st.number_input(
            'Frames per second', 
            min_value=0.1, 
            max_value=30.0,
            value=float(st.session_state.config["frames_per_second"]), 
            step=0.1,
            format="%.1f",
            help="Set the extraction rate: 0.1 FPS captures one frame every 10 seconds (low temporal detail, token-saving), 1 FPS offers a balance between detail and performance, while 30 FPS captures nearly every moment (high temporal detail, higher token usage)."
        ))
        
        st.session_state.config["resize"] = int(st.number_input(
            "Frame resize ratio", 
            min_value=0, 
            value=int(st.session_state.config["resize"]),
            help="Resize factor for extracted frames. Higher values mean smaller images (e.g., 4 = 1/4 size). 0 means no resizing"
        ))
        
        st.session_state.config["save_frames"] = st.checkbox(
            'Save frames', 
            value=st.session_state.config["save_frames"],
            help="Save extracted video frames to disk for later review"
        )
        
        st.session_state.config["temperature"] = st.slider(
            'Temperature', 
            min_value=0.0, 
            max_value=1.0, 
            value=st.session_state.config["temperature"],
            step=0.1,
            help="Controls randomness in AI responses. Higher values (e.g., 0.8) make output more creative, lower values (e.g., 0.2) make it more deterministic"
        )
        
        # AI prompts
        st.session_state.config["video_analysis_system_prompt"] = st.text_area(
            'System Prompt', 
            value=st.session_state.config["video_analysis_system_prompt"],
            height=100,
            help="Instructions for the AI on how to analyze the video. Defines the AI's role and approach"
        )
        
        st.session_state.config["video_analysis_user_prompt"] = st.text_area(
            'User Prompt', 
            value=st.session_state.config["video_analysis_user_prompt"],
            help="The specific request/question for the AI about the video frames"
        )
        
        # Time range options
        st.markdown("---")
        st.subheader("Analysis Range (Optional)")
        
        st.session_state.config["enable_range"] = st.checkbox(
            'Analyze specific time range only', 
            value=st.session_state.config["enable_range"],
            help="Analyze only a specific portion of the video rather than the entire duration"
        )
        
        if st.session_state.config["enable_range"]:
            col1, col2 = st.columns(2)
            with col1:
                st.session_state.config["start_time"] = st.number_input(
                    'Start time (seconds)', 
                    min_value=0, 
                    value=st.session_state.config["start_time"],
                    help="Starting point in the video (in seconds)"
                )
            with col2:
                st.session_state.config["end_time"] = st.number_input(
                    'End time (seconds)', 
                    min_value=0, 
                    value=st.session_state.config["end_time"],
                    help="Ending point in the video (in seconds). 0 means process until the end"
                )
        
        # Log when configuration changes
        old_config = getattr(st.session_state, '_previous_config', None)
        # Store current config for comparison next time
        st.session_state._previous_config = st.session_state.config.copy()
        
        if old_config:
            for key, value in st.session_state.config.items():
                if key in old_config and old_config[key] != value:
                    logger.info(f"Config changed: {key} = {value} (was {old_config[key]})")
    
    # Main upload container
    st.header("Upload Video")
    logger.debug("Rendering main upload area")
    
    if st.session_state.file_or_url == "File":
        # Add option to select between sample video and upload
        st.info("Choose a video source below:")
        
        # Add sample video button - smaller and inline
        if st.button("📹 Use Sample Video", key="use_sample_video"):
            # Path to sample video
            sample_video_path = "./media/sample-video-circuit-board.mp4"
            
            logger.info(f"Using sample video from: {sample_video_path}")
            
            if os.path.exists(sample_video_path):
                # Open the sample video file
                with open(sample_video_path, "rb") as file:
                    # Create BytesIO object to mimic an uploaded file
                    file_content = file.read()
                    sample_video = io.BytesIO(file_content)
                    sample_video.name = "sample-video-circuit-board.mp4"
                    sample_video.size = len(file_content)
                    
                    # Store in session state
                    st.session_state.video_file = sample_video
                    st.session_state.video_url = ""
                    st.session_state.file_uploaded_success = True
                    
                    # Reset the file pointer and process the video
                    sample_video.seek(0)
                    process_uploaded_video(sample_video, is_sample=True)
                    
                    # Force a rerun to update the UI
                    st.rerun()
            else:
                st.error(f"Sample video not found at {sample_video_path}")
                logger.error(f"Sample video not found at {sample_video_path}")
        
        st.write("OR")
        
        # File uploader
        uploaded_file = st.file_uploader("Upload a video file", type=["mp4", "avi", "mov"], key="video_file_uploader")
        
        # When a file is uploaded, store it in session_state and set success flag
        if uploaded_file is not None:
            logger.info(f"File uploaded: {uploaded_file.name} ({uploaded_file.size} bytes)")
            
            # Store in session state
            st.session_state.video_file = uploaded_file
            st.session_state.video_url = ""
            st.session_state.file_uploaded_success = True
            
            # Process the uploaded video
            process_uploaded_video(uploaded_file)
        
        # If returning to this tab with a previously uploaded file
        elif st.session_state.video_file is not None and st.session_state.file_uploaded_success:
            # Display the previously uploaded video
            display_current_video()
    
    else:  # URL input section
        # For URL input, we need a consistent key and to preserve the entered value
        if "url_input" not in st.session_state:
            st.session_state.url_input = "https://www.youtube.com/watch?v=Y6kHpAeIr4c"
        
        st.warning("""
            ⚠️ **Important Note**: YouTube and other media sites has protective measures against webscraping that may block access to videos. 
            If you encounter errors, try:
            - Using file upload instead
            - Using a different video URL
            - Downloading the video first and then uploading it
        """)
        
        url = st.text_input("Enter video URL:", value=st.session_state.url_input, key="video_url_input")
        st.session_state.url_input = url  # Store the current value
        
        if url != "":
            logger.info(f"URL entered: {url}")
            # Extract and store video info
            with st.spinner("Analyzing video metadata..."):
                video_info = get_video_url_info(url)
                st.session_state.video_info = video_info
                logger.info(f"Extracted video info: {video_info}")
            
            # Check if we've analyzed this URL before
            start_time = st.session_state.config["start_time"] if st.session_state.config["enable_range"] else 0
            end_time = st.session_state.config["end_time"] if st.session_state.config["enable_range"] else 0
            previous_analysis_path = check_url_analyzed(url, start_time, end_time)
            
            if previous_analysis_path:
                logger.info(f"Found previous analysis at: {previous_analysis_path}")
                st.session_state.previous_analysis_path = previous_analysis_path
                
                # UI to let the user decide to use previous analysis or re-analyze
                st.info(f"This video URL has been analyzed before. Do you want to use the previous analysis?")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Load Previous Analysis", key="load_previous_url", use_container_width=True):
                        # Load previous analysis
                        previous_analyses = load_previous_analysis(previous_analysis_path)
                        
                        # Set the analyses in session state
                        st.session_state.analyses = previous_analyses
                        
                        # Also set current_analyses to make them visible in the analyze phase
                        st.session_state.current_analyses = []
                        for analysis in previous_analyses:
                            # Format data to match current_analyses structure
                            st.session_state.current_analyses.append({
                                "segment": analysis.get("segment", 0),
                                "start_time": analysis.get("start_time", 0),
                                "end_time": analysis.get("end_time", 0),
                                "analysis": analysis.get("analysis", ""),
                                "transcription": analysis.get("transcription", None)
                            })
                        
                        st.session_state.use_previous_analysis = True
                        st.session_state.current_phase = "Analyze"
                        st.rerun()
                
                with col2:
                    if st.button("Re-Analyze Video", key="re_analyze_url", use_container_width=True):
                        # Set flag to re-analyze
                        st.session_state.use_previous_analysis = False
                        # Continue with normal URL flow
                        st.session_state.video_url = url
                        st.session_state.video_file = None
                        st.session_state.url_entered_success = True
            else:
                # Normal URL flow for new videos
                st.session_state.video_url = url
                st.session_state.video_file = None
                st.session_state.url_entered_success = True
                st.session_state.previous_analysis_path = None
            
            # Add prominent video title display
            video_title = st.session_state.video_info.get('title', 'YouTube Video')
            st.markdown(f"## 🎬 Video: {video_title}")
            
            # Show the video and success message
            st.video(url)
            st.success("URL entered successfully!")
            
            # Display video info in a nice format
            with st.expander("Video Information", expanded=True):
                # First show video title prominently
                st.markdown(f"### 📽️ {video_title}")
                st.markdown("---")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Video Details:**")
                    st.write(f"📝 Title: {video_info.get('title', 'Unknown')}")
                    st.write(f"🖥️ Resolution: {video_info.get('resolution', 'Unknown')}")
                    st.write(f"⏱️ Duration: {video_info.get('duration_formatted', 'Unknown')}")
                    st.write(f"🎬 Source: {video_info.get('format', 'YouTube/URL Video')}")
                
                with col2:
                    st.markdown("**Processing Details:**")
                    segment_interval = st.session_state.config["segment_interval"]
                    st.write(f"🔄 Segment Duration: {segment_interval} seconds")
                    st.write(f"📊 Total Segments: {video_info.get('total_segments', 'Unknown')}")
                    if st.session_state.config["enable_range"]:
                        st.write(f"⏱️ Analysis Range: {st.session_state.config['start_time']}s - {st.session_state.config['end_time']}s")
                    else:
                        st.write(f"⏱️ Analysis Range: Full video (0s - {video_info.get('duration', 0):.1f}s)")
                    st.write(f"🖼️ Frames per Second: {st.session_state.config['frames_per_second']}")
    
    # Continue button - only enable if file is uploaded or URL is entered
    if st.session_state.video_file is not None or st.session_state.video_url != "":
        if not st.session_state.use_previous_analysis:  # Only show if not using previous analysis
            if st.button("Continue to Analysis", type="primary", use_container_width=True):
                logger.info("User clicked Continue to Analysis button")
                # IMPORTANT: Check which input method has content and set file_or_url accordingly
                if st.session_state.video_file is not None:
                    logger.info(f"Setting processing mode to File for {st.session_state.video_file.name}")
                    st.session_state.file_or_url = "File"
                elif st.session_state.video_url != "":
                    logger.info(f"Setting processing mode to URL for {st.session_state.video_url}")
                    st.session_state.file_or_url = "URL"
                
                # Now change the phase
                logger.info("Navigating to Analyze phase")
                st.session_state.current_phase = "Analyze"
                st.rerun()


def process_uploaded_video(video_file, is_sample=False):
    """Process an uploaded/sample video file."""
    # Add prominent video title display
    title = "Sample video: Circuit Board" if is_sample else video_file.name
    st.markdown(f"## 🎬 Video: {title}")
    
    # Extract and store video info
    with st.spinner("Analyzing video metadata..."):
        # Reset file pointer position if needed
        if hasattr(video_file, 'seek'):
            video_file.seek(0)
        video_info = get_video_file_info(video_file)
        st.session_state.video_info = video_info
        logger.info(f"Extracted video info: {video_info}")
    
    # Check if we've analyzed this video before
    with TimerLog(logger, "Checking for previous analysis"):
        # Reset file pointer position if needed
        if hasattr(video_file, 'seek'):
            video_file.seek(0)
        previous_analysis_path = check_video_analyzed(video_file)
    
    if previous_analysis_path:
        logger.info(f"Found previous analysis at: {previous_analysis_path}")
        st.session_state.previous_analysis_path = previous_analysis_path
        
        # UI to let the user decide to use previous analysis or re-analyze
        st.info(f"This video has been analyzed before. Do you want to use the previous analysis?")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Load Previous Analysis", key="load_previous", use_container_width=True):
                # Load previous analysis
                previous_analyses = load_previous_analysis(previous_analysis_path)
                
                # Set the analyses in session state
                st.session_state.analyses = previous_analyses
                
                # Also set current_analyses to make them visible in the analyze phase
                st.session_state.current_analyses = []
                for analysis in previous_analyses:
                    # Format data to match current_analyses structure
                    st.session_state.current_analyses.append({
                        "segment": analysis.get("segment", 0),
                        "start_time": analysis.get("start_time", 0),
                        "end_time": analysis.get("end_time", 0),
                        "analysis": analysis.get("analysis", ""),
                        "transcription": analysis.get("transcription", None)
                    })
                
                st.session_state.use_previous_analysis = True
                st.session_state.current_phase = "Analyze"
                st.rerun()
        
        with col2:
            if st.button("Re-Analyze Video", key="re_analyze", use_container_width=True):
                # Set flag to re-analyze
                st.session_state.use_previous_analysis = False
    else:
        # Normal upload flow for new videos
        st.session_state.previous_analysis_path = None
    
    # Show the video
    if hasattr(video_file, 'seek'):
        video_file.seek(0)
    st.video(video_file)
    st.success(f"{'Sample' if is_sample else 'File'} loaded successfully!")
    
    # Display video info in a nice format
    with st.expander("Video Information", expanded=True):
        # First show video title prominently
        st.markdown(f"### 📽️ {title}")
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**File Details:**")
            st.write(f"📊 File Size: {video_info.get('file_size_formatted', 'Unknown')}")
            st.write(f"🎬 Format: {video_info.get('format', 'Unknown')}")
            st.write(f"🖥️ Resolution: {video_info.get('resolution', 'Unknown')}")
            st.write(f"⏱️ Duration: {video_info.get('duration_formatted', 'Unknown')}")
            st.write(f"🎞️ FPS: {video_info.get('fps', 'Unknown'):.2f}")
        
        with col2:
            st.markdown("**Processing Details:**")
            segment_interval = st.session_state.config["segment_interval"]
            st.write(f"🔄 Segment Duration: {segment_interval} seconds")
            st.write(f"📊 Total Segments: {video_info.get('total_segments', 'Unknown')}")
            if st.session_state.config["enable_range"]:
                st.write(f"⏱️ Analysis Range: {st.session_state.config['start_time']}s - {st.session_state.config['end_time']}s")
            else:
                st.write(f"⏱️ Analysis Range: Full video (0s - {video_info.get('duration', 0):.1f}s)")
            st.write(f"🖼️ Frames per Second: {st.session_state.config['frames_per_second']}")


def display_current_video():
    """Display the currently loaded video and its information."""
    video_file = st.session_state.video_file
    
    # Check if the file is still valid
    if not hasattr(video_file, 'name'):
        st.warning("Video file reference has expired. Please reload the video.")
        return
    
    # Add prominent video title display
    is_sample = video_file.name == "sample-video-circuit-board.mp4"
    title = "Sample video: Circuit Board" if is_sample else video_file.name
    st.markdown(f"## 🎬 Video: {title}")
    
    # Re-display the video
    if hasattr(video_file, 'seek'):
        video_file.seek(0)
    st.video(video_file)
    st.success(f"{'Sample' if is_sample else 'File'} loaded successfully!")
    
    # Display video info if available
    if st.session_state.video_info:
        with st.expander("Video Information", expanded=True):
            # First show video title prominently
            st.markdown(f"### 📽️ {title}")
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**File Details:**")
                st.write(f"📊 File Size: {st.session_state.video_info.get('file_size_formatted', 'Unknown')}")
                st.write(f"🎬 Format: {st.session_state.video_info.get('format', 'Unknown')}")
                st.write(f"🖥️ Resolution: {st.session_state.video_info.get('resolution', 'Unknown')}")
                st.write(f"⏱️ Duration: {st.session_state.video_info.get('duration_formatted', 'Unknown')}")
                st.write(f"🎞️ FPS: {st.session_state.video_info.get('fps', 'Unknown'):.2f}")
            
            with col2:
                st.markdown("**Processing Details:**")
                segment_interval = st.session_state.config["segment_interval"]
                st.write(f"🔄 Segment Duration: {segment_interval} seconds")
                st.write(f"📊 Total Segments: {st.session_state.video_info.get('total_segments', 'Unknown')}")
                if st.session_state.config["enable_range"]:
                    st.write(f"⏱️ Analysis Range: {st.session_state.config['start_time']}s - {st.session_state.config['end_time']}s")
                else:
                    st.write(f"⏱️ Analysis Range: Full video (0s - {st.session_state.video_info.get('duration', 0):.1f}s)")
                st.write(f"🖼️ Frames per Second: {st.session_state.config['frames_per_second']}")
