# 📹 Video Analysis with GPT-4o

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/john-carroll-sw/video-analysis-with-gpt-4o)

A Streamlit application that leverages AI vision capabilities to analyze video content, extract insights, and enable interactive conversations about visual content.

![Video Analysis With LLMs](https://raw.githubusercontent.com/john-carroll-sw/video-analysis-with-gpt-4o/main/media/VideoAnalysisWithLLMs.gif)

## ✨ Features

### 🎬 Upload

- Upload local video files (MP4, AVI, MOV) for AI-powered analysis
- Use a convenient sample video for quick testing and demonstration
- Analyze videos from URLs (YouTube, etc.) with automatic metadata extraction
- Reuse previous analyses to save time and processing resources
- Configure detailed processing parameters for customized analysis

### 🔍 Analyze

- Automated segmentation of videos for detailed frame-by-frame analysis
- Advanced vision model integration for sophisticated visual understanding
- Optional audio transcription to incorporate spoken content into analysis
- Adjustable analysis parameters (segment length, frame rate) for performance optimization
- Save frames for later reference and review
- Analyze specific time ranges within longer videos

### 💬 Chat

- Discuss analysis results with the AI in natural language
- Ask detailed questions about specific visual content, scenes, or objects
- Cross-reference insights across different video segments
- Explore patterns and observations with AI-assisted interpretation

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- OpenAI API access with GPT-4o vision capabilities
- Authentication service (optional)

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/john-carroll-sw/video-analysis-with-gpt-4o.git
   cd video-analysis-with-gpt-4o
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set up your `.env` file with your Azure OpenAI credentials:

   ```bash
   # Copy the sample environment file and edit it with your credentials
   cp .env.sample .env
   # Now edit the .env file with your preferred editor
   nano .env  # or use any text editor you prefer
   ```

### Running the Application

Run the Streamlit application:

```bash
streamlit run Video_Analysis.py
```

Open your web browser to <http://localhost:8501> to use the application.

## 📖 Usage Guide

### Video Upload

1. Select your video source (File or URL) in the sidebar
2. For file upload:
   - Click "Use Sample Video" for quick testing without uploading, OR
   - Upload your own video file through the file uploader
3. For URL analysis:
   - Paste a YouTube or other video URL in the input field
   - **Note**: YouTube has protective measures against webscraping that may block access
4. Review detailed video information in the expandable section
5. If the video was analyzed previously, choose to load the existing analysis or re-analyze

### Video Analysis

1. Configure analysis parameters in the sidebar:
   - **Segment interval**: Duration of each video segment for analysis
   - **Frames per second**: Rate at which frames are captured (0.1-30)
   - **Audio transcription**: Enable to include spoken content in analysis
   - **Frame resize ratio**: Reduce image size for processing efficiency
   - **Temperature**: Adjust AI creativity level
2. Customize system and user prompts to guide the analysis direction
3. Optionally specify a time range to analyze only part of the video
4. Click "Continue to Analysis" to begin processing
5. View segment-by-segment analysis results as they are generated
6. Compare AI insights with visual content for each segment

### Chat Interface

1. Navigate to the Chat tab after analysis is complete
2. Ask open-ended questions about the video content
3. Request specific information about scenes, objects, or activities
4. Compare different segments or request summary insights
5. The AI will reference analyzed frames to provide context-aware responses

## 🔐 Authentication

The application includes an optional authentication system that:

1. Secures access using an external authentication service
2. Automatically detects if running locally or in a deployed environment
3. Properly handles login/logout flows and session management
4. Can be enabled or disabled based on your requirements

### Configuring Authentication

To enable authentication:

1. Set `VITE_AUTH_ENABLED=true` in your `.env` file
2. Configure `VITE_AUTH_URL` to point to your authentication service
3. Set `FRONTEND_URL` if deploying to a custom domain

To disable authentication:

1. Set `VITE_AUTH_ENABLED=false` in your `.env` file

## 🧰 How It Works

The application uses a sophisticated multi-stage approach:

1. **Video Processing**: Videos are segmented into manageable chunks and frames are extracted at specified intervals.

2. **Frame Analysis**: The AI vision model examines frames from each segment to understand visual content.

3. **Optional Audio Transcription**: If enabled, the audio is transcribed to provide additional context.

4. **AI Analysis**: The extracted frames and transcriptions are analyzed using AI models with customized prompts.

5. **Interactive Interface**: Results are presented in a segment-by-segment view with the option to chat about insights.

## 🚀 Deployment

You can deploy this application to a server using the included deployment script:

### Quick Deployment

For standard deployment with default settings:

```bash
./deployment/deploy.sh cool-app-name
```

### Custom Deployment

For deployment with specific parameters:

```bash
./deployment/deploy.sh \
  --env-file .env \
  --dockerfile deployment/Dockerfile \
  --context . \
  --entry-file Video_Analysis.py \
  cool-app-name
```

The deployment script parameters:

- `--env-file`: Path to your environment file with API keys and configuration
- `--dockerfile`: Path to the Dockerfile for containerization
- `--context`: Build context for Docker
- `--entry-file`: Main Python file to run
- `cool-app-name`: Name for your deployed application (required)

After deployment, you'll receive a URL where your application is hosted.

## 📁 Project Structure

```plaintext
video-analysis-with-gpt-4o/
├── Video_Analysis.py         # Main application entry point
├── components/               # UI components
│   ├── upload.py             # Video upload functionality
│   ├── analyze.py            # Analysis component
│   └── chat.py               # Chat interface
├── models/                   # Data models
│   └── session_state.py      # Session state management
├── utils/                    # Utility functions
│   ├── api_clients.py        # API client initialization
│   ├── auth.py               # Authentication handling
│   ├── analysis_cache.py     # Previous analysis caching
│   ├── logging_utils.py      # Logging configuration
│   └── video_processing.py   # Video handling utilities
├── media/                    # Media assets
│   ├── microsoft.png         # Brand assets
│   └── sample-video-circuit-board.mp4 # Sample video
├── config.py                 # Configuration settings
├── deployment/               # Deployment scripts
├── requirements.txt          # Project dependencies
├── .env                      # Environment variables (not tracked)
├── CONTRIBUTING.md           # Contribution guidelines
└── README.md                 # Project documentation
```

## ⚙️ Configuration Options

The sidebar provides numerous configuration options:

- **Audio Transcription**: Enable to transcribe and analyze video audio
- **Segment Interval**: Set the duration of analysis segments (in seconds)
- **Frames Per Second**: Control how many frames are extracted (0.1-30)
- **Frame Resize Ratio**: Optionally reduce frame size for processing
- **Temperature**: Adjust AI response creativity (0.0-1.0)
- **Custom Prompts**: Modify system and user prompts for tailored analysis
- **Time Range**: Analyze only specific portions of longer videos

## ⚠️ Notes

- YouTube and other media sites have protective measures against web scraping that may block video access
- For more reliable results, consider downloading videos and uploading the files directly
- Processing large videos may take significant time and API resources
- Adjust the frame rate and segment interval to balance between analysis detail and processing time

## 🤝 Contributing

Please see the [CONTRIBUTING.md](./CONTRIBUTING.md) file for details on how to contribute to this project.

## 📄 License

This project is licensed under the [MIT License](LICENSE)

## 🙏 Acknowledgements

- [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service/) for providing the powerful AI models
- [Streamlit](https://streamlit.io/) for the simple web application framework
- [OpenCV](https://opencv.org/) for video processing capabilities
