import streamlit as st
import time
import os
import cv2
import yt_dlp
from yt_dlp.utils import download_range_func
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from moviepy.editor import VideoFileClip
from utils.video_processing import execute_video_processing, load_all_analyses
from utils.analysis_cache import register_video_analysis, register_url_analysis
import logging
import re  # Add this import for regex handling
from utils.logging_utils import log_session_state, TimerLog

# Set up logger for this component
logger = logging.getLogger('analyze')

def show_analyze_page():
    """Display the analysis page."""
    logger.info("Rendering analyze page")
    
    # Log current session state
    log_session_state(logger, st.session_state, "ANALYZE: ")
    logger.info(f"Processing mode: {st.session_state.file_or_url}")
    
    # Minimal sidebar for this phase
    with st.sidebar:
        logger.debug("Rendering sidebar")
        st.info("Video Analysis Results. You can view the detailed analysis in the main panel.")
        
        # Add button to expand/collapse all segments
        if "all_segments_expanded" not in st.session_state:
            st.session_state.all_segments_expanded = False
            
        if st.button("Expand All Segments" if not st.session_state.all_segments_expanded else "Collapse All Segments", use_container_width=True):
            # Toggle the master state
            st.session_state.all_segments_expanded = not st.session_state.all_segments_expanded
            
            # Apply to all segments
            for analysis_data in st.session_state.current_analyses:
                segment_key = f"segment_{analysis_data['segment']}_expanded"
                st.session_state[segment_key] = st.session_state.all_segments_expanded
            
            st.rerun()
            
        if st.button("Edit Configuration", use_container_width=True):
            st.session_state.current_phase = "Upload"
            st.rerun()
    
    # Main processing container
    st.header("Video Processing & Analysis")
    
    # Always show previously processed analyses to keep them visible
    logger.debug(f"Number of analyses to display: {len(st.session_state.current_analyses)}")
    if st.session_state.current_analyses:
        logger.debug("Displaying existing analyses")
        # Create container to display all analyses
        analyses_display_container = st.container()
        
        with analyses_display_container:
            st.subheader(f"Analysis Results ({len(st.session_state.current_analyses)} segments)")
            
            # Show each analysis in an expandable container
            for i, analysis_data in enumerate(st.session_state.current_analyses):
                # Determine if this segment should be expanded
                segment_key = f"segment_{analysis_data['segment']}_expanded"
                if segment_key not in st.session_state:
                    st.session_state[segment_key] = st.session_state.all_segments_expanded
                
                # Create a unique key for each segment's expander and button
                segment_idx = analysis_data['segment']
                
                # Show the segment in an expander - use the state to control expansion
                with st.expander(
                    f"Segment {segment_idx} ({analysis_data['start_time']}-{analysis_data['end_time']} seconds)", 
                    expanded=st.session_state[segment_key]
                ):
                    # Add button to toggle just this segment with a unique key
                    toggle_text = "Collapse" if st.session_state[segment_key] else "Expand"
                    if st.button(toggle_text, key=f"toggle_btn_{segment_idx}", use_container_width=True):
                        # Toggle just this segment's state
                        st.session_state[segment_key] = not st.session_state[segment_key]
                        st.rerun()
                    
                    # Display segment content
                    st.markdown(f"**Analysis**: {analysis_data['analysis']}", unsafe_allow_html=True)
                    if st.session_state.config["show_transcription"] and "transcription" in analysis_data and analysis_data["transcription"]:
                        st.markdown(f"**Transcription**: {analysis_data['transcription']}", unsafe_allow_html=True)
    
    # Check if we need to start processing
    if len(st.session_state.current_analyses) == 0:
        logger.info("No analyses found, initiating processing")
        # We need to process the video
        process_container = st.container()
        
        with process_container:
            st.info(f"Starting video analysis process using mode: {st.session_state.file_or_url}")
            logger.info(f"Starting video analysis with mode: {st.session_state.file_or_url}")
            
            # Add very explicit debug info right before processing
            processing_details = {
                "mode": st.session_state.file_or_url,
                "has_file": st.session_state.video_file is not None,
                "has_url": st.session_state.video_url != "",
                "file_name": st.session_state.video_file.name if st.session_state.video_file else None,
                "url": st.session_state.video_url,
            }
            logger.info(f"Processing details: {processing_details}")
            
            # Clear previous analyses before starting new analysis
            st.session_state.current_analyses = []
            
            # Process either file or URL based on what was provided
            if st.session_state.file_or_url == "File" and st.session_state.video_file is not None:
                logger.info(f"Processing file: {st.session_state.video_file.name}")
                st.write("🔄 Processing file...")
                with TimerLog(logger, f"Processing file {st.session_state.video_file.name}"):
                    process_uploaded_file(st.session_state.video_file)
            elif st.session_state.file_or_url == "URL" and st.session_state.video_url != "":
                logger.info(f"Processing URL: {st.session_state.video_url}")
                st.write("🔄 Processing URL...")
                with TimerLog(logger, f"Processing URL {st.session_state.video_url}"):
                    process_video_url(st.session_state.video_url)
            else:
                error_msg = f"Cannot process - invalid mode {st.session_state.file_or_url} or missing content"
                logger.error(error_msg)
                st.error(error_msg)
    
    # Show continue button if we have analysis results
    if len(st.session_state.current_analyses) > 0:
        if st.button("Continue to Chat", type="primary", use_container_width=True):
            logger.info("User clicked Continue to Chat button")
            st.session_state.current_phase = "Chat"
            st.rerun()

