# Import libraries
import streamlit as st
import cv2
import os
import platform
import time
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
from moviepy import VideoFileClip
from openai import AzureOpenAI
import base64
import yt_dlp
from yt_dlp.utils import download_range_func
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from prompts import *

# Helper to locate a TrueType font on the current OS
def _get_font_path() -> str:
    if platform.system() == "Windows":
        win_font = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")
        if os.path.isfile(win_font):
            return win_font
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        if os.path.isfile(path):
            return path
    return ""

# Stamp 'video_time: MM:SS:mmm' on a black stripe added below the frame
def _stamp_video_time(frame, timestamp_sec, font_size=16):
    minutes = int(timestamp_sec // 60)
    seconds = int(timestamp_sec % 60)
    milliseconds = int((timestamp_sec - int(timestamp_sec)) * 1000)
    timestamp = f"{minutes:02}:{seconds:02}:{milliseconds:03}"
    timestamp_text = f"video_time: {timestamp}"

    font_path = _get_font_path()
    font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()

    stripe_height = font_size + 4
    new_frame_height = frame.shape[0] + stripe_height
    new_frame = np.zeros((new_frame_height, frame.shape[1], 3), dtype=np.uint8)
    new_frame[:frame.shape[0], :] = frame

    pil_img = Image.fromarray(new_frame)
    draw = ImageDraw.Draw(pil_img)
    draw.rectangle([(0, frame.shape[0]), (frame.shape[1], new_frame_height)], fill=(0, 0, 0))
    draw.text((5, frame.shape[0] + 1), timestamp_text, font=font, fill=(255, 255, 255))
    return np.array(pil_img)

# System prompt for the Purpose
SYSTEM_PROMPT = GENERIC_SYSTEM_PROMPT
#SYSTEM_PROMPT = SYSTEM_PROMPT_COMBINED
print(f'SYSTEM PROMPT: [{SYSTEM_PROMPT}]')
print(f'USER PROMPT:   [{USER_PROMPT}]')

# Default configuration
SEGMENT_DURATION = 16 # In seconds, Set to 0 to not split the video
DEFAULT_TEMPERATURE = 0.5
RESIZE_OF_FRAMES = 1
FRAMES_PER_SECOND = 3
REASONING_EFFORT = "medium" # "none", "low", "medium" or "high"

# Load configuration
load_dotenv(override=True)

# Whisper: enable/disable from .env (USE_WHISPER=true|false). Defaults to False.
USE_WHISPER = os.environ.get("USE_WHISPER", "False").strip().lower() in ("true", "1", "yes")

# Configuration of OpenAI
aoai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
aoai_api_version = '2025-04-01-preview'
aoai_model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

# Create AOAI client once per Streamlit session/process. @st.cache_resource ensures
# the client (and the underlying credential / token provider) is created only on
# the first run and reused across every script rerun.
# Authentication: if the AZURE_OPENAI_API_KEY environment variable is set, the
# client authenticates using that API key. Otherwise it falls back to Microsoft
# Entra ID via DefaultAzureCredential (which tries env vars, Managed Identity,
# Azure CLI, VS Code, etc., in order) and a bearer token provider scoped to
# Cognitive Services.
@st.cache_resource(show_spinner=False)
def _get_aoai_client():
    print(f'aoai_endpoint: {aoai_endpoint}, aoai_model_name: {aoai_model_name} with reasoning: {REASONING_EFFORT}')
    if api_key := os.environ.get("AZURE_OPENAI_API_KEY"):
        print("Using API key authentication for Azure OpenAI")
        aoai_client = AzureOpenAI(
            azure_deployment=aoai_model_name,
            api_version=aoai_api_version,
            azure_endpoint=aoai_endpoint,
            api_key=api_key
        )
    else:
        print("Using Azure AD authentication for Azure OpenAI") 
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        aoai_client = AzureOpenAI(
            azure_deployment=aoai_model_name,
            api_version=aoai_api_version,
            azure_endpoint=aoai_endpoint,
            azure_ad_token_provider=token_provider
        )
    return aoai_client

aoai_client = _get_aoai_client()

# Configuration of Whisper
if USE_WHISPER:
    whisper_endpoint = os.environ["WHISPER_ENDPOINT"]
    whisper_apikey = os.environ["WHISPER_API_KEY"]
    whisper_model_name = os.environ["WHISPER_DEPLOYMENT_NAME"]

    @st.cache_resource(show_spinner=False)
    def _get_whisper_client():
        return AzureOpenAI(
            api_version='2024-02-01',
            azure_endpoint=whisper_endpoint,
            api_key=whisper_apikey
        )

    whisper_client = _get_whisper_client()

# Function to encode a local video into frames
def process_video(video_path, frames_per_second=FRAMES_PER_SECOND, resize=RESIZE_OF_FRAMES, output_dir='', temperature = DEFAULT_TEMPERATURE, segment_offset=0):
    base64Frames = []

    # Prepare the video analysis
    video = cv2.VideoCapture(video_path)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = video.get(cv2.CAP_PROP_FPS)
    # Number of source frames to skip between extracted frames, derived from the desired frames-per-second sampling rate
    if frames_per_second <= 0:
        frames_to_skip = 1
    else:
        frames_to_skip = max(1, int(round(fps / frames_per_second)))
    curr_frame=0

    # Prepare to write the frames to disk
    if output_dir != '': # if we want to write the frame to disk
        os.makedirs(output_dir, exist_ok=True)
        frame_count = 1

    # Loop through the video reading frames sequentially and keeping one every `frames_to_skip`.
    # Sequential read avoids the keyframe-snapping behavior of cv2.CAP_PROP_POS_FRAMES on H.264.
    while True:
        success, frame = video.read()
        if not success:
            break

        if curr_frame % frames_to_skip == 0:
            # Resize the frame to save tokens and get faster answer from the model. resize<=1 means no resize.
            if resize > 1:
                height, width, _ = frame.shape
                frame = cv2.resize(frame, (width // resize, height // resize))

            # Compute absolute timestamp from the start of the ORIGINAL video and stamp it on the frame
            timestamp_sec = segment_offset + (curr_frame / fps if fps > 0 else 0)
            frame = _stamp_video_time(frame, timestamp_sec)

            _, buffer = cv2.imencode(".jpg", frame)

            # Save frame as JPG file
            if output_dir != '': # if we want to write the frame to disk
                frame_filename = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(video_path))[0]}_frame_{frame_count}.jpg")
                print(f'Saving frame {frame_filename}')
                with open(frame_filename, "wb") as f:
                    f.write(buffer)
                frame_count += 1

            base64Frames.append(base64.b64encode(buffer).decode("utf-8"))

        curr_frame += 1
    video.release()
    print(f"Extracted {len(base64Frames)} frames")
    
    return base64Frames

# Function to transcript the audio from the local video with Whisper
def process_audio(video_path):

    transcription_text = ''
    try:
        base_video_path, _ = os.path.splitext(video_path)
        audio_path = f"{base_video_path}.mp3"
        clip = VideoFileClip(video_path)
        clip.audio.write_audiofile(audio_path, bitrate="32k")
        clip.audio.close()
        clip.close()
        print(f"Extracted audio to {audio_path}")

        # Transcribe the audio
        transcription = whisper_client.audio.transcriptions.create(
            model=whisper_model_name,
            file=open(audio_path, "rb"),
        )
        transcription_text = transcription.text
        print("Transcript: ", transcription_text + "\n\n")
    except Exception as ex:
        print(f'ERROR: {ex}')
        transcription_text = ''

    return transcription_text

# Function to analyze the video with AOAI
def analyze_video(base64frames, system_prompt, user_prompt, transcription, temperature):
    try:
        if transcription != '': # Include the audio transcription
            response = aoai_client.chat.completions.create(
                model=aoai_model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}, #"These are the frames from the video.",},
                    {"role": "user", "content": [
                        *map(lambda x: {"type": "image_url", "image_url": {"url": f'data:image/jpg;base64,{x}', "detail": "high"}}, base64frames),
                        {"type": "text", "text": f"The audio transcription is: {transcription.text}"}
                    ]}
                ],
                #temperature=temperature, #0.5,
                #max_tokens=4096,
                max_completion_tokens=8192,
                reasoning_effort=REASONING_EFFORT,
                response_format={"type": "json_object"},
            )
        else: # Without the audio transcription
            response = aoai_client.chat.completions.create(
                model=aoai_model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}, #"These are the frames from the video.",},
                    {"role": "user", "content": [
                        *map(lambda x: {"type": "image_url", "image_url": {"url": f'data:image/jpg;base64,{x}', "detail": "high"}}, base64frames),
                    ]}
                ],
                #temperature=temperature,
                #max_tokens=4096,
                max_completion_tokens=8192,
                reasoning_effort=REASONING_EFFORT,
                response_format={"type": "json_object"},
            )

        json_response = json.loads(response.model_dump_json())
        #print(f'RESPONSE: [{response.model_dump_json(indent=2)}]')
        response = json_response['choices'][0]['message']['content']

    except Exception as ex:
        print(f'ERROR: {ex}')
        response = f'ERROR: {ex}'

    return response

