import numpy as np
import time
import asyncio

import pythoncom, pyHook
import winput
import pyautogui

from pathlib import Path
from collections import Counter, defaultdict

import random
from itertools import chain

from dataclasses import dataclass

vk_mapping = {
    "escape": 27,
    "up":38,
    "right":39,
    "down":40,
    "return":13,
    "z":90,
    "x":88,
    "lshift":160
}


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

button_down_dict:dict = defaultdict(lambda:False)

replay_buffer = []
key_buffer = []
last_keypress_time = 0

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
async def delay(delay_len):
    start = time.time()
    while (time.time() - start) < delay_len:
        await asyncio.sleep(0)
    await asyncio.sleep(0)

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
    print("Started replaying from txt!")
    set_state("REPLAYING_TXT")
    bps = []
    with open(replay_buffer_path/ f"{GAME_NAME}.txt", "r") as f:
        for data in f:
            vals = data[:-1].split(",")
            bps.append(vals)
    bps = np.array(bps)
    bps = np.char.replace(bps, "lshift", "shiftleft")
    key_list = list(bps)
    print(key_list)
    while key_list:
        start = time.time()
        action, value = key_list[0]
        value = value.strip()
        

        if action == "down":
            # pyautogui.keyDown(value)
            vk_key = vk_mapping[action]
            winput.press_key(vk_key)

        if action == "delay":
            while (time.time() - start) * 1000 < float(value):
                await asyncio.sleep(0)

        if action == "up":
            # pyautogui.keyUp(value)
            vk_key = vk_mapping[action]
            winput.release_key(vk_key)

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
    global last_keypress_time
    global key_buffer

    if not event.WindowName == GAME_NAME:
        print(f"Focused on the wrong screen! Please focus on {GAME_NAME}")
        return True

    AddKeyDown(event)

    if event.Key == "F12":
        print("\n\nStopped recording and started replaying from offline data.\n\n")
        set_state("START_REPLAYING")
        return True

    if event.Key == "F11":
        print("\n\nStopped recording and started sampling.\n\n")
        set_state("START_SAMPLING")
        return True

    if event.Key == "F10":
        last_keypress_time = event.Time
        if replay_buffer:
            replay_buffer.clear()
            print("The replay buffer emptied!")
        print("Back to recording!")
        key_buffer = []
        set_state("RECORDING")
        return True

    if event.Key == "F9":
        print("Saved the data in the buffer!")
        print(key_buffer)
        with open(replay_buffer_path/ f"{GAME_NAME}.txt", "w") as f:
            for action, value in key_buffer:
                f.write(f"{action}, {value}\n")
            key_buffer.clear()
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
        SESSION_START_TIME = event.Time
        set_state("START_REPLAYING_TXT")
        return True


    return True

def AddKeyUp(event) -> bool:
    global last_keypress_time
    if not event.WindowName == GAME_NAME:
        return True

    released_key = event.Key.lower()
    
    if "f10" in released_key or "f9" in released_key or "f8" in released_key:
        return True

    delay_len = event.Time - last_keypress_time

    delay_data = ("delay", delay_len)
    up_data = ("up", released_key)
    
    key_buffer.append(delay_data)
    key_buffer.append(up_data)

    # print("Time pressed down:", button_down_dict[released_key])
    # print("Time pressed up:", (event.Time, time.time()))
    # print("Time delta:", (button_down_dict[released_key][0] - event.Time, 
    #                      (button_down_dict[released_key][1] - time.time())*1000))
    # print("Time delta across:", (button_down_dict[released_key][0] - event.Time - (button_down_dict[released_key][1] - time.time())*1000))
                         
    # print()
    button_down_dict[released_key] = False

    return True

def AddKeyDown(event) -> bool:
    global last_keypress_time

    if not event.WindowName == GAME_NAME:
        return True
    pressed_key = event.Key.lower() 

    if button_down_dict[pressed_key]:
        return True
    
    button_down_dict[pressed_key] = True
    # return True

    if "f10" in pressed_key or "f9" in pressed_key or "f8" in pressed_key:
        return True

    delay_len = event.Time - last_keypress_time
    last_keypress_time = event.Time

    delay_data = ("delay", delay_len)
    down_data = ("down", pressed_key)

    key_buffer.append(delay_data)
    key_buffer.append(down_data)
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
    hm.KeyUp = AddKeyUp
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
    