// The sidebar: every idea is a board of its own, with its past chats under it.
// Uses app.js's api(), esc(), CUR and openIdea().

(() => {
  const $ = id => document.getElementById(id);

  function ago(iso) {
    const s = (Date.now() - new Date(iso)) / 1000;
    if (s < 60) return "now";
    if (s < 3600) return `${Math.floor(s / 60)} min`;
    if (s < 86400) return `${Math.floor(s / 3600)} h`;
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  async function renderSidebar() {
    const boards = await api("GET", "/api/boards");
    $("ideaList").innerHTML = boards.map(b => {
      const open = CUR.board && b.id === CUR.board.id;
      const chats = open ? `<div class="chats">
          ${b.chats.map(c => `<div class="chat-row ${CUR.chat && c.id === CUR.chat.id ? "on" : ""}" data-chat="${c.id}" data-board="${b.id}">
            <span class="chat-title" title="Double-click to rename">${esc(c.title)}</span><span class="when">${ago(c.updated_at)}</span>
            <button class="x" data-del-chat="${c.id}" title="Delete this chat">×</button></div>`).join("")}
          <button class="new-chat" data-new-chat="${b.id}">＋ new chat</button>
        </div>` : "";
      return `<section class="idea ${open ? "open" : ""}">
        <div class="idea-row" data-board="${b.id}">
          <span class="idea-title" title="Double-click to rename">${esc(b.title)}</span>
          <span class="when">${b.notes} note${b.notes === 1 ? "" : "s"}</span>
          <button class="x" data-del-board="${b.id}" title="Delete this idea">×</button>
        </div>${chats}</section>`;
    }).join("");

    const list = $("ideaList");
    list.querySelectorAll(".idea-row").forEach(el => el.onclick = e => { if (!e.target.closest("button")) openIdea(el.dataset.board); });
    list.querySelectorAll(".chat-row").forEach(el => el.onclick = e => { if (!e.target.closest("button")) openIdea(el.dataset.board, el.dataset.chat); });
    list.querySelectorAll("[data-new-chat]").forEach(el => el.onclick = async () => {
      const c = await api("POST", `/api/boards/${el.dataset.newChat}/chats`);
      openIdea(el.dataset.newChat, c.id);
    });
    list.querySelectorAll("[data-del-chat]").forEach(el => el.onclick = async () => {
      if (!confirm("Delete this chat? Its messages go; the notes stay.")) return;
      await api("DELETE", `/api/chats/${el.dataset.delChat}`);
      openIdea(CUR.board.id, el.dataset.delChat === CUR.chat.id ? null : CUR.chat.id);
    });
    list.querySelectorAll("[data-del-board]").forEach(el => el.onclick = async () => {
      if (!confirm("Delete this idea with all its notes, chats and comic books?")) return;
      await api("DELETE", `/api/boards/${el.dataset.delBoard}`);
      openIdea(el.dataset.delBoard === CUR.board.id ? null : CUR.board.id);
    });
    list.querySelectorAll(".idea-title, .chat-title").forEach(el => el.ondblclick = e => rename(e, el));
  }

  function rename(e, el) {
    e.stopPropagation();
    const row = el.closest("[data-chat], [data-board]");
    const isChat = !!row.dataset.chat;
    el.contentEditable = "true";
    el.focus();
    document.getSelection().selectAllChildren(el);
    const done = async () => {
      el.contentEditable = "false";
      const title = el.textContent.trim();
      if (title) await api("PATCH", isChat ? `/api/chats/${row.dataset.chat}` : `/api/boards/${row.dataset.board}`, { title });
      if (!isChat && CUR.board.id === row.dataset.board) document.title = `${title} · Lightheart`;
      renderSidebar();
    };
    el.addEventListener("blur", done, { once: true });
    el.onkeydown = k => { if (k.key === "Enter" || k.key === "Escape") { k.preventDefault(); el.blur(); } };
  }

  function toggle(open) {
    $("ideas").hidden = !open;
    document.body.classList.toggle("ideas-open", open);
    localStorage.setItem("lh-ideas", open ? "1" : "0");
    if (open) renderSidebar();
  }

  $("ideasToggle").onclick = () => toggle($("ideas").hidden);
  $("ideasClose").onclick = () => toggle(false);
  $("newIdea").onclick = async () => {
    const title = prompt("What's the new idea called?", "New idea");
    if (title === null) return;
    const r = await api("POST", "/api/boards", { title });
    openIdea(r.board.id, r.chat.id);
  };
  window.renderSidebar = renderSidebar;
  if (localStorage.getItem("lh-ideas") === "1" && window.innerWidth > 900) toggle(true);
})();