# Split the video in segments of N seconds (by default 3 minutes). If segment_length is 0 the full video is processed
def split_video(video_path, output_dir, segment_length=180, start_second=0):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    cap.release()

    if segment_length == 0: # Do not split
        segment_length = int(duration)

    # Clamp the starting second to the video duration
    start_second = max(0, min(int(start_second), int(duration)))

    # Open a fresh VideoFileClip per segment. Sharing one VideoFileClip across
    # multiple subclipped()/close() calls breaks moviepy's underlying FFmpeg
    # reader (subclips share the reader; closing one leaves the parent's
    # `proc` set to None, causing 'NoneType has no attribute stdout' on the
    # next iteration). Reopening per segment is slightly slower but reliable.
    for start_time in range(start_second, int(duration), segment_length):
        end_time = min(start_time + segment_length, duration)
        output_file = os.path.join(
            output_dir,
            f'{os.path.splitext(os.path.basename(video_path))[0]}_segment_{start_time}-{int(end_time)}_secs.mp4'
        )
        clip = VideoFileClip(video_path)
        try:
            # moviepy 2.x uses subclipped(); fall back to subclip() for moviepy 1.x
            sub = clip.subclipped(start_time, end_time) if hasattr(clip, 'subclipped') else clip.subclip(start_time, end_time)
            sub.write_videofile(
                output_file,
                codec='libx264',
                audio_codec='aac',
                logger=None,
            )
        finally:
            try:
                clip.close()
            except Exception:
                pass
        yield output_file, start_time

