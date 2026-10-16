// Voice mode: talk to it and hear it answer.
// With an OpenAI key on the server: the microphone is recorded here, transcribed there (accurate, also
// Finnish) and the reply is spoken in a natural voice. Without one: the browser's own (free) speech.
// Recording stops by itself after a moment of silence. Uses app.js's send() and its
// "lightheart:reply" event.

(() => {
  const $ = id => document.getElementById(id);
  const BrowserRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANGS = { fi: "fi-FI", en: "en-US" };
  let lang = localStorage.getItem("lh-lang") || ((navigator.language || "fi").startsWith("en") ? "en" : "fi");
  let voiceOn = localStorage.getItem("lh-voice") === "1";
  let engine = "browser";
  let listening = false;
  let stopNow = null;   // stops the current listening
  let playing = null;   // the reply being played
  let askedByVoice = false; // the last message was spoken: its reply is spoken too

  function note(text) { $("voiceNote").textContent = text || ""; }

  function paint() {
    $("voiceMode").textContent = voiceOn ? "🔊 voice mode on" : "🔈 voice mode off";
    $("voiceMode").classList.toggle("on", voiceOn);
    $("voiceLang").textContent = lang;
    $("mic").classList.toggle("listening", listening);
  }

  function stopSpeaking() {
    if (playing) { playing.pause(); playing = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  // ---- listening: recorded here, transcribed on the server ------------------------------------

  async function listenServer() {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { note("The microphone is blocked: allow it in the browser."); return; }
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
    let heard = false, quietSince = performance.now(), started = performance.now();
    const tick = setInterval(() => {
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += (v - 128) * (v - 128);
      const level = Math.sqrt(sum / buf.length);
      const t = performance.now();
      if (level > 6) { heard = true; quietSince = t; }
      if ((heard && t - quietSince > 1300) || (!heard && t - started > 7000) || t - started > 60000) finish();
    }, 100);

    let done = false;
    function finish() {
      if (done) return;
      done = true;
      clearInterval(tick);
      if (rec.state !== "inactive") rec.stop();
    }
    stopNow = finish;
    rec.onstop = async () => {
      stream.getTracks().forEach(tr => tr.stop());
      ctx.close();
      listening = false; stopNow = null; paint();
      if (!heard || !parts.length) { note("I didn't hear anything."); return; }
      note("Writing down what you said…");
      const fd = new FormData();
      fd.append("audio", new Blob(parts, { type: rec.mimeType || "audio/webm" }), type.includes("mp4") ? "speech.mp4" : "speech.webm");
      fd.append("lang", lang);
      try {
        const r = await fetch("/api/voice/transcribe", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || "failed");
        note("");
        if (j.text) { askedByVoice = true; send(j.text); }
        else note("I didn't catch that.");
      } catch (e) { note(e.message); }
    };
    listening = true;
    note("Listening… (stops when you stop)");
    paint();
    rec.start(250);
  }

  // ---- listening: the browser's own -------------------------------------------------------------

  function listenBrowser() {
    if (!BrowserRec) { note("Speaking needs Chrome or Edge (or an OpenAI key on the server)."); return; }
    const rec = new BrowserRec();
    rec.lang = LANGS[lang];
    rec.interimResults = true;
    const before = $("input").value;
    let finalText = "";
    rec.onresult = e => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t; else interim += t;
      }
      $("input").value = (before ? before + " " : "") + finalText + interim;
    };
    rec.onerror = e => { if (e.error !== "aborted") note(e.error === "no-speech" ? "I didn't hear anything." : `Couldn't listen (${e.error}).`); };
    rec.onend = () => {
      listening = false; stopNow = null; paint();
      const text = $("input").value.trim();
      if (finalText.trim() && text) { askedByVoice = true; send(text); }
    };
    stopNow = () => rec.stop();
    listening = true;
    note("Listening…");
    paint();
    rec.start();
  }

  function listen() {
    if (listening) { stopNow && stopNow(); return; }
    stopSpeaking();
    if (engine === "openai") listenServer(); else listenBrowser();
  }

  // ---- speaking -----------------------------------------------------------------------------------

  async function speakServer(text) {
    const r = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, lang }) });
    if (!r.ok) throw new Error("speak failed");
    const url = URL.createObjectURL(await r.blob());
    await new Promise(resolve => {
      playing = new Audio(url);
      playing.onended = playing.onerror = resolve;
      playing.play().catch(resolve);
    });
    URL.revokeObjectURL(url);
    playing = null;
  }

  function speakBrowser(text) {
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
    note("Speaking…");
    try { if (engine === "openai") await speakServer(text); else await speakBrowser(text); }
    catch (e) { await speakBrowser(text); }
    note("");
  }

  // a reply came: spoken when you spoke (or in voice mode); in voice mode it then listens again
  window.addEventListener("lightheart:reply", async e => {
    const spoke = askedByVoice;
    askedByVoice = false;
    if (!voiceOn && !spoke) return;
    await speak(e.detail.reply);
    if (voiceOn && !listening) listen();
  });
  // the 🔊 on a reply
  window.addEventListener("lightheart:speak", e => { stopSpeaking(); speak(e.detail.text); });

  // ---- wiring -------------------------------------------------------------------------------------

  $("mic").onclick = listen;
  $("voiceMode").onclick = () => {
    voiceOn = !voiceOn;
    localStorage.setItem("lh-voice", voiceOn ? "1" : "0");
    if (!voiceOn) { stopSpeaking(); if (listening && stopNow) stopNow(); note(""); }
    else { note("Talk to me: click 🎤. After each reply I listen again."); listen(); }
    paint();
  };
  $("voiceLang").onclick = () => { lang = lang === "fi" ? "en" : "fi"; localStorage.setItem("lh-lang", lang); paint(); };
  fetch("/api/voice").then(r => r.json()).then(j => {
    engine = j.engine;
    $("mic").title = engine === "openai" ? "Speak (stops by itself when you stop)" : "Speak (the browser's own voice)";
  }).catch(() => {});
  if ("speechSynthesis" in window) speechSynthesis.getVoices();
  paint();
})();
