#!/usr/bin/env python
"""NAO WoZ – Wizard-of-Oz web interface for the NAO v6 robot.

    python server.py                 # real robot (choose IP in the UI)
    python server.py --mock          # simulated robot, no hardware needed
    python server.py --ip 192.168.1.42 --autoconnect
"""
from __future__ import annotations

import argparse
import asyncio
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from nao import sensors as S
from nao.mock import MockRobot

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.yaml"

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ip = STATE.get("autoconnect_ip")
    if ip:
        class _Req:  # minimal stand-in for a Request carrying {"ip": ...}
            async def json(self):
                return {"ip": ip}
        await connect(_Req())  # type: ignore[arg-type]
    yield
    r = STATE.get("robot")
    if r is not None:
        try:
            r.close()
        except Exception:
            pass


app = FastAPI(title="NAO WoZ", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

STATE: Dict[str, Any] = {"robot": None, "config": {}, "mock": False, "log": deque(maxlen=300), "lock": threading.Lock()}


# ----------------------------------------------------------------- helpers
def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    STATE["config"] = cfg
    return cfg


def log(kind: str, msg: str) -> None:
    STATE["log"].appendleft({"t": time.strftime("%H:%M:%S"), "kind": kind, "msg": msg})


def robot():
    r = STATE["robot"]
    if r is None or not r.connected:
        raise HTTPException(status_code=409, detail="Not connected to a robot")
    return r


async def do(fn, *args, action: Optional[str] = None, **kw):
    """Run a blocking robot call in the threadpool, log it and return a JSON ok/err."""
    try:
        result = await run_in_threadpool(fn, *args, **kw)
        if action:
            log("action", action)
        return {"ok": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:  # NAOqi raises RuntimeError with a descriptive message
        log("error", f"{action or fn.__name__}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


async def body(request: Request) -> Dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        return {}


def apply_on_connect(r, cfg: Dict[str, Any]) -> None:
    oc = cfg.get("on_connect", {}) or {}
    def nz(v):
        return v is not None and v != ""
    try:
        if nz(oc.get("volume")):
            r.set_volume(int(oc["volume"]))
        r.set_tts(speed=oc.get("voice_speed") if nz(oc.get("voice_speed")) else None,
                  pitch=oc.get("voice_pitch") if nz(oc.get("voice_pitch")) else None,
                  language=oc.get("language") if nz(oc.get("language")) else None)
        if nz(oc.get("autonomous_life")):
            r.set_life_state(oc["autonomous_life"])
        if nz(oc.get("basic_awareness")):
            r.set_setting("basic_awareness", bool(oc["basic_awareness"]))
        if nz(oc.get("blinking")):
            r.set_setting("blinking", bool(oc["blinking"]))
        if nz(oc.get("eye_color")):
            for c in cfg.get("colors", []):
                if c.get("title") == oc["eye_color"]:
                    r.set_led_color("FaceLeds", c["r"], c["g"], c["b"])
    except Exception as e:
        log("error", f"on_connect defaults: {e}")


# ----------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


# ----------------------------------------------------------------- connection / config
@app.get("/api/config")
async def get_config():
    return {"config": load_config(), "postures": S.POSTURES, "led_groups": S.LED_GROUPS,
            "stiffness_chains": S.STIFFNESS_CHAINS, "breath_chains": S.BREATH_CHAINS,
            "joint_limits": S.JOINT_LIMITS_DEG, "mock": STATE["mock"]}


@app.post("/api/connect")
async def connect(request: Request):
    data = await body(request)
    cfg = load_config()
    ip = data.get("ip") or (cfg.get("robot_ips") or ["127.0.0.1"])[0]
    port = int(cfg.get("port", 9559))
    with STATE["lock"]:
        old = STATE["robot"]
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
            STATE["robot"] = None
        try:
            if STATE["mock"] or ip == "mock":
                r = MockRobot(ip, port)
            else:
                from nao.robot import NaoRobot
                r = await run_in_threadpool(NaoRobot, ip, port)
        except Exception as e:
            log("error", f"connect {ip}: {e}")
            return JSONResponse(status_code=502, content={"ok": False, "error": f"Could not connect to {ip}:{port}: {e}"})
        STATE["robot"] = r
    await run_in_threadpool(apply_on_connect, r, cfg)
    log("system", f"connected to {ip}")
    return {"ok": True, "status": await run_in_threadpool(r.status)}


@app.post("/api/disconnect")
async def disconnect():
    r = STATE["robot"]
    if r is not None:
        await run_in_threadpool(r.close)
        STATE["robot"] = None
        log("system", "disconnected")
    return {"ok": True}


@app.get("/api/status")
async def status():
    r = STATE["robot"]
    if r is None or not r.connected:
        return {"connected": False, "mock": STATE["mock"]}
    try:
        return await run_in_threadpool(r.status)
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.get("/api/log")
async def get_log():
    return list(STATE["log"])


# ----------------------------------------------------------------- speech
@app.post("/api/say")
async def say(request: Request):
    d = await body(request)
    text = (d.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty text")
    return await do(robot().say_async, text, bool(d.get("animated", False)),
                    action=f"say: {text[:80]}")


@app.post("/api/tts/stop")
async def tts_stop():
    return await do(robot().stop_speech, action="stop speech")


@app.get("/api/tts")
async def tts_info():
    return await do(robot().tts_info)


@app.post("/api/tts")
async def tts_set(request: Request):
    d = await body(request)
    return await do(robot().set_tts, d.get("speed"), d.get("pitch"), d.get("language"), d.get("voice"),
                    action=f"tts params {d}")


# ----------------------------------------------------------------- audio
@app.post("/api/audio/volume")
async def audio_volume(request: Request):
    d = await body(request)
    return await do(robot().set_volume, int(d.get("value", 50)), action=f"volume {d.get('value')}")


@app.post("/api/audio/play")
async def audio_play(request: Request):
    d = await body(request)
    return await do(robot().play_audio, d.get("path", ""), float(d.get("volume", 1.0)), action=f"play {d.get('path')}")


@app.post("/api/audio/stop")
async def audio_stop():
    return await do(robot().stop_audio, action="stop audio")


@app.post("/api/audio/record")
async def audio_record(request: Request):
    d = await body(request)
    r = robot()
    if d.get("start"):
        folder = STATE["config"].get("robot_record_dir", "/home/nao")
        path = f"{folder.rstrip('/')}/rec_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        return await do(r.start_recording, path, action=f"recording -> {path}")
    return await do(r.stop_recording, action="recording stopped")


# ----------------------------------------------------------------- animations / behaviors
@app.get("/api/behaviors")
async def behaviors():
    return await do(robot().list_behaviors)


@app.post("/api/animation")
async def animation(request: Request):
    d = await body(request)
    return await do(robot().run_animation, d.get("name", ""), action=f"animation {d.get('name')}")


@app.post("/api/behavior")
async def behavior(request: Request):
    d = await body(request)
    r = robot()
    op, name = d.get("op", "run"), d.get("name", "")
    if op == "run":
        return await do(r.run_behavior, name, action=f"behavior {name}")
    if op == "stop":
        return await do(r.stop_behavior, name, action=f"stop behavior {name}")
    return await do(r.stop_all_behaviors, action="stop all behaviors")


# ----------------------------------------------------------------- motion
@app.post("/api/motion/{cmd}")
async def motion(cmd: str, request: Request):
    d = await body(request)
    r = robot()
    if cmd == "wake":
        return await do(r.wake_up, action="wake up")
    if cmd == "rest":
        return await do(r.rest, action="rest")
    if cmd == "posture":
        return await do(r.go_to_posture, d.get("name", "Stand"), float(d.get("speed", 0.7)),
                        action=f"posture {d.get('name')}")
    if cmd == "stiffness":
        return await do(r.set_stiffness, d.get("chain", "Body"), float(d.get("value", 1.0)),
                        action=f"stiffness {d.get('chain')}={d.get('value')}")
    if cmd == "stiffness_get":
        return await do(r.get_stiffness)
    if cmd == "move":
        return await do(r.move_toward, float(d.get("x", 0)), float(d.get("y", 0)), float(d.get("theta", 0)))
    if cmd == "move_to":
        return await do(r.move_to, float(d.get("x", 0)), float(d.get("y", 0)), float(d.get("theta", 0)),
                        action=f"moveTo {d}")
    if cmd == "stop":
        return await do(r.stop_move, action="stop move")
    if cmd == "head":
        return await do(r.set_head, d.get("yaw"), d.get("pitch"), float(d.get("speed", 0.2)))
    if cmd == "joint":
        return await do(r.set_joint, d.get("name"), float(d.get("angle", 0)), float(d.get("speed", 0.2)))
    if cmd == "joints":
        return await do(r.get_joints)
    if cmd == "hand":
        return await do(r.open_hand, d.get("hand", "RHand"), bool(d.get("open", True)),
                        action=f"{'open' if d.get('open') else 'close'} {d.get('hand')}")
    raise HTTPException(404, f"unknown motion command {cmd}")


# ----------------------------------------------------------------- LEDs
@app.post("/api/leds/{cmd}")
async def leds(cmd: str, request: Request):
    d = await body(request)
    r = robot()
    group = d.get("group", "FaceLeds")
    if cmd == "color":
        return await do(r.set_led_color, group, int(d.get("r", 255)), int(d.get("g", 255)), int(d.get("b", 255)),
                        float(d.get("duration", 0.3)), action=f"{group} rgb({d.get('r')},{d.get('g')},{d.get('b')})")
    if cmd == "intensity":
        return await do(r.set_led_intensity, group, float(d.get("value", 1.0)), action=f"{group} intensity {d.get('value')}")
    if cmd == "off":
        return await do(r.leds_off, group, action=f"{group} off")
    if cmd == "on":
        return await do(r.leds_on, group, action=f"{group} on")
    if cmd == "reset":
        return await do(r.leds_reset, group, action=f"{group} reset")
    if cmd == "anim":
        return await do(r.led_animation, d.get("kind", "rasta"), float(d.get("duration", 3.0)),
                        action=f"eye animation {d.get('kind')}")
    raise HTTPException(404, f"unknown led command {cmd}")


# ----------------------------------------------------------------- autonomous life
@app.post("/api/life/{cmd}")
async def life(cmd: str, request: Request):
    d = await body(request)
    r = robot()
    if cmd == "state":
        return await do(r.set_life_state, d.get("state", "disabled"), action=f"life state {d.get('state')}")
    if cmd == "setting":
        return await do(r.set_setting, d.get("name", ""), bool(d.get("enabled", False)),
                        action=f"{d.get('name')} = {d.get('enabled')}")
    if cmd == "engagement":
        return await do(r.set_engagement, d.get("mode", "Unengaged"), action=f"engagement {d.get('mode')}")
    if cmd == "tracking":
        return await do(r.set_tracking_mode, d.get("mode", "Head"), action=f"tracking {d.get('mode')}")
    raise HTTPException(404, f"unknown life command {cmd}")


# ----------------------------------------------------------------- sensors
@app.get("/api/sensors")
async def sensors():
    return await do(robot().sensors)


@app.post("/api/memory")
async def memory(request: Request):
    d = await body(request)
    return await do(robot().memory_get, d.get("key", ""))


@app.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await ws.accept()
    last_log_len = -1
    try:
        while True:
            r = STATE["robot"]
            payload: Dict[str, Any] = {"connected": bool(r and r.connected)}
            if r and r.connected:
                try:
                    payload["sensors"] = await run_in_threadpool(r.sensors)
                except Exception as e:
                    payload["error"] = str(e)
            payload["log"] = list(STATE["log"])[:40]
            await ws.send_json(payload)
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ----------------------------------------------------------------- camera
@app.post("/api/camera/config")
async def camera_config(request: Request):
    d = await body(request)
    return await do(robot().camera_config, int(d.get("camera", 0)), int(d.get("resolution", 1)), int(d.get("fps", 10)),
                    action=f"camera {d}")


@app.get("/api/camera/stream")
async def camera_stream():
    r = robot()

    def gen():
        while r.connected:
            try:
                frame = r.camera_frame()
            except Exception as e:
                log("error", f"camera: {e}")
                time.sleep(1.0)
                continue
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
            else:
                time.sleep(0.05)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/camera/snapshot")
async def camera_snapshot(save: int = 0):
    r = robot()
    frame = await run_in_threadpool(r.camera_frame)
    if not frame:
        raise HTTPException(503, "no frame")
    if save:
        folder = BASE / STATE["config"].get("snapshot_dir", "snapshots")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"snap_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        path.write_bytes(frame)
        log("action", f"snapshot saved {path.name}")
    return Response(content=frame, media_type="image/jpeg")


@app.post("/api/camera/stop")
async def camera_stop():
    return await do(robot().camera_unsubscribe)


# ----------------------------------------------------------------- system
@app.post("/api/system/{action}")
async def system(action: str):
    if action not in ("reboot", "shutdown"):
        raise HTTPException(404)
    return await do(robot().system, action, action=f"system {action}")


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--mock", action="store_true", help="use a simulated robot")
    ap.add_argument("--ip", help="robot IP to pre-select")
    ap.add_argument("--autoconnect", action="store_true", help="connect at start-up")
    ap.add_argument("--reload", action="store_true", help="auto-reload server on code change (dev)")
    args = ap.parse_args()

    STATE["mock"] = args.mock
    cfg = load_config()
    if args.ip:
        cfg.setdefault("robot_ips", [])
        if args.ip not in cfg["robot_ips"]:
            cfg["robot_ips"].insert(0, args.ip)
    if args.autoconnect or args.mock:
        STATE["autoconnect_ip"] = args.ip or ("mock" if args.mock else (cfg.get("robot_ips") or ["127.0.0.1"])[0])

    import uvicorn
    print(f"\n  NAO WoZ  ->  http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"
          f"   ({'MOCK robot' if args.mock else 'real robot'})\n", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