# Process the video
def execute_video_processing(st, segment_path, system_prompt, user_prompt, temperature, segment_offset=0):
    # Show the video on the screen
    st.write(f"Video: {segment_path}:")
    st.video(segment_path)

    with st.spinner(f"Analyzing video segment: {segment_path}"):
        # Extract frames at the configured frames-per-second sampling rate. Adjust `frames_per_second` to change it
        with st.spinner(f"Extracting frames..."):
            inicio = time.time()
            if save_frames:
                output_dir = 'frames'
            else:
                output_dir = ''
            base64frames = process_video(segment_path, frames_per_second=frames_per_second, resize=resize, output_dir=output_dir, temperature=temperature, segment_offset=segment_offset)
            fin = time.time()
            print(f'\t>>>> Frames extraction took {(fin - inicio):.3f} seconds <<<<')
            ### st.write(f'Extracted {len(base64frames)} frames in {(fin - inicio):.3f} seconds')

        # Extract the transcription of the audio
        if audio_transcription:
            msg = f'Analyzing frames and audio with {aoai_model_name}...'
            with st.spinner(f"Transcribing audio from video file..."):
                inicio = time.time()
                transcription = process_audio(segment_path)
                fin = time.time()
            ### st.write(f'Transcription finished in {(fin - inicio):.3f} seconds')
            print(f'Transcription: [{transcription}]')
            if show_transcription:
                st.markdown(f"**Transcription**: {transcription}", unsafe_allow_html=True)
            print(f'\t>>>> Audio transcription took {(fin - inicio):.3f} seconds <<<<')
        else:
            msg = f'Analyzing frames with {aoai_model_name}...'
            transcription = ''
        # Analyze the video frames and the audio transcription with AOAI
        with st.spinner(msg):
            inicio = time.time()
            analysis = analyze_video(base64frames, system_prompt, user_prompt, transcription, temperature)
            fin = time.time()
        print(f'\t>>>> Analysys with {aoai_model_name} took {(fin - inicio):.3f} seconds <<<<')

    ### st.write(f"**Analysis of segment {segment_path}** ({(fin - inicio):.3f} seconds)")
    fin = time.time()
    print(f'\t>>>> {(fin - inicio):.6f} segundos <<<<')
    st.success("Analysis completed.")

    return analysis

# Helper to display the model response: pretty-print JSON when possible, otherwise markdown
def display_analysis(st, analysis, label='Description'):
    if not isinstance(analysis, str):
        st.json(analysis, expanded=True)
        return

    text = analysis.strip()
    # Strip ```json ... ``` or ``` ... ``` fences if the model wrapped the JSON in a code block
    if text.startswith('```'):
        lines = text.splitlines()
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        text = '\n'.join(lines).strip()

    try:
        parsed = json.loads(text)
        st.markdown(f"**{label}**")
        st.json(parsed, expanded=True)
    except (json.JSONDecodeError, ValueError):
        # Fallback: show as markdown so newlines/markdown formatting are respected
        st.markdown(f"**{label}**\n\n{analysis}", unsafe_allow_html=True)

