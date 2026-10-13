"""Real NAO v6 backend built on the `qi` Python 3 bindings (NAOqi 2.8 / 2.9)."""
from __future__ import annotations

import io
import math
import threading
import time
from typing import Any, Dict, List, Optional

from PIL import Image

from . import sensors as S

try:
    import qi  # type: ignore
except ImportError:  # pragma: no cover - mock mode still works
    qi = None


def _log(msg: str) -> None:
    print(f"[nao] {msg}", flush=True)


class NaoRobot:
    """Thin, thread-safe wrapper around the NAOqi services used by the interface."""

    is_mock = False

    def __init__(self, ip: str, port: int = 9559):
        if qi is None:
            raise RuntimeError("The `qi` package is not installed (pip install qi).")
        self.ip, self.port = ip, port
        self.session = qi.Session()
        self.session.connect(f"tcp://{ip}:{port}")
        self._svc: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._cam_sub: Optional[str] = None
        self._cam_lock = threading.Lock()
        self._cam_cfg = (0, 1, 10)  # camera, resolution, fps
        self._eye_color = (255, 255, 255)
        self.connected = True

    # ------------------------------------------------------------ helpers
    def svc(self, name: str):
        if name not in self._svc:
            self._svc[name] = self.session.service(name)
        return self._svc[name]

    def _try(self, name: str):
        try:
            return self.svc(name)
        except Exception as e:  # service missing on this robot
            _log(f"service {name} unavailable: {e}")
            return None

    def close(self) -> None:
        self.connected = False
        try:
            self.camera_unsubscribe()
        except Exception:
            pass
        try:
            self.session.close()
        except Exception:
            pass

    # ------------------------------------------------------------ status
    def status(self) -> Dict[str, Any]:
        st: Dict[str, Any] = {"connected": self.connected, "ip": self.ip, "mock": False}
        def get(fn, default=None):
            try:
                return fn()
            except Exception:
                return default
        st["name"] = get(lambda: self.svc("ALSystem").robotName(), "NAO")
        st["version"] = get(lambda: self.svc("ALSystem").systemVersion(), "?")
        st["battery"] = get(lambda: self.svc("ALBattery").getBatteryCharge(), None)
        st["charging"] = get(lambda: self.svc("ALMemory").getData("BatteryChargingFlagChanged") == 1, None)
        st["posture"] = get(lambda: self.svc("ALRobotPosture").getPostureFamily(), "?")
        st["life_state"] = get(lambda: self.svc("ALAutonomousLife").getState(), "?")
        st["volume"] = get(lambda: self.svc("ALAudioDevice").getOutputVolume(), None)
        st["awake"] = get(lambda: self.svc("ALMotion").robotIsWakeUp(), None)
        st["language"] = get(lambda: self.svc("ALTextToSpeech").getLanguage(), "?")
        st["awareness"] = get(lambda: self.svc("ALBasicAwareness").isEnabled(), None)
        st["blinking"] = get(lambda: self.svc("ALAutonomousBlinking").isEnabled(), None)
        st["listening_movement"] = get(lambda: self.svc("ALListeningMovement").isEnabled(), None)
        st["speaking_movement"] = get(lambda: self.svc("ALSpeakingMovement").isEnabled(), None)
        st["breathing"] = get(lambda: self.svc("ALMotion").getBreathEnabled("Body"), None)
        st["fall_manager"] = get(lambda: self.svc("ALMotion").getFallManagerEnabled(), None)
        st["eye_color"] = self._eye_color
        st["tts_speed"] = get(lambda: self.svc("ALTextToSpeech").getParameter("speed"), None)
        st["tts_pitch"] = get(lambda: self.svc("ALTextToSpeech").getParameter("pitchShift"), None)
        return st

    # ------------------------------------------------------------ speech
    def say(self, text: str, animated: bool = False) -> None:
        if animated:
            self.svc("ALAnimatedSpeech").say(text, {"bodyLanguageMode": "contextual"})
        else:
            self.svc("ALTextToSpeech").say(text)

    def say_async(self, text: str, animated: bool = False) -> None:
        threading.Thread(target=self._safe, args=(self.say, text, animated), daemon=True).start()

    def _safe(self, fn, *a):
        try:
            fn(*a)
        except Exception as e:
            _log(f"{fn.__name__} failed: {e}")

    def stop_speech(self) -> None:
        self.svc("ALTextToSpeech").stopAll()

    def set_tts(self, speed: Optional[float] = None, pitch: Optional[float] = None,
                language: Optional[str] = None, voice: Optional[str] = None) -> None:
        tts = self.svc("ALTextToSpeech")
        if language:
            tts.setLanguage(language)
        if voice:
            tts.setVoice(voice)
        if speed is not None:
            tts.setParameter("speed", float(speed))
        if pitch is not None:
            tts.setParameter("pitchShift", float(pitch))

    def tts_info(self) -> Dict[str, Any]:
        tts = self.svc("ALTextToSpeech")
        return {
            "languages": tts.getAvailableLanguages(),
            "language": tts.getLanguage(),
            "voices": tts.getAvailableVoices(),
            "voice": tts.getVoice(),
            "speed": tts.getParameter("speed"),
            "pitch": tts.getParameter("pitchShift"),
        }

    # ------------------------------------------------------------ audio
    def get_volume(self) -> int:
        return int(self.svc("ALAudioDevice").getOutputVolume())

    def set_volume(self, value: int) -> None:
        self.svc("ALAudioDevice").setOutputVolume(int(max(0, min(100, value))))

    def play_audio(self, path: str, volume: float = 1.0) -> None:
        threading.Thread(target=self._safe, args=(self.svc("ALAudioPlayer").playFile, path, float(volume), 0.0),
                         daemon=True).start()

    def stop_audio(self) -> None:
        self.svc("ALAudioPlayer").stopAll()

    def start_recording(self, path: str) -> None:
        self.svc("ALAudioRecorder").startMicrophonesRecording(path, "wav", 16000, [0, 0, 1, 0])

    def stop_recording(self) -> None:
        self.svc("ALAudioRecorder").stopMicrophonesRecording()

    # ------------------------------------------------------------ animations / behaviors
    def run_animation(self, name: str) -> None:
        threading.Thread(target=self._safe, args=(self.svc("ALAnimationPlayer").run, name), daemon=True).start()

    def list_behaviors(self) -> Dict[str, List[str]]:
        bm = self.svc("ALBehaviorManager")
        installed = sorted(bm.getInstalledBehaviors())
        running = bm.getRunningBehaviors()
        return {
            "animations": [b for b in installed if b.startswith("animations/")],
            "behaviors": [b for b in installed if not b.startswith("animations/")],
            "running": running,
        }

    def run_behavior(self, name: str) -> None:
        threading.Thread(target=self._safe, args=(self.svc("ALBehaviorManager").runBehavior, name), daemon=True).start()

    def stop_behavior(self, name: str) -> None:
        self.svc("ALBehaviorManager").stopBehavior(name)

    def stop_all_behaviors(self) -> None:
        self.svc("ALBehaviorManager").stopAllBehaviors()

    # ------------------------------------------------------------ motion
    def wake_up(self) -> None:
        self.svc("ALMotion").wakeUp()

    def rest(self) -> None:
        self.svc("ALMotion").rest()

    def go_to_posture(self, name: str, speed: float = 0.7) -> None:
        threading.Thread(target=self._safe, args=(self.svc("ALRobotPosture").goToPosture, name, float(speed)),
                         daemon=True).start()

    def set_stiffness(self, chain: str, value: float) -> None:
        self.svc("ALMotion").setStiffnesses(chain, float(value))

    def get_stiffness(self) -> Dict[str, float]:
        m = self.svc("ALMotion")
        out = {}
        for c in S.STIFFNESS_CHAINS:
            try:
                vals = m.getStiffnesses(c)
                out[c] = round(sum(vals) / len(vals), 2) if vals else 0.0
            except Exception:
                out[c] = None
        return out

    def move_toward(self, x: float, y: float, theta: float) -> None:
        self.svc("ALMotion").moveToward(float(x), float(y), float(theta))

    def move_to(self, x: float, y: float, theta: float) -> None:
        threading.Thread(target=self._safe, args=(self.svc("ALMotion").moveTo, float(x), float(y), float(theta)),
                         daemon=True).start()

    def stop_move(self) -> None:
        m = self.svc("ALMotion")
        m.stopMove()
        try:
            m.killMove()
        except Exception:
            pass

    def set_head(self, yaw_deg: Optional[float], pitch_deg: Optional[float], speed: float = 0.2) -> None:
        m = self.svc("ALMotion")
        names, angles = [], []
        if yaw_deg is not None:
            names.append("HeadYaw"); angles.append(math.radians(yaw_deg))
        if pitch_deg is not None:
            names.append("HeadPitch"); angles.append(math.radians(pitch_deg))
        if names:
            m.setStiffnesses("Head", 1.0)
            m.setAngles(names, angles, float(speed))

    def set_joint(self, name: str, angle_deg: float, speed: float = 0.2) -> None:
        self.svc("ALMotion").setAngles([name], [math.radians(angle_deg)], float(speed))

    def get_joints(self) -> Dict[str, Any]:
        m = self.svc("ALMotion")
        angles = m.getAngles(S.JOINT_NAMES, True)
        return {
            "names": S.JOINT_NAMES,
            "angles": [round(math.degrees(a), 1) for a in angles],
            "limits": S.JOINT_LIMITS_DEG,
        }

    def open_hand(self, hand: str, open_: bool) -> None:
        m = self.svc("ALMotion")
        (m.openHand if open_ else m.closeHand)(hand)

    def set_fall_manager(self, enabled: bool) -> None:
        self.svc("ALMotion").setFallManagerEnabled(bool(enabled))

    # ------------------------------------------------------------ LEDs
    def set_led_color(self, group: str, r: int, g: int, b: int, duration: float = 0.3) -> None:
        self.svc("ALLeds").fadeRGB(group, int(r) / 255.0, int(g) / 255.0, int(b) / 255.0, float(duration))
        if group in ("FaceLeds", "AllLeds"):
            self._eye_color = (int(r), int(g), int(b))

    def set_led_intensity(self, group: str, value: float) -> None:
        self.svc("ALLeds").setIntensity(group, float(value))

    def leds_off(self, group: str) -> None:
        self.svc("ALLeds").off(group)

    def leds_on(self, group: str) -> None:
        self.svc("ALLeds").on(group)

    def leds_reset(self, group: str) -> None:
        self.svc("ALLeds").reset(group)

    def led_animation(self, kind: str, duration: float = 3.0) -> None:
        leds = self.svc("ALLeds")
        fn = {"rasta": leds.rasta, "random": leds.randomEyes, "rotate": None}.get(kind)
        r, g, b = self._eye_color

        def run():
            try:
                if kind == "rotate":
                    leds.rotateEyes(0x00FFFFFF & ((r << 16) | (g << 8) | b), 1.0, float(duration))
                elif fn:
                    fn(float(duration))
            except Exception as e:
                _log(f"led anim failed: {e}")
            try:
                leds.fadeRGB("FaceLeds", r / 255.0, g / 255.0, b / 255.0, 0.3)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ autonomous life
    def set_life_state(self, state: str) -> None:
        self.svc("ALAutonomousLife").setState(state)

    def set_setting(self, name: str, enabled: bool) -> None:
        enabled = bool(enabled)
        if name == "basic_awareness":
            self.svc("ALBasicAwareness").setEnabled(enabled)
        elif name == "blinking":
            self.svc("ALAutonomousBlinking").setEnabled(enabled)
        elif name == "listening_movement":
            self.svc("ALListeningMovement").setEnabled(enabled)
        elif name == "speaking_movement":
            self.svc("ALSpeakingMovement").setEnabled(enabled)
        elif name == "fall_manager":
            self.set_fall_manager(enabled)
        elif name.startswith("breath_"):
            self.svc("ALMotion").setBreathEnabled(name.split("_", 1)[1], enabled)
        else:
            raise ValueError(f"unknown setting {name}")

    def set_engagement(self, mode: str) -> None:
        self.svc("ALBasicAwareness").setEngagementMode(mode)

    def set_tracking_mode(self, mode: str) -> None:
        self.svc("ALBasicAwareness").setTrackingMode(mode)

    # ------------------------------------------------------------ sensors
    def sensors(self) -> Dict[str, Any]:
        mem = self.svc("ALMemory")
        keys = list(S.ALL_KEYS.keys())
        try:
            vals = mem.getListData([S.ALL_KEYS[k] for k in keys])
        except Exception:
            vals = []
            for k in keys:
                try:
                    vals.append(mem.getData(S.ALL_KEYS[k]))
                except Exception:
                    vals.append(None)
        out = {k: v for k, v in zip(keys, vals)}
        try:
            out["head_angles"] = [round(math.degrees(a), 1) for a in
                                  self.svc("ALMotion").getAngles(["HeadYaw", "HeadPitch"], True)]
        except Exception:
            out["head_angles"] = None
        out["t"] = time.time()
        return out

    def memory_get(self, key: str) -> Any:
        return self.svc("ALMemory").getData(key)

    # ------------------------------------------------------------ camera
    def camera_config(self, camera: int, resolution: int, fps: int) -> None:
        with self._cam_lock:
            self._cam_cfg = (int(camera), int(resolution), int(fps))
            self._camera_unsubscribe_locked()

    def _camera_subscribe_locked(self) -> None:
        cam, res, fps = self._cam_cfg
        vd = self.svc("ALVideoDevice")
        self._cam_sub = vd.subscribeCamera("naowoz", cam, res, 11, fps)  # 11 = RGB

    def _camera_unsubscribe_locked(self) -> None:
        if self._cam_sub:
            try:
                self.svc("ALVideoDevice").unsubscribe(self._cam_sub)
            except Exception:
                pass
            self._cam_sub = None

    def camera_unsubscribe(self) -> None:
        with self._cam_lock:
            self._camera_unsubscribe_locked()

    def camera_frame(self) -> Optional[bytes]:
        """Return one JPEG frame."""
        with self._cam_lock:
            if not self._cam_sub:
                self._camera_subscribe_locked()
            img = self.svc("ALVideoDevice").getImageRemote(self._cam_sub)
            if not img:
                return None
            w, h, data = img[0], img[1], img[6]
            pil = Image.frombytes("RGB", (w, h), bytes(data))
            buf = io.BytesIO()
            pil.save(buf, format="JPEG", quality=80)
            return buf.getvalue()

    # ------------------------------------------------------------ system
    def system(self, action: str) -> None:
        sysv = self.svc("ALSystem")
        {"reboot": sysv.reboot, "shutdown": sysv.shutdown}[action]()
