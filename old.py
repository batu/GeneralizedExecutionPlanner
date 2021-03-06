import numpy as np
import time
import asyncio

import pythoncom, pyHook
import pyautogui

from pathlib import Path
from collections import Counter, defaultdict

import random
from itertools import chain

key_press_path = Path("ButtonPresses")
replay_buffer_path = Path("ReplayBuffers")

# If when presed a certain key start sampling from that
kp_path = Path("ButtonPresses")

# How many times has it been pressed?
kp_counter = Counter()

# What is the current hold time for the key.
kp_curr_hold_time:dict = defaultdict(lambda: 0)

# All the hold times for keys.
kp_hold_times:dict = defaultdict(lambda: [])

replay_buffer = []

def set_state(new_state:str)->None:
    """
        Possible States:
            [RECORDING, START_REPLAY, REPLAYING, SAMPLE]
    """
    global STATE
    possible_states = ["RECORDING", "START_REPLAYING", "REPLAYING", "START_REPLAYING_TXT", "REPLAYING_TXT", "START_SAMPLING", "SAMPLING"]
    assert new_state in possible_states
    STATE = new_state


########
async def hold_key(key, hold_time, press_time=0):
    start = time.time()
    pyautogui.keyDown(key)
    print(f"Pressed {key}, at time {time_in_session()} for {hold_time}")
    while (time.time() - start) < float(hold_time):
        await asyncio.sleep(0)
    pyautogui.keyUp(key)
    await asyncio.sleep(0)


async def play_from_recording():
    global SESSION_START_TIME
    print("Started replaying!")
    set_state("REPLAYING")
    bps = np.load(key_press_path/f"{GAME_NAME}_presses.npy")
    bps = np.char.replace(bps, "lshift", "shiftleft")
    drift_offset = 100
    key_list = list(bps)
    SESSION_START_TIME = time.time()
    while key_list:
        key, press_time, press_len = key_list[0]
        if (time_in_session()) * 1000 >= int(press_time) - drift_offset:
            loop.create_task(hold_key(key, press_len, press_time))
            key_list = key_list[1:]
        await asyncio.sleep(0)
    set_state("RECORDING")
    print("\n\nDone replaying, switching to recording.\nA human is playing now.\n\n")
    await asyncio.sleep(0)

async def play_from_txt():
    global SESSION_START_TIME
    print("Started replaying from txt!")
    set_state("REPLAYING_TXT")
    bps = []
    with open(replay_buffer_path/ f"{GAME_NAME}.txt", "r") as f:
        for data in f:
            vals = data[:-1].split(",")
            vals = (vals[0], float(vals[1]), float(vals[2]))
            bps.append(vals)
    bps = np.array(bps)
    bps = np.char.replace(bps, "lshift", "shiftleft")
    drift_offset = 100
    key_list = list(bps)
    print(key_list)
    SESSION_START_TIME = time.time()
    while key_list:
        key, press_time, press_len = key_list[0]
        if (time_in_session()) >= float(press_time):
            loop.create_task(hold_key(key, press_len, press_time))
            key_list = key_list[1:]
        await asyncio.sleep(0)
    set_state("RECORDING")
    print("\n\nDone replaying, switching to recording.\nA human is playing now.\n\n")
    await asyncio.sleep(0)

########

def time_in_session()->float:
    return time.time() - SESSION_START_TIME

