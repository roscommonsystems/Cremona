// ── State ──────────────────────────────────────────────────────────
let ws = null;
let audioCtx = null;
let micStream = null;
let workletNode = null;
let state = "idle"; // idle | connecting | active | error

// Audio playback scheduling
let playbackCtx = null;
let nextPlayTime = 0;
const BUFFER_LEAD = 0.05; // seconds of lead time for gapless scheduling

// Sound alerts
const sounds = {};
let waitingLoop = null;

// ── DOM ────────────────────────────────────────────────────────────
const logo = document.getElementById("logo");
const appEl = document.getElementById("app");
const statusEl = document.getElementById("status");
const generatedImage = document.getElementById("generated-image");
const downloadBtn = document.getElementById("download-btn");

// ── Preload sounds ─────────────────────────────────────────────────
function preloadSounds() {
    ["open", "error", "waiting"].forEach(name => {
        const audio = new Audio(`/static/audio/cremona-${name}.wav`);
        audio.preload = "auto";
        sounds[name] = audio;
    });
}
preloadSounds();

function playSound(name) {
    const s = sounds[name];
    if (!s) {
        console.log(`[playSound] Sound "${name}" not found`);
        return;
    }
    const clone = s.cloneNode();
    clone.play()
        .then(() => console.log(`[playSound] Playing sound "${name}"`))
        .catch((err) => console.log(`[playSound] Failed to play sound "${name}": ${err}`));
}

function startWaitingLoop() {
    stopWaitingLoop();
    const s = sounds.waiting;
    if (!s) return;
    waitingLoop = s.cloneNode();
    waitingLoop.loop = true;
    waitingLoop.play().catch(() => {});
}

function stopWaitingLoop() {
    if (waitingLoop) {
        waitingLoop.pause();
        waitingLoop.currentTime = 0;
        waitingLoop = null;
    }
}

// ── Status display ─────────────────────────────────────────────────
function setStatus(text) {
    if (text) {
        statusEl.textContent = text;
        statusEl.classList.remove("hidden");
    } else {
        statusEl.classList.add("hidden");
    }
}

// ── Base64 helpers ─────────────────────────────────────────────────
function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function base64ToInt16Array(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new Int16Array(bytes.buffer);
}

// ── Audio playback ─────────────────────────────────────────────────
function initPlayback() {
    if (!playbackCtx) {
        playbackCtx = new AudioContext({ sampleRate: 24000 });
    }
    nextPlayTime = 0;
}

function playAudioChunk(b64data) {
    if (!playbackCtx) initPlayback();

    const int16 = base64ToInt16Array(b64data);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768;
    }

    const buffer = playbackCtx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);

    const source = playbackCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(playbackCtx.destination);

    const now = playbackCtx.currentTime;
    if (nextPlayTime < now + BUFFER_LEAD) {
        nextPlayTime = now + BUFFER_LEAD;
    }
    source.start(nextPlayTime);
    nextPlayTime += buffer.duration;
}

function clearPlaybackQueue() {
    if (playbackCtx) {
        playbackCtx.close();
        playbackCtx = null;
    }
    nextPlayTime = 0;
    initPlayback();
}

// ── Mic capture via AudioWorklet ───────────────────────────────────
async function startMic() {
    micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
        }
    });

    audioCtx = new AudioContext();
    await audioCtx.audioWorklet.addModule("/static/js/audio-processor.js");

    const source = audioCtx.createMediaStreamSource(micStream);
    workletNode = new AudioWorkletNode(audioCtx, "pcm-processor");

    workletNode.port.onmessage = (e) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "input.audio",
                audio: arrayBufferToBase64(e.data),
            }));
        }
    };

    source.connect(workletNode);
    workletNode.connect(audioCtx.destination); // required for worklet to process
}

function stopMic() {
    if (workletNode) {
        workletNode.disconnect();
        workletNode = null;
    }
    if (audioCtx) {
        audioCtx.close();
        audioCtx = null;
    }
    if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }
}

// ── WebSocket connection ───────────────────────────────────────────
function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setStatus("Connecting to voice service...");
    };

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        handleServerMessage(msg);
    };

    ws.onclose = () => {
        if (state !== "idle") {
            setStatus("Connection lost. Click logo to reconnect.");
            playSound("error");
            setState("idle");
        }
    };

    ws.onerror = () => {
        setStatus("Connection error. Click logo to retry.");
        playSound("error");
        setState("idle");
    };
}

// ── Message handling ───────────────────────────────────────────────
let userTranscript = "";
let agentTranscript = "";

function handleServerMessage(msg) {
    switch (msg.type) {
        case "session.ready":
            setState("active");
            setStatus("");
            break;

        case "input.speech.started":
            userTranscript = "";
            setStatus("Listening...");
            break;

        case "input.speech.stopped":
            setStatus("Processing...");
            break;

        case "transcript.user.delta":
            userTranscript = msg.text;
            setStatus(`You: ${userTranscript}`);
            break;

        case "transcript.user":
            userTranscript = msg.text;
            setStatus(`You: ${userTranscript}`);
            break;

        case "reply.started":
            agentTranscript = "";
            break;

        case "transcript.agent":
            agentTranscript = msg.text;
            setStatus(`Agent: ${agentTranscript}`);
            break;

        case "reply.audio":
            playAudioChunk(msg.data);
            break;

        case "reply.interrupted":
            clearPlaybackQueue();
            break;

        case "sound":
            playSound(msg.name);
            break;

        case "sound_loop":
            if (msg.action === "start") startWaitingLoop();
            else stopWaitingLoop();
            break;

        case "image":
            showImage(msg.data);
            break;

        case "trigger_download":
            downloadBtn.click();
            break;

        case "session.timeout":
            setStatus("Session timed out due to inactivity.");
            setState("idle");
            break;

        case "error":
            setStatus(`Error: ${msg.message}`);
            playSound("error");
            setState("idle");
            break;
    }
}

// ── Image display ──────────────────────────────────────────────────
function showImage(dataUrl) {
    generatedImage.src = dataUrl;
    downloadBtn.href = dataUrl;
    appEl.classList.add("image-shown");
}

// ── State machine ──────────────────────────────────────────────────
function setState(newState) {
    state = newState;

    if (newState === "idle") {
        logo.src = "/static/img/circular_logo_teal.png";
        logo.classList.remove("active");
        logo.setAttribute("aria-label", "Cremona, click to start session");
        stopMic();
        stopWaitingLoop();
        if (ws) {
            ws.close();
            ws = null;
        }
    } else if (newState === "connecting") {
        logo.setAttribute("aria-label", "Cremona, connecting\u2026");
        setStatus("Requesting microphone access...");
    } else if (newState === "active") {
        logo.src = "/static/img/circular_logo_orange.png";
        logo.classList.add("active");
        logo.setAttribute("aria-label", "Cremona, session active, click to stop");
    }
}

// ── Click / keyboard handler ───────────────────────────────────────
logo.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        logo.click();
    }
});

logo.addEventListener("click", async () => {
    if (state !== "idle") {
        // Click while active — stop session
        setState("idle");
        setStatus("");
        appEl.classList.remove("image-shown");
        return;
    }

    setState("connecting");

    try {
        await startMic();
        initPlayback();
        connectWS();
    } catch (err) {
        setStatus(`Microphone error: ${err.message}`);
        setState("idle");
    }
});
