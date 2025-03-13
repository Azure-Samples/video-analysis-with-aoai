import cv2
import os
import base64
import streamlit as st
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from moviepy.editor import VideoFileClip
import json
import time
import logging

import yt_dlp

# Get logger for this module
logger = logging.getLogger(__name__)

def process_video(video_path, frames_per_second=1, resize=4, output_dir=''):
    """Extract and encode frames from a video file."""
    logger.info(f"Processing video: {video_path}")
    
    base64Frames = []

    video = cv2.VideoCapture(video_path)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = video.get(cv2.CAP_PROP_FPS)
    frames_to_skip = int(fps / frames_per_second)
    curr_frame = 0
    frame_count = 1

    while curr_frame < total_frames - 1:
        video.set(cv2.CAP_PROP_POS_FRAMES, curr_frame)
        success, frame = video.read()
        if not success:
            break

        logger.debug(f"Processing frame {curr_frame}/{total_frames}")

        if resize != 0:
            height, width, _ = frame.shape
            frame = cv2.resize(frame, (width // resize, height // resize))

        _, buffer = cv2.imencode(".jpg", frame)

        if output_dir:
            frame_filename = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(video_path))[0]}_frame_{frame_count}.jpg")
            with open(frame_filename, "wb") as f:
                f.write(buffer)
                logger.debug(f"Saved frame: {frame_filename}")
            frame_count += 1

        base64Frames.append(base64.b64encode(buffer).decode("utf-8"))
        curr_frame += frames_to_skip
    video.release()
    
    logger.info(f"Extracted {len(base64Frames)} frames")
    return base64Frames

def process_audio(video_path):
    """Extract and transcribe audio from a video file."""
    logger.info(f"Starting audio transcription for {video_path}")
    transcription_text = ''
    
    try:
        # First check if the video file exists and has audio
        clip = VideoFileClip(video_path)
        if not clip.audio:
            logger.info(f"No audio track found in {video_path}")
            clip.close()
            return "No audio found in this segment."

        # Extract audio to file in the same directory as the video
        base_video_path, _ = os.path.splitext(video_path)
        audio_path = f"{base_video_path}.mp3"
        
        try:
            clip.audio.write_audiofile(audio_path, bitrate="32k", verbose=False, logger=None)
            clip.audio.close()
            clip.close()
            logger.info(f"Extracted audio to {audio_path}")

            # Transcribe the audio
            with open(audio_path, "rb") as audio_file:
                transcription = st.session_state.whisper_client.audio.transcriptions.create(
                    model=st.session_state.whisper_model_name,
                    file=audio_file
                )
                transcription_text = transcription.text
                logger.info(f"Transcription successful: {transcription_text}")
                logger.info(f"Audio file saved at: {audio_path}")

        except Exception as ex:
            logger.error(f'ERROR in audio processing: {str(ex)}')
            if os.path.exists(audio_path):
                os.remove(audio_path)  # Only remove on error
            
    except Exception as ex:
        logger.error(f'ERROR processing audio: {str(ex)}')
        transcription_text = "Audio processing failed."

    return transcription_text

def load_segment_summary(analysis_dir, segment_num):
    """Load the analysis summary from a previous segment."""
    try:
        files = sorted([f for f in os.listdir(analysis_dir) if f.endswith('_analysis.json')])
        if segment_num > 0 and segment_num <= len(files):
            previous_file = os.path.join(analysis_dir, files[segment_num - 1])
            with open(previous_file, 'r') as f:
                analysis_data = json.load(f)
                return analysis_data.get('summary', '')
    except Exception as ex:
        logger.error(f"Error loading previous summary: {ex}")
    return ''

