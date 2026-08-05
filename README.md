# Talk-to-Agent

Talk-to-Agent is a local realtime voice demo that connects a browser microphone to Google's Gemini Live API through a Python backend and WebRTC.

It demonstrates practical integration work across asynchronous Python, FastAPI, realtime media, browser APIs, and an external AI API. The active demo conducts a short, generic French-language pre-screening conversation and streams the model's voice back to the browser.

> **Current scope:** local technical demo / portfolio prototype. Production deployment would require authentication, hardened session isolation, rate limiting, production TLS/TURN configuration and an explicit privacy/data-retention policy.

## The problem it explores

Realtime voice applications need more than a conventional request/response API. They must coordinate microphone permissions, WebRTC signaling, continuous audio conversion, asynchronous AI sessions, low-latency playback, connection cleanup, and local security requirements.

This repository provides a compact working example of those integration concerns without presenting itself as a complete recruitment platform or production SaaS.

## What the demo does today

- Serves a small browser interface from FastAPI.
- Lets the user select one of five Gemini voices.
- Captures microphone audio with `getUserMedia()`.
- Negotiates a bidirectional WebRTC audio connection through FastRTC.
- Resamples incoming audio to mono 16 kHz PCM for Gemini Live.
- Streams Gemini's 24 kHz audio response back to the browser.
- Loads a server-side, non-static French interview-demo system prompt.
- Caps local WebRTC sessions at ten minutes to limit runaway demo sessions.
- Supports local HTTP on loopback and optional local HTTPS.
- Supports browser ICE configuration through `RTC_CONFIGURATION`.

The current demo does **not** upload a CV or job description, generate a structured interview report, display or save transcripts, authenticate users, or provide production-grade multi-user isolation.

## Technology stack

- **Python 3.11**
- **FastAPI** and **Uvicorn**
- **FastRTC / WebRTC**
- **Google Gemini Live API**
- **AsyncIO** and **NumPy** for realtime audio flow
- **JavaScript, HTML, and CSS** in the browser

## Simplified architecture

```text
Browser microphone
       │
       │ WebRTC audio + signaling
       ▼
FastAPI + FastRTC
       │
       │ mono PCM audio, asynchronous streaming
       ▼
Gemini Live API
       │
       │ generated voice audio
       ▼
Browser audio output
```

The browser obtains its public ICE configuration from `GET /config/rtc`. Application secrets remain on the server.

## Project structure

```text
.
├── .env.example                  # Safe local configuration template
├── config.ini                    # Active server-side prompt path
├── requirements.txt              # Pinned direct Python dependencies
├── src/
│   ├── app/
│   │   └── agent.py              # FastAPI, FastRTC, Gemini and local launcher
│   ├── prompts/
│   │   └── interview_demo.txt    # Server-side, non-static system prompt
│   ├── static/
│   │   ├── css/styles.css
│   │   ├── icone/
│   │   └── script/script.js
│   └── template/index.html
└── ssl/                          # Optional local certificates; ignored by Git
```

The system prompt is intentionally outside `src/static`, so FastAPI does not expose it as a public asset.

## Prerequisites

- Python 3.11
- A Gemini API key from Google AI Studio
- A modern browser with WebRTC support
- Optional: OpenSSL if you want local HTTPS

No Gemini request is made until a browser starts a voice session.

## Local installation

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks virtual-environment activation, use a process-scoped policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Linux and macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

## Configuration

Open the local `.env` file and set at least:

```dotenv
GEMINI_API_KEY=your_local_api_key
```

Available variables:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | empty | Server-side Gemini API key; required for a voice session |
| `APP_HOST` | `127.0.0.1` | Local bind address |
| `APP_PORT` | `7860` | Local server port |
| `APP_PEM` | empty | Optional TLS certificate path |
| `APP_KEY` | empty | Optional TLS private-key path |
| `RTC_CONFIGURATION` | empty | Public browser ICE configuration as JSON |

