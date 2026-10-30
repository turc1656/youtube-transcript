// ==UserScript==
// @name         YouTube Transcript Button
// @namespace    https://yt.ryanturcotte.me/
// @version      2.0.0
// @description  Adds a "Summarize" button under YouTube videos that sends the video's transcript to ChatGPT through YouTube Transcript Fetcher
// @match        https://www.youtube.com/*
// @grant        GM_addStyle
// @grant        GM_openInTab
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      www.youtube.com
// @connect      yt.ryanturcotte.me
// @run-at       document-idle
// @noframes
// ==/UserScript==

(function () {
    "use strict";

    const APP_URL = "https://yt.ryanturcotte.me/";
    const BUTTON_ID = "yt-transcript-app-button";
    const BUTTON_LABEL = "Summarize";
    // The row with the Like / Share / Save buttons under the video. YouTube renames
    // its markup from time to time; if the button stops appearing, check this first.
    const BUTTON_ROW_SELECTOR = "ytd-watch-metadata #top-level-buttons-computed";
    // YouTube's private API that loads the "Show transcript" panel
    const YOUTUBE_PANEL_API_URL = "https://www.youtube.com/youtubei/v1/get_panel?prettyPrint=false";
    // Used when the page's own client version can't be read; YouTube accepted older versions in testing
    const FALLBACK_CLIENT_VERSION = "2.20261029.01.00";

    let summarizeInProgress = false;

    // Returns the current video's ID, or null when not on a video page
    function getVideoId() {
        const url = new URL(window.location.href);

        if (url.pathname === "/watch") {
            return url.searchParams.get("v");
        }
        if (url.pathname.startsWith("/shorts/")) {
            return url.pathname.split("/")[2] || null;
        }
        return null;
    }

    // Sends the user to the transcript app with the video URL prefilled (the app fetches
    // the transcript itself through RapidAPI)
    function openTranscriptApp(videoId) {
        const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;
        GM_openInTab(`${APP_URL}?video_url=${encodeURIComponent(videoUrl)}`, { active: true, insert: true });
    }

    function openCurrentVideoInApp() {
        // Read the URL at click time: YouTube changes videos without reloading the page
        const videoId = getVideoId();
        if (videoId) {
            openTranscriptApp(videoId);
        }
    }

    // POSTs JSON and resolves with the parsed JSON response. GM_xmlhttpRequest runs
    // outside the page, so it isn't affected by CORS or the userscript sandbox.
    function postJson(url, body) {
        return new Promise(function (resolve, reject) {
            GM_xmlhttpRequest({
                method: "POST",
                url: url,
                headers: { "Content-Type": "application/json" },
                data: JSON.stringify(body),
                timeout: 20000,
                onload: function (response) {
                    if (response.status < 200 || response.status >= 300) {
                        reject(new Error(`HTTP ${response.status} from ${url}`));
                        return;
                    }
                    try {
                        resolve(JSON.parse(response.responseText));
                    } catch (error) {
                        reject(new Error(`Invalid JSON from ${url}`));
                    }
                },
                onerror: function () {
                    reject(new Error(`Request to ${url} failed`));
                },
                ontimeout: function () {
                    reject(new Error(`Request to ${url} timed out`));
                }
            });
        });
    }

    function getClientVersion() {
        try {
            return unsafeWindow.ytcfg.get("INNERTUBE_CLIENT_VERSION") || FALLBACK_CLIENT_VERSION;
        } catch (error) {
            return FALLBACK_CLIENT_VERSION;
        }
    }

    // The panel API's "params" value is the video ID wrapped in a small protobuf
    // message: { 149: { 1: videoId, 3: 1 } }, base64-encoded
    function buildTranscriptParams(videoId) {
        const inner = [0x0a, videoId.length, ...Array.from(videoId, (c) => c.charCodeAt(0)), 0x18, 0x01];
        return btoa(String.fromCharCode(0xaa, 0x09, inner.length, ...inner));
    }

    // The transcript lines are nested deep in the response; collect them wherever they appear
    function collectTranscriptLines(node, lines) {
        if (!node || typeof node !== "object") {
            return;
        }
        if (node.transcriptSegmentViewModel) {
            lines.push(node.transcriptSegmentViewModel.simpleText || "");
            return;
        }
        for (const key in node) {
            collectTranscriptLines(node[key], lines);
        }
    }

    // Returns the video's transcript as one block of text ("" if YouTube has none)
    async function fetchYouTubeTranscript(videoId) {
        const response = await postJson(YOUTUBE_PANEL_API_URL, {
            context: { client: { clientName: "WEB", clientVersion: getClientVersion() } },
            panelId: "PAmodern_transcript_view",
            params: buildTranscriptParams(videoId)
        });

        const lines = [];
        collectTranscriptLines(response, lines);
        return lines.join(" ").replace(/\s+/g, " ").trim();
    }

    // Fetches the transcript from YouTube, stores it in the transcript app, and opens
    // ChatGPT with the app's link. Falls back to the transcript app if any step fails.
    async function summarizeVideo() {
        const videoId = getVideoId();
        if (!videoId || summarizeInProgress) {
            return;
        }

        summarizeInProgress = true;
        setButtonBusy(true);
        try {
            const transcript = await fetchYouTubeTranscript(videoId);
            if (!transcript) {
                throw new Error("YouTube returned no transcript");
            }

            const result = await postJson(`${APP_URL}store_transcript`, { transcript: transcript });
            if (!result || !result.success || !result.chatgpt_url) {
                throw new Error("Transcript app did not return a ChatGPT link");
            }

            // GM_openInTab isn't subject to the popup blocker, which would stop
            // window.open this long after the click
            GM_openInTab(result.chatgpt_url, { active: true, insert: true });
        } catch (error) {
            console.warn("[YouTube Transcript Button] Falling back to the transcript app:", error);
            openTranscriptApp(videoId);
        } finally {
            summarizeInProgress = false;
            setButtonBusy(false);
        }
    }

    function setButtonBusy(isBusy) {
        const button = document.getElementById(BUTTON_ID);
        if (!button) {
            return;
        }
        button.disabled = isBusy;
        button.querySelector("span").textContent = isBusy ? "Working…" : BUTTON_LABEL;
    }

    // Built with DOM APIs rather than innerHTML, which YouTube's Trusted Types policy blocks
    function createButton() {
        const button = document.createElement("button");
        button.id = BUTTON_ID;
        button.type = "button";
        button.title = "Summarize this video's transcript in ChatGPT";

        const label = document.createElement("span");
        label.textContent = BUTTON_LABEL;

        button.appendChild(createIcon());
        button.appendChild(label);
        button.addEventListener("click", summarizeVideo);
        return button;
    }

    // Material "subtitles" icon
    function createIcon() {
        const svgNs = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(svgNs, "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("width", "24");
        svg.setAttribute("height", "24");
        svg.setAttribute("aria-hidden", "true");

        const path = document.createElementNS(svgNs, "path");
        path.setAttribute("fill", "currentColor");
        path.setAttribute("d", "M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zM4 12h4v2H4v-2zm10 6H4v-2h10v2zm6 0h-4v-2h4v2zm0-4H10v-2h10v2z");

        svg.appendChild(path);
        return svg;
    }

    // Adds the button on video pages if it isn't already there
    function ensureButton() {
        if (window.location.pathname !== "/watch" || document.getElementById(BUTTON_ID)) {
            return;
        }
        const buttonRow = document.querySelector(BUTTON_ROW_SELECTOR);
        if (buttonRow) {
            buttonRow.prepend(createButton());
        }
    }

    // Matches YouTube's own pill buttons; html[dark] is set when YouTube's dark theme is on
    GM_addStyle(`
        #${BUTTON_ID} {
            display: inline-flex;
            flex-shrink: 0;
            align-items: center;
            gap: 6px;
            height: 40px;
            margin-right: 8px;
            padding: 0 16px 0 12px;
            border: none;
            border-radius: 20px;
            background: rgba(0, 0, 0, 0.05);
            color: #0f0f0f;
            font: 500 14px Roboto, Arial, sans-serif;
            white-space: nowrap;
            cursor: pointer;
        }
        #${BUTTON_ID}:hover {
            background: rgba(0, 0, 0, 0.1);
        }
        #${BUTTON_ID}:disabled {
            cursor: progress;
            opacity: 0.6;
        }
        html[dark] #${BUTTON_ID} {
            background: rgba(255, 255, 255, 0.1);
            color: #f1f1f1;
        }
        html[dark] #${BUTTON_ID}:hover {
            background: rgba(255, 255, 255, 0.2);
        }
    `);

    // Also available from the Tampermonkey toolbar menu, which works on Shorts
    // and keeps working even if YouTube's layout changes break the button
    GM_registerMenuCommand("Summarize in ChatGPT", summarizeVideo);
    GM_registerMenuCommand("Open in transcript app", openCurrentVideoInApp);

    // YouTube is a single-page app that builds (and rebuilds) its UI after load,
    // so re-check whenever the page changes rather than only once at startup
    let checkScheduled = false;
    new MutationObserver(function () {
        if (checkScheduled) {
            return;
        }
        checkScheduled = true;
        requestAnimationFrame(function () {
            checkScheduled = false;
            ensureButton();
        });
    }).observe(document.body, { childList: true, subtree: true });

    ensureButton();
})();
