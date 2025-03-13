import os
import time
import json
import hashlib
import logging
from typing import Dict, Optional, Tuple

# Set up logger for this component
logger = logging.getLogger('cache')

# Path to the file that stores video analysis metadata
CACHE_FILE = os.path.join("video", "analysis_cache.json")

def ensure_cache_file():
    """Ensure the cache file exists."""
    logger.debug(f"Ensuring cache file exists at: {CACHE_FILE}")
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    if not os.path.exists(CACHE_FILE):
        logger.info(f"Creating new cache file at: {CACHE_FILE}")
        with open(CACHE_FILE, 'w') as f:
            json.dump({}, f)

def get_file_identifier(file) -> Tuple[str, int]:
    """Generate a unique identifier for a file based on name and size."""
    return (file.name, file.size)

def compute_file_hash(file) -> str:
    """Compute a hash of the file contents for more accurate identification."""
    logger.debug(f"Computing hash for file: {file.name}")
    file_content = file.getvalue()  # Get the file content as bytes
    file_hash = hashlib.md5(file_content).hexdigest()
    logger.debug(f"File hash computed: {file_hash}")
    return file_hash

def get_analysis_cache() -> Dict:
    """Get the analysis cache from disk."""
    logger.debug(f"Loading analysis cache from: {CACHE_FILE}")
    ensure_cache_file()
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
            logger.debug(f"Loaded cache with {len(cache)} entries")
            return cache
    except Exception as e:
        logger.error(f"Error loading analysis cache: {str(e)}")
        return {}

def save_analysis_cache(cache: Dict):
    """Save the analysis cache to disk."""
    logger.debug(f"Saving analysis cache with {len(cache)} entries to {CACHE_FILE}")
    ensure_cache_file()
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
            logger.debug("Cache saved successfully")
    except Exception as e:
        logger.error(f"Error saving analysis cache: {str(e)}")

def check_video_analyzed(file) -> Optional[str]:
    """
    Check if a video has been analyzed before.
    
    Args:
        file: The uploaded file object
        
    Returns:
        The path to the analysis directory if found, None otherwise
    """
    if file is None:
        logger.warning("check_video_analyzed called with None file")
        return None
        
    logger.info(f"Checking if video has been analyzed: {file.name}")
    
    # Look up by file hash
    file_hash = compute_file_hash(file)
    cache = get_analysis_cache()
    
    # Reset file position after reading for hash
    file.seek(0)
    
    if file_hash in cache:
        analysis_path = cache[file_hash]["analysis_dir"]
        # Verify the analysis directory still exists
        if os.path.exists(analysis_path):
            logger.info(f"Found existing analysis at: {analysis_path}")
            return analysis_path
        else:
            logger.warning(f"Analysis directory not found: {analysis_path}")
    
    logger.info(f"No previous analysis found for: {file.name}")
    return None

def register_video_analysis(file, analysis_dir: str):
    """
    Register that a video has been analyzed.
    
    Args:
        file: The uploaded file object
        analysis_dir: The path to the analysis directory
    """
    if file is None:
        logger.warning("register_video_analysis called with None file")
        return
        
    logger.info(f"Registering analysis for file: {file.name} at {analysis_dir}")
    
    file_hash = compute_file_hash(file)
    # Reset file position after reading for hash
    file.seek(0)
    
    cache = get_analysis_cache()
    
    # Store metadata about the video and its analysis
    cache[file_hash] = {
        "filename": file.name,
        "size": file.size,
        "analysis_dir": analysis_dir,
        "timestamp": time.time()  # Add timestamp of when analysis was done
    }
    
    save_analysis_cache(cache)
    logger.info(f"Successfully registered analysis for: {file.name}")

def check_url_analyzed(url, start_time=0, end_time=0) -> Optional[str]:
    """
    Check if a video URL has been analyzed before.
    
    Args:
        url: The video URL
        start_time: Start time for partial video analysis
        end_time: End time for partial video analysis
        
    Returns:
        The path to the analysis directory if found, None otherwise
    """
    if not url:
        return None
        
    # Create a unique identifier for this URL and time range
    url_id = hashlib.md5(f"{url}_{start_time}_{end_time}".encode()).hexdigest()
    
    cache = get_analysis_cache()
    
    if url_id in cache:
        analysis_path = cache[url_id]["analysis_dir"]
        # Verify the analysis directory still exists
        if os.path.exists(analysis_path):
            return analysis_path
    
    return None

def register_url_analysis(url, analysis_dir, start_time=0, end_time=0):
    """
    Register that a video URL has been analyzed.
    
    Args:
        url: The video URL
        analysis_dir: The path to the analysis directory
        start_time: Start time for partial video analysis
        end_time: End time for partial video analysis
    """
    if not url:
        return
        
    # Create a unique identifier for this URL and time range
    url_id = hashlib.md5(f"{url}_{start_time}_{end_time}".encode()).hexdigest()
    
    cache = get_analysis_cache()
    
    # Store metadata about the video URL and its analysis
    cache[url_id] = {
        "url": url,
        "start_time": start_time,
        "end_time": end_time,
        "analysis_dir": analysis_dir,
        "timestamp": time.time()
    }
    
    save_analysis_cache(cache)

def load_previous_analysis(analysis_dir: str) -> Dict:
    """
    Load the previous analysis results.
    
    Args:
        analysis_dir: The path to the analysis directory
        
    Returns:
        A dictionary with the analysis results
    """
    analyses = []
    try:
        # This would load the analysis files similar to load_all_analyses in video_processing.py
        analysis_subdir = os.path.join(analysis_dir, "analysis")
        files = sorted([f for f in os.listdir(analysis_subdir) if f.endswith('_analysis.json')])
        
        for file in files:
            with open(os.path.join(analysis_subdir, file), 'r') as f:
                analysis_data = json.load(f)
                analyses.append(analysis_data)
                
        return analyses
    except Exception as ex:
        logger.error(f"Error loading previous analysis: {ex}")
        return []

def get_all_previous_analyses():
    """
    Get a list of all previously analyzed videos.
    
    Returns:
        A list of dictionaries with metadata about previous analyses
    """
    cache = get_analysis_cache()
    analyses = []
    
    for key, data in cache.items():
        # Verify the analysis directory exists
        if "analysis_dir" in data and os.path.exists(data["analysis_dir"]):
            # Add metadata with a friendly name
            if "url" in data:
                # It's a URL analysis
                name = f"URL: {data['url'][:30]}..." if len(data['url']) > 30 else data['url']
                if data["start_time"] > 0 or data["end_time"] > 0:
                    name += f" ({data['start_time']}-{data['end_time']} seconds)"
            else:
                # It's a file analysis
                name = f"File: {data['filename']}"
            
            analyses.append({
                "key": key,
                "name": name,
                "path": data["analysis_dir"],
                "timestamp": data["timestamp"],
                "type": "url" if "url" in data else "file"
            })
    
    # Sort by timestamp, newest first
    analyses.sort(key=lambda x: x["timestamp"], reverse=True)
    return analyses
