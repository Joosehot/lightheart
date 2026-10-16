// Voice: one button, on or off.
// With an OpenAI key on the server it is OpenAI's realtime voice mode (the voice ChatGPT talks with):
// the browser talks straight to gpt-realtime over WebRTC with a short-lived key from /api/voice/session.
// It hears you, answers aloud, can be interrupted, and puts cards on the board with update_board.
// What both of you said is written into the chat and kept like typed messages.
// Without a key: the browser's own (free) speech, through the typed chat.
// Uses app.js's CUR, addMessage, notes, renderCard, revealCard, send and renderSidebar.

(() => {
  const $ = id => document.getElementById(id);
  let voiceOn = false;
  let engine = "browser";
  const ready = fetch("/api/voice").then(r => r.json()).then(j => { engine = j.engine; }).catch(() => {});

  function note(text) { $("voiceNote").textContent = text || ""; }
  function paint(state) {
    $("voiceMode").textContent = voiceOn ? "Voice on" : "Voice off";
    $("voiceMode").classList.toggle("on", voiceOn);
    $("voiceMode").classList.toggle("listening", state === "listening");
  }

  // ---- OpenAI realtime ------------------------------------------------------------------------------

  let rt = null; // { pc, dc, mic, audio, bubbles, pendingUser }

  async function startRealtime() {
    note("Connecting…");
    const s = await fetch("/api/voice/session", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_id: CUR.board.id, chat_id: CUR.chat.id }),
    });
    const sj = await s.json();
    if (!s.ok) throw new Error(sj.detail || "the session failed");

    let mic;
    try { mic = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { throw new Error("the microphone is blocked: allow it in the browser"); }

    const pc = new RTCPeerConnection();
    const audio = new Audio();
    audio.autoplay = true;
    pc.ontrack = e => { audio.srcObject = e.streams[0]; };
    pc.addTrack(mic.getTracks()[0], mic);
    const dc = pc.createDataChannel("oai-events");
    rt = { pc, dc, mic, audio, bubbles: new Map(), pendingUser: Promise.resolve() };
    dc.onmessage = e => { try { onEvent(JSON.parse(e.data)); } catch (err) { console.error("voice event:", err); } };
    dc.onopen = () => { note("Talk: I'm listening."); paint("listening"); };
    pc.onconnectionstatechange = () => {
      if (voiceOn && ["failed", "disconnected", "closed"].includes(pc.connectionState)) { note("The voice connection dropped."); turnOff(); }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const r = await fetch(`https://api.openai.com/v1/realtime/calls?model=${encodeURIComponent(sj.model)}`, {
      method: "POST", body: offer.sdp,
      headers: { Authorization: `Bearer ${sj.key}`, "Content-Type": "application/sdp" },
    });
    if (!r.ok) throw new Error(`OpenAI said ${r.status}`);
    await pc.setRemoteDescription({ type: "answer", sdp: await r.text() });
  }

  function stopRealtime() {
    if (!rt) return;
    try { rt.dc.close(); } catch (e) {}
    try { rt.pc.close(); } catch (e) {}
    rt.mic.getTracks().forEach(t => t.stop());
    rt.audio.srcObject = null;
    rt = null;
  }

  function sendEvent(ev) { if (rt && rt.dc.readyState === "open") rt.dc.send(JSON.stringify(ev)); }

  // kept in the chat in the order said: the reply waits for the words it answers
  function keep(role, content) {
    return fetch("/api/voice/turn", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content, board_id: CUR.board.id, chat_id: CUR.chat.id }),
    }).then(r => r.json()).then(j => {
      if (j.chat && j.chat.title !== CUR.chat.title) { CUR.chat = j.chat; window.renderSidebar && renderSidebar(); }
    }).catch(() => {});
  }

  async function onEvent(ev) {
    switch (ev.type) {
      case "input_audio_buffer.speech_started":
        paint("listening"); note("Listening…");
        break;
      case "input_audio_buffer.committed": {
        // your words get their place in the chat now, the text when it is written down
        const el = addMessage("user", "…");
        let done;
        const p = new Promise(res => { done = res; setTimeout(res, 8000); });
        rt.bubbles.set(ev.item_id, { el, done });
        const before = rt.pendingUser;
        rt.pendingUser = before.then(() => p);
        paint(); note("");
        break;
      }
      case "conversation.item.input_audio_transcription.completed":
      case "conversation.item.input_audio_transcription.failed": {
        const b = rt.bubbles.get(ev.item_id);
        const text = (ev.transcript || "").trim();
        if (b) {
          rt.bubbles.delete(ev.item_id);
          if (text) { b.el.textContent = text; await keep("user", text); } else b.el.remove();
          b.done();
        }
        break;
      }
      case "response.output_audio_transcript.done": {
        const text = (ev.transcript || "").trim();
        if (!text) break;
        addMessage("assistant", text);
        const wait = rt.pendingUser;
        await wait;
        keep("assistant", text);
        break;
      }
      case "response.done": {
        const out = (ev.response && ev.response.output) || [];
        const calls = out.filter(o => o.type === "function_call" && o.name === "update_board");
        if (!calls.length) break;
        const spoke = out.some(o => o.type === "message");
        await rt.pendingUser;
        for (const c of calls) {
          let result = { ok: false };
          try {
            const args = JSON.parse(c.arguments || "{}");
            const r = await fetch("/api/voice/ops", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ops: args.ops || [], board_id: CUR.board.id, chat_id: CUR.chat.id }),
            });
            const j = await r.json();
            for (const n of j.notes_changed || []) {
              const how = notes.has(n.id) ? "changed" : "enter";
              notes.set(n.id, n);
              renderCard(n, how);
            }
            if ((j.notes_changed || []).length) {
              setTimeout(() => revealCard(j.notes_changed[0].id), 80);
              window.dispatchEvent(new CustomEvent("lightheart:reply", { detail: { reply: "" } })); // views redraw
            }
            result = { ok: true, changed: (j.notes_changed || []).map(n => ({ id: n.id, title: n.title })), board: j.board };
          } catch (e) { result = { ok: false, error: String(e) }; }
          sendEvent({ type: "conversation.item.create", item: { type: "function_call_output", call_id: c.call_id, output: JSON.stringify(result) } });
        }
        // it already spoke in the same turn: no second answer; otherwise it says what it did
        if (!spoke) sendEvent({ type: "response.create" });
        break;
      }
      case "error":
        console.error("voice:", ev.error);
        note((ev.error && ev.error.message) || "Voice error.");
        break;
    }
  }

  // ---- without a key: the browser's own speech, through the typed chat ---------------------------

  const BrowserRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;

  function listenBrowser() {
    if (!voiceOn) return;
    if (!BrowserRec) { note("Voice needs an OpenAI key on the server (or Chrome)."); turnOff(); return; }
    rec = new BrowserRec();
    rec.lang = (navigator.language || "fi").startsWith("en") ? "en-US" : "fi-FI";
    let text = "";
    rec.onresult = e => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) text += e.results[i][0].transcript; };
    rec.onend = () => { rec = null; if (voiceOn) { if (text.trim()) send(text); else { note("I didn't hear anything."); turnOff(); } } };
    note("Listening…"); paint("listening");
    rec.start();
  }

  window.addEventListener("lightheart:reply", e => {
    if (!voiceOn || engine === "openai" || !e.detail.reply) return;
    const u = new SpeechSynthesisUtterance(e.detail.reply);
    u.lang = (navigator.language || "fi").startsWith("en") ? "en-US" : "fi-FI";
    u.onend = listenBrowser;
    speechSynthesis.speak(u);
  });

  // ---- the button ---------------------------------------------------------------------------------

  function turnOff() {
    voiceOn = false;
    stopRealtime();
    if (rec) { try { rec.abort(); } catch (e) {} rec = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    paint();
  }

  $("voiceMode").onclick = async () => {
    if (voiceOn) { turnOff(); note(""); return; }
    voiceOn = true;
    paint();
    await ready;
    if (engine !== "openai") { listenBrowser(); return; }
    try { await startRealtime(); }
    catch (e) { console.error("voice:", e); note(`Couldn't start voice mode: ${e.message}`); turnOff(); }
  };
  paint();
})();
