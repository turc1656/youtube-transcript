from flask import Flask, render_template, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.proxies import GenericProxyConfig
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import os

app = Flask(__name__)

def get_video_id(youtube_url):
    parsed = urlparse(youtube_url)
    if parsed.hostname in ["www.youtube.com", "youtube.com", "m.youtube.com"]:
        return parse_qs(parsed.query).get("v", [None])[0]
    elif parsed.hostname == "youtu.be":
        return parsed.path[1:]
    return None

def fetch_transcript(video_url):
    video_id = get_video_id(video_url)
    if not video_id:
        return "Invalid YouTube URL."
    try:
        http_proxy = os.getenv('PROXY_CHEAP_HTTP')
        https_proxy = os.getenv('PROXY_CHEAP_HTTPS')
        proxy_username = os.getenv('PROXY_CHEAP_USERNAME')
        proxy_password = os.getenv('PROXY_CHEAP_PASSWORD')
        
        # Check if proxy settings are complete
        if not all([http_proxy, https_proxy, proxy_username, proxy_password]):
            # Use direct connection if proxy settings are incomplete
            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id, languages=['en'])
        else:
            # Create proper proxy URL format with hostnames and ports
            http_url = f"http://{proxy_username}:{proxy_password}@{http_proxy.replace('http://', '')}"
            print(f"HTTP Proxy URL: {http_url}")
            https_url = f"http://{proxy_username}:{proxy_password}@{https_proxy.replace('https://', '')}"
            print(f"HTTPS Proxy URL: {https_url}")
            ytt_api = YouTubeTranscriptApi(
                proxy_config = GenericProxyConfig(
                    http_url=http_url,
                    # https_url=https_url
                )
            )
            
            # Use the static fetch_transcript method with proxy configuration
            transcript = ytt_api.fetch(
                video_id,
                languages=['en'],  # hardcoded to English
            )
            
        # transcript_text = "\n".join([entry['text'] for entry in transcript])
        transcript_text = "\n".join([entry.text for entry in transcript])
        return transcript_text
    except TranscriptsDisabled:
        return "Transcripts are disabled for this video."
    except NoTranscriptFound:
        return "No English transcript found for this video."
    except VideoUnavailable:
        return "The video is unavailable."
    except Exception as e:
        return f"An unexpected error occurred: {e}"

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/fetch_transcript', methods=['POST'])
def fetch_transcript_endpoint():
    video_url = request.form.get('video_url')
    transcript = fetch_transcript(video_url)
    
    # Check if the transcript is an error message
    if transcript.startswith("Invalid") or transcript.startswith("No") or transcript.startswith("An") or transcript.startswith("Transcripts") or transcript.startswith("The video"):
        return jsonify({"success": False, "message": transcript})
    else:
        return jsonify({"success": True, "transcript": transcript})

if __name__ == '__main__':
    load_dotenv()  # Load environment variables from .env file
    app.run(host='0.0.0.0', port=5000, debug=True)  # Adding debug=True for auto-reload