def execute_video_processing(st, segment_path, system_prompt, user_prompt, temperature, frames_per_second, 
                          analysis_dir, segment_num=0, total_duration=0):
    """Process a video segment, incorporating previous segment context."""
    from utils.analysis import analyze_video
    
    logger.info(f"Processing segment {segment_num + 1} from {segment_path}")
    
    # Get video name from path
    video_folder = os.path.basename(os.path.dirname(os.path.dirname(segment_path)))
    video_name = video_folder.replace("_analysis", "").replace("_", " ")
    
    # Create a segment subcontainer to keep each segment's content organized
    segment_subcontainer = st.container()
    
    with segment_subcontainer:
        # Add prominent video name and segment information
        st.markdown(f"## 🎬 {video_name}")
        st.markdown(f"### Processing segment {segment_num + 1}:")
        
        # Get the segment timing information
        filename = os.path.basename(segment_path)
        timing = filename.split('_')[-1].replace('.mp4', '')
        start_time, end_time = map(float, timing.split('-'))
        st.markdown(f"**Segment Time Range**: {start_time:.1f}s - {end_time:.1f}s")
        
        # Show the video segment
        st.video(segment_path)
    
    # Get the segment timing information for processing
    filename = os.path.basename(segment_path)
    timing = filename.split('_')[-1].replace('.mp4', '')
    start_time, end_time = map(float, timing.split('-'))
    
    with st.spinner(f"Analyzing {video_name} - segment {segment_num + 1} ({start_time:.1f}s - {end_time:.1f}s)"):
        # Extract frames
        with st.spinner("Extracting frames..."):
            start_time_proc = time.time()
            
            if st.session_state.config["save_frames"]:
                video_analysis_dir = os.path.dirname(analysis_dir)
                frames_dir = os.path.join(video_analysis_dir, "frames")
                os.makedirs(frames_dir, exist_ok=True)
                logger.debug(f"Using frames directory: {frames_dir}")
                output_dir = frames_dir
            else:
                output_dir = ''
                
            base64frames = process_video(segment_path, frames_per_second, 
                                      resize=st.session_state.config["resize"], output_dir=output_dir)
            logger.info(f"Frame extraction took {(time.time() - start_time_proc):.3f} seconds")
            
        # Get audio transcription if enabled
        if st.session_state.config["audio_transcription"]:
            with st.spinner("Transcribing audio..."):
                start_time_proc = time.time()
                transcription = process_audio(segment_path)
                logger.info(f"Audio transcription took {(time.time() - start_time_proc):.3f} seconds")
        else:
            transcription = ''

        # Load previous segment summary for context
        previous_summary = load_segment_summary(analysis_dir, segment_num)

        # Analyze the segment
        with st.spinner("Analyzing frames..."):
            start_time_proc = time.time()
            analysis = analyze_video(base64frames, system_prompt, user_prompt, transcription, 
                                  previous_summary, start_time, end_time, total_duration, temperature)
            logger.info(f"Analysis took {(time.time() - start_time_proc):.3f} seconds")

    # Show results in the segment subcontainer
    with segment_subcontainer:
        st.success(f"Analysis completed for {video_name} - segment {segment_num + 1}")
        st.markdown(f"**Analysis**: {analysis}", unsafe_allow_html=True)
        if st.session_state.config["show_transcription"] and st.session_state.config["audio_transcription"] and transcription:
            st.markdown(f"**Transcription**: {transcription}", unsafe_allow_html=True)
    
    # Save analysis results
    analysis_filename = os.path.join(analysis_dir, f"segment_{segment_num+1}_analysis.json")
    analysis_data = {
        "segment": segment_num + 1,
        "start_time": start_time,
        "end_time": end_time,
        "analysis": analysis,
    }
    with open(analysis_filename, 'w') as f:
        json.dump(analysis_data, f, indent=4)
        
    # Store in session state for reference
    from models.session_state import add_analysis
    add_analysis({
        "segment": segment_num + 1,
        "start_time": start_time,
        "end_time": end_time, 
        "analysis": analysis,
        "transcription": transcription if st.session_state.config["audio_transcription"] else None
    })

    # Update session state after each segment is processed
    analyses = load_all_analyses(analysis_dir)
    st.session_state.analyses = analyses
    st.session_state.show_chat = True

    return analysis

