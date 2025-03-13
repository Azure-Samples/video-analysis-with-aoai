# Configuration constants used throughout the application

# Default processing parameters
DEFAULT_SEGMENT_INTERVAL = 10  # In seconds
DEFAULT_FRAMES_PER_SECOND = 1
RESIZE_OF_FRAMES = 4
DEFAULT_TEMPERATURE = 0.5

# System prompts
VIDEO_ANALYSIS_SYSTEM_PROMPT = """You are an expert video analyst. You will be shown frames from a video segment. 
Analyze what is happening in detail, considering both visual elements and any provided audio transcription.
If provided with previous segment context, ensure your analysis maintains continuity with what came before."""

VIDEO_ANALYSIS_USER_PROMPT = "These are the frames from the video segment."

# Chat system prompt
CHAT_SYSTEM_PROMPT = """You are an assistant that answers questions about a video based on its analysis. 
Use the provided analysis context to give accurate and relevant answers.
Maintain context from the ongoing conversation."""
