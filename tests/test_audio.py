import asyncio
import struct

import numpy as np
import pytest


@pytest.mark.parametrize(
    ("array", "values"),
    [
        (np.array([0, 1, -1, 32767, -32768], dtype=np.int16), (0, 1, -1, 32767, -32768)),
        (np.array([[12, -34], [56, -78]], dtype=np.int32), (12, -34, 56, -78)),
        (np.array([258, -258], dtype=">i2"), (258, -258)),
    ],
)
def test_pcm_audio_to_bytes_returns_little_endian_pcm16(agent, array, values):
    expected = struct.pack(f"<{len(values)}h", *values)

    assert agent.pcm_audio_to_bytes(array) == expected


def test_put_bounded_preserves_fifo_order_when_space_is_available(agent):
    queue = asyncio.Queue(maxsize=3)

    agent.put_bounded(queue, "first")
    agent.put_bounded(queue, "second")

    assert queue.qsize() == 2
    assert queue.get_nowait() == "first"
    assert queue.get_nowait() == "second"


def test_put_bounded_drops_oldest_item_when_queue_is_full(agent):
    queue = asyncio.Queue(maxsize=2)
    queue.put_nowait("oldest")
    queue.put_nowait("middle")

    agent.put_bounded(queue, "newest")

    assert queue.qsize() == 2
    assert queue.get_nowait() == "middle"
    assert queue.get_nowait() == "newest"