Relative certificate paths are resolved from the repository root. `APP_PEM` and `APP_KEY` must either both be configured and point to existing files, or both remain empty. A partial TLS configuration stops immediately with a clear error.

## Start the demo

From the repository root:

```powershell
python src/app/agent.py
```

With the default empty TLS settings, open:

<http://127.0.0.1:7860>

Loopback HTTP is intended only for local development. Browsers treat localhost/loopback as a trustworthy context for microphone access; this mode must not be exposed to a LAN or the Internet.

## Demo walkthrough

1. Start the Python process.
2. Open `http://127.0.0.1:7860` in a modern browser.
3. Select a Gemini voice.
4. Click **Start Recording**.
5. Allow microphone access when prompted.
6. Have a short French conversation with the interview-demo assistant.
7. Use the mute control if needed, then click **Stop Recording**.

The prompt deliberately states that no CV or job description is available. The application currently returns voice audio only; it does not claim to create a report or transcript.

## Optional local HTTPS

HTTPS is useful when testing through a hostname or a non-loopback development setup. The following command creates a local self-signed certificate with localhost SAN entries. It requires OpenSSL.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force ssl | Out-Null
openssl req -x509 -newkey rsa:2048 -nodes `
  -keyout ssl/app.key -out ssl/app.pem -days 365 `
  -subj "/CN=localhost" `
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

### Linux and macOS

```bash
mkdir -p ssl
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout ssl/app.key -out ssl/app.pem -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

Then set:

```dotenv
APP_PEM=ssl/app.pem
APP_KEY=ssl/app.key
```

Restart the application and open `https://localhost:7860`. A self-signed certificate is suitable only for controlled local development and will normally require explicit browser trust.

The entire `ssl/` directory, `*.pem`, and `*.key` files are ignored by Git. Never commit a private key or reuse development certificates in production.

## RTC configuration

When `RTC_CONFIGURATION` is empty, the backend returns a simple public STUN configuration suitable for many local demos.

Example custom value:

```dotenv
RTC_CONFIGURATION={"iceServers":[{"urls":["stun:stun.l.google.com:19302"]}]}
```

The value must be a JSON object containing an `iceServers` array. It is returned to the browser by `/config/rtc`, so do not place server-side API keys or long-lived secrets in it. Production deployments commonly need provider-specific TURN credentials and network testing; that setup is intentionally outside the current scope.

## Security and privacy

- `.env`, TLS keys, certificates, virtual environments, archives, and generated audio are ignored by Git.
- The Gemini API key is read only by the Python backend and is not included in the HTML or JavaScript.
- The active prompt is stored outside the public static directory.
- The application does not intentionally write audio or transcripts to disk.
- Voice audio is sent to the configured Gemini service when a session starts. Use fictional or non-sensitive data for portfolio demonstrations and review the provider's terms before handling real candidate data.
- The current endpoints are not authenticated and there is no rate limiting. Bind to loopback for local demonstrations.

## Current limitations

- Local portfolio prototype, not a production service.
- No user accounts, authentication, authorization, or rate limiting.
- No hardened multi-user session isolation.
- One active generic French interview-demo workflow.
- No CV/job-description upload or prompt enrichment.
- No displayed/saved transcription and no structured report.
- No database, dashboard, telephony, or administrative interface.
- The Gemini model and voice/language settings are currently defined in code.
- The installed Gemini streaming helper used by this prototype is deprecated upstream and should be migrated before long-term production use.
- Production deployment requires trusted TLS, TURN design, observability, privacy rules, retention rules, and broader automated tests.

## Engineering skills demonstrated

This project is intended to demonstrate hands-on capability in:

- Python backend engineering
- FastAPI and REST endpoint integration
- WebRTC and browser media APIs
- Realtime AI API integration
- Asynchronous producer/consumer workflows
- Audio format and sample-rate handling
- Configuration, TLS, and cross-platform debugging
- Frontend/backend integration and failure handling
