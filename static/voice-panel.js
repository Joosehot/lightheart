// The voice panel: which voice voice mode talks with, how it talks (a comic-book character or your
// own description) and how fast. "Listen" plays a sample in exactly that voice; "Save" keeps it for
// the next time voice mode starts. Uses app.js's esc().

(() => {
  const $ = id => document.getElementById(id);
  let info = null;   // what the server offers
  let pick = null;   // { voice, style, custom, speed }
  let player = null;

  function chips(el, items, key) {
    el.innerHTML = items.map(x => `<button type="button" class="art ${pick[key] === x.id ? "on" : ""}" data-v="${esc(x.id)}">${esc(x.label)}</button>`).join("");
    el.querySelectorAll("[data-v]").forEach(b => b.onclick = () => { pick[key] = b.dataset.v; render(); });
  }

  function render() {
    chips($("vVoices"), info.voices, "voice");
    chips($("vStyles"), info.styles, "style");
    chips($("vSpeeds"), info.speeds.map(s => ({ id: s, label: s[0].toUpperCase() + s.slice(1) })), "speed");
    $("vCustom").hidden = pick.style !== "custom";
  }

  function current() { return { ...pick, custom: $("vCustom").value.trim() }; }

  async function open() {
    $("vErr").textContent = "";
    try { info = await api("GET", "/api/voice/settings"); }
    catch (e) { return; }
    if (!info.voices.length) {
      $("vErr").textContent = "Voices need GEMINI_API_KEY or OPENAI_API_KEY in .env.";
    }
    pick = { ...info.current };
    $("vCustom").value = pick.custom || "";
    render();
    $("voicePanel").hidden = false;
  }

  function close() {
    if (player) { player.pause(); player = null; }
    $("voicePanel").hidden = true;
  }

  async function listen() {
    if (player) { player.pause(); player = null; }
    const b = $("vListen");
    b.disabled = true; b.textContent = "Making a sample…"; $("vErr").textContent = "";
    try {
      const r = await fetch("/api/voice/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(current()) });
      if (!r.ok) throw new Error((await r.json()).detail || "no sample");
      const url = URL.createObjectURL(await r.blob());
      player = new Audio(url);
      b.textContent = "Playing…";
      await new Promise(res => { player.onended = player.onpause = player.onerror = res; player.play().catch(res); });
      URL.revokeObjectURL(url);
    } catch (e) { $("vErr").textContent = e.message; }
    b.disabled = false; b.textContent = "Listen";
  }

  async function save() {
    try {
      pick = await api("PUT", "/api/voice/settings", current());
      close();
      toast("Voice saved: it is used the next time you turn voice on.");
    } catch (e) { $("vErr").textContent = "Couldn't save."; }
  }

  $("voiceSettings").onclick = open;
  $("voiceClose").onclick = close;
  $("voicePanel").onclick = e => { if (e.target === $("voicePanel")) close(); };
  $("vListen").onclick = listen;
  $("vSave").onclick = save;
})();
