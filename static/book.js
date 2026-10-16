// The comic book: make one from the board, keep them on a shelf, read them page by page.
// Uses app.js's api(), esc(), notes and selected.

(() => {
  const $ = id => document.getElementById(id);
  let book = null;   // the book being read
  let page = 0;      // the left page of the spread (0 = the cover)
  let poll = null;

  const lettering = document.createElement("link");
  lettering.rel = "stylesheet";
  lettering.href = "https://fonts.googleapis.com/css2?family=Comic+Neue:wght@400;700&family=Bangers&display=swap";
  document.head.appendChild(lettering);

  // ---- making one -----------------------------------------------------------------------------

  async function openMaker() {
    const from = $("bookFrom");
    const all = [...notes.values()];
    from.innerHTML = `<option value="">the whole board (${all.length} card${all.length === 1 ? "" : "s"})</option>`
      + (selected && notes.get(selected) ? `<option value="${selected}">just “${esc(notes.get(selected).title || "this card")}”</option>` : "");
    if (selected && notes.get(selected)) from.value = selected;
    $("bookErr").textContent = "";
    $("bookMaker").hidden = false;
    updateEstimate();
    renderShelf();
  }

  async function updateEstimate() {
    const n = +$("bookPages").value;
    $("bookPagesN").textContent = n;
    try {
      const e = await api("GET", `/api/books/estimate?pages=${n}`);
      $("bookEstimate").textContent = `About ${e.images} pictures, roughly $${e.usd.toFixed(2)} (${e.quality} quality).`;
    } catch (_) { $("bookEstimate").textContent = ""; }
  }

  async function makeBook() {
    const go = $("bookGo");
    go.disabled = true;
    go.textContent = "Writing the story…";
    $("bookErr").textContent = "";
    const id = $("bookFrom").value;
    try {
      const r = await fetch("/api/books", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note_ids: id ? [id] : null, direction: $("bookWish").value, pages: +$("bookPages").value }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "Something went wrong.");
      $("bookMaker").hidden = true;
      openBook(j);
    } catch (e) {
      $("bookErr").textContent = e.message;
    }
    go.disabled = false;
    go.textContent = "Write and draw it";
  }

  async function renderShelf() {
    const books = await api("GET", "/api/books");
    $("shelf").innerHTML = books.length ? `<h3>Your shelf</h3><div class="spines">${books.map(b => `
      <button class="spine" data-book="${b.id}">
        <span class="cover-img">${b.cover ? `<img src="/images/${b.cover}" alt="">` : ""}</span>
        <span class="spine-title">${esc(b.title)}</span>
        <span class="muted small">${b.done < b.panels ? `drawing ${b.done}/${b.panels}` : `${b.panels} panels`}</span>
      </button>`).join("")}</div>` : "";
    $("shelf").querySelectorAll("[data-book]").forEach(el => el.onclick = async () => { $("bookMaker").hidden = true; openBook(await api("GET", `/api/books/${el.dataset.book}`)); });
  }

  // ---- reading --------------------------------------------------------------------------------

  function pagesOf(b) {
    const out = [];
    for (const p of b.panels) (out[p.page] ||= []).push(p);
    return out;
  }

  function openBook(b) {
    book = b;
    page = 0;
    $("reader").hidden = false;
    render();
    watch();
  }

  function closeBook() {
    $("reader").hidden = true;
    clearTimeout(poll);
    book = null;
  }

  function watch() {
    clearTimeout(poll);
    if (!book) return;
    const left = book.panels.filter(p => p.status === "waiting" || p.status === "drawing").length;
    $("readerStatus").textContent = left ? `drawing… ${book.panels.length - left}/${book.panels.length}` : "";
    if (left) poll = setTimeout(async () => {
      if (!book) return;
      try { book = await api("GET", `/api/books/${book.id}`); render(); } catch (_) {}
      watch();
    }, 2500);
  }

  function wide() { return window.innerWidth >= 1000; }

  function render() {
    const pages = pagesOf(book);
    const sheets = [{ cover: true }].concat(pages.map((panels, i) => ({ panels, n: i + 1 })));
    const per = wide() ? 2 : 1;
    page = Math.max(0, Math.min(page, sheets.length - 1));
    if (per === 2 && page % 2) page -= 1;
    $("readerTitle").textContent = book.title;
    $("spread").innerHTML = sheets.slice(page, page + per).map(sheetHtml).join("");
    $("spread").classList.toggle("single", per === 1);
    $("pageNo").textContent = page === 0 ? "cover" : `${page}${per === 2 && page + 1 < sheets.length ? "–" + (page + 1) : ""} / ${sheets.length - 1}`;
    $("prevPage").disabled = page === 0;
    $("nextPage").disabled = page + per >= sheets.length;
    $("spread").querySelectorAll("[data-redraw]").forEach(b => b.onclick = async e => {
      e.stopPropagation();
      try { await api("POST", `/api/panels/${b.dataset.redraw}/redraw`); book = await api("GET", `/api/books/${book.id}`); render(); watch(); } catch (_) {}
    });
  }

  function sheetHtml(s) {
    if (s.cover) {
      const first = book.panels.find(p => p.image);
      const who = book.characters.map(c => esc(c.name)).join(" · ");
      return `<div class="sheet-page cover">
        ${first ? `<img class="cover-art" src="/images/${first.image}" alt="">` : `<div class="cover-art blank"></div>`}
        <div class="cover-title">${esc(book.title)}</div>
        ${who ? `<div class="cover-who">${who}</div>` : ""}
      </div>`;
    }
    return `<div class="sheet-page panels n${s.panels.length}">${s.panels.map(panelHtml).join("")}<div class="folio">${s.n}</div></div>`;
  }

  function panelHtml(p, i) {
    const img = p.status === "done" && p.image
      ? `<img src="/images/${p.image}" alt="${esc(p.scene)}">`
      : `<div class="drawing ${p.status}">${p.status === "failed" ? "couldn't draw this one" : "drawing…"}</div>`;
    const caption = p.caption ? `<div class="caption">${esc(p.caption)}</div>` : "";
    const bubbles = p.bubbles.map((b, k) => `<div class="bubble b${k} ${(i + k) % 2 ? "right" : "left"}"><span class="who">${esc(b.speaker)}</span>${esc(b.text)}</div>`).join("");
    return `<figure class="panel">${img}${caption}${bubbles}<button class="redraw" data-redraw="${p.id}" title="Draw this panel again">↻</button></figure>`;
  }

  function turn(d) {
    if (!book) return;
    page += d * (wide() ? 2 : 1);
    render();
  }

  // ---- wiring ---------------------------------------------------------------------------------

  $("bookBtn").onclick = openMaker;
  $("bookPages").oninput = updateEstimate;
  $("bookGo").onclick = makeBook;
  document.querySelectorAll("[data-close]").forEach(b => b.onclick = () => { $("bookMaker").hidden = true; });
  $("bookMaker").addEventListener("pointerdown", e => { if (e.target === $("bookMaker")) $("bookMaker").hidden = true; });
  $("readerClose").onclick = closeBook;
  $("readerShelf").onclick = () => { closeBook(); openMaker(); };
  $("prevPage").onclick = () => turn(-1);
  $("nextPage").onclick = () => turn(1);
  $("spread").addEventListener("click", e => {
    if (e.target.closest("button")) return;
    const r = $("spread").getBoundingClientRect();
    turn(e.clientX < r.left + r.width / 2 ? -1 : 1);
  });
  document.addEventListener("keydown", e => {
    if (!$("reader").hidden) {
      if (e.key === "ArrowRight") turn(1);
      else if (e.key === "ArrowLeft") turn(-1);
      else if (e.key === "Escape") closeBook();
    } else if (!$("bookMaker").hidden && e.key === "Escape") $("bookMaker").hidden = true;
  });
  window.addEventListener("resize", () => { if (book) render(); });
})();
