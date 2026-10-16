// Voice mode: talk to it and hear it answer. The browser's own speech recognition and speech
// synthesis (free, no keys; Chrome and Edge recognise speech, Edge has the best Finnish voices).
// Uses app.js's send() and its "lightheart:reply" event.

(() => {
  const $ = id => document.getElementById(id);
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANGS = { fi: "fi-FI", en: "en-US" };
  let lang = localStorage.getItem("lh-lang") || ((navigator.language || "fi").startsWith("en") ? "en" : "fi");
  let voiceOn = localStorage.getItem("lh-voice") === "1";
  let rec = null;
  let listening = false;

  function note(text) { $("voiceNote").textContent = text || ""; }

  function paint() {
    $("voiceMode").textContent = voiceOn ? "🔊 voice mode on" : "🔈 voice mode off";
    $("voiceMode").classList.toggle("on", voiceOn);
    $("voiceLang").textContent = lang;
    $("mic").classList.toggle("listening", listening);
  }

  // ---- listening --------------------------------------------------------------------------------

  function listen() {
    if (!Recognition) { note("Speaking needs Chrome or Edge."); return; }
    if (listening) { rec && rec.stop(); return; }
    speechSynthesis.cancel();
    rec = new Recognition();
    rec.lang = LANGS[lang];
    rec.interimResults = true;
    rec.continuous = false;
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
    rec.onerror = e => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") note("The microphone is blocked: allow it in the browser.");
      else if (e.error === "no-speech") note("I didn't hear anything.");
      else if (e.error !== "aborted") note(`Couldn't listen (${e.error}).`);
    };
    rec.onend = () => {
      listening = false;
      paint();
      const text = $("input").value.trim();
      if (finalText.trim() && text) send(text);
    };
    listening = true;
    note("Listening…");
    paint();
    rec.start();
  }

  // ---- speaking ---------------------------------------------------------------------------------

  function voiceFor(code) {
    const all = speechSynthesis.getVoices().filter(v => v.lang.replace("_", "-").toLowerCase().startsWith(code.slice(0, 2)));
    // the natural (online, neural) voices sound best; then the local ones
    return all.find(v => /natural|online|neural/i.test(v.name)) || all.find(v => v.lang.toLowerCase() === code.toLowerCase()) || all[0];
  }

  function speak(text) {
    return new Promise(resolve => {
      if (!("speechSynthesis" in window) || !text) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = LANGS[lang];
      const v = voiceFor(LANGS[lang]);
      if (v) u.voice = v;
      u.rate = 1.02;
      u.onend = resolve;
      u.onerror = resolve;
      note("Speaking…");
      speechSynthesis.speak(u);
    });
  }

  // a reply came: in voice mode it is read aloud, then it listens again
  window.addEventListener("lightheart:reply", async e => {
    if (!voiceOn) return;
    await speak(e.detail.reply);
    note("");
    if (voiceOn && Recognition) listen();
  });

  // ---- wiring -----------------------------------------------------------------------------------

  $("mic").onclick = listen;
  $("voiceMode").onclick = () => {
    voiceOn = !voiceOn;
    localStorage.setItem("lh-voice", voiceOn ? "1" : "0");
    if (!voiceOn) { speechSynthesis.cancel(); if (listening && rec) rec.abort(); note(""); }
    else if (!Recognition) note("Replies are read aloud; to speak yourself, use Chrome or Edge.");
    else note("Click 🎤 and talk. After each reply it listens again.");
    paint();
  };
  $("voiceLang").onclick = () => {
    lang = lang === "fi" ? "en" : "fi";
    localStorage.setItem("lh-lang", lang);
    paint();
  };
  if (!Recognition) $("mic").title = "Speaking needs Chrome or Edge";
  speechSynthesis.getVoices(); // starts loading the voices
  paint();
})();
