import asyncio
import configparser
import json
import os
from pathlib import Path
from typing import AsyncGenerator, Literal

import numpy as np
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastrtc import (
    AsyncStreamHandler,
    Stream,
    get_cloudflare_turn_credentials_async,
    wait_for_item,
)
from google import genai
from google.genai.types import (
    LiveConnectConfig,
    PrebuiltVoiceConfig,
    SpeechConfig,
    VoiceConfig,
    ProactivityConfig,
    RealtimeInputConfig,
    AutomaticActivityDetection,
    StartSensitivity,
    EndSensitivity,
    Content,
    Part,
)
from gradio.utils import get_space
from pydantic import BaseModel, Field

current_dir = Path(__file__).resolve().parent.parent
project_root = current_dir.parent

load_dotenv(project_root / ".env", encoding="utf-8")

config_prompt = configparser.ConfigParser()
config_path = project_root / "config.ini"
if not config_prompt.read(config_path, encoding="utf-8"):
    raise RuntimeError(f"Configuration file not found: {config_path}")
try:
    prompt_setting = config_prompt["PROMPT"]["SYSTEM_PROMPT"]
except KeyError as exc:
    raise RuntimeError(
        "config.ini must define PROMPT.SYSTEM_PROMPT."
    ) from exc
prompt_file = project_root / prompt_setting
if not prompt_file.is_file():
    raise RuntimeError(f"System prompt file not found: {prompt_file}")
with open(prompt_file, "r", encoding="utf-8") as file:
    prompt = " ".join(line.rstrip() for line in file)

AUDIO_QUEUE_MAX_SIZE = 64
VOICE_SELECTION_TIMEOUT_SECONDS = 10
LOCAL_SESSION_TIME_LIMIT_SECONDS = 600
WEBRTC_ID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
DEFAULT_RTC_CONFIGURATION = {
    "iceServers": [
        {
            "urls": [
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
            ]
        }
    ]
}


def pcm_audio_to_bytes(data: np.ndarray) -> bytes:
    """Return little-endian 16-bit PCM bytes for Gemini Live."""
    return np.asarray(data, dtype="<i2").tobytes()


def put_bounded(queue: asyncio.Queue, item: object) -> None:
    """Keep realtime queues bounded by dropping the oldest item when full."""
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(item)


def load_rtc_configuration() -> dict:
    """Load the public browser ICE configuration from the environment."""
    value = os.getenv("RTC_CONFIGURATION")
    if not value:
        return DEFAULT_RTC_CONFIGURATION

    try:
        configuration = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("RTC_CONFIGURATION must be valid JSON.") from exc

    if not isinstance(configuration, dict):
        raise RuntimeError("RTC_CONFIGURATION must be a JSON object.")
    ice_servers = configuration.get("iceServers")
    if not isinstance(ice_servers, list):
        raise RuntimeError("RTC_CONFIGURATION.iceServers must be a JSON array.")
    return configuration


rtc_configuration = load_rtc_configuration()


def select_rtc_configuration():
    """Use Cloudflare TURN on Spaces or whenever HF_TOKEN is configured."""
    if get_space() or os.getenv("HF_TOKEN", "").strip():
        return get_cloudflare_turn_credentials_async
    return rtc_configuration


