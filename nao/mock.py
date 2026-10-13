"""Simulated robot with the same interface as NaoRobot, for testing the UI without hardware."""
from __future__ import annotations

import io
import math
import random
import threading
import time
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from . import sensors as S

MOCK_ANIMS = [
    "animations/Stand/Gestures/Hey_1", "animations/Stand/Gestures/Hey_6", "animations/Stand/Gestures/Yes_1",
    "animations/Stand/Gestures/No_1", "animations/Stand/Gestures/Explain_1", "animations/Stand/Gestures/Thinking_1",
    "animations/Stand/Gestures/Me_1", "animations/Stand/Gestures/You_1", "animations/Stand/Gestures/Please_1",
    "animations/Stand/Gestures/Excited_1", "animations/Stand/Gestures/Enthusiastic_4",
    "animations/Stand/Gestures/Confused_1", "animations/Stand/Gestures/Desperate_1", "animations/Stand/Gestures/Bored_1",
    "animations/Stand/Gestures/Salute_1", "animations/Stand/Gestures/ShowSky_1", "animations/Stand/Gestures/ShowFloor_1",
    "animations/Stand/Gestures/Stretch_1", "animations/Stand/Emotions/Positive/Happy_1",
    "animations/Stand/Emotions/Positive/Proud_1", "animations/Stand/Emotions/Positive/Laugh_1",
    "animations/Stand/Emotions/Negative/Sad_1", "animations/Stand/Emotions/Negative/Angry_1",
    "animations/Stand/Emotions/Negative/Fearful_1", "animations/Stand/Waiting/AirGuitar_1",
    "animations/Stand/Waiting/WipeForehead_1", "animations/Sit/Gestures/Hey_1", "animations/Sit/BodyTalk/BodyTalk_1",
]
MOCK_BEHAVIORS = ["animationMode", "dialog_demo/.", "my-study-behavior/intro", "take-picture/."]


