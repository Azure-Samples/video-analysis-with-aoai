import json
import streamlit as st
import logging
from config import CHAT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def analyze_video(base64frames, system_prompt, user_prompt, transcription, previous_summary, start_time, end_time, total_duration, temperature):
    """Analyze video frames with GPT-4o Vision, incorporating context from previous segments."""
    try:
        # Construct content array with frames
        content = [
            *map(lambda x: {
                "type": "image_url",
                "image_url": {"url": f'data:image/jpg;base64,{x}', "detail": "auto"}
            }, base64frames)
        ]

        # Add segment context and transcription if available
        segment_context = f"\nAnalyzing segment from {start_time} to {end_time} seconds of a {total_duration} second video."
        if previous_summary:
            segment_context += f"\nPrevious segment summary: {previous_summary}"
        if transcription:
            segment_context += f"\nAudio transcription: {transcription}"

        content.append({"type": "text", "text": segment_context})

        response = st.session_state.aoai_client.chat.completions.create(
            model=st.session_state.aoai_model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "user", "content": content}
            ],
            temperature=temperature,
            max_tokens=4096
        )

        json_response = json.loads(response.model_dump_json())
        return json_response['choices'][0]['message']['content']

    except Exception as ex:
        logger.error(f'ERROR in analyze_video: {ex}')
        return f'ERROR: {ex}'

def chat_with_video_analysis(query, analyses, chat_history=None, temperature=0.7, summarize_first=True):
    """Use GPT-4o to answer questions about the video using the collected analyses."""
    try:
        # Construct context from analyses
        context = "Video Analysis Context:\n\n"
        
        if summarize_first and len(analyses) > 1:
            # First create a summary of all segments to provide a high-level overview
            summary_prompt = "Summarize the following video analysis segments into a coherent overview:\n\n"
            for analysis in analyses:
                summary_prompt += f"Segment {analysis['segment']} ({analysis['start_time']}-{analysis['end_time']} seconds):\n"
                summary_prompt += f"{analysis['analysis']}...\n\n"
                
            summary_response = st.session_state.aoai_client.chat.completions.create(
                model=st.session_state.aoai_model_name,
                messages=[
                    {"role": "system", "content": "Create a concise summary of the video based on these segment analyses."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=temperature,
                max_tokens=1000
            )
            
            summary_json = json.loads(summary_response.model_dump_json())
            context += "Overall Summary:\n" + summary_json['choices'][0]['message']['content'] + "\n\n"

        # Add individual segment analyses
        for analysis in analyses:
            context += f"Segment {analysis['segment']} ({analysis['start_time']}-{analysis['end_time']} seconds):\n"
            context += f"{analysis['analysis']}\n\n"

        # Construct messages array with chat history
        messages = [
            {"role": "system", "content": st.session_state.chat_config.get("chat_system_prompt", CHAT_SYSTEM_PROMPT)},
            {"role": "user", "content": f"Here is the video analysis to reference:\n{context}"}
        ]

        # Add chat history if it exists
        if chat_history:
            messages.extend(chat_history)

        # Add current query
        messages.append({"role": "user", "content": query})

        # Return streaming response
        response = st.session_state.aoai_client.chat.completions.create(
            model=st.session_state.aoai_model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=1000,
            stream=True
        )
        
        return response

    except Exception as ex:
        logger.error(f'Chat error: {ex}')
        return f'Error generating response: {ex}'