# Streamlit User Interface
st.set_page_config(
    page_title=f"Video Analysis with {aoai_model_name}",
    layout="centered",
    initial_sidebar_state="auto",
)
st.image("microsoft.png", width=100)
st.title(f'Video Analysis with {aoai_model_name}')

with st.sidebar:
    file_or_url = st.selectbox("Video source:", ["File", "URL"], index=0, help="Select the source, file or url")
    initial_split = SEGMENT_DURATION
    if file_or_url == "URL":
        continuous_transmision = st.checkbox('Continuous transmision', False, help="Video of a continuous transmision")

    if USE_WHISPER:
        audio_transcription = st.checkbox('Transcript audio', True, help="Extract the audio transcription and use in the analysis or not")
        if audio_transcription:
            show_transcription = st.checkbox('Show audio transcription', True, help="Present the audio transcription or not")
    else:
        audio_transcription = False
        show_transcription = False

    starting_second = int(st.number_input('Starting second', 0, help="Second of the video at which to start processing. Frames before this second will be skipped."))
    seconds_split = int(st.number_input('Number of seconds to split the video', min_value=0, value=initial_split, step=1, help="The video will be processed in smaller segments based on the number of seconds specified in this field. (0 to not split)"))
    frames_per_second = float(st.text_input('Frames per second to extract', FRAMES_PER_SECOND, help="Number of frames to extract per second of video. It can be a decimal number, like 0.5 (one frame every 2 seconds) or 2 (two frames per second)."))
    resize = st.number_input("Frames resizing ratio", min_value=1, value=RESIZE_OF_FRAMES, step=1, help="Divider applied to width and height of each frame. 1 = original size (no resize), 2 = half size, 3 = one third, etc. Useful to reduce latency and token consumption.")
    save_frames = st.checkbox('Save the frames to the folder "frames"', False)
    #temperature = float(st.number_input('Temperature for the model', DEFAULT_TEMPERATURE))
    temperature = 0.0
    system_prompt = st.text_area('System Prompt', SYSTEM_PROMPT)
    user_prompt = st.text_area('User Prompt', USER_PROMPT)

    # Validate that the number of frames per segment doesn't exceed the model limit (50)
    MAX_FRAMES_PER_SEGMENT = 50
    estimated_frames = int(seconds_split * frames_per_second) if seconds_split > 0 else 0
    if estimated_frames > MAX_FRAMES_PER_SEGMENT:
        st.error(
            f"⚠️ The combination of {seconds_split}s × {frames_per_second} fps = {estimated_frames} frames per segment "
            f"exceeds the model limit of {MAX_FRAMES_PER_SEGMENT} frames. "
            f"Reduce the seconds to split or the frames per second."
        )
        exceeds_frame_limit = True
    else:
        if seconds_split > 0:
            st.caption(f"Estimated frames per segment: {estimated_frames} / {MAX_FRAMES_PER_SEGMENT}")
        exceeds_frame_limit = False

# Prepare the segment directory
output_dir = "segments"
os.makedirs(output_dir, exist_ok=True)

# Video file or Video URL
if file_or_url == 'File':
    video_file = st.file_uploader("Upload a video file", type=["mp4", "avi", "mov"])
else:
    url = st.text_area("Enter de url:", value='https://www.youtube.com/watch?v=Y6kHpAeIr4c', height=10)

# Analyze the video when the button is pressed
# The button lives inside a placeholder so we can re-render it as a 'Cancel'
# button while the analysis is running. Cancellation is best-effort and is
# checked between segments (not in the middle of a single AOAI call).
analyze_btn_slot = st.empty()

if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'cancel_requested' not in st.session_state:
    st.session_state.cancel_requested = False

# If the previous run requested cancel, the script was rerun by the on_click callback.
# At this point the previous in-flight loop is gone (Streamlit aborted it), so we
# must clear both flags before rendering the button — otherwise it would stay
# disabled forever showing "Analyze video".
if st.session_state.cancel_requested:
    st.session_state.processing = False
    st.session_state.cancel_requested = False
    st.warning("Analysis cancelled by user.")

def _request_cancel():
    st.session_state.cancel_requested = True

analyze_clicked = analyze_btn_slot.button(
    "Analyze video",
    use_container_width=True,
    type='primary',
    disabled=exceeds_frame_limit or st.session_state.processing,
    key='analyze_btn',
)

