// Voice: one button, on or off. A live voice model hears you, answers aloud, can be interrupted and
// puts cards on the board with update_board; what both of you said is written into the chat.
// The server picks the model (GET /api/voice) and mints a short-lived key (/api/voice/session):
// - gemini: Gemini Live over a WebSocket; the microphone is sent as 16 kHz PCM, the reply plays
//   from 24 kHz PCM;
// - openai: OpenAI realtime over WebRTC;
// - browser (no key): the browser's own speech, through the typed chat.
// Uses app.js's CUR, addMessage, notes, renderCard, revealCard, send and renderSidebar.

(() => {
  const $ = id => document.getElementById(id);
  let voiceOn = false;
  let engine = "browser";
  let run = 0; // each start gets a number; a start that was turned off meanwhile quietly stops
  const ready = fetch("/api/voice").then(r => r.json()).then(j => { engine = j.engine; }).catch(() => {});

  function note(text) { $("voiceNote").textContent = text || ""; }
  function paint(state) {
    const b = $("voiceMode");
    b.textContent = !voiceOn ? "Voice off" : state === "connecting" ? "Connecting…" : "Voice on";
    b.classList.toggle("on", voiceOn);
    b.classList.toggle("listening", state === "listening");
  }

  // ---- shared: the chat and the board ------------------------------------------------------------

  const ids = () => ({ board_id: CUR.board.id, chat_id: CUR.chat.id });

  function keep(role, content) {
    return fetch("/api/voice/turn", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content, ...ids() }),
    }).then(r => r.json()).then(j => {
      if (j.chat && j.chat.title !== CUR.chat.title) { CUR.chat = j.chat; window.renderSidebar && renderSidebar(); }
    }).catch(() => {});
  }

  async function applyOps(opsList) {
    try {
      const r = await fetch("/api/voice/ops", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ops: opsList || [], ...ids() }),
      });
      const j = await r.json();
      const changed = j.notes_changed || [];
      for (const n of changed) {
        const how = notes.has(n.id) ? "changed" : "enter";
        notes.set(n.id, n);
        renderCard(n, how);
      }
      if (changed.length) {
        setTimeout(() => revealCard(changed[0].id), 80);
        window.dispatchEvent(new CustomEvent("lightheart:reply", { detail: { reply: "" } })); // the views redraw
      }
      return { ok: true, changed: changed.map(n => ({ id: n.id, title: n.title })), board: j.board };
    } catch (e) { return { ok: false, error: String(e) }; }
  }

  async function session() {
    const s = await fetch("/api/voice/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ids()) });
    const j = await s.json();
    if (!s.ok) throw new Error(j.detail || "the session failed");
    return j;
  }

  async function microphone() {
    try { return await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
    catch (e) { throw new Error("the microphone is blocked: allow it in the browser"); }
  }

  let live = null; // the running session: { stop() }

  // ---- Gemini Live ----------------------------------------------------------------------------------

  const WORKLET = `class Tap extends AudioWorkletProcessor {
    process(inputs) { const ch = inputs[0] && inputs[0][0]; if (ch) this.port.postMessage(ch.slice(0)); return true; }
  }
  registerProcessor("tap", Tap);`;

  function toBase64(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }

  async function startGemini(my) {
    const s = await session();
    const mic = await microphone();
    if (my !== run) { mic.getTracks().forEach(t => t.stop()); return; }

    const ctx = new AudioContext();
    const ws = new WebSocket(s.url);
    const playing = new Set();
    let nextAt = 0;
    let micNode = null, src = null;
    // this turn: what you said and what it said, shown as it comes and kept when the turn ends
    let turn = { user: "", said: "", userEl: null, saidEl: null };

    function stop() {
      try { ws.close(); } catch (e) {}
      mic.getTracks().forEach(t => t.stop());
      try { micNode && micNode.disconnect(); src && src.disconnect(); } catch (e) {}
      for (const p of playing) { try { p.stop(); } catch (e) {} }
      ctx.close().catch(() => {});
    }
    live = { stop };

    function play(b64) {
      const bin = atob(b64);
      const pcm = new Int16Array(bin.length >> 1);
      for (let i = 0; i < pcm.length; i++) pcm[i] = (bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8)) << 16 >> 16;
      const buf = ctx.createBuffer(1, pcm.length, 24000);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
      const node = ctx.createBufferSource();
      node.buffer = buf;
      node.connect(ctx.destination);
      nextAt = Math.max(nextAt, ctx.currentTime + 0.04);
      node.start(nextAt);
      nextAt += buf.duration;
      playing.add(node);
      node.onended = () => playing.delete(node);
    }

    function hush() { for (const p of playing) { try { p.stop(); } catch (e) {} } playing.clear(); nextAt = 0; }

    function show() {
      if (turn.user && !turn.userEl) {
        turn.userEl = addMessage("user", "");
        if (turn.saidEl) $("messages").insertBefore(turn.userEl, turn.saidEl); // your words before its answer
      }
      if (turn.userEl) turn.userEl.textContent = turn.user.trim();
      if (turn.said && !turn.saidEl) turn.saidEl = addMessage("assistant", "");
      if (turn.saidEl) turn.saidEl.textContent = turn.said.trim();
      $("messages").scrollTop = $("messages").scrollHeight;
    }

    async function endTurn() {
      const t = turn;
      turn = { user: "", said: "", userEl: null, saidEl: null };
      if (t.user.trim()) await keep("user", t.user.trim());
      if (t.said.trim()) await keep("assistant", t.said.trim());
    }

    async function startMic() {
      await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" })));
      src = ctx.createMediaStreamSource(mic);
      micNode = new AudioWorkletNode(ctx, "tap");
      const ratio = ctx.sampleRate / 16000;
      let pending = [], pendingLen = 0, carry = 0;
      micNode.port.onmessage = e => {
        // down to 16 kHz (linear), sent every 100 ms
        const x = e.data;
        const out = [];
        for (let pos = carry; pos < x.length - 1; pos += ratio) {
          const i = Math.floor(pos), f = pos - i;
          out.push(x[i] * (1 - f) + x[i + 1] * f);
        }
        carry = (carry + out.length * ratio) - x.length;
        if (carry < 0) carry = 0;
        pending.push(out); pendingLen += out.length;
        if (pendingLen < 1600 || ws.readyState !== 1) return;
        const pcm = new Int16Array(pendingLen);
        let k = 0;
        for (const part of pending) for (const v of part) pcm[k++] = Math.max(-1, Math.min(1, v)) * 0x7fff;
        pending = []; pendingLen = 0;
        ws.send(JSON.stringify({ realtimeInput: { audio: { data: toBase64(new Uint8Array(pcm.buffer)), mimeType: "audio/pcm;rate=16000" } } }));
      };
      src.connect(micNode);
    }

    async function onMessage(m) {
      if (m.setupComplete) {
        await startMic();
        paint("listening"); note("Talk: I'm listening.");
        return;
      }
      if (m.toolCall) {
        const answers = [];
        for (const c of m.toolCall.functionCalls || []) {
          const result = c.name === "update_board" ? await applyOps((c.args || {}).ops) : { ok: false, error: "unknown tool" };
          answers.push({ id: c.id, name: c.name, response: { result } });
        }
        if (ws.readyState === 1) ws.send(JSON.stringify({ toolResponse: { functionResponses: answers } }));
        return;
      }
      if (m.goAway) { note("The voice session is ending soon."); return; }
      const sc = m.serverContent;
      if (!sc) return;
      if (sc.interrupted) { hush(); await endTurn(); }
      if (sc.inputTranscription && sc.inputTranscription.text) { turn.user += sc.inputTranscription.text; show(); paint("listening"); note(""); }
      if (sc.outputTranscription && sc.outputTranscription.text) { turn.said += sc.outputTranscription.text; show(); paint(); }
      for (const p of (sc.modelTurn && sc.modelTurn.parts) || []) if (p.inlineData && p.inlineData.data) play(p.inlineData.data);
      if (sc.turnComplete) await endTurn();
    }

    // messages are handled one by one, in order (they come as Blobs)
    let chain = Promise.resolve();
    ws.onmessage = e => {
      chain = chain.then(async () => {
        const text = typeof e.data === "string" ? e.data : await e.data.text();
        await onMessage(JSON.parse(text));
      }).catch(err => console.error("voice:", err));
    };
    ws.onopen = () => ws.send(JSON.stringify({ setup: { model: s.model } }));
    ws.onclose = e => {
      if (my === run && voiceOn) { note(e.reason ? `The voice closed: ${e.reason}` : "The voice connection closed."); turnOff(); }
    };
  }

  // ---- OpenAI realtime ------------------------------------------------------------------------------

  async function startOpenAI(my) {
    const s = await session();
    const mic = await microphone();
    if (my !== run) { mic.getTracks().forEach(t => t.stop()); return; }

    const pc = new RTCPeerConnection();
    const audio = new Audio();
    audio.autoplay = true;
    pc.ontrack = e => { audio.srcObject = e.streams[0]; };
    pc.addTrack(mic.getTracks()[0], mic);
    const dc = pc.createDataChannel("oai-events");
    const bubbles = new Map();
    let pendingUser = Promise.resolve();
    live = {
      stop() {
        try { dc.close(); } catch (e) {}
        try { pc.close(); } catch (e) {}
        mic.getTracks().forEach(t => t.stop());
        audio.srcObject = null;
      },
    };
    const sendEvent = ev => { if (dc.readyState === "open") dc.send(JSON.stringify(ev)); };

    dc.onopen = () => { note("Talk: I'm listening."); paint("listening"); };
    pc.onconnectionstatechange = () => {
      if (my === run && voiceOn && ["failed", "disconnected"].includes(pc.connectionState)) { note("The voice connection dropped."); turnOff(); }
    };
    dc.onmessage = e => {
      let ev;
      try { ev = JSON.parse(e.data); } catch (err) { return; }
      (async () => {
        switch (ev.type) {
          case "input_audio_buffer.speech_started":
            paint("listening"); note("");
            break;
          case "input_audio_buffer.committed": {
            const el = addMessage("user", "…");
            let done;
            const p = new Promise(res => { done = res; setTimeout(res, 8000); });
            bubbles.set(ev.item_id, { el, done });
            const before = pendingUser;
            pendingUser = before.then(() => p);
            paint();
            break;
          }
          case "conversation.item.input_audio_transcription.completed":
          case "conversation.item.input_audio_transcription.failed": {
            const b = bubbles.get(ev.item_id);
            const text = (ev.transcript || "").trim();
            if (b) {
              bubbles.delete(ev.item_id);
              if (text) { b.el.textContent = text; await keep("user", text); } else b.el.remove();
              b.done();
            }
            break;
          }
          case "response.output_audio_transcript.done": {
            const text = (ev.transcript || "").trim();
            if (!text) break;
            addMessage("assistant", text);
            await pendingUser;
            keep("assistant", text);
            break;
          }
          case "response.done": {
            const out = (ev.response && ev.response.output) || [];
            const calls = out.filter(o => o.type === "function_call" && o.name === "update_board");
            if (!calls.length) break;
            await pendingUser;
            for (const c of calls) {
              let args = {};
              try { args = JSON.parse(c.arguments || "{}"); } catch (e) {}
              const result = await applyOps(args.ops);
              sendEvent({ type: "conversation.item.create", item: { type: "function_call_output", call_id: c.call_id, output: JSON.stringify(result) } });
            }
            // it already spoke in that turn: no second answer; otherwise it says what it did
            if (!out.some(o => o.type === "message")) sendEvent({ type: "response.create" });
            break;
          }
          case "error":
            console.error("voice:", ev.error);
            note((ev.error && ev.error.message) || "Voice error.");
            break;
        }
      })().catch(err => console.error("voice:", err));
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const r = await fetch(`https://api.openai.com/v1/realtime/calls?model=${encodeURIComponent(s.model)}`, {
      method: "POST", body: offer.sdp,
      headers: { Authorization: `Bearer ${s.key}`, "Content-Type": "application/sdp" },
    });
    if (!r.ok) throw new Error(`OpenAI said ${r.status}`);
    const answer = await r.text();
    if (my !== run || pc.signalingState === "closed") return; // turned off while connecting
    await pc.setRemoteDescription({ type: "answer", sdp: answer });
  }

  // ---- without a key: the browser's own speech, through the typed chat ---------------------------

  const BrowserRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;

  function listenBrowser() {
    if (!voiceOn) return;
    if (!BrowserRec) { note("Voice needs a Gemini or OpenAI key on the server (or Chrome)."); turnOff(); return; }
    rec = new BrowserRec();
    rec.lang = (navigator.language || "fi").startsWith("en") ? "en-US" : "fi-FI";
    let text = "";
    rec.onresult = e => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) text += e.results[i][0].transcript; };
    rec.onend = () => { rec = null; if (voiceOn) { if (text.trim()) send(text); else { note("I didn't hear anything."); turnOff(); } } };
    note("Listening…"); paint("listening");
    rec.start();
  }

  window.addEventListener("lightheart:reply", e => {
    if (!voiceOn || engine !== "browser" || !e.detail.reply) return;
    const u = new SpeechSynthesisUtterance(e.detail.reply);
    u.lang = (navigator.language || "fi").startsWith("en") ? "en-US" : "fi-FI";
    u.onend = listenBrowser;
    speechSynthesis.speak(u);
  });

  // ---- the button ---------------------------------------------------------------------------------

  function turnOff() {
    voiceOn = false;
    run++;
    if (live) { live.stop(); live = null; }
    if (rec) { try { rec.abort(); } catch (e) {} rec = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    paint();
  }

  $("voiceMode").onclick = async () => {
    if (voiceOn) { turnOff(); note(""); return; }
    voiceOn = true;
    const my = ++run;
    paint("connecting"); note("");
    await ready;
    if (my !== run) return;
    if (engine === "browser") { listenBrowser(); return; }
    try { await (engine === "gemini" ? startGemini(my) : startOpenAI(my)); }
    catch (e) {
      if (my !== run) return; // turned off while connecting: not an error
      console.error("voice:", e);
      note(`Couldn't start voice mode: ${e.message}`);
      turnOff();
    }
  };
  paint();
})();