class MockRobot:
    is_mock = True

    def __init__(self, ip: str = "mock", port: int = 9559):
        self.ip, self.port = ip, port
        self.connected = True
        self.t0 = time.time()
        self.volume = 60
        self.speed, self.pitch, self.language = 100.0, 1.0, "English"
        self.life_state = "disabled"
        self.awake = True
        self.posture = "Standing"
        self.settings = {"basic_awareness": False, "blinking": True, "listening_movement": True,
                         "speaking_movement": True, "fall_manager": True,
                         **{"breath_" + c: False for c in S.BREATH_CHAINS}}
        self.stiff = {c: 1.0 for c in S.STIFFNESS_CHAINS}
        self.head = [0.0, 0.0]
        self.joints = {j: 0.0 for j in S.JOINT_NAMES}
        self._eye_color = (255, 255, 255)
        self.led_intensity: Dict[str, float] = {}
        self.running: List[str] = []
        self.vel = (0.0, 0.0, 0.0)
        self.last_said = ""
        self.recording = False
        self._cam_cfg = (0, 1, 10)
        self.log: List[str] = []

    def _note(self, s: str):
        self.log.append(s)
        print(f"[mock] {s}", flush=True)

    def close(self): self.connected = False

    # status
    def status(self) -> Dict[str, Any]:
        return {"connected": self.connected, "ip": self.ip, "mock": True, "name": "NaoSim", "version": "2.8.7.4",
                "battery": int(75 + 10 * math.sin((time.time() - self.t0) / 30)), "charging": False,
                "posture": self.posture, "life_state": self.life_state, "volume": self.volume, "awake": self.awake,
                "language": self.language, "awareness": self.settings["basic_awareness"],
                "blinking": self.settings["blinking"], "listening_movement": self.settings["listening_movement"],
                "speaking_movement": self.settings["speaking_movement"], "breathing": self.settings["breath_Body"],
                "fall_manager": self.settings["fall_manager"], "eye_color": self._eye_color,
                "tts_speed": self.speed, "tts_pitch": self.pitch}

    # speech
    def say(self, text, animated=False): self.last_said = text; self._note(f"say({'anim' if animated else 'tts'}): {text}")
    def say_async(self, text, animated=False): self.say(text, animated)
    def stop_speech(self): self._note("stop speech")
    def set_tts(self, speed=None, pitch=None, language=None, voice=None):
        if speed is not None: self.speed = float(speed)
        if pitch is not None: self.pitch = float(pitch)
        if language: self.language = language
    def tts_info(self):
        return {"languages": ["English", "French", "Dutch", "German"], "language": self.language,
                "voices": ["naoenu", "naomnc"], "voice": "naoenu", "speed": self.speed, "pitch": self.pitch}

    # audio
    def get_volume(self): return self.volume
    def set_volume(self, v): self.volume = int(max(0, min(100, v)))
    def play_audio(self, path, volume=1.0): self._note(f"play {path}")
    def stop_audio(self): self._note("stop audio")
    def start_recording(self, path): self.recording = True; self._note(f"record -> {path}")
    def stop_recording(self): self.recording = False

    # animations / behaviors
    def run_animation(self, name): self._note(f"animation {name}")
    def list_behaviors(self):
        return {"animations": MOCK_ANIMS, "behaviors": MOCK_BEHAVIORS, "running": list(self.running)}
    def run_behavior(self, name):
        self.running.append(name)
        threading.Timer(4.0, lambda: name in self.running and self.running.remove(name)).start()
    def stop_behavior(self, name):
        if name in self.running: self.running.remove(name)
    def stop_all_behaviors(self): self.running.clear()

    # motion
    def wake_up(self): self.awake = True; self.posture = "Standing"
    def rest(self): self.awake = False; self.posture = "Crouch"
    def go_to_posture(self, name, speed=0.7):
        fam = {"Stand": "Standing", "StandInit": "Standing", "StandZero": "Standing", "Crouch": "Crouch",
               "Sit": "Sitting", "SitRelax": "Sitting", "LyingBelly": "Belly", "LyingBack": "Back"}
        self.posture = fam.get(name, name); self._note(f"posture {name} @ {speed}")
    def set_stiffness(self, chain, value): self.stiff[chain] = float(value)
    def get_stiffness(self): return dict(self.stiff)
    def move_toward(self, x, y, theta): self.vel = (x, y, theta); self._note(f"moveToward {x} {y} {theta}")
    def move_to(self, x, y, theta): self._note(f"moveTo {x} {y} {theta}")
    def stop_move(self): self.vel = (0, 0, 0); self._note("stopMove")
    def set_head(self, yaw, pitch, speed=0.2):
        if yaw is not None: self.head[0] = max(-119.5, min(119.5, yaw))
        if pitch is not None: self.head[1] = max(-38.5, min(29.5, pitch))
        self.joints["HeadYaw"], self.joints["HeadPitch"] = self.head
    def set_joint(self, name, angle, speed=0.2):
        self.joints[name] = float(angle)
        if name == "HeadYaw": self.head[0] = angle
        if name == "HeadPitch": self.head[1] = angle
    def get_joints(self):
        return {"names": S.JOINT_NAMES, "angles": [round(self.joints[j], 1) for j in S.JOINT_NAMES],
                "limits": S.JOINT_LIMITS_DEG}
    def open_hand(self, hand, open_): self.joints[hand] = 57.0 if open_ else 0.0
    def set_fall_manager(self, enabled): self.settings["fall_manager"] = bool(enabled)

    # leds
    def set_led_color(self, group, r, g, b, duration=0.3):
        if group in ("FaceLeds", "AllLeds"): self._eye_color = (int(r), int(g), int(b))
        self._note(f"led {group} rgb({r},{g},{b})")
    def set_led_intensity(self, group, value): self.led_intensity[group] = float(value)
    def leds_off(self, group): self._note(f"led off {group}")
    def leds_on(self, group): self._note(f"led on {group}")
    def leds_reset(self, group): self._note(f"led reset {group}")
    def led_animation(self, kind, duration=3.0): self._note(f"led anim {kind} {duration}s")

    # life
    def set_life_state(self, state): self.life_state = state
    def set_setting(self, name, enabled):
        if name not in self.settings: raise ValueError(name)
        self.settings[name] = bool(enabled)
    def set_engagement(self, mode): self._note(f"engagement {mode}")
    def set_tracking_mode(self, mode): self._note(f"tracking {mode}")

    # sensors
    def sensors(self):
        t = time.time() - self.t0
        out: Dict[str, Any] = {k: 0.0 for k in S.ALL_KEYS}
        out["sonar_left"] = round(1.0 + 0.6 * math.sin(t / 2), 2)
        out["sonar_right"] = round(1.2 + 0.5 * math.cos(t / 3), 2)
        out["angle_x"] = round(0.02 * math.sin(t), 3); out["angle_y"] = round(0.03 * math.cos(t / 1.5), 3)
        out["acc_x"], out["acc_y"], out["acc_z"] = round(0.1 * math.sin(t), 2), round(0.1 * math.cos(t), 2), -9.8
        out["gyro_x"], out["gyro_y"], out["gyro_z"] = 0.01, -0.02, 0.0
        out["lfoot_weight"], out["rfoot_weight"] = round(2.6 + 0.2 * math.sin(t), 2), round(2.5 - 0.2 * math.sin(t), 2)
        out["battery_charge"] = 0.78; out["battery_current"] = -0.6; out["battery_temp"] = 31.0
        out["head_front"] = 1.0 if int(t) % 10 == 3 else 0.0
        out["rhand_back"] = 1.0 if int(t) % 7 == 1 else 0.0
        for j in S.JOINT_NAMES:
            out["temp_" + j] = round(34 + 8 * abs(math.sin(t / 40 + hash(j) % 7)), 1)
        out["head_angles"] = list(self.head)
        out["t"] = time.time()
        return out
    def memory_get(self, key): return f"<mock value for {key}>"

    # camera
    def camera_config(self, camera, resolution, fps): self._cam_cfg = (camera, resolution, fps)
    def camera_unsubscribe(self): pass
    def camera_frame(self) -> Optional[bytes]:
        cam, res, fps = self._cam_cfg
        w, h = {0: (160, 120), 1: (320, 240), 2: (640, 480), 3: (1280, 960)}.get(res, (320, 240))
        t = time.time() - self.t0
        img = Image.new("RGB", (w, h), (18 + int(20 * (cam)), 24, 38))
        d = ImageDraw.Draw(img)
        cx, cy = w / 2 + 0.3 * w * math.sin(t), h / 2 + 0.2 * h * math.cos(t / 1.3)
        r = w / 8
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 160, 255) if cam == 0 else (255, 150, 0))
        d.text((8, 8), f"MOCK {'top' if cam == 0 else 'bottom'} cam  {w}x{h} @{fps}fps  t={t:5.1f}s", fill=(230, 230, 230))
        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=80)
        time.sleep(max(0.0, 1.0 / max(1, fps)))
        return buf.getvalue()

    def system(self, action): self._note(f"system {action}")