if analyze_clicked:
    st.session_state.processing = True
    st.session_state.cancel_requested = False
    # Swap the slot to a Cancel button. on_click sets the cancel flag and
    # Streamlit will trigger a rerun, which raises a RerunException at the
    # next st.* call, aborting the loop early.
    analyze_btn_slot.button(
        "Cancel Analysis",
        use_container_width=True,
        type='secondary',
        on_click=_request_cancel,
        key='cancel_btn_active',
    )

    try:
        # Placeholder shown while the first segment is being prepared (downloaded for URL,
        # written + split for File). It is cleared right before the first segment is
        # processed so it doesn't overlap with the per-segment "Analyzing video..." spinner.
        startup_status = st.empty()
        startup_status.info(f"⏳ Starting video analysis: {url if file_or_url == 'URL' else video_file.name}")

        # Show parameters:
        print(f"PARAMETERS:")
        print(f"file_or_url: {file_or_url}, audio_transcription: {audio_transcription}, seconds to split: {seconds_split}")
        print(f"frames_per_second: {frames_per_second}, resize ratio: {resize}, save_frames: {save_frames}, temperature: {temperature}")

        if file_or_url == 'URL': # Process Youtube video
            st.write(f'Analyzing video from url {url}...')

            ydl_opts = {
                    #'format': 'best',
                    'format': '(bestvideo[vcodec^=av01]/bestvideo[vcodec^=vp9]/bestvideo)+bestaudio/best',
                    'outtmpl': 'segment_%(start)s.mp4',
                    'force_keyframes_at_cuts': True,
            }
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            if continuous_transmision == False:
                info_dict = ydl.extract_info(url, download=False)
                video_duration = info_dict.get('duration', 0)

                if seconds_split == 0:
                    duracion_segmento=video_duration
                else:
                    duracion_segmento=seconds_split #SEGMENT_DURATION
            else:
                video_duration = 48*60*60

                if seconds_split == 0:
                    duracion_segmento=180 # 3 minutes
                else:
                    duracion_segmento=seconds_split #SEGMENT_DURATION

            for start in range(starting_second, video_duration, duracion_segmento):
                if st.session_state.cancel_requested:
                    st.warning("Analysis cancelled by user.")
                    break
                end = start + duracion_segmento
                filename = f'segments/segment_{start}-{end}.mp4'
                with st.spinner(f"Downloading video from second {start} to {end}..."):
                    ydl_opts['outtmpl']['default'] = filename
                    ydl_opts['download_ranges'] = download_range_func(None, [(start, end)])

                    print(f'start: {start}, video_duration: {video_duration}, duracion_segmento: {duracion_segmento}')
                    try:
                        ydl.download([url])
                    except:
                        break

                if os.path.exists(filename): # ext .mp4
                    segment_path = filename
                else:
                    segment_path = filename + '.mkv'
                    if not os.path.exists(segment_path):
                        segment_path = filename + '.webm'

                print(f"Segment downloaded: {segment_path}")

                # First segment ready: remove the startup placeholder before showing the video.
                startup_status.empty()

                # Process the video segment (start = absolute offset from the beginning of the original video)
                analysis = execute_video_processing(st, segment_path, system_prompt, user_prompt, temperature, segment_offset=start)
                display_analysis(st, analysis, label='Description')

                # Example detecting an event
                #event="guitarra eléctrica"
                #if event in analysis:
                #    st.write(f'**Detected event "{event}" in segment {segment_path}**')

                # Delete the video segment
                os.remove(segment_path)

        else: # Process the fideo file
            if video_file is not None:
                os.makedirs("temp", exist_ok=True)
                video_path = os.path.join("temp", video_file.name)
            try:
                with open(video_path, "wb") as f:
                    f.write(video_file.getbuffer())

                # Splitting video in segment of N seconds (if seconds is 0 t will not split the video)
                for segment_path, segment_start in split_video(video_path, output_dir, seconds_split, start_second=starting_second):
                    if st.session_state.cancel_requested:
                        st.warning("Analysis cancelled by user.")
                        try:
                            os.remove(segment_path)
                        except Exception:
                            pass
                        break
                    # First segment ready: remove the startup placeholder before showing the video.
                    startup_status.empty()
                    # Process the video segment passing the absolute offset from the beginning of the original video
                    analysis = execute_video_processing(st, segment_path, system_prompt, user_prompt, temperature, segment_offset=segment_start)
                    display_analysis(st, analysis, label='Description')

                    # Delete the video segment
                    os.remove(segment_path)

            except Exception as ex:
                print(f'ERROR: {ex}')
                st.write(f'ERROR: {ex}')
    finally:
        # Re-enable the button in the same slot so the user can launch a new analysis.
        st.session_state.processing = False
        st.session_state.cancel_requested = False
        analyze_btn_slot.button(
            "Analyze video",
            use_container_width=True,
            type='primary',
            disabled=exceeds_frame_limit,
            key='analyze_btn_done',
        )
