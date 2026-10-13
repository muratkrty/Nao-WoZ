/* NAO WoZ – front-end logic (vanilla JS, no build step) */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const state = { cfg: {}, meta: {}, connected: false, status: {}, ledGroup: "FaceLeds", shortcuts: [], animated: true,
                  camRunning: false, holding: null, joints: null, sensors: null };

  // ------------------------------------------------------------ helpers
  async function api(path, data, method) {
    const opts = { method: method || (data !== undefined ? "POST" : "GET"), headers: { "Content-Type": "application/json" } };
    if (data !== undefined) opts.body = JSON.stringify(data);
    let res;
    try { res = await fetch(path, opts); } catch (e) { toast("server unreachable", "err"); throw e; }
    let json = {};
    try { json = await res.json(); } catch (_) {}
    if (!res.ok) { toast(json.error || json.detail || `${res.status} ${res.statusText}`, "err"); throw new Error(json.error || res.statusText); }
    return json;
  }
  const post = (p, d = {}) => api(p, d);
  function toast(msg, kind = "") {
    const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg;
    $("#toasts").appendChild(t); setTimeout(() => t.remove(), kind === "err" ? 5000 : 2200);
  }
  const rgbHex = (r, g, b) => "#" + [r, g, b].map(v => Number(v).toString(16).padStart(2, "0")).join("");
  const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const kbd = k => k ? `<span class="kbd">${k}</span>` : "";
  const fmt = (v, d = 2) => (v === null || v === undefined || isNaN(v)) ? "–" : Number(v).toFixed(d);

  // ------------------------------------------------------------ navigation
  $$("#nav button[data-panel]").forEach(b => b.addEventListener("click", () => showPanel(b.dataset.panel)));
  function showPanel(name) {
    $$("#nav button[data-panel]").forEach(b => b.classList.toggle("active", b.dataset.panel === name));
    $$(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + name));
    location.hash = name;
    if (name === "animations" && state.connected && !$("#animList").dataset.loaded) loadBehaviors();
    if (name === "behaviors" && state.connected) loadBehaviors();
    if (name === "motion" && state.connected) { loadJoints(); loadStiffness(); }
    if (name === "speech" && state.connected) loadTts();
  }

  // ------------------------------------------------------------ config -> UI
  async function loadConfig() {
    const r = await api("/api/config");
    state.cfg = r.config; state.meta = r; state.shortcuts = [];
    const cfg = state.cfg;
    $("#iplist").innerHTML = (cfg.robot_ips || []).map(ip => `<option value="${ip}">`).join("");
    if (!$("#ip").value) $("#ip").value = r.mock ? "mock" : (cfg.robot_ips || [""])[0];
    if (r.mock) $("#chipMock").style.display = "";
    $("#recDir").textContent = cfg.robot_record_dir || "/home/nao";

    // speech presets
    $("#speechPresets").innerHTML = (cfg.speech || []).map((p, i) =>
      `<button class="btn" data-i="${i}" title="${(p.text || "").replace(/"/g, "&quot;")}"><span class="lbl">${p.title}</span>${kbd(p.key)}</button>`).join("");
    $$("#speechPresets button").forEach(b => b.addEventListener("click", () => sayPreset(cfg.speech[b.dataset.i])));
    (cfg.speech || []).forEach(p => p.key && state.shortcuts.push({ key: p.key, label: `say "${p.title}"`, fn: () => sayPreset(p) }));

    // animations
    $("#animFavs").innerHTML = (cfg.animations || []).map((a, i) =>
      `<button class="btn" data-i="${i}" title="${a.name}"><span class="lbl">${a.title}</span>${kbd(a.key)}</button>`).join("");
    $$("#animFavs button").forEach(b => b.addEventListener("click", () => runAnimation(cfg.animations[b.dataset.i].name)));
    (cfg.animations || []).forEach(a => a.key && state.shortcuts.push({ key: a.key, label: `animation ${a.title}`, fn: () => runAnimation(a.name) }));

    // colours
    $("#colorPresets").innerHTML = (cfg.colors || []).map((c, i) =>
      `<div class="swatch" data-i="${i}"><i style="background:${rgbHex(c.r, c.g, c.b)};box-shadow:0 0 12px ${rgbHex(c.r, c.g, c.b)}"></i><span>${c.title}</span>${kbd(c.key)}</div>`).join("");
    $$("#colorPresets .swatch").forEach(s => s.addEventListener("click", () => { const c = cfg.colors[s.dataset.i]; setLed(c.r, c.g, c.b); }));
    (cfg.colors || []).forEach(c => c.key && state.shortcuts.push({ key: c.key, label: `eyes ${c.title}`, fn: () => setLed(c.r, c.g, c.b) }));

    // audio
    $("#audioPresets").innerHTML = (cfg.audio_files || []).map((a, i) => `<button class="btn" data-i="${i}" title="${a.path}"><span class="lbl">${a.title}</span>${kbd(a.key)}</button>`).join("");
    $$("#audioPresets button").forEach(b => b.addEventListener("click", () => post("/api/audio/play", { path: cfg.audio_files[b.dataset.i].path })));
    (cfg.audio_files || []).forEach(a => a.key && state.shortcuts.push({ key: a.key, label: `play ${a.title}`, fn: () => post("/api/audio/play", { path: a.path }) }));

    // postures
    $("#postures").innerHTML = r.postures.map(p => `<button class="btn" data-p="${p}">${p}</button>`).join("");
    $$("#postures button").forEach(b => b.addEventListener("click", () => post("/api/motion/posture", { name: b.dataset.p, speed: +$("#postureSpeed").value })));

    // stiffness chains
    $("#stiffChains").innerHTML = r.stiffness_chains.map(c => `<button class="btn sm" data-chain="${c}">${c}</button>`).join("");
    $$("#stiffChains button").forEach(b => b.addEventListener("click", async () => {
      const on = !b.classList.contains("active");
      await post("/api/motion/stiffness", { chain: b.dataset.chain, value: on ? 1 : 0 }); loadStiffness();
    }));

    // led groups
    $("#ledGroups").innerHTML = Object.entries(r.led_groups).map(([k, v]) => `<button class="btn sm ${k === state.ledGroup ? "active" : ""}" data-g="${k}">${v}</button>`).join("");
    $$("#ledGroups button").forEach(b => b.addEventListener("click", () => { state.ledGroup = b.dataset.g; $$("#ledGroups button").forEach(x => x.classList.toggle("active", x === b)); }));

    // life toggles
    const toggles = [["basic_awareness", "Basic awareness (look at people/sounds)"], ["blinking", "Autonomous blinking"],
      ["listening_movement", "Listening movements"], ["speaking_movement", "Speaking movements"], ["fall_manager", "Fall manager"],
      ...r.breath_chains.map(c => ["breath_" + c, `Breathing · ${c}`])];
    $("#lifeToggles").innerHTML = toggles.map(([k, l]) => `<label class="switch unknown" data-setting="${k}"><span>${l}</span><span class="tog"></span></label>`).join("");
    $$("#lifeToggles .switch").forEach(s => s.addEventListener("click", async () => {
      const on = !s.classList.contains("on");
      await post("/api/life/setting", { name: s.dataset.setting, enabled: on });
      s.classList.toggle("on", on); s.classList.remove("unknown"); refreshStatus();
    }));

    // touch map
    const touches = [["head_front", "Head front"], ["head_middle", "Head middle"], ["head_rear", "Head rear"],
      ["lhand_back", "L hand back"], ["lhand_left", "L hand left"], ["lhand_right", "L hand right"],
      ["rhand_back", "R hand back"], ["rhand_left", "R hand left"], ["rhand_right", "R hand right"],
      ["lfoot_bumper_left", "L bumper L"], ["lfoot_bumper_right", "L bumper R"], ["chest_button", "Chest button"],
      ["rfoot_bumper_left", "R bumper L"], ["rfoot_bumper_right", "R bumper R"]];
    $("#touchmap").innerHTML = touches.map(([k, l]) => `<div class="touch" data-k="${k}">${l}</div>`).join("");
    $("#miniTouch").innerHTML = touches.map(([k, l]) => `<span data-k="${k}">${l}</span>`).join("");

    // built-in shortcuts list
    const builtin = [["Esc", "STOP ALL (speech, motion, behaviours)"], ["Enter (in text box)", "say text"],
      ["↑ ↓ ← →", "walk (hold)"], ["Q / E", "turn left / right (hold)"], ["Shift + arrows", "nudge head"], ["Ctrl+Space", "stop speech"]];
    $("#shortcutKv").innerHTML = [...builtin, ...state.shortcuts.map(s => [s.key, s.label])].map(([k, l]) => `<span>${k}</span><span>${l}</span>`).join("");
  }

  // ------------------------------------------------------------ connection & status
  $("#btnConnect").addEventListener("click", async () => {
    $("#btnConnect").disabled = true; $("#btnConnect").textContent = "Connecting…";
    try { const r = await post("/api/connect", { ip: $("#ip").value.trim() }); applyStatus(r.status); toast("connected to " + r.status.name, "ok"); onConnected(); }
    catch (_) {} finally { $("#btnConnect").disabled = false; $("#btnConnect").textContent = "Connect"; }
  });
  $("#btnDisconnect").addEventListener("click", async () => { stopCamera(); await post("/api/disconnect"); applyStatus({ connected: false }); });

  function onConnected() { loadTts(); loadStiffness(); loadBehaviors(); loadJoints(); }
  async function refreshStatus() { try { applyStatus(await api("/api/status")); } catch (_) {} }

  function applyStatus(s) {
    state.status = s; const was = state.connected; state.connected = !!s.connected;
    $("#chipConn").classList.toggle("on", state.connected);
    $("#robotName").textContent = state.connected ? `${s.name || "NAO"} @ ${s.ip}` : "offline";
    $("#btnConnect").style.display = state.connected ? "none" : ""; $("#btnDisconnect").style.display = state.connected ? "" : "none";
    $("#chipMock").style.display = s.mock ? "" : "none";
    const b = s.battery; $("#battPct").textContent = b == null ? "–" : b + "%";
    $("#battFill").style.width = (b || 0) + "%"; $("#battFill").style.background = b < 20 ? "var(--bad)" : b < 40 ? "var(--warn)" : "var(--ok)";
    $("#stPosture").textContent = s.posture || "–"; $("#stLife").textContent = s.life_state || "–";
    $("#stVolume").textContent = s.volume == null ? "–" : s.volume + "%"; $("#stAwake").textContent = s.awake == null ? "–" : (s.awake ? "on" : "rest");
    if (s.volume != null) { $("#volume").value = s.volume; $("#volume2").value = s.volume; $("#volVal").textContent = $("#volVal2").textContent = s.volume + "%"; }
    if (s.tts_speed != null) { $("#ttsSpeed").value = s.tts_speed; $("#speedVal").textContent = s.tts_speed; }
    if (s.tts_pitch != null) { $("#ttsPitch").value = s.tts_pitch; $("#pitchVal").textContent = Number(s.tts_pitch).toFixed(2); }
    $$("#lifeStates button").forEach(x => x.classList.toggle("active", x.dataset.v === s.life_state));
    const map = { basic_awareness: s.awareness, blinking: s.blinking, listening_movement: s.listening_movement, speaking_movement: s.speaking_movement, fall_manager: s.fall_manager, breath_Body: s.breathing };
    $$("#lifeToggles .switch").forEach(x => { const v = map[x.dataset.setting]; if (v !== undefined && v !== null) { x.classList.toggle("on", !!v); x.classList.remove("unknown"); } });
    if (s.eye_color) paintEyes(rgbHex(...s.eye_color));
    $("#sysKv").innerHTML = state.connected ? [["name", s.name], ["ip", s.ip], ["NAOqi", s.version], ["language", s.language], ["battery", b + "%" + (s.charging ? " (charging)" : "")],
      ["posture", s.posture], ["autonomous life", s.life_state], ["mode", s.mock ? "simulated" : "real robot"]].map(([k, v]) => `<span>${k}</span><span>${v ?? "–"}</span>`).join("") : "<span>status</span><span>not connected</span>";
    if (!state.connected && was) toast("disconnected");
  }

  // ------------------------------------------------------------ speech
  const sayHistory = [];
  async function say(text, animated) {
    text = (text || "").trim(); if (!text) return;
    await post("/api/say", { text, animated });
    if (!sayHistory.includes(text)) { sayHistory.unshift(text); if (sayHistory.length > 30) sayHistory.pop();
      $("#sayHistory").innerHTML = '<option value="">(previously said)</option>' + sayHistory.map(t => `<option>${t.replace(/</g, "&lt;")}</option>`).join(""); }
  }
  const sayPreset = p => say(p.text, p.animated !== false);
  $("#btnSay").addEventListener("click", () => say($("#sayText").value, state.animated));
  $("#sayText").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); say($("#sayText").value, state.animated); } });
  $("#sayHistory").addEventListener("change", e => { if (e.target.value) { $("#sayText").value = e.target.value; e.target.value = ""; } });
  $("#swAnimated").classList.toggle("on", state.animated);
  $("#swAnimated").addEventListener("click", () => { state.animated = !state.animated; $("#swAnimated").classList.toggle("on", state.animated); });
  $("#btnStopSpeech").addEventListener("click", () => post("/api/tts/stop"));
  async function loadTts() {
    try { const r = await api("/api/tts"); const i = r.result;
      $("#ttsLang").innerHTML = i.languages.map(l => `<option ${l === i.language ? "selected" : ""}>${l}</option>`).join("");
      $("#ttsSpeed").value = i.speed; $("#speedVal").textContent = i.speed; $("#ttsPitch").value = i.pitch; $("#pitchVal").textContent = Number(i.pitch).toFixed(2);
    } catch (_) {}
  }
  $("#ttsLang").addEventListener("change", e => post("/api/tts", { language: e.target.value }));
  const slider = (id, label, fmtf, onchange) => { const el = $(id); el.addEventListener("input", () => $(label).textContent = fmtf(el.value)); el.addEventListener("change", () => onchange(el.value)); };
  slider("#ttsSpeed", "#speedVal", v => v, v => post("/api/tts", { speed: +v }));
  slider("#ttsPitch", "#pitchVal", v => Number(v).toFixed(2), v => post("/api/tts", { pitch: +v }));
  slider("#volume", "#volVal", v => v + "%", v => { post("/api/audio/volume", { value: +v }); $("#volume2").value = v; $("#volVal2").textContent = v + "%"; });
  slider("#volume2", "#volVal2", v => v + "%", v => { post("/api/audio/volume", { value: +v }); $("#volume").value = v; $("#volVal").textContent = v + "%"; });

  // ------------------------------------------------------------ animations & behaviours
  const runAnimation = name => post("/api/animation", { name });
  $("#btnAnimCustom").addEventListener("click", () => runAnimation($("#animCustom").value.trim()));
  $("#btnAnimRefresh").addEventListener("click", loadBehaviors); $("#btnBehRefresh").addEventListener("click", loadBehaviors);
  $("#btnBehStopAll").addEventListener("click", async () => { await post("/api/behavior", { op: "stop_all" }); loadBehaviors(); });
  let behData = { animations: [], behaviors: [], running: [] };
  async function loadBehaviors() {
    if (!state.connected) return;
    try { behData = (await api("/api/behaviors")).result; $("#animList").dataset.loaded = "1"; renderAnims(); renderBehs(); } catch (_) {}
  }
  function renderAnims() {
    const f = $("#animFilter").value.toLowerCase();
    const items = behData.animations.filter(a => a.toLowerCase().includes(f));
    $("#animList").innerHTML = items.length ? items.map(a => `<div class="item"><span class="name">${a.replace("animations/", "")}</span><button class="btn sm" data-a="${a}">▶ run</button></div>`).join("") : '<div class="empty">no animations match</div>';
    $$("#animList button").forEach(b => b.addEventListener("click", () => runAnimation(b.dataset.a)));
  }
  function renderBehs() {
    const f = $("#behFilter").value.toLowerCase();
    const items = behData.behaviors.filter(a => a.toLowerCase().includes(f));
    $("#behList").innerHTML = items.length ? items.map(a => { const run = behData.running.includes(a);
      return `<div class="item ${run ? "running" : ""}"><span class="name">${a}</span>${run ? '<span class="kbd">running</span>' : ""}<button class="btn sm" data-op="${run ? "stop" : "run"}" data-b="${a}">${run ? "■ stop" : "▶ run"}</button></div>`; }).join("") : '<div class="empty">no behaviours match</div>';
    $$("#behList button").forEach(b => b.addEventListener("click", async () => { await post("/api/behavior", { op: b.dataset.op, name: b.dataset.b }); setTimeout(loadBehaviors, 500); }));
  }
  $("#animFilter").addEventListener("input", renderAnims); $("#behFilter").addEventListener("input", renderBehs);

  // ------------------------------------------------------------ motion
  $("#btnWake").addEventListener("click", async () => { await post("/api/motion/wake"); setTimeout(refreshStatus, 1500); });
  $("#btnRest").addEventListener("click", async () => { await post("/api/motion/rest"); setTimeout(refreshStatus, 2500); });
  slider("#postureSpeed", "#postureSpeedVal", v => v, () => {});
  slider("#walkSpeed", "#walkSpeedVal", v => v, () => {});
  slider("#headSpeed", "#headSpeedVal", v => v, () => {});
  $$("[data-hand]").forEach(b => b.addEventListener("click", () => post("/api/motion/hand", { hand: b.dataset.hand, open: b.dataset.open === "1" })));
  async function loadStiffness() {
    try { const r = (await api("/api/motion/stiffness_get", {})).result;
      $$("#stiffChains button").forEach(b => { const v = r[b.dataset.chain]; b.classList.toggle("active", v != null && v > 0.5); b.title = v == null ? "" : "stiffness " + v; }); } catch (_) {}
  }
  // walking: hold to move
  function startMove(vec) {
    if (state.holding === vec) return; state.holding = vec;
    const sp = +$("#walkSpeed").value; const [x, y, t] = vec.split(",").map(Number);
    post("/api/motion/move", { x: x * sp, y: y * sp, theta: t * sp });
    $$(".dpad .hold").forEach(b => b.classList.toggle("holding", b.dataset.move === vec));
  }
  function stopMove() { if (state.holding === null) return; state.holding = null; post("/api/motion/stop"); $$(".dpad .hold").forEach(b => b.classList.remove("holding")); }
  $$(".dpad .hold").forEach(b => {
    b.addEventListener("pointerdown", e => { e.preventDefault(); startMove(b.dataset.move); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(ev => b.addEventListener(ev, stopMove));
  });
  $("#btnStopMove").addEventListener("click", () => { state.holding = null; post("/api/motion/stop"); });
  $$("[data-step]").forEach(b => b.addEventListener("click", () => {
    const m = state.cfg.movement || {}; const d = m.step_distance ?? 0.2, a = (m.turn_angle ?? 30) * Math.PI / 180;
    const v = { fwd: [d, 0, 0], back: [-d, 0, 0], left: [0, 0, a], right: [0, 0, -a] }[b.dataset.step];
    post("/api/motion/move_to", { x: v[0], y: v[1], theta: v[2] });
  }));
  // head
  let headTimer = null;
  function sendHead(yaw, pitch) {
    $("#headYaw").value = yaw; $("#headPitch").value = pitch; $("#yawVal").textContent = Math.round(yaw) + "°"; $("#pitchHVal").textContent = Math.round(pitch) + "°";
    clearTimeout(headTimer); headTimer = setTimeout(() => post("/api/motion/head", { yaw, pitch, speed: +$("#headSpeed").value }), 60);
  }
  const headpad = $("#headpad");
  function padToAngles(e) { const r = headpad.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    return [(0.5 - px) * 2 * 119, (py - 0.5) * 2 * 38]; }   // yaw: left of screen = robot's left = positive yaw
  let padDown = false;
  headpad.addEventListener("pointerdown", e => { padDown = true; headpad.setPointerCapture(e.pointerId); sendHead(...padToAngles(e)); });
  headpad.addEventListener("pointermove", e => { if (padDown) sendHead(...padToAngles(e)); });
  ["pointerup", "pointercancel"].forEach(ev => headpad.addEventListener(ev, () => padDown = false));
  $("#headYaw").addEventListener("input", () => sendHead(+$("#headYaw").value, +$("#headPitch").value));
  $("#headPitch").addEventListener("input", () => sendHead(+$("#headYaw").value, +$("#headPitch").value));
  $("#btnHeadCenter").addEventListener("click", () => sendHead(0, 0));
  function nudgeHead(dy, dp) { const st = (state.cfg.movement || {}).head_step ?? 10; sendHead(Math.max(-119, Math.min(119, +$("#headYaw").value + dy * st)), Math.max(-38, Math.min(29, +$("#headPitch").value + dp * st))); }
  function paintHeadCursor(yaw, pitch) { $("#headCur").style.left = (50 - yaw / 119 * 50) + "%"; $("#headCur").style.top = (50 + pitch / 38 * 50) + "%"; }
  // joints
  async function loadJoints() {
    try { const j = (await api("/api/motion/joints", {})).result; state.joints = j;
      $("#joints").innerHTML = j.names.map((n, i) => { const [lo, hi] = j.limits[n] || [-180, 180];
        return `<label class="field"><span>${n} <b data-jv="${n}">${j.angles[i]}°</b></span><input type="range" data-j="${n}" min="${lo}" max="${hi}" step="0.5" value="${j.angles[i]}"></label>`; }).join("");
      $$("#joints input").forEach(el => { let t; el.addEventListener("input", () => { $(`[data-jv="${el.dataset.j}"]`).textContent = el.value + "°"; clearTimeout(t); t = setTimeout(() => post("/api/motion/joint", { name: el.dataset.j, angle: +el.value, speed: +$("#headSpeed").value }), 80); }); });
    } catch (_) {}
  }
  $("#btnJointsRefresh").addEventListener("click", loadJoints);

  // ------------------------------------------------------------ LEDs
  function paintEyes(hex) { $$(".eye").forEach(e => { e.style.background = hex; e.style.boxShadow = `0 0 24px ${hex}`; }); if (state.ledGroup === "FaceLeds") $("#ledColor").value = hex; }
  async function setLed(r, g, b, group) {
    group = group || state.ledGroup;
    await post("/api/leds/color", { group, r, g, b, duration: +$("#ledFade").value });
    if (group === "FaceLeds" || group === "AllLeds") paintEyes(rgbHex(r, g, b));
  }
  $("#btnLedApply").addEventListener("click", () => setLed(...hexRgb($("#ledColor").value)));
  $("#ledColor").addEventListener("change", () => setLed(...hexRgb($("#ledColor").value)));
  slider("#ledFade", "#ledFadeVal", v => v + "s", () => {});
  slider("#ledIntensity", "#ledIntVal", v => Number(v).toFixed(2), v => post("/api/leds/intensity", { group: state.ledGroup, value: +v }));
  $("#btnLedOn").addEventListener("click", () => post("/api/leds/on", { group: state.ledGroup }));
  $("#btnLedOff").addEventListener("click", () => post("/api/leds/off", { group: state.ledGroup }));
  $("#btnLedReset").addEventListener("click", () => post("/api/leds/reset", { group: state.ledGroup }));
  slider("#eyeAnimDur", "#eyeAnimDurVal", v => v + "s", () => {});
  $$("[data-eyeanim]").forEach(b => b.addEventListener("click", () => post("/api/leds/anim", { kind: b.dataset.eyeanim, duration: +$("#eyeAnimDur").value })));

  // ------------------------------------------------------------ autonomy
  $$("#lifeStates button").forEach(b => b.addEventListener("click", async () => { await post("/api/life/state", { state: b.dataset.v }); setTimeout(refreshStatus, 800); }));
  $("#engagement").addEventListener("change", e => post("/api/life/engagement", { mode: e.target.value }));
  $("#tracking").addEventListener("change", e => post("/api/life/tracking", { mode: e.target.value }));

  // ------------------------------------------------------------ camera
  $$("#camSel button").forEach(b => b.addEventListener("click", () => { $$("#camSel button").forEach(x => x.classList.toggle("active", x === b)); if (state.camRunning) startCamera(); }));
  $("#camRes").addEventListener("change", () => state.camRunning && startCamera());
  slider("#camFps", "#camFpsVal", v => v, () => state.camRunning && startCamera());
  async function startCamera() {
    if (!state.connected) return toast("connect first", "err");
    await post("/api/camera/config", { camera: +$("#camSel .active").dataset.v, resolution: +$("#camRes").value, fps: +$("#camFps").value });
    $("#camwrap").innerHTML = `<img src="/api/camera/stream?t=${Date.now()}" alt="camera">`; state.camRunning = true;
  }
  function stopCamera() { if (!state.camRunning) return; state.camRunning = false; $("#camwrap").innerHTML = '<span class="off">stream stopped</span>'; post("/api/camera/stop").catch(() => {}); }
  $("#btnCamStart").addEventListener("click", startCamera); $("#btnCamStop").addEventListener("click", stopCamera);
  $("#btnSnap").addEventListener("click", async () => { const r = await fetch("/api/camera/snapshot?save=1"); if (r.ok) toast("snapshot saved", "ok"); else toast("snapshot failed", "err"); });
  $("#btnCamFs").addEventListener("click", () => $("#camwrap").classList.toggle("fs"));
  $("#camwrap").addEventListener("dblclick", () => $("#camwrap").classList.remove("fs"));

  // ------------------------------------------------------------ audio
  $("#btnAudioPlay").addEventListener("click", () => post("/api/audio/play", { path: $("#audioPath").value.trim() }));
  $("#btnAudioStop").addEventListener("click", () => post("/api/audio/stop"));
  $("#btnRecStart").addEventListener("click", async () => { await post("/api/audio/record", { start: true }); $("#btnRecStart").classList.add("active"); });
  $("#btnRecStop").addEventListener("click", async () => { await post("/api/audio/record", { start: false }); $("#btnRecStart").classList.remove("active"); });

  // ------------------------------------------------------------ sensors / memory
  $("#btnMem").addEventListener("click", async () => { try { const r = await post("/api/memory", { key: $("#memKey").value.trim() }); $("#memOut").textContent = JSON.stringify(r.result, null, 1); } catch (_) {} });
  function renderSensors(s) {
    state.sensors = s;
    $$("#touchmap .touch, #miniTouch span").forEach(el => el.classList.toggle("on", s[el.dataset.k] > 0.5));
    const sl = s.sonar_left, sr = s.sonar_right;
    $("#sonarLVal").textContent = fmt(sl) + " m"; $("#sonarRVal").textContent = fmt(sr) + " m";
    $("#sonarL").style.width = Math.min(100, (sl || 0) / 2.5 * 100) + "%"; $("#sonarR").style.width = Math.min(100, (sr || 0) / 2.5 * 100) + "%";
    $("#liveSonar").textContent = `${fmt(sl)} / ${fmt(sr)} m`;
    $("#battKv").innerHTML = [["charge", fmt(s.battery_charge * 100, 0) + " %"], ["current", fmt(s.battery_current) + " A"], ["temperature", fmt(s.battery_temp, 0) + " °C"]].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("");
    $("#liveBatt").textContent = fmt(s.battery_charge * 100, 0) + " % · " + fmt(s.battery_current, 1) + " A";
    $("#imuKv").innerHTML = [["angle X/Y", `${fmt(s.angle_x * 57.3, 1)}° / ${fmt(s.angle_y * 57.3, 1)}°`], ["accel", `${fmt(s.acc_x)} ${fmt(s.acc_y)} ${fmt(s.acc_z)}`], ["gyro", `${fmt(s.gyro_x)} ${fmt(s.gyro_y)} ${fmt(s.gyro_z)}`]].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("");
    $("#fsrKv").innerHTML = [["left weight", fmt(s.lfoot_weight, 1) + " kg"], ["right weight", fmt(s.rfoot_weight, 1) + " kg"], ["L CoP", `${fmt(s.lfoot_cop_x, 3)}, ${fmt(s.lfoot_cop_y, 3)}`], ["R CoP", `${fmt(s.rfoot_cop_x, 3)}, ${fmt(s.rfoot_cop_y, 3)}`]].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("");
    const temps = Object.keys(s).filter(k => k.startsWith("temp_"));
    $("#temps").innerHTML = temps.map(k => { const v = s[k]; return `<div class="temp ${v > 70 ? "hot" : v > 55 ? "warm" : ""}"><span>${k.slice(5)}</span><b>${fmt(v, 0)}</b></div>`; }).join("");
    if (s.head_angles) { const [y, p] = s.head_angles; $("#liveHead").textContent = `yaw ${fmt(y, 0)}° · pitch ${fmt(p, 0)}°`; paintHeadCursor(y, p);
      if (!padDown && document.activeElement !== $("#headYaw") && document.activeElement !== $("#headPitch")) { $("#headYaw").value = y; $("#headPitch").value = p; $("#yawVal").textContent = Math.round(y) + "°"; $("#pitchHVal").textContent = Math.round(p) + "°"; } }
  }
  function renderLog(items) { $("#log").innerHTML = items.map(l => `<div class="${l.kind}"><span class="t">${l.t}</span><span>${l.msg.replace(/</g, "&lt;")}</span></div>`).join(""); }

  // ------------------------------------------------------------ websocket telemetry
  function connectWs() {
    const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/telemetry");
    ws.onmessage = e => { const d = JSON.parse(e.data);
      if (d.connected !== state.connected) refreshStatus();
      if (d.sensors) renderSensors(d.sensors); if (d.log) renderLog(d.log); };
    ws.onclose = () => setTimeout(connectWs, 1500);
  }

  // ------------------------------------------------------------ stop all & shortcuts
  async function stopAll() {
    state.holding = null;
    await Promise.allSettled([post("/api/tts/stop"), post("/api/motion/stop"), post("/api/behavior", { op: "stop_all" }), post("/api/audio/stop")]);
    toast("STOP ALL sent", "ok");
  }
  $("#btnStopAll").addEventListener("click", stopAll);
  function comboOf(e) { const p = []; if (e.ctrlKey) p.push("ctrl"); if (e.altKey) p.push("alt"); if (e.shiftKey) p.push("shift"); if (e.metaKey) p.push("meta");
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase(); if (!["control", "alt", "shift", "meta"].includes(k)) p.push(e.code.startsWith("Digit") ? e.code.slice(5) : k); return p.join("+"); }
  const arrowMoves = { ArrowUp: "1,0,0", ArrowDown: "-1,0,0", ArrowLeft: "0,1,0", ArrowRight: "0,-1,0", KeyQ: "0,0,1", KeyE: "0,0,-1" };
  document.addEventListener("keydown", e => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
    if (e.key === "Escape") { e.preventDefault(); document.activeElement.blur(); return stopAll(); }
    if (e.ctrlKey && e.code === "Space") { e.preventDefault(); return post("/api/tts/stop"); }
    if (typing) return;
    if (e.shiftKey && e.key.startsWith("Arrow")) { e.preventDefault(); return nudgeHead({ ArrowLeft: 1, ArrowRight: -1 }[e.key] || 0, { ArrowUp: -1, ArrowDown: 1 }[e.key] || 0); }
    if (arrowMoves[e.code] && !e.ctrlKey && !e.altKey) { e.preventDefault(); if (state.connected) startMove(arrowMoves[e.code]); return; }
    const combo = comboOf(e); const sc = state.shortcuts.find(s => s.key.toLowerCase().replace(/\s/g, "") === combo);
    if (sc) { e.preventDefault(); sc.fn(); }
  });
  document.addEventListener("keyup", e => { if (arrowMoves[e.code] && state.holding) stopMove(); });
  window.addEventListener("blur", stopMove);

  // ------------------------------------------------------------ system
  $("#btnReloadCfg").addEventListener("click", async () => { await loadConfig(); toast("config reloaded", "ok"); });
  $("#btnReboot").addEventListener("click", () => confirm("Reboot the robot?") && post("/api/system/reboot"));
  $("#btnShutdown").addEventListener("click", () => confirm("Shut down the robot?") && post("/api/system/shutdown"));

  // ------------------------------------------------------------ boot
  (async () => {
    await loadConfig(); await refreshStatus(); connectWs();
    if (state.connected) onConnected();
    const h = location.hash.slice(1); if (h && $("#panel-" + h)) showPanel(h);
    setInterval(() => { if (state.connected) refreshStatus(); }, 10000);
  })();
})();