def load_all_analyses(analysis_dir):
    """Load all segment analyses for the chat context."""
    analyses = []
    try:
        files = sorted([f for f in os.listdir(analysis_dir) if f.endswith('_analysis.json')])
        for file in files:
            with open(os.path.join(analysis_dir, file), 'r') as f:
                analysis_data = json.load(f)
                analyses.append(analysis_data)
    except Exception as ex:
        logger.error(f"Error loading analyses: {ex}")
    return analyses

def get_video_file_info(video_file):
    """Extract metadata from an uploaded video file."""
    try:
        # Save the file temporarily to get its info
        temp_path = f"temp_{video_file.name}"
        with open(temp_path, "wb") as f:
            f.write(video_file.getbuffer())
        
        # Get file size
        file_size = os.path.getsize(temp_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Get video metadata using OpenCV
        cap = cv2.VideoCapture(temp_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        
        # Clean up
        cap.release()
        os.remove(temp_path)
        
        # Calculate number of segments based on config
        segment_interval = st.session_state.config["segment_interval"]
        enable_range = st.session_state.config["enable_range"]
        start_time = st.session_state.config["start_time"] if enable_range else 0
        end_time = st.session_state.config["end_time"] if enable_range and st.session_state.config["end_time"] > 0 else duration
        
        total_segments = (end_time - start_time) // segment_interval
        if (end_time - start_time) % segment_interval > 0:
            total_segments += 1
            
        # Return info dictionary with enhanced information
        return {
            "file_size": file_size,
            "file_size_formatted": f"{file_size_mb:.2f} MB",
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}",
            "fps": fps,
            "duration": duration,
            "duration_formatted": f"{int(duration // 60)}:{int(duration % 60):02d}",
            "frame_count": frame_count,
            "format": os.path.splitext(video_file.name)[1][1:].upper(),
            "total_segments": int(total_segments),
            "segment_duration": segment_interval,
            "title": video_file.name,
            "display_name": os.path.splitext(video_file.name)[0].replace("_", " ")
        }
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return {
            "error": f"Failed to extract video information: {str(e)}",
            "file_size_formatted": f"{video_file.size / (1024 * 1024):.2f} MB",
            "format": os.path.splitext(video_file.name)[1][1:].upper() if video_file.name else "Unknown"
        }

def get_video_url_info(url):
    """Extract metadata from a video URL."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            
            # Extract available information
            duration = info_dict.get('duration', 0)
            title = info_dict.get('title', 'Unknown')
            
            # Get best format info
            formats = info_dict.get('formats', [])
            best_video = None
            for fmt in formats:
                if fmt.get('width') and fmt.get('height'):
                    if not best_video or (fmt.get('width', 0) > best_video.get('width', 0)):
                        best_video = fmt
            
            width = best_video.get('width', 0) if best_video else 0
            height = best_video.get('height', 0) if best_video else 0
            
            # Calculate number of segments
            segment_interval = st.session_state.config["segment_interval"]
            enable_range = st.session_state.config["enable_range"]
            start_time = st.session_state.config["start_time"] if enable_range else 0
            end_time = st.session_state.config["end_time"] if enable_range and st.session_state.config["end_time"] > 0 else duration
            
            total_segments = (end_time - start_time) // segment_interval
            if (end_time - start_time) % segment_interval > 0:
                total_segments += 1
            
            # Return enhanced info dictionary
            return {
                "title": title,
                "display_title": title.replace("_", " "),
                "width": width,
                "height": height,
                "resolution": f"{width}x{height}" if width and height else "Unknown",
                "duration": duration,
                "duration_formatted": f"{int(duration // 60)}:{int(duration % 60):02d}",
                "format": "YouTube Video",
                "total_segments": int(total_segments),
                "segment_duration": segment_interval,
                "url": url
            }
    except Exception as e:
        logger.error(f"Error getting URL video info: {str(e)}")
        return {
            "error": f"Failed to extract video information: {str(e)}",
            "format": "YouTube/URL Video",
            "duration": 0,
            "duration_formatted": "Unknown"
        }

