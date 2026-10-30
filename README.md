# YouTube Transcript
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-supported-blue)](https://www.docker.com/)
[![RapidAPI](https://img.shields.io/badge/API-RapidAPI-orange)](https://rapidapi.com/ytjar/api/yt-api)

A small Flask web app that fetches **English subtitles/transcripts** for a YouTube video and displays them in the browser.

The sole purpose of this project is to make it easy for an end user to:
1. Paste a YouTube link  
2. Click a button  
3. Copy a clean, human‑readable transcript  

This is especially useful for feeding transcripts into LLMs for summarization, analysis, or note‑taking.

---

## TL;DR / Quickstart

1. **Create a RapidAPI account**
   - Sign up at https://rapidapi.com
2. **Subscribe to this exact API (free plan is sufficient)**
   - 👉 https://rapidapi.com/ytjar/api/yt-api  
   - The free tier currently allows **300 requests per month**
3. **Create a RapidAPI App**
   - RapidAPI will generate an **API key** for that app
4. **Create a `.env` file** with the values below
5. **Run the app (locally or with Docker)**

That’s it — no direct YouTube API credentials required.

---

## Current status

> **Main branch:**  
> This app uses **one provider only**: the **yt-api RapidAPI provider**.  
> While the code could be refactored to support additional providers, **only this RapidAPI integration is wired in on `main`**.

This project originally attempted to call YouTube APIs directly. That approach works locally, but once deployed to a server or datacenter IP, requests were blocked.  Using RapidAPI avoids those IP‑based restrictions and provides a reliable hosted endpoint.

---

## What it does

- Accepts a YouTube URL:
  - `youtube.com/watch?v=…`
  - `m.youtube.com`
  - `youtu.be/…`
- Queries the RapidAPI **yt-api** endpoint for subtitle metadata
- Selects an **English** subtitle track (SRV1 format)
- Downloads and parses the XML transcript
- Renders a single, clean block of readable text
- Displays remaining request quota information
- Prefills the URL box from a `?video_url=` query parameter (used by the [YouTube button](#optional-youtube-button-tampermonkey))
- Accepts transcript text fetched elsewhere at `POST /store_transcript` and returns the same temporary link and ChatGPT link (used by the YouTube button)

---

## Tech stack

- Python
- Flask
- `requests` for HTTP calls
- `gunicorn` for production serving
- Docker + docker‑compose for deployment

---

## RapidAPI requirements (important)

You **must** do the following:

1. Have a **RapidAPI account**
2. Subscribe to **yt-api**:
   - https://rapidapi.com/ytjar/api/yt-api
3. Create a **RapidAPI App**
4. Use the **App’s API key** in this project

Without this, the app will not work.

---

## Configuration

Create a `.env` file (or set environment variables) with **these exact values**:

```env
RAPIDAPI_HOST="yt-api.p.rapidapi.com"
YT_API_RAPIDAPI_URL="https://yt-api.p.rapidapi.com/subtitles"
RAPIDAPI_KEY="your_rapidapi_app_key_here"
```

### Environment variable details

| Variable | Description |
|---|---|
| `RAPIDAPI_HOST` | Must be `yt-api.p.rapidapi.com` |
| `YT_API_RAPIDAPI_URL` | Subtitles endpoint used by the app |
| `RAPIDAPI_KEY` | API key from your RapidAPI **App** |
---

## Run locally (no Docker)

```bash
pip install -r requirements.txt
python app.py
```

Then open:

```
http://localhost:5000
```

---

## Run with Docker (local build)

Build the image:

```bash
docker build -t youtube-transcript-app .
```

Run it:

```bash
docker run --rm -p 5000:5000 --env-file .env youtube-transcript-app
```

Open:

```
http://localhost:5000
```

---

## Run with docker‑compose (recommended for servers)

The repository includes a `docker-compose.yml` file.

```bash
docker compose up -d
```

This expects:
- a `.env` file in the same directory
- the RapidAPI variables defined above

---

## Deployment notes (Docker Hub + server pull)

A common deployment flow:

1. Build the image locally
2. Tag it
3. Push to your registry (e.g. Docker Hub)
4. Pull and restart on your server

Example:

```bash
docker build -t youtube-transcript-app .
docker tag youtube-transcript-app turc1656/youtube-transcript:latest
docker push turc1656/youtube-transcript:latest
```

Ensure `docker-compose.yml` references the same image tag.

---

## Optional: deployment webhook

This repo includes `deploy_script.py`, which can trigger a server‑side webhook to pull the latest image and restart the container.

### Required environment variables

| Variable | Description |
|---|---|
| `DEPLOYMENT_WEBHOOK_URL` | Server endpoint that performs the deploy |
| `DEPLOYMENT_SECRET_TOKEN` | Shared secret validated by the server |

Run:

```bash
python deploy_script.py
```

### Security note

The current script sends the token as a **query parameter** (`?token=...`).  
For better security in production, consider:
- Sending the token in a request header
- Validating it server‑side before deploying

---

## Optional: YouTube button (Tampermonkey)

`userscript/youtube-transcript-button.user.js` adds a **Summarize** button under every YouTube video — next to the Like / Share buttons on desktop, and right after **Subscribe** on the mobile site (`m.youtube.com`, e.g. Firefox for Android with Tampermonkey). One click:

1. Fetches the video's transcript directly from YouTube (the same private API YouTube's own "Show transcript" panel uses — no RapidAPI request)
2. Sends it to this app's `POST /store_transcript`, which stores it like any other transcript (temporary `/t/<token>` link, `TRANSCRIPT_TTL_SECONDS`)
3. Opens ChatGPT with the app's "summarize this transcript" link

If any step fails (the video has no transcript, YouTube changes its API, or the app can't be reached), it opens this app instead with the video URL filled in — then just click **Fetch Transcript**.

To install:

1. Install the [Tampermonkey](https://www.tampermonkey.net/) browser extension
2. Open the Tampermonkey dashboard and create a new script
3. Replace the template with the contents of `userscript/youtube-transcript-button.user.js` and save

If you host the app somewhere else, change `APP_URL` and the matching `@connect` line at the top of the script.

The Tampermonkey menu (toolbar icon on desktop; **⋮ → Extensions → Tampermonkey** in Firefox for Android) has two commands for the current video:
- **Summarize in ChatGPT** — same as the button
- **Open in transcript app** — opens this app with the video URL filled in, for reading, copying, or downloading the transcript

The menu commands also work on Shorts, and keep working if a YouTube layout change stops the button from appearing (`DESKTOP_BUTTON_ROW_SELECTOR` / `MOBILE_BUTTON_ROW_SELECTOR` in the script are what need updating).

### `POST /store_transcript`

Request body: `{"transcript": "..."}` (JSON, up to 1,000,000 characters)

Response: `{"success": true, "transcript_token": "...", "transcript_url": ".../t/<token>", "chatgpt_url": "..."}`

Returns `400` for missing or empty text and `413` for text over the limit. The endpoint is open (no key), like `/fetch_transcript`.

---

## License

MIT — see [LICENSE](LICENSE).