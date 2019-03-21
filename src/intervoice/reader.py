import functools
import os
import itertools


import trio


BUFSIZE = 2 ** 14
counter = itertools.count()
_RECEIVE_SIZE = 4096  # pretty arbitrary


class TerminatedFrameReceiver:
    """Parse frames out of a Trio stream, where each frame is terminated by a
    fixed byte sequence.

    For example, you can parse newline-terminated lines by setting the
    terminator to b"\n".

    This uses some tricks to protect against denial of service attacks:

    - It puts a limit on the maximum frame size, to avoid memory overflow; you
    might want to adjust the limit for your situation.

    - It uses some algorithmic trickiness to avoid "slow loris" attacks. All
      algorithms are amortized O(n) in the length of the input.

    """

    def __init__(self, stream, terminator, max_frame_length=16384):
        self.stream = stream
        self.terminator = terminator
        self.max_frame_length = max_frame_length
        self._buf = bytearray()
        self._next_find_idx = 0

    async def receive(self):
        while True:
            terminator_idx = self._buf.find(self.terminator, self._next_find_idx)
            if terminator_idx < 0:
                # no terminator found
                if len(self._buf) > self.max_frame_length:
                    raise ValueError("frame too long")
                # next time, start the search where this one left off
                self._next_find_idx = max(0, len(self._buf) - len(self.terminator) + 1)
                # add some more data, then loop around
                more_data = await self.stream.receive_some(_RECEIVE_SIZE)
                if more_data == b"":
                    if self._buf:
                        raise ValueError("incomplete frame")
                    raise trio.EndOfChannel
                self._buf += more_data
            else:
                # terminator found in buf, so extract the frame
                frame = self._buf[:terminator_idx]
                # Update the buffer in place, to take advantage of bytearray's
                # optimized delete-from-beginning feature.
                del self._buf[: terminator_idx + len(self.terminator)]
                # next time, start the search from the beginning
                self._next_find_idx = 0
                return frame

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.receive()
        except trio.EndOfChannel:
            raise StopAsyncIteration


async def open_unix_domain_listeners(path, *, permissions=None):
    sock = trio.socket.socket(trio.socket.AF_UNIX, trio.socket.SOCK_STREAM)
    try:
        os.unlink(path)
    except OSError:
        pass
    await sock.bind(path)
    if permissions is not None:
        os.fchmod(sock.fileno(), permissions)
    sock.listen(100)
    return [trio.SocketListener(sock)]


async def serve_unix_domain(
    handler,
    path,
    *,
    permissions=None,
    handler_nursery=None,
    task_status=trio.TASK_STATUS_IGNORED,
):
    listeners = await open_unix_domain_listeners(path, permissions=permissions)
    await trio.serve_listeners(
        handler, listeners, handler_nursery=handler_nursery, task_status=task_status
    )


numbers = {
    word: integer
    for integer, word in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
        ]
    )
}


async def handle_stream(handle_message, stream):

    receiver = TerminatedFrameReceiver(stream, b"\n")
    async with trio.open_nursery() as nursery:
        async for message in receiver:
            text = message.decode()
            nursery.start_soon(handle_message, text)


async def async_main(path):
    await serve_unix_domain(handler=handle_stream, path=path)


def main(path):
    trio.run(functools.partial(async_main, path=path))
