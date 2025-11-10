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

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

def query_rapidapi_provider(video_url):
    rapidapi_host = os.getenv("RAPIDAPI_HOST")
    rapidapi_key = os.getenv("RAPIDAPI_KEY")
    query_url = os.getenv("YT_API_RAPIDAPI_URL")

    # Validate environment variables are set
    if not rapidapi_host:
        raise ValueError("RAPIDAPI_HOST environment variable is not set")
    if not rapidapi_key:
        raise ValueError("RAPIDAPI_KEY environment variable is not set")
    if not query_url:
        raise ValueError("YT_API_RAPIDAPI_URL environment variable is not set")

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
    
    # Handle quota_reset conversion safely
    try:
        quota_seconds = int(quota_reset)
        readable_quota_seconds = str(timedelta(seconds=quota_seconds))
    except (ValueError, TypeError):
        readable_quota_seconds = quota_reset
    
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
    
    Returns a dict with:
      - ok: bool
      - text: transcript text (when ok)
      - error: error message (when not ok)
      - status, headers, preview: debug info (when available)
    """
    try:
        response = requests.get(transcript_url, timeout=10)
        status = response.status_code
        headers = dict(response.headers)
        text_body = response.text

        # Will raise for non-2xx responses
        response.raise_for_status()

        # Parse the SRV1 XML format
        root = ET.fromstring(text_body)

        # Extract all text elements and decode HTML entities
        text_segments = []
        for text_element in root.findall('text'):
            text_content = text_element.text
            if text_content:
                decoded_text = html.unescape(text_content)
                text_segments.append(decoded_text)

        transcript_text = ' '.join(text_segments)
        return {"ok": True, "text": transcript_text, "status": status, "headers": headers}

    except requests.HTTPError as e:
        resp = getattr(e, "response", None)
        status = resp.status_code if resp is not None else "N/A"
        preview = (resp.text[:1000] if resp is not None else "")
        headers = (dict(resp.headers) if resp is not None else {})
        err = f"HTTP error fetching transcript: {e}"
        print(err, "status=", status, "headers=", headers, "preview_len=", len(preview))
        return {"ok": False, "error": err, "status": status, "headers": headers, "preview": preview}

    except requests.RequestException as e:
        err = f"Request exception fetching transcript: {e}"
        print(err)
        return {"ok": False, "error": err}

    except ET.ParseError as e:
        preview = (text_body[:1000] if 'text_body' in locals() else "")
        err = f"Error parsing XML transcript: {e}"
        print(err, "preview_len=", len(preview) if preview else 0)
        return {"ok": False, "error": err, "status": status if 'status' in locals() else "N/A", "preview": preview}

    except Exception as e:
        err = f"An unexpected error occurred: {e}"
        print(err)
        return {"ok": False, "error": err}

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
    try:
        video_url = request.form.get('video_url')
        video_id = extract_video_id(video_url)
        if not video_id:
            return jsonify({"success": False, "message": "Invalid YouTube URL"})
        
        # Wrap RapidAPI call in try-except
        try:
            api_response, requests_remaining, quota_reset = query_rapidapi_provider(video_id)
        except Exception as e:
            err_msg = f"Error querying RapidAPI: {e}"
            print(err_msg)
            return jsonify({
                "success": False,
                "message": "Error fetching transcript data. Please try again."
                # "debug": {"error": str(e)}  # DEBUG ONLY: Uncomment for debugging, remove in production
            })
        
        subtitle_url = parse_query_response(api_response)
        if not subtitle_url:
            return jsonify({
                "success": False,
                "message": "No English subtitles found",
                "requests_remaining": requests_remaining,
                "quota_reset": quota_reset
                # , "debug": {"api_response": api_response}  # DEBUG ONLY: Uncomment for debugging, remove in production
            })

        transcript_result = fetch_transcript(subtitle_url)
        
        # When fetch_transcript returns structured data, include debug info on failure
        if not transcript_result.get("ok"):
            # debug = {  # DEBUG ONLY: Uncomment for debugging, remove in production
            #     "status": transcript_result.get("status"),
            #     "headers": transcript_result.get("headers"),
            #     "preview": transcript_result.get("preview")
            # }
            return jsonify({
                "success": False,
                "message": "Error fetching transcript. Please try again.",
                # "debug": debug,  # DEBUG ONLY: Uncomment for debugging, remove in production
                "requests_remaining": requests_remaining,
                "quota_reset": quota_reset
            })
        else:
            return jsonify({
                "success": True,
                "transcript": transcript_result.get("text"),
                "requests_remaining": requests_remaining,
                "quota_reset": quota_reset
            })
    
    except Exception as e:
        # Catch-all for any unhandled exceptions
        err_msg = f"Unexpected server error: {e}"
        print(err_msg)
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred. Please try again."
            # , "debug": {"exception": str(e), "type": type(e).__name__}  # DEBUG ONLY: Uncomment for debugging, remove in production
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)  # TODO REMINDER: Remove debug=True when deploying (this is the auto-reload feature)
