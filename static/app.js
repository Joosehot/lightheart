// Lightheart's page: the chat on the left, the scrapbook board on the right.
// Every style comes from /api/styles (the server's styles.py); nothing else is rendered.

const $ = id => document.getElementById(id);
let STYLES = null;
let notes = new Map();
let selected = null;
let busy = false;

const EXAMPLE = "A lighthouse keeper who collects lost letters and answers them, but signs every reply with a different name.";

// ---- api -----------------------------------------------------------------------------------------

async function api(method, path, body) {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status}`);
  return r.json();
}

// save a card's changes, debounced per card (so a drag saves once, on drop)
const pending = new Map();
function save(id, fields, wait = 250) {
  const p = pending.get(id) || { fields: {} };
  Object.assign(p.fields, fields);
  clearTimeout(p.timer);
  p.timer = setTimeout(async () => {
    pending.delete(id);
    try { const n = await api("PATCH", `/api/notes/${id}`, p.fields); notes.set(n.id, n); }
    catch (e) { toast("Couldn't save that change."); }
  }, wait);
  pending.set(id, p);
}

// ---- rendering ---------------------------------------------------------------------------------

const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// the first occurrence of each phrase, wrapped in a highlighter swash
function highlighted(body, phrases) {
  const spans = [];
  for (const p of phrases || []) {
    if (!p) continue;
    const i = body.indexOf(p);
    if (i >= 0 && !spans.some(s => i < s[1] && i + p.length > s[0])) spans.push([i, i + p.length]);
  }
  spans.sort((a, b) => a[0] - b[0]);
  let out = "", at = 0;
  for (const [a, b] of spans) { out += esc(body.slice(at, a)) + "<mark>" + esc(body.slice(a, b)) + "</mark>"; at = b; }
  return out + esc(body.slice(at));
}

function paletteOf(n) { return STYLES.palettes[n.palette] || STYLES.palettes.butter; }

function renderCard(n, how) {
  let el = document.querySelector(`.card[data-id="${n.id}"]`);
  const fresh = !el;
  if (fresh) {
    el = document.createElement("div");
    el.className = "card";
    el.dataset.id = n.id;
    el.innerHTML = `<div class="tape"></div><div class="sticker"></div><h3 class="title"></h3><p class="body"></p><div class="tags"></div>`;
    attachCard(el);
    $("board").appendChild(el);
  }
  const p = paletteOf(n);
  el.style.left = n.x + "px";
  el.style.top = n.y + "px";
  el.style.setProperty("--rot", `${n.rotation}deg`);
  el.style.transform = `rotate(${n.rotation}deg)`;
  el.style.background = p.paper;
  el.style.color = p.ink;
  el.style.setProperty("--hl", hexA(p.highlight, .62));
  el.querySelector(".tape").style.display = n.tape ? "" : "none";
  el.querySelector(".tape").style.background = p.tape;
  el.querySelector(".sticker").textContent = STYLES.stickers[n.sticker] || "";
  const title = el.querySelector(".title");
  if (title.contentEditable !== "true") title.textContent = n.title;
  title.style.fontFamily = STYLES.fonts[n.font] || STYLES.fonts.caveat;
  const body = el.querySelector(".body");
  if (body.contentEditable !== "true") body.innerHTML = highlighted(n.body, n.highlights);
  el.querySelector(".tags").innerHTML = (n.tags || []).map(t => `<span class="tag">#${esc(t)}</span>`).join("");
  el.classList.toggle("selected", selected === n.id);
  if (how) { el.classList.remove("enter", "changed"); void el.offsetWidth; el.classList.add(how); }
  return el;
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${a})`;
}

function renderMessages(msgs) {
  const box = $("messages");
  box.innerHTML = "";
  if (!msgs.length) {
    box.innerHTML = `<div class="empty"><h2>What's on your mind?</h2><div>Tell me a half-formed idea, a line, a character. I'll help it grow and pin it to your board.</div><button class="chip" id="example">“${esc(EXAMPLE)}”</button></div>`;
    $("example").onclick = () => { $("input").value = EXAMPLE; $("input").focus(); };
    return;
  }
  for (const m of msgs) addMessage(m.role, m.content);
}

function addMessage(role, text, extra = "") {
  const empty = document.querySelector(".empty");
  if (empty) empty.remove();
  $("island").classList.remove("folded"); // a new message opens the conversation again
  const d = document.createElement("div");
  d.className = `msg ${role} ${extra}`;
  d.textContent = text;
  $("messages").appendChild(d);
  $("messages").scrollTop = $("messages").scrollHeight;
  return d;
}

// ---- cards: drag, select, edit -----------------------------------------------------------------

function attachCard(el) {
  let start = null;
  el.addEventListener("pointerdown", e => {
    if (e.target.isContentEditable) return;
    const n = notes.get(el.dataset.id);
    // the target is kept: with the pointer captured, pointerup's target is the card itself
    start = { x: e.clientX, y: e.clientY, nx: n.x, ny: n.y, moved: false, target: e.target };
    el.setPointerCapture(e.pointerId);
  });
  el.addEventListener("pointermove", e => {
    if (!start) return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y;
    if (!start.moved && Math.hypot(dx, dy) < 4) return;
    if (!start.moved) { start.moved = true; el.classList.add("dragging"); closePopover(); }
    const n = notes.get(el.dataset.id);
    n.x = Math.max(0, start.nx + dx); n.y = Math.max(0, start.ny + dy);
    el.style.left = n.x + "px"; el.style.top = n.y + "px";
  });
  el.addEventListener("pointerup", e => {
    if (!start) return;
    const n = notes.get(el.dataset.id);
    if (start.moved) { el.classList.remove("dragging"); save(n.id, { x: n.x, y: n.y }, 300); }
    else if (selected === n.id && start.target.closest(".title, .body")) editField(el, start.target.closest(".title, .body"));
    else select(n.id);
    start = null;
  });
}

function editField(el, field) {
  const n = notes.get(el.dataset.id);
  const isTitle = field.classList.contains("title");
  field.contentEditable = "true";
  if (!isTitle) field.textContent = n.body; // plain text while editing
  field.focus();
  const range = document.createRange(); range.selectNodeContents(field); range.collapse(false);
  const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
  const done = () => {
    field.contentEditable = "false";
    const text = field.innerText.replace(/\n{3,}/g, "\n\n").trim();
    const key = isTitle ? "title" : "body";
    if (text !== n[key]) { n[key] = text; save(n.id, { [key]: text }, 0); }
    renderCard(n);
  };
  field.addEventListener("blur", done, { once: true });
  field.onkeydown = e => {
    if (e.key === "Escape" || (isTitle && e.key === "Enter")) { e.preventDefault(); field.blur(); }
  };
}

function select(id) {
  const prev = selected;
  selected = id;
  for (const pid of [prev, id]) if (pid && notes.get(pid)) renderCard(notes.get(pid));
  if (id) openPopover(id); else closePopover();
}

function openPopover(id) {
  const n = notes.get(id);
  const el = document.querySelector(`.card[data-id="${id}"]`);
  const pop = $("popover");
  const pal = Object.entries(STYLES.palettes).map(([k, p]) => `<button class="swatch ${n.palette === k ? "on" : ""}" data-palette="${k}" title="${k}" style="background:${p.paper};box-shadow: inset 0 0 0 7px ${p.paper}, inset 0 0 0 15px ${p.highlight}"></button>`).join("");
  const fonts = Object.entries(STYLES.fonts).map(([k, f]) => `<button class="font-btn ${n.font === k ? "on" : ""}" data-font="${k}" style="font-family:${f}">${STYLES.font_labels[k]}</button>`).join("");
  const stick = [`<button class="stick ${!n.sticker ? "on" : ""}" data-sticker="" title="none">∅</button>`].concat(Object.entries(STYLES.stickers).map(([k, s]) => `<button class="stick ${n.sticker === k ? "on" : ""}" data-sticker="${k}" title="${k}">${s}</button>`)).join("");
  pop.innerHTML = `<h4>Color</h4><div class="swatches">${pal}</div><h4>Title font</h4><div class="fonts">${fonts}</div><h4>Sticker</h4><div class="stickers">${stick}</div>
    <div class="pop-row"><label><input type="checkbox" id="tapeBox" ${n.tape ? "checked" : ""}> washi tape</label><button class="danger" id="delBtn">Delete</button></div>
    <div class="pop-row" style="margin-top:6px;color:var(--ink-soft);font-size:12px">Click the title or text to edit it.</div>`;
  pop.hidden = false;
  const r = el.getBoundingClientRect();
  const left = Math.min(window.innerWidth - 280, Math.max(8, r.right + 14));
  pop.style.left = left + "px";
  pop.style.top = Math.max(8, Math.min(window.innerHeight - pop.offsetHeight - 8, r.top)) + "px";
  const set = fields => { Object.assign(n, fields); renderCard(n); openPopover(id); save(id, fields, 0); };
  pop.querySelectorAll("[data-palette]").forEach(b => b.onclick = () => set({ palette: b.dataset.palette }));
  pop.querySelectorAll("[data-font]").forEach(b => b.onclick = () => set({ font: b.dataset.font }));
  pop.querySelectorAll("[data-sticker]").forEach(b => b.onclick = () => set({ sticker: b.dataset.sticker || null }));
  $("tapeBox").onchange = e => set({ tape: e.target.checked });
  $("delBtn").onclick = () => removeCard(id);
}

function closePopover() { $("popover").hidden = true; }

async function removeCard(id) {
  const n = notes.get(id);
  closePopover();
  selected = null;
  document.querySelector(`.card[data-id="${id}"]`)?.remove();
  notes.delete(id);
  try { await api("DELETE", `/api/notes/${id}`); } catch (e) { toast("Couldn't delete it."); return; }
  toast("Card deleted.", "Undo", async () => {
    const { id: _, created_at, updated_at, source_message_id, ...fields } = n;
    const back = await api("POST", "/api/notes", fields);
    notes.set(back.id, back);
    renderCard(back, "enter");
  });
}

let toastTimer = null;
function toast(text, action, onAction) {
  const t = $("toast");
  t.innerHTML = `<span>${esc(text)}</span>` + (action ? `<button>${esc(action)}</button>` : "");
  t.hidden = false;
  if (action) t.querySelector("button").onclick = () => { t.hidden = true; onAction(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 6000);
}

function revealCard(id) {
  const el = document.querySelector(`.card[data-id="${id}"]`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
}

// ---- chat --------------------------------------------------------------------------------------

async function send(text) {
  if (busy || !text.trim()) return;
  busy = true; $("send").disabled = true;
  addMessage("user", text.trim());
  $("input").value = "";
  $("input").style.height = "auto";
  const thinking = addMessage("assistant", "thinking…", "thinking");
  try {
    const r = await api("POST", "/api/chat", { content: text });
    thinking.remove();
    if (r.reply) addMessage("assistant", r.reply);
    window.dispatchEvent(new CustomEvent("lightheart:reply", { detail: { reply: r.reply } })); // voice.js reads it aloud
    for (const n of r.notes_changed) {
      const how = notes.has(n.id) ? "changed" : "enter";
      notes.set(n.id, n);
      renderCard(n, how);
    }
    if (r.notes_changed.length) setTimeout(() => revealCard(r.notes_changed[0].id), 80);
  } catch (e) {
    thinking.remove();
    addMessage("assistant", "I couldn't reach the server. Is it running?", "error");
  }
  busy = false; $("send").disabled = false; $("input").focus();
}

// ---- start -------------------------------------------------------------------------------------

async function start() {
  STYLES = await api("GET", "/api/styles");
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = `https://fonts.googleapis.com/css2?family=${STYLES.google_fonts}&display=swap`;
  document.head.appendChild(link);
  const b = await api("GET", "/api/board");
  for (const n of b.notes) { notes.set(n.id, n); renderCard(n); }
  renderMessages(b.messages);

  $("composer").onsubmit = e => { e.preventDefault(); send($("input").value); };
  $("input").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("input").value); }
  });
  // the input grows with what is written, up to a few lines
  const grow = () => { const t = $("input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; };
  $("input").addEventListener("input", grow);
  $("fold").onclick = () => $("island").classList.toggle("folded");
  $("addCard").onclick = async () => {
    const n = await api("POST", "/api/notes", {});
    notes.set(n.id, n);
    const el = renderCard(n, "enter");
    revealCard(n.id);
    select(n.id);
    setTimeout(() => editField(el, el.querySelector(".title")), 340);
  };
  $("board").addEventListener("pointerdown", e => { if (e.target === $("board")) select(null); });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { if (document.activeElement?.isContentEditable) return; select(null); }
  });
  window.addEventListener("resize", () => { if (selected) openPopover(selected); });
  $("boardWrap").addEventListener("scroll", () => { if (selected) openPopover(selected); });
}

start();
