import functools
import sys


from typing import List
from typing import Callable
from typing import Coroutine
from typing import Awaitable

from intervoice import utils
from intervoice import platforms

import trio
import pyautogui
import pynput
import pynput.keyboard

registry = utils.Registry()

registry.define(
    {
        "?any_text": r"/\w.+/",
        "key": utils.regex("|".join(utils.pronunciation_to_value().keys())),
        "chord": 'key ("+" chord)*',
    }
)


def type_chord(chord):
    keyboard = pynput.keyboard.Controller()
    modifiers = [getattr(pynput.keyboard.Key, mod.name) for mod in chord.modifiers]
    with keyboard.pressed(*modifiers):

        keyboard.press(pynput.keyboard.Key[chord.name])
        keyboard.release(pynput.keyboard.Key[chord.name])


async def press(chord: str):
    if isinstance(chord, str):
        await trio.run_sync_in_worker_thread(
            functools.partial(pyautogui.typewrite, [chord])
        )
        return

    await trio.run_sync_in_worker_thread(type_chord, chord)


async def write(message: str):
    await trio.run_sync_in_worker_thread(
        functools.partial(pyautogui.typewrite, message)
    )


@registry.register('"alert" any_text')
async def _alert(text):
    await trio.run_sync_in_worker_thread(functools.partial(pyautogui.alert, text))


async def speak(message):
    await utils.run_subprocess(["say", message])


@registry.register('"say" chord')
async def _say(message: List[str]):
    [chord_string] = message
    chord_value = utils.pronunciation_to_value()[chord_string]
    await press(chord_value)


@registry.register('"switch" chord')
async def _switch(message: List[str]):
    [chord_string] = message
    chord_value = utils.pronunciation_to_value()[chord_string]
    await press(f"super+{chord_value}")


key: Callable = utils.async_runner(press)


registry.pattern_to_function['"monitor"'] = key("M")
registry.pattern_to_function['"mouse"'] = key("O")


@registry.register('"div0"')
async def _div0(*args):
    1 / 0


wrapper = utils.Wrapper(registry)
