// The same notes seen four ways: Scrapbook (the free board), Post-it, Notes and Comic.
// Every note is in every view; clicking a title or text edits it in place. Uses app.js's notes,
// STYLES, esc(), highlighted(), save() and renderCard().

(() => {
  const $ = id => document.getElementById(id);
  let view = localStorage.getItem("lh-view") || "scrapbook";

  const fonts = document.createElement("link");
  fonts.rel = "stylesheet";
  fonts.href = "https://fonts.googleapis.com/css2?family=Bangers&family=Comic+Neue:wght@400;700&family=Permanent+Marker&family=Inter:wght@400;600;700&display=swap";
  document.head.appendChild(fonts);

  // a soft palette's bright sticky-note twin, for the Post-it view
  const BRIGHT = { peach: "tangerine", sage: "lime", lavender: "magenta", butter: "sunflower", sky: "aqua", rose: "coral" };

  function ordered() {
    return [...notes.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }

  function set(v) {
    view = v;
    localStorage.setItem("lh-view", v);
    document.querySelectorAll("#views [data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === v));
    const alt = v !== "scrapbook";
    $("boardWrap").hidden = alt;
    $("altView").hidden = !alt;
    $("altView").dataset.view = v;
    document.body.dataset.view = v;
    if (alt) { closePopover(); render(); }
  }

  function render() {
    if (view === "scrapbook") return;
    const list = ordered();
    if (!list.length) {
      $("altView").innerHTML = `<div class="alt-empty">No notes yet. Tell me an idea below.</div>`;
      return;
    }
    $("altView").innerHTML = `<div class="alt-inner">${list.map(n => view === "postit" ? postit(n) : view === "notes" ? plain(n) : comic(n)).join("")}</div>`;
    $("altView").querySelectorAll("[data-edit]").forEach(el => el.addEventListener("click", () => edit(el)));
  }

  const tags = n => (n.tags || []).map(t => `<span class="t">#${esc(t)}</span>`).join("");
  const sticker = n => STYLES.stickers[n.sticker] || "";

  function postit(n) {
    const p = STYLES.palettes[BRIGHT[n.palette] || n.palette] || STYLES.palettes.sunflower;
    const tilt = ((n.rotation || 0) * 0.8).toFixed(1);
    return `<article class="pi" style="--bg:${p.paper};--ink:${p.ink};--hl:${hexA(p.highlight, .7)};--tilt:${tilt}deg">
      <span class="pin"></span>
      <h3 data-edit="title" data-id="${n.id}">${esc(n.title)}</h3>
      <p data-edit="body" data-id="${n.id}">${highlighted(n.body, n.highlights)}</p>
      <span class="pi-sticker">${sticker(n)}</span>
    </article>`;
  }

  function plain(n) {
    const p = paletteOf(n);
    const day = new Date(n.updated_at).toLocaleDateString(undefined, { day: "numeric", month: "short" });
    return `<article class="pl" style="--dot:${p.accent};--hl:${hexA(p.highlight, .55)}">
      <div class="pl-meta"><span class="dot"></span>${day}${n.tags && n.tags.length ? " · " + tags(n) : ""}</div>
      <h3 data-edit="title" data-id="${n.id}">${esc(n.title)}</h3>
      <p data-edit="body" data-id="${n.id}">${highlighted(n.body, n.highlights)}</p>
    </article>`;
  }

  function comic(n) {
    const p = paletteOf(n);
    return `<article class="cm" style="--bg:${p.paper};--accent:${p.accent};--hl:${hexA(p.highlight, .8)}">
      <div class="cm-cap" data-edit="title" data-id="${n.id}">${esc(n.title)}</div>
      <div class="cm-art"><span class="cm-pow">${sticker(n) || "✦"}</span></div>
      <div class="cm-bub"><p data-edit="body" data-id="${n.id}">${highlighted(n.body, n.highlights)}</p></div>
    </article>`;
  }

  function edit(el) {
    if (el.isContentEditable) return;
    const n = notes.get(el.dataset.id);
    const key = el.dataset.edit;
    el.contentEditable = "true";
    el.textContent = n[key];
    el.focus();
    const done = () => {
      el.contentEditable = "false";
      const text = el.innerText.trim();
      if (text !== n[key]) { n[key] = text; save(n.id, { [key]: text }, 0); renderCard(n); }
      render();
    };
    el.addEventListener("blur", done, { once: true });
    el.onkeydown = e => { if (e.key === "Escape" || (key === "title" && e.key === "Enter")) { e.preventDefault(); el.blur(); } };
  }

  document.querySelectorAll("#views [data-view]").forEach(b => b.onclick = () => set(b.dataset.view));
  // when the chat makes or changes a card, the view shows it too
  window.addEventListener("lightheart:reply", () => setTimeout(render, 50));
  window.lightheartViews = { render };
  $("addCard").addEventListener("click", () => setTimeout(render, 400));
  // wait for the board to load before the first render
  const ready = setInterval(() => { if (STYLES) { clearInterval(ready); set(view); } }, 50);
})();