def KeyDown(event) -> bool:
    global STATE
    global SESSION_START_TIME

    if not event.WindowName == GAME_NAME:
        print(f"Focused on the wrong screen! Please focus on {GAME_NAME}")
        return True

    if event.Key == "F12":
        print("\n\nStopped recording and started replaying from offline data.\n\n")
        set_state("START_REPLAYING")
        return True

    if event.Key == "F11":
        print("\n\nStopped recording and started sampling.\n\n")
        set_state("START_SAMPLING")
        return True

    if event.Key == "F10":
        SESSION_START_TIME = time.time()
        if replay_buffer:
            replay_buffer.clear()
            print("The replay buffer emptied!")
        print("Back to recording!")
        set_state("RECORDING")
        return True

    if event.Key == "F9":
        print("Saved the data in the buffer!")
        replay_buffer.sort(key=lambda x:x[1])
        with open(replay_buffer_path/ f"{GAME_NAME}.txt", "w") as f:
            for key, time_at_down, down_length in replay_buffer:
                f.write(f"{key}, {time_at_down}, {down_length}\n")
            replay_buffer.clear()
        return True

    # If the reset file is there, do that.
    # if event.Key == "F8":
    #     print("Saved the data in the buffer!")
    #     replay_buffer.sort(key=lambda x:x[1])
    #     with open(replay_buffer_path/ f"{GAME_NAME}_reset.txt", "w") as f:
    #         for key, time_at_down, down_length in replay_buffer:
    #             f.write(f"{key}, {time_at_down}, {down_length}\n")
    #         replay_buffer.clear()
    #     return True

    if event.Key == "F8":
        print("Replay from TXT!")
        set_state("START_REPLAYING_TXT")
        return True

    pressed_key = event.Key.lower() 

    HandleKeyDown(pressed_key)

    return True

def HandleKeyDown(pressed_key):
    if not kp_curr_hold_time[pressed_key]:
        kp_counter[pressed_key] += 1
        kp_curr_hold_time[pressed_key] = time_in_session()

def RecordKeyPress(event) -> bool:

    if not event.WindowName == GAME_NAME:
        return True

    released_key = event.Key.lower() 

    if kp_curr_hold_time[released_key]:
        hold_down_time = time_in_session() - kp_curr_hold_time[released_key]
        kp_hold_times[released_key].append(hold_down_time)

        time_at_down = kp_curr_hold_time[released_key]

        replay_point = (released_key, time_at_down, hold_down_time)
        replay_buffer.append(replay_point)

        kp_curr_hold_time[released_key] = 0

    return True


async def sample_actions():
    set_state("SAMPLING")
    print("Started sampling from", kp_counter)

    unrolled_list = list(kp_counter.elements())
    # flatten the values
    all_wait_times = sorted(set(chain(*kp_hold_times.values())))

    while STATE == "SAMPLING":
        selected_key = random.choice(unrolled_list)
        selected_duration = random.choice(kp_hold_times[selected_key])
        loop.create_task(hold_key(selected_key, selected_duration*1000))
        hold_start = time.time()
        wait_time = random.choice(all_wait_times)
        while time.time() - hold_start < wait_time / 2:
            await asyncio.sleep(0)
        await asyncio.sleep(0)
    pass

async def main():
    global SESSION_START_TIME

    hm = pyHook.HookManager()
    hm.KeyDown = KeyDown
    hm.KeyUp = RecordKeyPress
    hm.HookKeyboard()

    while True:

        if STATE == "RECORDING":
            pythoncom.PumpWaitingMessages()
            await asyncio.sleep(0)

        if STATE == "START_REPLAYING":
            loop.create_task(play_from_recording())
            await asyncio.sleep(0)

        if STATE == "START_SAMPLING":
            loop.create_task(sample_actions())
            await asyncio.sleep(0)

        if STATE == "START_REPLAYING_TXT":
            loop.create_task(play_from_txt())
            await asyncio.sleep(0)
        
        await asyncio.sleep(0)
    
    await asyncio.sleep(5)

import sys
if __name__ == "__main__":
    STATE = "RECORDING"
    GAME_NAME = "mixandjam-celestemovement"
    GAME_NAME = sys.argv[1]
    # GAME_NAME = "Cuphead"
    SESSION_START_TIME = time.time()

    print("Started recording key presses.\nA human is playing now.")
    try:
        start_time = 0
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except Exception as e:
        print(e)
    finally:
        loop.close()
    print("Fiiniiish.")
    