class GeminiHandler(AsyncStreamHandler):
    """Handler for the Gemini API"""

    def __init__(
        self,
        expected_layout: Literal["mono"] = "mono",
        output_sample_rate: int = 24000,
    ) -> None:
        super().__init__(
            expected_layout,
            output_sample_rate,
            input_sample_rate=16000,
        )
        self.input_queue: asyncio.Queue = asyncio.Queue(
            maxsize=AUDIO_QUEUE_MAX_SIZE
        )
        self.output_queue: asyncio.Queue = asyncio.Queue(
            maxsize=AUDIO_QUEUE_MAX_SIZE
        )
        self.quit: asyncio.Event = asyncio.Event()

    def copy(self) -> "GeminiHandler":
        return GeminiHandler(
            expected_layout="mono",
            output_sample_rate=self.output_sample_rate,
        )

    async def agent_stream(self, session: genai.live.AsyncSession):
        async for audio in session.start_stream(
            stream=self.stream(), mime_type="audio/pcm"
        ):
            if audio.data:
                array = np.frombuffer(audio.data, dtype=np.int16)
                put_bounded(
                    self.output_queue, (self.output_sample_rate, array)
                )

    async def start_up(self):
        if not self.phone_mode:
            try:
                await asyncio.wait_for(
                    self.wait_for_args(),
                    timeout=VOICE_SELECTION_TIMEOUT_SECONDS,
                )
            except (asyncio.TimeoutError, TimeoutError) as exc:
                self.quit.set()
                raise RuntimeError(
                    "Voice selection was not received before the session timeout."
                ) from exc
            if self.quit.is_set():
                return
            voice_name = self.latest_args[1:]
        else:
            voice_name = "Alnilam"

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required before starting a voice session."
            )

        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1alpha"},
        )

        config = LiveConnectConfig(
            response_modalities=["AUDIO"],  # type: ignore
            speech_config=SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        voice_name="".join(map(str, voice_name))
                    ),
                ),
                language_code="fr-FR",
            ),
            system_instruction=Content(parts=[Part(text=prompt)]),
            enable_affective_dialog=False,
            proactivity=ProactivityConfig(proactive_audio=False),
            realtime_input_config=RealtimeInputConfig(
                automatic_activity_detection=AutomaticActivityDetection(
                    disabled=False,
                    start_of_speech_sensitivity=StartSensitivity.START_SENSITIVITY_LOW,
                    end_of_speech_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
                    prefix_padding_ms=20,
                    silence_duration_ms=100,
                )
            ),
        )

        async with client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            config=config,
        ) as session:
            print("=============== START SESSION ===============")
            await self.agent_stream(session=session)

    async def stream(self) -> AsyncGenerator[bytes, None]:
        while not self.quit.is_set():
            try:
                audio = await asyncio.wait_for(self.input_queue.get(), 0.1)
                yield audio
            except (asyncio.TimeoutError, TimeoutError):
                pass

    async def receive(self, frame: tuple[int, np.ndarray]) -> None:
        _, array = frame
        array = array.squeeze()
        audio_message = pcm_audio_to_bytes(array)
        put_bounded(self.input_queue, audio_message)

    async def emit(self) -> tuple[int, np.ndarray] | None:
        return await wait_for_item(self.output_queue)

    def shutdown(self) -> None:
        self.quit.set()
        self.args_set.set()
        for queue in (self.input_queue, self.output_queue):
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break


stream = Stream(
    modality="audio",
    mode="send-receive",
    handler=GeminiHandler(),
    rtc_configuration=select_rtc_configuration(),
    concurrency_limit=5,
    time_limit=90 if get_space() else LOCAL_SESSION_TIME_LIMIT_SECONDS,
)


class InputData(BaseModel):
    webrtc_id: str = Field(
        min_length=36,
        max_length=36,
        pattern=WEBRTC_ID_PATTERN,
    )
    voice_name: Literal["Zephyr", "Charon", "Kore", "Autonoe", "Alnilam"]


app = FastAPI()

app.mount("/static", StaticFiles(directory=current_dir / "static"), name="static_file")


def _resolve_cert(env_var: str) -> str | None:
    """Résout un chemin de certificat relatif à la racine du projet."""
    value = os.getenv(env_var)
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return str(path) if path.is_file() else None


def resolve_tls_files() -> tuple[str | None, str | None]:
    """Require a complete TLS pair, or no TLS configuration at all."""
    pem_value = os.getenv("APP_PEM")
    key_value = os.getenv("APP_KEY")
    if bool(pem_value) != bool(key_value):
        raise RuntimeError("APP_PEM and APP_KEY must be configured together.")
    if not pem_value:
        return None, None

    pem = _resolve_cert("APP_PEM")
    key = _resolve_cert("APP_KEY")
    if not pem or not key:
        raise RuntimeError(
            "APP_PEM and APP_KEY must both point to existing files."
        )
    return pem, key


app_pem, app_key = resolve_tls_files()


def resolve_app_host() -> str:
    """Keep plain HTTP bound to loopback for the local portfolio demo."""
    host = os.getenv("APP_HOST", "127.0.0.1").strip()
    if not host:
        raise RuntimeError("APP_HOST must not be empty.")
    if not (app_pem and app_key) and host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "HTTP mode may only bind to a loopback host. Configure TLS before "
            "using a LAN or public bind address."
        )
    return host


def resolve_app_port() -> int:
    """Validate the local TCP port before Uvicorn starts."""
    value = os.getenv("APP_PORT", "7860")
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError("APP_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("APP_PORT must be between 1 and 65535.")
    return port

stream.mount(app)


@app.post("/input_hook")
async def set_voice(body: InputData):
    if body.webrtc_id not in stream.connections:
        raise HTTPException(status_code=404, detail="Unknown WebRTC session.")
    stream.set_input(body.webrtc_id, body.voice_name)
    return {"status": "ok"}


@app.get("/config/rtc")
async def rtc_config():
    selected_configuration = select_rtc_configuration()
    if callable(selected_configuration):
        return await selected_configuration()
    return selected_configuration


@app.get("/")
async def index():
    html_content = (current_dir / "template/index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    if not (app_pem and app_key):
        print(
            "[WARN] TLS is not configured. Starting in HTTP loopback mode for "
            "local development only."
        )

    uvicorn.run(
        app,
        host=resolve_app_host(),
        port=resolve_app_port(),
        ssl_keyfile=app_key,
        ssl_certfile=app_pem,
    )
