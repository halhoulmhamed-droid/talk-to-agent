import asyncio
import base64
import json
import os
import io
import uvicorn
from pathlib import Path
import ssl
from typing import AsyncGenerator, Literal
import configparser
from scipy.io.wavfile import write
from enum import Enum

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastrtc import (
    AsyncStreamHandler,
    Stream,
    get_cloudflare_turn_credentials_async,
    wait_for_item,
    audio_to_bytes,
)
from google import genai
from google.genai.types import (
    LiveConnectConfig,
    PrebuiltVoiceConfig,
    SpeechConfig,
    VoiceConfig,
    AudioTranscriptionConfig,
    ThinkingConfig,
    ProactivityConfig,
    RealtimeInputConfig,
    AutomaticActivityDetection,
    StartSensitivity,
    EndSensitivity,
    Content,
    Part,
    Blob,
)
from gradio.utils import get_space
from pydantic import BaseModel

current_dir = Path(__file__).parent.parent
config_prompt = configparser.ConfigParser()
config_prompt.read("config.ini")
prompt_file = config_prompt["PROMPT"]["PROMPT_INTERVIEWER_A"]
with open(prompt_file, "r") as file:
    prompt = " ".join(line.rstrip() for line in file)

load_dotenv()


class Transcript(Enum):
    AGENT = "agent"
    CANDIDATE = "candidate"


def encode_audio(data: np.ndarray) -> str:
    """Encode Audio data to send to the server"""
    return base64.b64encode(data.tobytes()).decode("UTF-8")


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
        self.input_queue: asyncio.Queue = asyncio.Queue()
        self.output_queue: asyncio.Queue = asyncio.Queue()
        self.quit: asyncio.Event = asyncio.Event()
        self.audio_agent: list[bytes] = list()
        self.audio_candidate: list[bytes] = list()

    def copy(self) -> "GeminiHandler":
        return GeminiHandler(
            expected_layout="mono",
            output_sample_rate=self.output_sample_rate,
        )

    async def agent_stream(
        self, session: genai.live.AsyncSession, stream: AsyncGenerator
    ):
        async for audio in session.start_stream(
            stream=self.stream(), mime_type="audio/pcm"
        ):
            if audio.data:
                array = np.frombuffer(audio.data, dtype=np.int16)
                self.output_queue.put_nowait((self.output_sample_rate, array))


    async def echo(self, session: genai.live.AsyncSession, kind: str):
        transcript = Transcript(kind)
        match transcript:
            case Transcript.AGENT:
                async for response in session.receive():
                    if response.server_content.output_transcription:
                        print(
                            "[AGENT]:",
                            response.server_content.output_transcription.text,
                        )
            case Transcript.CANDIDATE:
                pass

    async def start_up(self):
        if not self.phone_mode:
            await self.wait_for_args()
            voice_name = self.latest_args[1:]
        else:
            voice_name = "Alnilam"

        client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY"),
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
            output_audio_transcription=AudioTranscriptionConfig(),
            input_audio_transcription=AudioTranscriptionConfig(),
            enable_affective_dialog=False,
            proactivity=ProactivityConfig(proactive_audio=False),
            thinking_config=ThinkingConfig(
                include_thoughts=True,
            ),
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
            await self.agent_stream(session=session, stream=self.stream())

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
        audio_message = encode_audio(array)
        self.input_queue.put_nowait(audio_message)

    async def emit(self) -> tuple[int, np.ndarray] | None:
        return await wait_for_item(self.output_queue)

    def shutdown(self) -> None:
        self.quit.set()


stream = Stream(
    modality="audio",
    mode="send-receive",
    handler=GeminiHandler(),
    rtc_configuration=get_cloudflare_turn_credentials_async if get_space() else None,
    concurrency_limit=5 if get_space() else 5,
    time_limit=90 if get_space() else None,
)


class InputData(BaseModel):
    webrtc_id: str
    voice_name: str


app = FastAPI()

app.mount("/static", StaticFiles(directory=current_dir / "static"), name="static_file")

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
app_pem = os.getenv("APP_PEM")
app_key = os.getenv("APP_KEY")
ssl_context.load_cert_chain(app_pem, app_key)

stream.mount(app)


@app.post("/input_hook")
async def _(body: InputData):
    stream.set_input(body.webrtc_id, body.voice_name)
    return {"status": "ok"}


@app.get("/")
async def index():
    rtc_config = (
        await get_cloudflare_turn_credentials_async()
        if get_space()
        else os.getenv("RTC_CONFIGURATION")
    )
    html_content = (current_dir / "template/index.html").read_text()
    html_content = html_content.replace("__RTC_CONFIGURATION__", json.dumps(rtc_config))
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="192.168.1.11",
        port=7860,
        ssl_keyfile=app_key,
        ssl_certfile=app_pem,
    )