def process_uploaded_file(video_file):
    """Process an uploaded video file."""
    try:
        logger.info(f"Starting file processing for: {video_file.name}")
        # Create well-organized directory structure
        video_title = os.path.splitext(video_file.name)[0]
        logger.debug(f"Video title: {video_title}")
        video_base_dir = 'video'
        os.makedirs(video_base_dir, exist_ok=True)
        
        # Create analysis directory structure
        analysis_dir = f"{video_title}_analysis"
        video_dir = os.path.join(video_base_dir, analysis_dir)
        
        # Create subdirectories
        segments_dir = os.path.join(video_dir, "segments")
        analysis_subdir = os.path.join(video_dir, "analysis")
        frames_dir = os.path.join(video_dir, "frames")
        
        # Create all necessary directories
        for dir_path in [video_dir, segments_dir, analysis_subdir, frames_dir]:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Created directory: {dir_path}")

        # Save uploaded file to the video directory
        video_path = os.path.join(video_dir, video_file.name)
        logger.debug(f"Saving video to: {video_path}")
        with open(video_path, "wb") as f:
            f.write(video_file.getbuffer())
        logger.info(f"Saved video file to: {video_path}")
        
        # Get video duration
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps
        cap.release()
        
        # Get configuration parameters
        segment_interval = st.session_state.config["segment_interval"]
        enable_range = st.session_state.config["enable_range"]
        start_time = st.session_state.config["start_time"]
        end_time = st.session_state.config["end_time"]
        system_prompt = st.session_state.config["video_analysis_system_prompt"]
        user_prompt = st.session_state.config["video_analysis_user_prompt"]
        temperature = st.session_state.config["temperature"]
        frames_per_second = st.session_state.config["frames_per_second"]
        
        # Validate range parameters
        if enable_range:
            if end_time == 0:
                end_time = video_duration
            if end_time > video_duration:
                st.warning(f"End time exceeds video duration. Setting to maximum ({video_duration:.1f} seconds)")
                end_time = video_duration
            if start_time >= end_time:
                st.error("Start time must be less than end time")
                st.stop()
            video_duration = end_time - start_time
        
        # Process video in segments
        segment_num = 0
        progress_bar = st.progress(0)
        segments_to_process = []
        
        # First, extract all segments
        for start_time_seg in range(int(start_time if enable_range else 0), 
                                   int(end_time if enable_range else video_duration), 
                                   segment_interval):
            end_time_seg = min(start_time_seg + segment_interval, 
                              end_time if enable_range else video_duration)
            segment_path = os.path.join(segments_dir, f'segment_{start_time_seg}-{end_time_seg}.mp4')
            logger.info(f"Creating segment: {segment_path}")
            
            # Extract segment
            try:
                ffmpeg_extract_subclip(video_path, start_time_seg, end_time_seg, targetname=segment_path)
                logger.info(f"Successfully created segment: {segment_path}")
                segments_to_process.append(segment_path)
            except Exception as ex:
                logger.error(f"Error extracting segment {start_time_seg}-{end_time_seg}: {str(ex)}")
                st.error(f"Error extracting segment {start_time_seg}-{end_time_seg}: {str(ex)}")
        
        # Now process all segments
        total_segments = len(segments_to_process)
        logger.info(f"Processing video in {total_segments} segments")
        with TimerLog(logger, f"Processing all {total_segments} segments"):
            for i, segment_path in enumerate(segments_to_process):
                # Update progress
                progress_percentage = int((i / total_segments) * 100)
                progress_bar.progress(progress_percentage)
                
                # Process segment
                try:
                    execute_video_processing(
                        st, segment_path, system_prompt, user_prompt, temperature,
                        frames_per_second, analysis_subdir, segment_num, video_duration
                    )
                    segment_num += 1
                except Exception as ex:
                    logger.error(f"Error processing segment {i+1}: {str(ex)}")
                    st.error(f"Error processing segment {i+1}: {str(ex)}")
        
        # Update progress to 100%
        progress_bar.progress(100)
        
        # Clean up original video file but keep segments
        try:
            os.remove(video_path)
            logger.info(f"Removed original video file: {video_path}")
        except Exception as ex:
            logger.error(f"Error removing original video file: {str(ex)}")
        
        # After all segments are processed, load all analyses
        analyses = load_all_analyses(analysis_subdir)
        st.session_state.analyses = analyses
        st.session_state.show_chat = True
        
        # Register this video in the cache system for future retrieval
        logger.info(f"Registering analysis in cache for {video_file.name}")
        register_video_analysis(video_file, video_dir)
        
        st.success(f"Processing complete! Analyzed {segment_num} segments.")
        logger.info(f"Processing complete for {video_file.name} with {segment_num} segments")
    
    except Exception as ex:
        logger.exception(f"Error processing video file: {str(ex)}")
        st.error(f"Error processing video file: {str(ex)}")

