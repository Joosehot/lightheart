// Voice: one button, on or off. On: it listens, sends what you said, says the reply aloud and
// listens again, like a call. Off: everything stops.
// With an OpenAI key on the server: the microphone is recorded here, transcribed there (accurate, also
// Finnish) and the reply is spoken in a natural voice. Without one: the browser's own (free) speech.
// Recording stops by itself after a moment of silence. The language is the one you speak: the
// transcriber detects it, and the reply is spoken in the reply's own language. Uses app.js's send()
// and its "lightheart:reply" event.

(() => {
  const $ = id => document.getElementById(id);
  const BrowserRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANGS = { fi: "fi-FI", en: "en-US" };
  let voiceOn = false;
  let engine = "browser";
  let listening = false;
  let stopNow = null;   // stops the current listening
  let playing = null;   // the reply being played

  function note(text) { $("voiceNote").textContent = text || ""; }

  function paint() {
    $("voiceMode").textContent = voiceOn ? "Voice on" : "Voice off";
    $("voiceMode").classList.toggle("on", voiceOn);
    $("voiceMode").classList.toggle("listening", listening);
  }

  // Finnish if the text looks Finnish (its letters or common words), else English
  function langOf(text) {
    if (/[äöå]/i.test(text) || /\b(on|ja|ei|se|mitä|että|kuin|minä|sinä|tämä)\b/i.test(text)) return "fi";
    if (/\b(the|and|is|you|what|this|that)\b/i.test(text)) return "en";
    return (navigator.language || "fi").startsWith("en") ? "en" : "fi";
  }

  function stopSpeaking() {
    if (playing) { playing.pause(); playing = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  // ---- listening: recorded here, transcribed on the server ------------------------------------

  async function listenServer() {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { note("The microphone is blocked: allow it in the browser."); turnOff(); return; }
    if (!voiceOn) { stream.getTracks().forEach(tr => tr.stop()); return; }
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
    const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    const parts = [];
    rec.ondataavailable = e => { if (e.data.size) parts.push(e.data); };

    // silence: once speech has been heard, 1.3 s of quiet ends the recording
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const an = ctx.createAnalyser();
    an.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    let heard = false, cancelled = false, quietSince = performance.now(), started = performance.now();
    const tick = setInterval(() => {
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += (v - 128) * (v - 128);
      const level = Math.sqrt(sum / buf.length);
      const t = performance.now();
      if (level > 6) { heard = true; quietSince = t; }
      if ((heard && t - quietSince > 1300) || t - started > 60000) finish();
      else if (!heard && t - started > 15000) { cancelled = true; finish(); }
    }, 100);

    let done = false;
    function finish() {
      if (done) return;
      done = true;
      clearInterval(tick);
      if (rec.state !== "inactive") rec.stop();
    }
    stopNow = () => { cancelled = true; finish(); };
    rec.onstop = async () => {
      stream.getTracks().forEach(tr => tr.stop());
      ctx.close();
      listening = false; stopNow = null; paint();
      if (!voiceOn) return;
      if (cancelled || !heard || !parts.length) { note("I didn't hear anything. Voice is off."); turnOff(); return; }
      note("Writing down what you said…");
      const fd = new FormData();
      fd.append("audio", new Blob(parts, { type: rec.mimeType || "audio/webm" }), type.includes("mp4") ? "speech.mp4" : "speech.webm");
      fd.append("lang", "");
      try {
        const r = await fetch("/api/voice/transcribe", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || "failed");
        note("");
        if (j.text) send(j.text);
        else { note("I didn't catch that."); listen(); }
      } catch (e) { note(e.message); turnOff(); }
    };
    listening = true;
    note("Listening…");
    paint();
    rec.start(250);
  }

  // ---- listening: the browser's own -------------------------------------------------------------

  function listenBrowser() {
    if (!BrowserRec) { note("Voice needs Chrome or Edge (or an OpenAI key on the server)."); turnOff(); return; }
    const rec = new BrowserRec();
    rec.lang = LANGS[(navigator.language || "fi").startsWith("en") ? "en" : "fi"];
    rec.interimResults = true;
    const before = $("input").value;
    let finalText = "", cancelled = false;
    rec.onresult = e => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t; else interim += t;
      }
      $("input").value = (before ? before + " " : "") + finalText + interim;
    };
    rec.onerror = e => { if (e.error !== "aborted" && e.error !== "no-speech") note(`Couldn't listen (${e.error}).`); };
    rec.onend = () => {
      listening = false; stopNow = null; paint();
      if (!voiceOn || cancelled) return;
      const text = $("input").value.trim();
      if (finalText.trim() && text) send(text);
      else { note("I didn't hear anything. Voice is off."); turnOff(); }
    };
    stopNow = () => { cancelled = true; rec.stop(); };
    listening = true;
    note("Listening…");
    paint();
    rec.start();
  }

  function listen() {
    if (!voiceOn || listening) return;
    stopSpeaking();
    if (engine === "openai") listenServer(); else listenBrowser();
  }

  // ---- speaking -----------------------------------------------------------------------------------

  async function speakServer(text, lang) {
    const r = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, lang }) });
    if (!r.ok) throw new Error("speak failed");
    const url = URL.createObjectURL(await r.blob());
    await new Promise(resolve => {
      playing = new Audio(url);
      playing.onended = playing.onerror = playing.onpause = resolve;
      playing.play().catch(resolve);
    });
    URL.revokeObjectURL(url);
    playing = null;
  }

  function speakBrowser(text, lang) {
    return new Promise(resolve => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = LANGS[lang];
      const all = speechSynthesis.getVoices().filter(v => v.lang.toLowerCase().startsWith(lang));
      u.voice = all.find(v => /natural|online|neural/i.test(v.name)) || all[0] || null;
      u.onend = u.onerror = resolve;
      speechSynthesis.speak(u);
    });
  }

  async function speak(text) {
    if (!text) return;
    const lang = langOf(text);
    note("Speaking…");
    try { if (engine === "openai") await speakServer(text, lang); else await speakBrowser(text, lang); }
    catch (e) { if (voiceOn) await speakBrowser(text, lang); }
    note("");
  }

  // a reply came: with voice on it is said aloud, then it listens again
  window.addEventListener("lightheart:reply", async e => {
    if (!voiceOn) return;
    await speak(e.detail.reply);
    listen();
  });

  // ---- the button ---------------------------------------------------------------------------------

  function turnOff() {
    voiceOn = false;
    stopSpeaking();
    if (listening && stopNow) stopNow();
    paint();
  }

  $("voiceMode").onclick = () => {
    if (voiceOn) { turnOff(); note(""); return; }
    voiceOn = true;
    paint();
    listen();
  };
  fetch("/api/voice").then(r => r.json()).then(j => { engine = j.engine; }).catch(() => {});
  if ("speechSynthesis" in window) speechSynthesis.getVoices();
  paint();
})();
