import asyncio
import struct

import numpy as np
import pytest


def test_handler_initializes_expected_audio_contract_and_bounded_queues(agent):
    handler = agent.GeminiHandler()

    assert handler.expected_layout == "mono"
    assert handler.input_sample_rate == 16000
    assert handler.output_sample_rate == 24000
    assert handler.input_queue.maxsize == agent.AUDIO_QUEUE_MAX_SIZE
    assert handler.output_queue.maxsize == agent.AUDIO_QUEUE_MAX_SIZE
    assert not handler.quit.is_set()


def test_handler_copy_has_independent_state(agent):
    original = agent.GeminiHandler(output_sample_rate=24000)
    copied = original.copy()

    assert copied is not original
    assert copied.input_queue is not original.input_queue
    assert copied.output_queue is not original.output_queue
    assert copied.quit is not original.quit
    assert copied.args_set is not original.args_set
    assert copied.input_sample_rate == original.input_sample_rate
    assert copied.output_sample_rate == original.output_sample_rate


def test_handler_receive_enqueues_pcm_bytes_from_numpy_frame(agent):
    handler = agent.GeminiHandler()
    samples = np.array([[0, 1, -1, 1024, -1024]], dtype=np.int16)

    asyncio.run(handler.receive((16000, samples)))

    assert handler.input_queue.get_nowait() == struct.pack(
        "<5h", 0, 1, -1, 1024, -1024
    )


def test_handler_shutdown_sets_events_and_drains_queues(agent):
    handler = agent.GeminiHandler()
    handler.input_queue.put_nowait(b"input")
    handler.output_queue.put_nowait((24000, np.array([1], dtype=np.int16)))

    handler.shutdown()

    assert handler.quit.is_set()
    assert handler.args_set.is_set()
    assert handler.input_queue.empty()
    assert handler.output_queue.empty()


def test_handler_start_up_without_api_key_never_creates_client(
    agent, monkeypatch
):
    handler = agent.GeminiHandler()
    handler.phone_mode = True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def forbidden_client(*args, **kwargs):
        pytest.fail("genai.Client must not be created without GEMINI_API_KEY")

    monkeypatch.setattr(agent.genai, "Client", forbidden_client)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is required"):
        asyncio.run(handler.start_up())
