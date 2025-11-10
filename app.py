from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.proxies import GenericProxyConfig
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import os
import xml.etree.ElementTree as ET
import html
import requests
import json
from datetime import timedelta


app = Flask(__name__)

def query_rapidapi_provider(video_url):
    rapidapi_host = os.getenv("RAPIDAPI_HOST")
    rapidapi_key = os.getenv("RAPIDAPI_KEY")
    query_url = os.getenv("YT_API_RAPIDAPI_URL")

    querystring = {"id":video_url}

    headers = {
        "x-rapidapi-key": rapidapi_key,
        "x-rapidapi-host": rapidapi_host
    }

    response = requests.get(query_url, headers=headers, params=querystring)
    
    # Access rate limit from response headers
    requests_remaining = response.headers.get('x-ratelimit-requests-remaining', 'N/A')
    quota_reset = response.headers.get('x-ratelimit-requests-reset', 'N/A')
    print(f"Rate limit remaining: {requests_remaining}")
    quota_seconds=int(quota_reset)
    readable_quota_seconds = str(timedelta(seconds=quota_seconds))
    print(f"Rate limit resets in: {readable_quota_seconds}")
    
    return response.json(), requests_remaining, readable_quota_seconds

def parse_query_response(api_response):
    """
    Parse the RapidAPI response and extract the English (en) subtitle URL in srv1 format.
    
    Args:
        api_response: JSON response from the RapidAPI provider
        
    Returns:
        str: The subtitle URL if found, None otherwise
    """
    try:
        subtitles = api_response.get('subtitles', [])
        
        # Look for English subtitle with srv1 format
        for subtitle in subtitles:
            if subtitle.get('languageCode') == 'en':
                # Verify format is srv1
                if api_response.get('format') == 'srv1':
                    return subtitle.get('url')
        
        return None
        
    except (KeyError, TypeError) as e:
        print(f"Error parsing subtitle data: {e}")
        return None

def fetch_transcript(transcript_url):
    """
    Fetch and parse the transcript from the provided URL.
    
    Args:
        transcript_url: URL to the SRV1 format XML transcript
        
    Returns:
        str: Parsed transcript text or error message
    """
    try:
        # Make HTTP request to fetch the transcript
        response = requests.get(transcript_url)
        response.raise_for_status()  # Raise exception for bad status codes
        
        xml_content = response.text
        
        # Parse the SRV1 XML format
        root = ET.fromstring(xml_content)
        
        # Extract all text elements and decode HTML entities
        text_segments = []
        for text_element in root.findall('text'):
            text_content = text_element.text
            if text_content:
                # Decode HTML entities like &#39; to '
                decoded_text = html.unescape(text_content)
                text_segments.append(decoded_text)
        
        # Join all segments with spaces to create readable text
        transcript_text = ' '.join(text_segments)
        return transcript_text
        
    except requests.RequestException as e:
        return f"Error fetching transcript: {e}"
    except ET.ParseError as e:
        return f"Error parsing XML transcript: {e}"
    except Exception as e:
        return f"An error occurred: {e}"

def extract_video_id(video_url):
    """
    Extract the video ID from a YouTube URL.
    
    Args:
        video_url: YouTube URL (e.g., https://www.youtube.com/watch?v=O4wBUysNe2k)
        
    Returns:
        str: The video ID if found, None otherwise
    """
    try:
        parsed_url = urlparse(video_url)
        
        # Handle standard YouTube URLs (youtube.com/watch?v=...)
        if parsed_url.hostname in ['www.youtube.com', 'youtube.com']:
            query_params = parse_qs(parsed_url.query)
            video_id = query_params.get('v', [None])[0]
            return video_id
        
        # Handle short YouTube URLs (youtu.be/...)
        elif parsed_url.hostname == 'youtu.be':
            video_id = parsed_url.path.lstrip('/')
            return video_id
        
        return None
        
    except Exception as e:
        print(f"Error extracting video ID: {e}")
        return None

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/fetch_transcript', methods=['POST'])
def fetch_transcript_endpoint():
    video_url = request.form.get('video_url')
    video_id = extract_video_id(video_url)
    if not video_id:
        return jsonify({"success": False, "message": "Invalid YouTube URL"})
    
    api_response, requests_remaining, quota_reset = query_rapidapi_provider(video_id)
    subtitle_url = parse_query_response(api_response)
    if not subtitle_url:
        return jsonify({"success": False, "message": "No English subtitles found", "requests_remaining": requests_remaining, "quota_reset": quota_reset})

    transcript = fetch_transcript(subtitle_url)
    
    # Check if the transcript is an error message
    if transcript.startswith("Error") or transcript.startswith("Invalid") or transcript.startswith("No") or transcript.startswith("An") or transcript.startswith("Transcripts") or transcript.startswith("The video"):
        return jsonify({"success": False, "message": transcript, "requests_remaining": requests_remaining, "quota_reset": quota_reset})
    else:
        return jsonify({"success": True, "transcript": transcript, "requests_remaining": requests_remaining, "quota_reset": quota_reset})

if __name__ == '__main__':
    load_dotenv()  # Load environment variables from .env file
    app.run(host='0.0.0.0', port=5000, debug=True)  # TODO REMINDER: Remove debug=True when deploying (this is the auto-reload feature)
