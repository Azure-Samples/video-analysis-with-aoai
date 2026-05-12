# Video Analysis with GPT-4o

The aim of this repository is to demonstrate the capabilities of Azure OpenAI multimodal models (GPT-4o, GPT-4.1, o-series reasoning models, etc.) to analyze and extract insights from a video file or a video URL (e.g., YouTube).

The steps to process a video are the following:

1. Split the video in segments of N seconds (or process it whole if `0` seconds is specified).
2. Extract frames from each segment at a configurable frames-per-second sampling rate, stamping the absolute video timestamp on each frame.
3. Optionally transcribe the audio with Whisper.
4. Send the frames (and the optional audio transcription) to Azure OpenAI to extract a description, summary, or any other insight driven by the system/user prompt.

## Table of Contents

- [Video Analysis with GPT-4o](#video-analysis-with-gpt-4o)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
    - [Set up a Python virtual environment in Visual Studio Code](#set-up-a-python-virtual-environment-in-visual-studio-code)
    - [Environment Configuration](#environment-configuration)
    - [Authentication](#authentication)
  - [Video Analysis Script](#video-analysis-script)
    - [Usage](#usage)
    - [Parameters](#parameters)
    - [Default tunables (in the script)](#default-tunables-in-the-script)
    - [Example](#example)
  - [Video Shot Analysis Script](#video-shot-analysis-script)
    - [Usage](#usage-1)
    - [Parameters](#parameters-1)
    - [Example](#example-1)
  - [YouTube Video Downloader Script](#youtube-video-downloader-script)
    - [Usage](#usage-2)
    - [Parameters](#parameters-2)
    - [Example](#example-2)
  - [Troubleshooting](#troubleshooting)
  - [Deploying to Azure](#deploying-to-azure)

## Prerequisites

- An Azure subscription, with [access to Azure OpenAI](https://aka.ms/oai/access).
- An Azure OpenAI resource (endpoint).
- A deployment of a multimodal model (e.g. `gpt-4o`, `gpt-4.1`, `o4-mini`, etc.).
- *(Optional)* A Whisper deployment if you want audio transcription.
- Python 3.10 or later. Tested with Python 3.12.5.
- [Visual Studio Code](https://code.visualstudio.com/) with the [Python extension](https://code.visualstudio.com/docs/python/python-tutorial) and the [Jupyter extension](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter).
- **[ffmpeg](https://ffmpeg.org/)** available in your `PATH`. Required by `yt-dlp` to download partial YouTube segments and by the frame/audio extraction pipeline. On Windows you can install it with:

  ```powershell
  winget install --id=Gyan.FFmpeg -e
  ```

  See the [Troubleshooting](#troubleshooting) section if `ffmpeg` is installed but not detected.

### Set up a Python virtual environment in Visual Studio Code

1. Open the Command Palette (`Ctrl+Shift+P`).
2. Search for **Python: Create Environment**.
3. Select **Venv**.
4. Select a Python interpreter (3.10 or later).
5. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

It can take a minute to set up. If you run into problems, see [Python environments in VS Code](https://code.visualstudio.com/docs/python/environments).

### Environment Configuration

Create a `.env` file in the root directory of your project with the following content. You can use the provided [`.env-sample.ini`](.env-sample.ini) as a template:

```env
SYSTEM_PROMPT="You are an expert on Video Analysis. You will be shown a series of images from a video. Describe what is happening in the video, including the objects, actions, and any other relevant details. Be as specific and detailed as possible."

AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=<your_azure_openai_api_version>
AZURE_OPENAI_DEPLOYMENT_NAME=<your-multimodal-deployment-name>

# Optional — only required if you authenticate with API key (see Authentication below)
AZURE_OPENAI_API_KEY=<your_azure_openai_api_key>

# Set to True to enable audio transcription via Whisper. Defaults to False.
USE_WHISPER=False
# Only required if USE_WHISPER=True
WHISPER_ENDPOINT=https://<your-whisper-resource>.openai.azure.com/
WHISPER_API_KEY=<your-whisper-api-key>
WHISPER_API_VERSION=<your_whisper_api_version>
WHISPER_DEPLOYMENT_NAME=<your-whisper-deployment-name>
```

The needed libraries are specified in [requirements.txt](requirements.txt).

### Authentication

The application supports two authentication modes for Azure OpenAI, selected automatically:

- **API key** — used when `AZURE_OPENAI_API_KEY` is defined in the environment.
- **Microsoft Entra ID** (recommended) — used as a fallback when `AZURE_OPENAI_API_KEY` is **not** set. It uses [`DefaultAzureCredential`](https://learn.microsoft.com/python/api/azure-identity/azure.identity.defaultazurecredential), which tries (in order): environment variables, Managed Identity, Azure CLI (`az login`), Visual Studio Code, etc.

To use Entra ID locally:

1. Run `az login`.
2. Make sure your user has the **Cognitive Services OpenAI User** role on the Azure OpenAI resource:

   ```powershell
   az role assignment create `
     --assignee-object-id <YOUR_USER_OBJECT_ID> `
     --assignee-principal-type User `
     --role "Cognitive Services OpenAI User" `
     --scope "/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<AOAI_ACCOUNT>"
   ```

3. Make sure `AZURE_OPENAI_API_KEY` is **not** set in your `.env` (or comment it out).

## Video Analysis Script

The `video-analysis-with-aoai.py` script demonstrates the capabilities of Azure OpenAI multimodal models to analyze and extract insights from a video file or a video URL (e.g., YouTube). This script is useful for analyzing videos in detail by splitting them into smaller segments and extracting frames at a specified rate. This allows for a more granular analysis of the video content, making it easier to identify specific events, actions, or objects within the video. This script is particularly useful for:

- Detailed video analysis for research or academic purposes.
- Analyzing training or instructional videos to extract key moments.
- Reviewing security footage to identify specific incidents.

Here is the code of this demo: [video-analysis-with-aoai.py](video-analysis-with-aoai.py)

### Usage

To run the `video-analysis-with-aoai.py` script, execute the following command:

```powershell
streamlit run video-analysis-with-aoai.py
```

A screenshot:

<img src="./Screenshot.png" alt="Sample Screenshot"/>

### Parameters

UI options (sidebar):

- **Video source**: `File` (upload) or `URL` (YouTube).
- **Continuous transmission** (URL only): treat the source as a live stream.
- **Transcribe audio / Show audio transcription**: only available if `USE_WHISPER=True`.
- **Starting second**: skip the first N seconds of the video.
- **Number of seconds to split the video**: segment length. `0` processes the whole video as a single segment.
- **Frames per second to extract**: sampling rate (decimal allowed, e.g. `0.5`).
- **Frames resizing ratio**: divider applied to width/height to reduce token usage and latency.
- **Save the frames to the folder `frames`**: persist extracted frames to disk for inspection.
- **Temperature for the model**: temperature passed to the model.
- **System Prompt / User Prompt**: editable, defaulted from [prompts.py](prompts.py).

> ⚠️ The model accepts a maximum of **50 images per request**. The UI validates that `seconds_to_split × frames_per_second ≤ 50` and disables the **Analyze video** button otherwise.

### Default tunables (in the script)

These are defined at the top of [video-analysis-with-aoai.py](video-analysis-with-aoai.py) and can be edited there:

| Constant | Default | Description |
| --- | --- | --- |
| `SEGMENT_DURATION` | `16` | Default segment length in seconds (`0` = no split). |
| `USE_WHISPER` | `False` | Enable audio transcription via Whisper. Read from the `USE_WHISPER` env var (`true`/`false`). |
| `FRAMES_PER_SECOND` | `3` | Default sampling rate. |
| `RESIZE_OF_FRAMES` | `1` | Default resize divider (1 = original size). |
| `REASONING_EFFORT` | `"medium"` | Reasoning effort for o-series models (`none`, `low`, `medium`, `high`). |
| `DEFAULT_TEMPERATURE` | `0.5` | Default temperature (currently overridden to `0.0` in the UI). |

### Example

To analyze a YouTube video with a segment interval of 60 seconds, extracting 1 frame every 30 seconds, you would set the parameters as follows:

- **Video source**: URL
- **URL**: `https://www.youtube.com/watch?v=example`
- **Number of seconds to split the video**: 60
- **Number of seconds per frame**: 30

Then click the "Analyze video" button to start the analysis.

## Video Shot Analysis Script

The `video_shot_analysis.py` script will download the specified video, split it into shots based on the defined interval, extract frames at the specified rate, perform the analysis on each shot, and save the analysis results to JSON files in the analysis subdirectory within the main video analysis directory. If `max_duration` is set, only up to that duration of the video will be processed. This script is useful for:

- Detailed video analysis for research or academic purposes.
- Analyzing training or instructional videos to extract key moments.
- Reviewing security footage to identify specific incidents.

Here is the code of this demo: [video_shot_analysis.py](video_shot_analysis.py)

### Usage

To run the `video_shot_analysis.py` script, execute the following command:

```powershell
streamlit run video_shot_analysis.py
```

### Parameters

- **Video source**: Select whether the video is from a file or a URL.
- **Continuous transmission**: Check this if the video is a continuous transmission.
- **Transcribe audio**: Check this to transcribe the audio using Whisper.
- **Show audio transcription**: Check this to display the audio transcription.
- **Shot interval in seconds**: Specify the interval for each video shot.
- **Frames per second**: Specify the number of frames to extract per second.
- **Frames resizing ratio**: Specify the resizing ratio for the frames.
- **Save the frames**: Check this to save the extracted frames to the "frames" folder.
- **Temperature for the model**: Specify the temperature for the GPT-4o model.
- **System Prompt**: Enter the system prompt for the GPT-4o model.
- **User Prompt**: Enter the user prompt for the GPT-4o model.
- **Maximum duration to process (seconds)**: Specify the maximum duration of the video to process. If the video is longer, only this duration will be processed. Set to 0 to process the entire video.

### Example

To analyze a YouTube video with a shot interval of 60 seconds, extracting 1 frame per second, and processing only the first 120 seconds of the video, you would set the parameters as follows:

- **Video source**: URL
- **URL**: `https://www.youtube.com/watch?v=example`
- **Shot interval in seconds**: 60
- **Frames per second**: 1
- **Maximum duration to process (seconds)**: 120

Then click the "Analyze video" button to start the analysis.

## YouTube Video Downloader Script

The `yt_video_downloader.py` script allows you to download a segment of a YouTube video, convert it to MP4 format, and ensure the file size is under 200 MB. This script is useful for:

- Downloading and saving specific parts of a YouTube video for offline viewing.
- Extracting segments of a video for use in presentations or reports.
- Ensuring the downloaded video segment is of a manageable size for sharing or storage.

Here is the code of this demo: [yt_video_downloader.py](yt_video_downloader.py)

### Usage

To run the `yt_video_downloader.py` script, execute the following command:

```powershell
python yt_video_downloader.py
```

### Parameters

- **YouTube URL**: Enter the URL of the YouTube video.
- **Start time in seconds**: Specify the start time of the segment to download (default is 0).
- **End time in seconds**: Specify the end time of the segment to download (default is 60).
- **Output directory**: Specify the directory to save the downloaded segment (default is 'output').

### Example

To download a 60-second segment of a YouTube video starting at 30 seconds, you would set the parameters as follows:

- **YouTube URL**: `https://www.youtube.com/watch?v=example`
- **Start time in seconds**: 30
- **End time in seconds**: 90
- **Output directory**: `output`

Then run the script to download and convert the segment:

```powershell
python yt_video_downloader.py
```

The script will save the segment as an MP4 file in the specified output directory and ensure the file size is under 200 MB.

## Troubleshooting

### `ERROR: You have requested downloading the video partially, but ffmpeg is not installed. Aborting`

`yt-dlp` requires **ffmpeg** to cut and remux YouTube streams when only a segment of the video is requested (which is what this app does whenever `seconds_to_split > 0`).

1. Install ffmpeg (Windows):

   ```powershell
   winget install --id=Gyan.FFmpeg -e
   ```

2. Make sure `ffmpeg.exe` is in your `PATH`. If `winget` reports it is already installed but `ffmpeg -version` fails, locate the binary and add its `bin` folder to the user `PATH`:

   ```powershell
   $ffmpegBin = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Recurse -Filter ffmpeg.exe | Select-Object -First 1).DirectoryName
   $userPath  = [Environment]::GetEnvironmentVariable("Path", "User")
   if ($userPath -notlike "*$ffmpegBin*") {
       [Environment]::SetEnvironmentVariable("Path", "$userPath;$ffmpegBin", "User")
   }
   ```

3. **Restart VS Code / your terminal** so the new `PATH` is picked up, then re-run the app.

### `WARNING: [youtube] No supported JavaScript runtime could be found`

A recent `yt-dlp` warning. It does not break downloads today, but YouTube will eventually require a JS runtime. Install Deno to silence it and future-proof the extractor:

```powershell
winget install DenoLand.Deno
```

`yt-dlp` will detect it automatically.

## Deploying to Azure

To deploy the application to Azure as a containerized web app:

1. Build and push the Docker image to Azure Container Registry — see [Build and store an image by using Azure Container Registry](https://learn.microsoft.com/training/modules/deploy-run-container-app-service/3-exercise-build-images).
2. Create and deploy the web app from the image — see [Create and deploy a web app from a Docker image](https://learn.microsoft.com/training/modules/deploy-run-container-app-service/5-exercise-deploy-web-app).

When deploying to Azure App Service, prefer **Managed Identity** (Entra ID) over API keys: assign the *Cognitive Services OpenAI User* role to the App Service's managed identity on the Azure OpenAI resource, and **do not** set `AZURE_OPENAI_API_KEY` in the app settings.