def process_video_url(url):
    """Process a video from URL (e.g., YouTube)."""
    try:
        logger.info(f"Starting URL processing for: {url}")
        # First get video info without downloading
        video_title = "video"  # Default title
        ydl_opts = {
            'format': '(bestvideo[vcodec^=av01]/bestvideo[vcodec^=vp9]/bestvideo)+bestaudio/best',
            'force_keyframes_at_cuts': True,
            'quiet': True,
            'no_warnings': True
        }
        
        # Get video info and title
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            video_title = info_dict.get('title', 'video').replace(' ', '_').replace('/', '_')
            video_duration = int(info_dict.get('duration', 0))
        
        # Create directory structure
        video_base_dir = 'video'
        os.makedirs(video_base_dir, exist_ok=True)
        
        analysis_dir = f"{video_title}_analysis"
        video_dir = os.path.join(video_base_dir, analysis_dir)
        segments_dir = os.path.join(video_dir, "segments")
        analysis_subdir = os.path.join(video_dir, "analysis")
        
        # Create all directories
        for dir_path in [video_dir, segments_dir, analysis_subdir]:
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Created directory: {dir_path}")
        
        # Get configuration parameters
        segment_interval = st.session_state.config["segment_interval"]
        enable_range = st.session_state.config["enable_range"]
        start_time = st.session_state.config["start_time"]
        end_time = st.session_state.config["end_time"]
        system_prompt = st.session_state.config["video_analysis_system_prompt"]
        user_prompt = st.session_state.config["video_analysis_user_prompt"]
        temperature = st.session_state.config["temperature"]
        frames_per_second = st.session_state.config["frames_per_second"]
        
        # Validate range parameters
        if enable_range:
            if end_time == 0:
                end_time = video_duration
            if end_time > video_duration:
                st.warning(f"End time exceeds video duration. Setting to maximum ({video_duration} seconds)")
                end_time = video_duration
            if start_time >= end_time:
                st.error("Start time must be less than end time")
                st.stop()
            duration_to_process = end_time - start_time
        else:
            start_time = 0
            end_time = video_duration
            duration_to_process = video_duration
        
        # Calculate number of segments
        num_segments = (end_time - start_time) // segment_interval
        if (end_time - start_time) % segment_interval > 0:
            num_segments += 1
        
        # Process video in segments
        progress_bar = st.progress(0)
        segment_num = 0
        
        for start in range(start_time, end_time, segment_interval):
            end = min(start + segment_interval, end_time)
            
            # Update progress
            progress_percentage = int((segment_num / num_segments) * 100)
            progress_bar.progress(progress_percentage)
            
            # Create segment path
            segment_path = os.path.join(segments_dir, f'segment_{start}-{end}.mp4')
            
            # Download segment
            with st.spinner(f"Downloading segment {segment_num+1}/{num_segments} ({start}-{end} seconds)..."):
                try:
                    segment_ydl_opts = ydl_opts.copy()
                    segment_ydl_opts['download_ranges'] = download_range_func(None, [(start, end)])
                    segment_ydl_opts['outtmpl'] = segment_path
                    
                    with yt_dlp.YoutubeDL(segment_ydl_opts) as ydl:
                        ydl.download([url])
                    
                    logger.info(f"Downloaded segment: {segment_path}")
                    
                    if not os.path.exists(segment_path):
                        # Try with different extensions
                        for ext in ['.webm', '.mkv']:
                            alt_path = os.path.splitext(segment_path)[0] + ext
                            if os.path.exists(alt_path):
                                segment_path = alt_path
                                break
                    
                    if not os.path.exists(segment_path):
                        st.warning(f"Segment download successful but file not found. Check the segments directory.")
                    
                    # Process segment
                    execute_video_processing(
                        st, segment_path, system_prompt, user_prompt, temperature,
                        frames_per_second, analysis_subdir, segment_num, duration_to_process
                    )
                    
                    # Clean up segment file
                    # try:
                    #     os.remove(segment_path)
                    #     logger.info(f"Removed segment file: {segment_path}")
                    # except:
                    #     logger.warning(f"Could not remove segment file: {segment_path}")
                    
                except Exception as ex:
                    logger.error(f"Error processing segment {start}-{end}: {str(ex)}")
                    st.error(f"Error processing segment {start}-{end}: {str(ex)}")
            
            segment_num += 1
        
        # Update progress to 100%
        progress_bar.progress(100)
        
        # After all segments are processed, load all analyses
        analyses = load_all_analyses(analysis_subdir)
        st.session_state.analyses = analyses
        st.session_state.show_chat = True
        
        # Register this URL in the cache system for future retrieval
        start_time = st.session_state.config["start_time"] if st.session_state.config["enable_range"] else 0
        end_time = st.session_state.config["end_time"] if st.session_state.config["enable_range"] else 0
        register_url_analysis(url, video_dir, start_time, end_time)
        
        st.success(f"Processing complete! Analyzed {segment_num} segments.")
    
    except Exception as ex:
        logger.exception(f"Error processing URL: {str(ex)}")
        st.error(f"Error processing URL: {str(ex)}")
