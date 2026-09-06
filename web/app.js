const $ = (id) => document.getElementById(id);
const stream = $("stream");
const PRESET_ENGINE = {
  cos: "board",
  think: "Hermes Agent",
  builder: "OpenCode",
  research: "fetch / Hermes",
  ops: "Hermes Agent"
};
let preset = "cos";
let projectId = "";
let workerId = "";
let expanded = new Set();
let inboxSeen = new Set();
let modelQuery = "";
let org = {};
let stage = "chat";
let brains = {};
let cfg = {};
let ocStarted = false;
let hermesStarted = false;
let hermesFailed = false;
let liveRunId = "";
let liveLane = "";
let liveAbort = null;
/** @type {Map<string, { runId: string, abort: AbortController | null, lane: string, projectId: string, workerId: string }>} */
const lives = new Map();
/** @type {Map<string, Array<{ message: string, preset: string, quote: string }>>} */
const messageQueues = new Map();
/** @type {Map<string, { step: number, total: number, last_result: string }>} */
const chainContexts = new Map();
let focusedLane = "";
let unreadLanes = new Set();
let hydratingHistory = false;
let seenCron = new Set();
let seenJobIds = new Set();
let replyQuote = "";
let lastOcFolder = "";
let lastHermesHome = "";
let pendingAttachments = [];

function aimKey(pid, wid) {
  return `${pid == null ? projectId : pid}::${wid == null ? workerId : wid}`;
}

function liveFor(key) {
  return lives.get(key || aimKey()) || null;
}

function queueFor(key) {
  const id = key || aimKey();
  if (!messageQueues.has(id)) messageQueues.set(id, []);
  return messageQueues.get(id);
}

function syncLiveFromAim() {
  const live = liveFor(aimKey());
  liveRunId = live ? live.runId : "";
  liveLane = live ? (live.lane || "") : "";
  liveAbort = live ? live.abort : null;
  lockComposer(Boolean(cfg.has_key));
  paintLanes();
  paintQueueChip();
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function addAttachment(file) {
  const MAX_SIZE = 50 * 1024 * 1024;
  if (file.size > MAX_SIZE) {
    showHint("File too large (max 50 MB)");
    return;
  }
  if (pendingAttachments.some((a) => a.file.name === file.name && a.file.size === file.size)) {
    return;
  }
  pendingAttachments.push({ file, id: Math.random().toString(36).slice(2) });
  paintAttachments();
}

function removeAttachment(id) {
  pendingAttachments = pendingAttachments.filter((a) => a.id !== id);
  paintAttachments();
}

function clearAttachments() {
  pendingAttachments = [];
  paintAttachments();
}

function paintAttachments() {
  const preview = $("attachmentsPreview");
  if (!preview) return;
  if (!pendingAttachments.length) {
    preview.classList.add("hidden");
    preview.innerHTML = "";
    return;
  }
  preview.classList.remove("hidden");
  preview.innerHTML = pendingAttachments.map((att) => {
    const isImage = att.file.type.startsWith("image/");
    const thumbHtml = isImage
      ? `<img src="${URL.createObjectURL(att.file)}" alt="" class="attachment-thumb" />`
      : `<div class="attachment-icon">📄</div>`;
    return `
      <div class="attachment-item" data-id="${att.id}">
        ${thumbHtml}
        <div class="attachment-info">
          <div class="attachment-name" title="${escapeHtml(att.file.name)}">${escapeHtml(att.file.name)}</div>
          <div class="attachment-size">${formatFileSize(att.file.size)}</div>
        </div>
        <button type="button" class="attachment-remove" data-id="${att.id}">×</button>
      </div>
    `;
  }).join("");
  preview.querySelectorAll(".attachment-remove").forEach((btn) => {
    btn.addEventListener("click", () => removeAttachment(btn.dataset.id));
  });
}

function showHint(msg) {
  const hint = $("workHint");
  if (!hint) return;
  hint.textContent = msg;
  hint.classList.remove("hidden");
  setTimeout(() => hint.classList.add("hidden"), 3000);
}
const PANEL_TITLES = {
  you: "You",
  account: "You",
  workspace: "Folder",
  folder: "Folder",
  keys: "Keys",
  ceo: "This CEO",
  models: "Models",
  connectors: "Connectors",
  git: "Git",
  memory: "Memory",
  usage: "Usage",
  import: "Import",
  channels: "Channels",
  jobs: "Usage",
  about: "About"
};
const PROVIDER_STAGE = { nous: "hermes" };

function prettyValue(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch (_err) {
    return String(value);
  }
}

function renderKv(el, rows) {
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = `<p class="muted">Nothing to show yet.</p>`;
    return;
  }
  el.innerHTML = rows.map(([key, value]) => (
    `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(prettyValue(value))}</dd></div>`
  )).join("");
}

function zenRows(zen) {
  if (!zen) return [["Status", "not loaded"]];
  const rows = [
    ["Connected", zen.connected ? "yes" : "no"],
    ["Source", zen.source || "—"]
  ];
  if (zen.http_status) rows.push(["HTTP", zen.http_status]);
  if (zen.note) rows.push(["Note", zen.note]);
  if (zen.usage_error) rows.push(["Usage error", zen.usage_error]);
  const usage = zen.usage;
  if (usage && typeof usage === "object" && !Array.isArray(usage)) {
    Object.entries(usage).forEach(([key, value]) => {
      if (key === "raw") return;
      rows.push([key, value]);
    });
  } else if (usage) {
    rows.push(["Usage", usage]);
  }
  return rows;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function renderEngines(engines, targetId) {
  const h = engines.hermes || {};
  const o = engines.opencode || {};
  const el = $(targetId);
  if (!el) return;
  const hermesHint = (!h.present && h.install_cmd)
    ? `<pre class="stats">${escapeHtml(h.install_cmd)}</pre>`
    : "";
  el.innerHTML = `
    <div class="${h.present ? "" : "missing"}">Hermes: <b>${h.present ? "found" : "missing"}</b></div>
    <div class="${o.present ? "" : "missing"}">OpenCode: <b>${o.present ? "found" : "missing"}</b></div>
    ${hermesHint}
  `;
}

function indexNow(text) {
  const match = String(text || "").match(/^Now:\s*(.*)$/m);
  return (match && match[1].trim()) || "source of truth";
}

function indexField(text, field) {
  const pattern = new RegExp(`^${field}:\\s*(.*)$`, "m");
  const match = String(text || "").match(pattern);
  return (match && match[1].trim()) || "—";
}

function renderIndex(text) {
  if ($("indexCard")) $("indexCard").textContent = text || "(empty brief)";
  if ($("indexSummary")) $("indexSummary").textContent = `Brief · ${indexNow(text)}`;
}

function moneyPair(input, output) {
  const a = Number(input);
  const b = Number(output);
  if (!Number.isFinite(a) && !Number.isFinite(b)) return "—";
  return `$${a.toFixed(2)} in · $${b.toFixed(2)} out`;
}

function optionLabel(opt) {
  const price = opt.id ? moneyPair(opt.in_usd, opt.out_usd) : "";
  const rec = opt.recommended ? "recommended" : "";
  return [opt.label, price, rec].filter(Boolean).join(" · ");
}

function modelName(id) {
  const raw = String(id || "").trim();
  if (!raw) return "";
  const row = ((cfg.catalog && cfg.catalog.models) || []).find((item) => item.id === raw);
  return (row && row.label) || raw.split("/").filter(Boolean).slice(-1)[0] || raw;
}

function defaultModelRow(seat, inheritFromStaff) {
  const models = (cfg.catalog && cfg.catalog.models) || [];
  if (inheritFromStaff) {
    const staffId = String(((cfg.seats && cfg.seats[seat.id]) || {}).model || "").trim();
    if (staffId) return models.find((row) => row.id === staffId) || { id: staffId, label: modelName(staffId) };
  }
  if (seat.id === "chat") {
    const rec = (cfg.catalog && cfg.catalog.recommended_chat) || "";
    if (rec) return models.find((row) => row.id === rec) || { id: rec, label: modelName(rec) };
  }
  const engine = seat.engine || "";
  return models.find((row) => row.id && row.default && (!engine || (row.engines || []).includes(engine))) || null;
}

function autoPick(seatId) {
  return ((cfg.catalog && cfg.catalog.auto) || {})[seatId] || {};
}

function defaultModelOptionLabel(seat, inheritFromStaff) {
  const auto = autoPick(seat.id);
  if (auto.label) {
    return inheritFromStaff ? `Auto / inherit — ${auto.label}` : `Auto — ${auto.label}`;
  }
  const row = defaultModelRow(seat, inheritFromStaff);
  if (row && (row.label || row.id)) return `${row.label || modelName(row.id)} (default)`;
  return inheritFromStaff ? "inherit Chief of Staff" : "Auto";
}

function defaultKeyAccount(inheritFromStaff) {
  const accounts = (cfg.keyring && cfg.keyring.accounts) || [];
  const order = (cfg.keyring && cfg.keyring.fallback) || [];
  const staffId = String(cfg.profile_account_id || "").trim();
  const id = inheritFromStaff ? (staffId || order[0] || "") : (order[0] || staffId || "");
  return accounts.find((row) => row.id === id) || null;
}

function groupKey(opt) {
  return opt.provider_label || opt.provider || "Other";
}

function seatOptions(options, selectedId) {
  const groups = [];
  const index = new Map();
  (options || []).forEach((opt) => {
    const key = groupKey(opt);
    if (!index.has(key)) {
      const group = { key, items: [] };
      index.set(key, group);
      groups.push(group);
    }
    index.get(key).items.push(opt);
  });
  const renderOpt = (opt) => {
    const ok = opt.connected || !opt.id;
    return `<option value="${escapeHtml(opt.id)}" ${opt.id === selectedId ? "selected" : ""} ${ok ? "" : "disabled"}>${escapeHtml(optionLabel(opt))}</option>`;
  };
  if (groups.length <= 1) return (options || []).map(renderOpt).join("");
  return groups.map((group) => `<optgroup label="${escapeHtml(group.key)}">${group.items.map(renderOpt).join("")}</optgroup>`).join("");
}

function keyringProviderRank(provider) {
  if (provider === "nous" && cfg.keyring && cfg.keyring.nous_portal) return -1;
  const accounts = (cfg.keyring && cfg.keyring.accounts) || [];
  const order = (cfg.keyring && cfg.keyring.fallback) || [];
  const ranks = [];
  order.forEach((id) => {
    const row = accounts.find((item) => item.id === id);
    if (row && row.provider && !ranks.includes(row.provider)) ranks.push(row.provider);
  });
  const at = ranks.indexOf(provider);
  return at < 0 ? 99 : at;
}

function providerHintHtml(item) {
  if (!item || !item.id) return "";
  const note = escapeHtml(item.note || "");
  const url = item.subscribe || item.connect || "";
  if (!url) return note;
  const label = item.id === "nous" ? "Subscribe to Nous Portal" : escapeHtml(item.id);
  return `${note} <a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${label}</a>`;
}

function syncProviderHint(selectId, hintId) {
  const select = $(selectId);
  const hint = $(hintId);
  if (!select || !hint) return;
  const catalog = (cfg.keyring && cfg.keyring.catalog) || [];
  const item = catalog.find((row) => row.id === select.value) || {};
  hint.innerHTML = providerHintHtml(item);
}

function sortSeatModels(seat, rows, recommendedId) {
  const list = (rows || []).slice();
  list.sort((a, b) => {
    if (!a.id && b.id) return -1;
    if (a.id && !b.id) return 1;
    const ra = keyringProviderRank(a.provider);
    const rb = keyringProviderRank(b.provider);
    if (ra !== rb) return ra - rb;
    if (recommendedId && a.id === recommendedId) return -1;
    if (recommendedId && b.id === recommendedId) return 1;
    const pa = Number(a.in_usd || 0) + Number(a.out_usd || 0);
    const pb = Number(b.in_usd || 0) + Number(b.out_usd || 0);
    if (pa !== pb) return pa - pb;
    return String(a.label || a.id).localeCompare(String(b.label || b.id));
  });
  if (seat.id === "chat") {
    return list.map((row) => (
      row.id === recommendedId ? { ...row, recommended: true } : row
    ));
  }
  return list;
}

function modelsForSeat(seat, models) {
  const recommendedId = (cfg.catalog && cfg.catalog.recommended_chat) || "";
  if (seat.locked) {
    return [{ id: "", label: "Brief", provider: "board", provider_label: "Board", in_usd: 0, out_usd: 0, connected: true, caps: ["status"] }];
  }
  const need = seat.need || [];
  const q = modelQuery.trim().toLowerCase();
  let rows = (models || []).filter((row) => {
    const engines = row.engines || [];
    if (seat.engine && engines.length && !engines.includes(seat.engine)) return false;
    if (need.length && row.id && !need.every((flag) => (row.caps || []).includes(flag))) return false;
    if (row.id && row.connected === false && !q) return false;
    if (!q) return true;
    const blob = `${row.label} ${row.id} ${row.provider} ${row.author || ""}`.toLowerCase();
    return blob.includes(q);
  });
  if (seat.id === "chat") {
    const auto = autoPick("chat");
    rows = [
      {
        id: "",
        label: defaultModelOptionLabel(seat, false),
        provider: auto.provider || "opencode",
        provider_label: "Auto",
        in_usd: Number(auto.in_usd || 0),
        out_usd: Number(auto.out_usd || 0),
        connected: true,
        caps: ["status"],
      },
      { id: "INDEX", label: "Board — free brief talk", provider: "board", provider_label: "Board", in_usd: 0, out_usd: 0, connected: true, caps: ["status"] },
      ...rows.filter((row) => row.id),
    ];
  } else {
    rows = rows.map((row) => (
      row.id ? row : { ...row, label: defaultModelOptionLabel(seat, false) }
    ));
    if (!rows.some((row) => !row.id)) {
      rows = [{ id: "", label: defaultModelOptionLabel(seat, false), provider: "opencode", provider_label: "Auto", connected: true }, ...rows];
    }
  }
  return sortSeatModels(seat, rows, recommendedId);
}

function renderSeats(catalog, seats) {
  const root = $("seatList");
  if (!root) return;
  const chosen = seats || {};
  const groups = (catalog && catalog.seats) || [];
  const models = (catalog && catalog.models) || [];
  root.innerHTML = groups.map((seat) => {
    let current = (chosen[seat.id] || {}).model || "";
    let options = seat.options && seat.options.length ? seat.options : modelsForSeat(seat, models);
    if (current && !options.some((opt) => opt.id === current)) {
      const kept = models.find((row) => row.id === current);
      if (kept) options = [kept, ...options];
    }
    const guide = ((catalog && catalog.guides) || {})[seat.id] || {};
    const guidePicks = (guide.picks || []).map((row) => row.label).filter(Boolean);
    const guideText = guidePicks.length
      ? `${guide.note || "Arena this week"}: ${guidePicks.join(" · ")}`
      : "";
    const auto = autoPick(seat.id);
    const selected = options.find((opt) => opt.id === current) || options.find((opt) => !opt.id) || options[0] || {};
    const selectedId = Object.prototype.hasOwnProperty.call(selected, "id") ? selected.id : "";
    const price = selected.id && selected.id !== "INDEX"
      ? moneyPair(selected.in_usd, selected.out_usd)
      : (auto.id ? moneyPair(auto.in_usd, auto.out_usd) : (seat.id === "chat" || seat.locked ? "$0.00" : "—"));
    const note = auto.why && !current
      ? auto.why
      : (seat.note || (seat.locked ? "brief only" : (selected.provider_label || selected.provider || seat.engine || "")));
    const asOf = auto.as_of ? `Arena as of ${auto.as_of}` : "";
    const extraGuide = [guideText, asOf].filter(Boolean).join(" · ");
    return `
      <article class="seat-card" data-seat-card="${escapeHtml(seat.id)}">
        <header>
          <div>
            <h3>${escapeHtml(seat.label)}</h3>
            <span class="engine">${escapeHtml(seat.engine)}</span>
          </div>
          <span class="price" data-seat-price>${price}</span>
        </header>
        <select data-seat="${escapeHtml(seat.id)}" ${seat.locked ? "disabled" : ""}>${seatOptions(options, selectedId)}</select>
        <p class="hint" data-seat-note>${escapeHtml(note)}</p>
        ${extraGuide ? `<p class="seat-guide">${escapeHtml(extraGuide)}</p>` : ""}
      </article>
    `;
  }).join("");
  root.querySelectorAll("select[data-seat]").forEach((select) => {
    select.addEventListener("change", () => {
      const card = select.closest("[data-seat-card]");
      const seat = groups.find((row) => row.id === select.dataset.seat);
      const options = (seat && seat.options) || modelsForSeat(seat || {}, models);
      const opt = options.find((row) => row.id === select.value) || {};
      if (card) {
        const price = card.querySelector("[data-seat-price]");
        if (price) price.textContent = opt.id ? moneyPair(opt.in_usd, opt.out_usd) : (seat && seat.id === "chat" ? "$0.00" : "—");
        const note = card.querySelector("[data-seat-note]");
        if (note && !(seat && seat.note)) note.textContent = opt.provider_label || opt.provider || (seat && seat.engine) || "";
      }
    });
  });
  const cite = $("rankCite");
  if (cite) {
    const first = Object.values((catalog && catalog.guides) || {}).find((row) => row && row.citation);
    cite.textContent = (catalog && catalog.ranking_citation) || (first && first.citation) || "";
  }
  renderAssignmentMap(catalog);
}

function renderAssignmentMap(catalog) {
  const root = $("assignmentMap");
  if (!root) return;
  const staff = ((catalog && catalog.assignment) || {}).staff || {};
  const chain = (staff.code && staff.code.chain) || (staff.chat && staff.chat.chain) || [];
  const chainText = chain.map((row) => row.label).filter(Boolean).join(" → ") || "Add wallets on Keys.";
  const seats = ["chat", "think", "code", "research", "ops"];
  const rows = seats.map((id) => {
    const row = staff[id] || {};
    const bits = [row.model_label || autoPick(id).label || "—", row.account_label || "—"];
    if (row.source === "auto") bits.push("Auto");
    if (row.why && row.source === "auto") bits.push(row.why);
    return `<div><dt>${escapeHtml(id)}</dt><dd>${escapeHtml(bits.join(" · "))}</dd></div>`;
  }).join("");
  root.innerHTML = `<div><dt>Wallets</dt><dd>${escapeHtml(chainText)}</dd></div>${rows}`;
}

function renderProfileSeats(rootId, chosen, inheritLabel) {
  const root = $(rootId);
  if (!root) return;
  const catalog = cfg.catalog || {};
  const groups = (catalog.seats || []).filter((seat) => !seat.locked);
  const models = catalog.models || [];
  const seats = chosen || {};
  const blank = inheritLabel || "inherit Chief of Staff";
  root.innerHTML = groups.map((seat) => {
    const current = (seats[seat.id] || {}).model || "";
    const options = seat.options && seat.options.length ? seat.options : modelsForSeat(seat, models);
    const extra = current && !options.some((opt) => opt.id === current)
      ? `<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>`
      : "";
    const inheritFromStaff = /inherit/i.test(blank);
    const emptyLabel = defaultModelOptionLabel(seat, inheritFromStaff);
    const opts = [`<option value="">${escapeHtml(emptyLabel)}</option>`, extra].concat(
      options.filter((opt) => opt.id).map((opt) => `<option value="${escapeHtml(opt.id)}"${opt.id === current ? " selected" : ""}>${escapeHtml(opt.label || opt.id)}</option>`)
    ).join("");
    return `<div class="field"><label>${escapeHtml(seat.label)}</label><select data-profile-seat="${escapeHtml(seat.id)}">${opts}</select></div>`;
  }).join("");
}

function renderCeoSeats(rootId) {
  const seats = (currentProject() && currentProject().tools && currentProject().tools.seats) || {};
  renderProfileSeats(rootId || "menuCeoSeatList", seats, "inherit Chief of Staff");
}

function renderStaffSeats() {
  renderProfileSeats("menuStaffSeatList", cfg.seats || {}, "engine default");
}

function routeHintText(name) {
  return ({
    cos: "Auto: this chat stays one pane. Work still reports here.",
    builder: "Next send goes to OpenCode in this folder.",
    think: "Next send goes to Hermes Think.",
    research: "Next send fetches a URL.",
    ops: "Next send sets a schedule."
  })[name] || "Pin a lane or leave Auto.";
}

function talkName() {
  const worker = currentWorker();
  if (worker) return worker.name;
  const project = currentProject();
  if (project) return project.name;
  return "Chief of Staff";
}

function syncComposerWho() {
  const who = talkName();
  const project = currentProject();
  const worker = currentWorker();
  let line = "Talking to Chief of Staff";
  if (worker && project) line = `Talking to ${worker.name} · helper for ${project.name}`;
  else if (project) line = `Talking to ${project.name}`;
  if ($("composerWho")) $("composerWho").textContent = line;
  if ($("msg")) {
    const pin = preset && preset !== "cos" ? `${jobLabel(preset)} · ` : "";
    $("msg").placeholder = `${pin}Message ${who}`;
  }
}

function workLane(job) {
  const presetName = job && job.preset;
  if (presetName && presetName !== "cos" && presetName !== "ask") return presetName;
  const handoff = (job && job.handoff) || [];
  const work = handoff.filter((step) => step && step !== "cos" && step !== "ask");
  return work[work.length - 1] || "";
}

function isChatAtBottom() {
  if (!stream) return true;
  return stream.scrollHeight - stream.scrollTop - stream.clientHeight < 96;
}

function scrollChatBottom() {
  if (!stream) return;
  stream.scrollTop = stream.scrollHeight;
}

function stampLane(el, job, unread) {
  if (!el) return;
  const lane = workLane(job);
  if (!lane) {
    if (!el.dataset.lane) el.dataset.lane = "cos";
    paintLanes();
    return;
  }
  el.dataset.lane = lane;
  if (!el.querySelector(".lane-pill")) {
    const pill = document.createElement("span");
    pill.className = "lane-pill";
    pill.textContent = jobLabel(lane);
    el.insertBefore(pill, el.firstChild);
  }
  const prev = el.previousElementSibling;
  if (prev && prev.classList.contains("user") && (!prev.dataset.lane || prev.dataset.lane === "cos")) {
    prev.dataset.lane = lane;
  }
  if (!hydratingHistory && unread !== false && !isChatAtBottom()) unreadLanes.add(lane);
  paintLanes();
}

function paintLanes() {
  document.querySelectorAll(".lane").forEach((btn) => {
    const lane = btn.dataset.lane === "all" ? "" : (btn.dataset.lane || "");
    const fresh = Boolean(lane) && unreadLanes.has(lane);
    btn.classList.toggle("has", fresh);
    btn.classList.toggle("working", Boolean(liveRunId) && Boolean(lane) && liveLane === lane);
    btn.classList.toggle("on", focusedLane === lane);
    btn.title = !lane
      ? "Show every turn in this chat"
      : (fresh ? `New ${jobLabel(lane)} — click to show only those` : `Show only ${jobLabel(lane)} jobs in this chat`);
  });
  document.querySelectorAll(".route-btn").forEach((btn) => {
    const route = btn.dataset.preset;
    btn.classList.toggle("on", route === preset);
    btn.classList.toggle("working", Boolean(liveRunId) && route === liveLane && route !== "cos");
  });
  applyLaneFilter();
}

function applyLaneFilter() {
  if (!stream) return;
  const lane = focusedLane;
  stream.classList.toggle("lane-filtered", Boolean(lane));
  stream.querySelectorAll(":scope > *").forEach((el) => {
    if (!lane || el.classList.contains("live")) {
      el.hidden = false;
      return;
    }
    el.hidden = (el.dataset.lane || "") !== lane;
  });
}

function focusLane(lane) {
  focusedLane = (!lane || lane === "all") ? "" : lane;
  if (focusedLane) unreadLanes.delete(focusedLane);
  paintLanes();
  scrollChatBottom();
}

function lockComposer(hasKey) {
  const msg = $("msg");
  const send = $("sendBtn");
  const hint = $("workHint");
  const live = Boolean(liveRunId);
  const typed = Boolean(msg && msg.value.trim());
  const queued = queueFor().length;
  if (msg) msg.disabled = !hasKey;
  if (send) {
    send.disabled = !hasKey && !live;
    if (live && typed) {
      send.textContent = "Queue";
      send.type = "submit";
      send.classList.remove("stop");
      send.setAttribute("aria-label", "Queue message");
    } else if (live) {
      send.textContent = "Stop";
      send.type = "button";
      send.classList.add("stop");
      send.setAttribute("aria-label", "Stop");
    } else {
      send.textContent = "Send";
      send.type = "submit";
      send.classList.remove("stop");
      send.setAttribute("aria-label", "Send");
    }
  }
  if (hint) {
    if (live) {
      const lane = liveLane ? jobLabel(liveLane) : "";
      const bits = [
        `${talkName()}${lane ? ` · ${lane}` : ""} is working…`,
        "Enter queues another message",
        "Stop cancels"
      ];
      if (queued) bits.splice(1, 0, `${queued} queued`);
      hint.textContent = bits.join(" · ");
      hint.classList.remove("hidden");
    } else if (queued) {
      hint.textContent = `${queued} queued — sending next…`;
      hint.classList.remove("hidden");
    } else if (preset !== "cos") {
      hint.textContent = routeHintText(preset);
      hint.classList.remove("hidden");
    } else {
      hint.textContent = "";
      hint.classList.add("hidden");
    }
  }
  paintLanes();
  paintQueueChip();
}

function paintQueueChip() {
  const chip = $("queueChip");
  const text = $("queueChipText");
  if (!chip || !text) return;
  const rows = queueFor();
  if (!rows.length) {
    chip.classList.add("hidden");
    text.textContent = "";
    return;
  }
  const preview = rows[0].message.slice(0, 80);
  text.textContent = rows.length === 1
    ? `Next: ${preview}`
    : `${rows.length} waiting · next: ${preview}`;
  chip.classList.remove("hidden");
}

function sizeComposer() {
  const msg = $("msg");
  if (!msg) return;
  msg.style.height = "auto";
  msg.style.height = `${Math.min(160, Math.max(44, msg.scrollHeight))}px`;
  if (liveRunId) lockComposer(Boolean(cfg.has_key));
}

function setLive(runId, meta) {
  const key = (meta && meta.key) || aimKey();
  const pid = (meta && meta.projectId != null) ? meta.projectId : (key.split("::")[0] || "");
  const wid = (meta && meta.workerId != null) ? meta.workerId : (key.split("::")[1] || "");
  if (!runId) {
    lives.delete(key);
  } else {
    const prev = lives.get(key) || {};
    lives.set(key, {
      runId,
      abort: meta && "abort" in meta ? meta.abort : prev.abort || null,
      lane: (meta && meta.lane != null) ? meta.lane : (prev.lane || ""),
      projectId: pid,
      workerId: wid
    });
  }
  if (key === aimKey()) syncLiveFromAim();
  else {
    paintLanes();
    renderOrg(org);
  }
}

async function stopLive(key) {
  const idKey = key || aimKey();
  const live = liveFor(idKey);
  if (!live) return;
  if (live.abort) {
    try { live.abort.abort(); } catch (_err) { /* already aborted */ }
  }
  const id = live.runId && live.runId !== "pending" ? live.runId : "";
  setLive("", { key: idKey, projectId: live.projectId, workerId: live.workerId });
  // Clear chain context and message queue (real cancel semantics)
  chainContexts.delete(idKey);
  const queue = messageQueues.get(idKey);
  if (queue && queue.length > 0) {
    messageQueues.set(idKey, []);
    paintQueueChip();
  }
  if (!id) return;
  await fetch(`/api/runs/${id}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  });
}

function enqueueMessage(message, opts) {
  const text = String(message || "").trim();
  if (!text) return;
  const key = aimKey();
  const quote = (opts && opts.quote != null) ? opts.quote : (replyQuote || "");
  queueFor(key).push({
    message: text,
    preset: (opts && opts.preset) || preset || "cos",
    quote: quote || ""
  });
  if (!(opts && opts.keepQuote)) clearReply();
  paintQueueChip();
  lockComposer(Boolean(cfg.has_key));
}

async function drainQueue() {
  if (liveRunId) return;
  const key = aimKey();
  const rows = queueFor(key);
  if (!rows.length) {
    paintQueueChip();
    return;
  }
  const next = rows.shift();
  paintQueueChip();
  if (next.quote) {
    replyQuote = next.quote;
    const chip = $("replyChip");
    const text = $("replyChipText");
    if (chip && text) {
      text.textContent = next.quote;
      chip.classList.remove("hidden");
    }
  }
  await sendMessage(next.message, { preset: next.preset, allowSecret: false });
}

async function loadSpend() {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  try {
    const spendRes = await fetch(`/api/spend${qs}`);
    if (spendRes.ok) renderSpend(await spendRes.json());
  } catch (_err) {
    /* keep last spend */
  }
}

async function loadGit() {
  const project = currentProject();
  const folder = (project && project.folder)
    || (($("settingsFolder") && $("settingsFolder").value.trim()) || cfg.work_dir || "");
  const params = new URLSearchParams();
  if (project && project.id) params.set("project_id", project.id);
  else if (folder) params.set("folder", folder);
  try {
    const res = await fetch(`/api/git?${params.toString()}`);
    const data = await res.json();
    const el = $("gitStatus");
    if (el) {
      const who = project ? `${project.name} Code folder` : "Default OpenCode folder";
      if (!data.ok && data.error) {
        el.textContent = data.error;
      } else if (!data.is_repo) {
        el.innerHTML = `<div><b>${escapeHtml(who)}</b></div><div>Not a git folder</div><div>${escapeHtml(data.folder || "")}</div>`;
      } else {
        const remote = data.remote || "";
        const remoteHtml = /^https?:\/\//i.test(remote)
          ? `<a href="${escapeHtml(remote)}" target="_blank" rel="noreferrer">${escapeHtml(remote)}</a>`
          : escapeHtml(remote || "local repo, no origin");
        el.innerHTML = `
          <div><b>${escapeHtml(who)}</b></div>
          <div><b>${escapeHtml(data.branch || "detached")}</b> · ${data.dirty ? "uncommitted" : "clean"}</div>
          <div>${remoteHtml}</div>
          <div>${escapeHtml(data.folder || "")}</div>
        `;
      }
    }
  } catch (_err) {
    /* git panel is optional */
  }
}

function money(n) {
  const value = Number(n);
  return `$${(Number.isFinite(value) ? value : 0).toFixed(2)}`;
}

function renderSpend(spend) {
  const by = (spend && spend.by_engine) || {};
  const write = (id, val) => { if ($(id)) $(id).textContent = money(val); };
  write("spendChat", by.chat);
  write("spendOpenCode", by.opencode);
  write("spendHermes", by.hermes);
  const el = $("spend");
  if (!el) return;
  const capNum = Number(spend && spend.spend_cap_usd);
  const usedNum = Number(spend && spend.spent_usd);
  const cap = Number.isFinite(capNum) ? capNum.toFixed(2) : "0.00";
  const used = Number.isFinite(usedNum) ? usedNum.toFixed(2) : "0.00";
  const period = (spend && spend.spend_cap_period) || "week";
  const policy = (spend && spend.policy) || {};
  const bind = policy.bind === "all" ? "all" : "PAYG";
  const scope = spend && spend.project_id ? "CEO" : "org";
  const halt = spend && spend.enforced ? " · stopped" : "";
  el.textContent = `$${used} / $${cap} ${bind} ${period}${halt}`;
  const wallets = $("walletList");
  if (wallets) {
    const rows = (spend.wallets || []).map((wallet) => {
      let value = "—";
      if (wallet.unit === "%" && wallet.used != null) {
        value = `${wallet.remaining}% left`;
      } else if (wallet.unit === "usd") {
        value = money(wallet.used);
      }
      return `<div><span>${escapeHtml(wallet.label)}</span><b>${escapeHtml(value)}</b></div>`;
    });
    if (spend.unknown_jobs) {
      rows.push(`<div><span>Unknown cost</span><b>${spend.unknown_jobs} jobs</b></div>`);
    }
    wallets.innerHTML = rows.join("");
  }
  const box = $("spendBreak");
  if (box) {
    box.innerHTML = `
      <div><span>Chat</span><b>${money(by.chat)}</b></div>
      <div><span>OpenCode</span><b>${money(by.opencode)}</b></div>
      <div><span>Hermes</span><b>${money(by.hermes)}</b></div>
      <div><span>Cap</span><b>$${cap} ${bind} ${period} · ${scope}${halt}</b></div>
    `;
  }
}

function engineStage(engine) {
  const name = String(engine || "").toLowerCase();
  if (name.includes("opencode")) return "opencode";
  if (name.includes("hermes")) return "hermes";
  return "";
}

function jobLabel(name) {
  return ({ cos: "Auto", builder: "Code", think: "Think", research: "Research", ops: "Ops" })[name] || name || "";
}

function seatLabel(name) {
  return ({ cos: "Cos / Auto", builder: "Code / Builder", think: "Think", research: "Research", ops: "Ops" })[name] || name || "";
}

function allSeats() {
  const seats = [
    { id: "cos", label: "Cos / Auto", description: "Chief of Staff (routing)" },
    { id: "builder", label: "Code / Builder", description: "OpenCode in this folder" },
    { id: "think", label: "Think", description: "Hermes reasoning" },
    { id: "research", label: "Research", description: "Fetch + Hermes snapshot" },
    { id: "ops", label: "Ops", description: "Hermes cron + schedule" }
  ];
  const project = currentProject();
  if (project && project.name) {
    seats.push({ id: `ceo:${project.id}`, label: project.name, description: "CEO" });
  }
  return seats;
}

function renderActivity(data) {
  const activity = data || {};
  lockComposer(Boolean(activity.has_key || cfg.has_key));
  if (data) {
    cfg.activity = activity;
    if (org && org.projects) renderOrg(org);
  }
}

let menuJustOpened = false;

function hideNodeMenu() {
  const menu = $("nodeMenu");
  if (menu) menu.classList.add("hidden");
  hideMsgMenu();
}

function hideMsgMenu() {
  const menu = $("msgMenu");
  if (menu) menu.classList.add("hidden");
}

function articleText(el) {
  if (!el) return "";
  const text = el.querySelector(".bubble-text");
  if (text) return (text.textContent || "").trim();
  const pre = el.querySelector("pre");
  if (pre) return (pre.textContent || "").trim();
  return (el.textContent || "").trim();
}

function attachQuotePreview(el, text) {
  if (!el || !text) return;
  if (el.querySelector(".bubble-quote")) return;
  const quote = document.createElement("blockquote");
  quote.className = "bubble-quote";
  quote.textContent = String(text).replace(/\s+/g, " ").trim().slice(0, 160);
  const body = el.querySelector(".bubble-text") || el.firstChild;
  el.insertBefore(quote, body);
}

function clearReply() {
  replyQuote = "";
  const chip = $("replyChip");
  if (chip) chip.classList.add("hidden");
  if ($("replyChipText")) $("replyChipText").textContent = "";
}

function startReply(el) {
  const text = articleText(el).replace(/\s+/g, " ").trim();
  if (!text) return;
  replyQuote = text.slice(0, 400);
  const chip = $("replyChip");
  if ($("replyChipText")) $("replyChipText").textContent = replyQuote.slice(0, 140);
  if (chip) chip.classList.remove("hidden");
  const lane = el.dataset.lane || "";
  if (lane && lane !== "cos" && PRESET_ENGINE[lane]) setRoute(lane);
  const msg = $("msg");
  if (msg) {
    msg.focus();
    sizeComposer();
  }
}

function showMsgMenu(x, y, el) {
  const menu = $("msgMenu");
  if (!menu || !el) return;
  hideNodeMenu();
  const lane = el.dataset.lane || "";
  const laneLabel = lane && lane !== "cos" ? jobLabel(lane) : "";
  menu.innerHTML = `
    <button type="button" role="menuitem" data-msg="reply">Reply</button>
    <button type="button" role="menuitem" data-msg="copy">Copy</button>
    ${laneLabel ? `<button type="button" role="menuitem" data-msg="filter">Show only ${escapeHtml(laneLabel)}</button>` : ""}
  `;
  menu.classList.remove("hidden");
  const left = Math.min(x, window.innerWidth - 260);
  const top = Math.min(y, window.innerHeight - 80);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
  menuJustOpened = true;
  setTimeout(() => { menuJustOpened = false; }, 0);
  menu.querySelectorAll("[data-msg]").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const action = btn.dataset.msg;
      hideMsgMenu();
      if (action === "reply") startReply(el);
      if (action === "copy") {
        try { await navigator.clipboard.writeText(articleText(el)); } catch (_err) { /* ignore */ }
      }
      if (action === "filter" && lane && lane !== "cos") focusLane(lane);
    });
  });
}

function projectById(id) {
  return (org.projects || []).find((row) => row.id === id) || null;
}

async function applyOrg(next) {
  org = next;
  renderOrg(org);
  renderBotMeta();
  fillCeoPanel();
  fillChannels();
}

async function postProject(folder, name) {
  const res = await fetch("/api/org/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder: folder || "", name: name || "" })
  });
  const data = await res.json();
  $("orgStatus").textContent = res.ok ? "" : (data.error || "add failed");
  if (res.ok) {
    hideNodeMenu();
    await applyOrg(data);
    if (data.project_id) await setOrgNode(data.project_id, "");
  }
}

async function saveProjectFolder(id, folder) {
  const res = await fetch(`/api/org/projects/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder })
  });
  const data = await res.json();
  $("orgStatus").textContent = res.ok ? "" : (data.error || "folder failed");
  if (res.ok) {
    hideNodeMenu();
    await applyOrg(data);
    fetch("/api/index").then((r) => r.json()).then(applyConfig);
  }
}

async function renameNode(kind, pid, wid, name) {
  const title = (name || "").trim();
  if (!title) return;
  let res;
  if (kind === "ceo") {
    res = await fetch(`/api/org/projects/${pid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: title })
    });
  } else {
    res = await fetch(`/api/org/projects/${pid}/workers/${wid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: title })
    });
  }
  const data = await res.json();
  $("orgStatus").textContent = res.ok ? "" : (data.error || "rename failed");
  if (res.ok) {
    hideNodeMenu();
    await applyOrg(data);
  }
}

async function addNamedWorker(id, name) {
  const res = await fetch(`/api/org/projects/${id}/workers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  const data = await res.json();
  $("orgStatus").textContent = res.ok ? "" : (data.error || "add failed");
  if (res.ok) {
    expanded.add(id);
    hideNodeMenu();
    await applyOrg(data);
  }
}

async function deleteProject(id, confirmName) {
  const typed = (confirmName || "").trim();
  if (!typed) {
    if ($("orgStatus")) $("orgStatus").textContent = "Type the CEO name to delete";
    return;
  }
  const res = await fetch(`/api/org/projects/${id}?confirm=${encodeURIComponent(typed)}`, { method: "DELETE" });
  const data = await res.json();
  if (res.ok) {
    if (projectId === id) {
      projectId = "";
      workerId = "";
      preset = "cos";
    }
    hideNodeMenu();
    await applyOrg(data);
  } else if ($("orgStatus")) {
    $("orgStatus").textContent = data.error || "delete failed";
  }
}

async function deleteWorker(pid, wid, confirmName) {
  const typed = (confirmName || "").trim();
  if (!typed) {
    if ($("orgStatus")) $("orgStatus").textContent = "Type the helper name to delete";
    return;
  }
  const worker = (projectById(pid) && (projectById(pid).workers || []).find((row) => row.id === wid)) || {};
  const expected = String(worker.name || wid);
  if (typed.toLowerCase() !== expected.toLowerCase() && typed !== wid) {
    if ($("orgStatus")) $("orgStatus").textContent = `Type ${expected} to delete`;
    return;
  }
  const res = await fetch(`/api/org/projects/${pid}/workers/${wid}`, { method: "DELETE" });
  const data = await res.json();
  if (res.ok) {
    if (workerId === wid) workerId = "";
    hideNodeMenu();
    await applyOrg(data);
  } else if ($("orgStatus")) {
    $("orgStatus").textContent = data.error || "delete failed";
  }
}

function showNodeMenu(x, y, kind, pid, wid) {
  const menu = $("nodeMenu");
  if (!menu) return;
  const project = pid ? projectById(pid) : null;
  const folder = (project && project.folder) || "";
  let html = "";
  if (kind === "staff") {
    html = `
      <div class="menu-field">
        <label for="menuCeoAddName">Add CEO</label>
        <input id="menuCeoAddName" type="text" placeholder="Name" autocomplete="off" />
      </div>
      <div class="menu-field">
        <label for="menuProjectFolder">Folder (optional)</label>
        <input id="menuProjectFolder" type="text" placeholder="${escapeHtml((org && org.folder) || "default OpenCode folder")}" autocomplete="off" />
        <button type="button" class="ghost-btn" data-menu="add-project">Add</button>
      </div>
      <div class="menu-field">
        <label for="menuIndexEdit">Staff brief</label>
        <textarea id="menuIndexEdit" rows="6">${escapeHtml(org.index || "")}</textarea>
        <button type="button" class="ghost-btn" data-menu="save-index">Save brief</button>
      </div>
      <button type="button" role="menuitem" data-menu="configure">Open settings</button>`;
  } else if (kind === "ceo") {
    const git = (project && project.git) || {};
    const tools = (project && project.tools) || {};
    html = `
      <div class="menu-field">
        <label for="menuCeoName">Name</label>
        <input id="menuCeoName" type="text" value="${escapeHtml((project && project.name) || "")}" autocomplete="off" />
        <button type="button" class="ghost-btn" data-menu="rename-ceo" data-project="${escapeHtml(pid)}">Save</button>
      </div>
      <div class="menu-field">
        <label for="menuCeoFolder">Code folder</label>
        <input id="menuCeoFolder" type="text" value="${escapeHtml(folder)}" autocomplete="off" />
        <button type="button" class="ghost-btn" data-menu="save-folder" data-project="${escapeHtml(pid)}">Save</button>
      </div>
      <p class="muted menu-note">${escapeHtml(git.remote || (git.is_repo ? "local git, no origin" : "not a git folder"))}</p>
      <p class="muted menu-note">${escapeHtml(tools.hermes_home || "no Hermes home")}</p>
      <button type="button" role="menuitem" data-menu="opencode">Open OpenCode</button>
      <button type="button" role="menuitem" data-menu="hermes">Open Hermes</button>
      <button type="button" role="menuitem" data-menu="configure">Configure</button>
      <div class="menu-field menu-danger">
        <label for="menuDeleteConfirm">Type ${escapeHtml((project && project.name) || pid)} to delete</label>
        <input id="menuDeleteConfirm" type="text" autocomplete="off" placeholder="${escapeHtml((project && project.name) || pid)}" />
        <button type="button" class="ghost-btn danger" data-menu="remove-project" data-project="${escapeHtml(pid)}">Delete CEO</button>
      </div>`;
  } else if (kind === "worker") {
    const worker = project && (project.workers || []).find((row) => row.id === wid);
    html = `
      <div class="menu-field">
        <label for="menuWorkerRename">Name</label>
        <input id="menuWorkerRename" type="text" value="${escapeHtml((worker && worker.name) || "")}" autocomplete="off" />
        <button type="button" class="ghost-btn" data-menu="rename-worker" data-project="${escapeHtml(pid)}" data-worker="${escapeHtml(wid)}">Save</button>
      </div>
      <button type="button" role="menuitem" data-menu="hermes">Open Hermes</button>
      <div class="menu-field menu-danger">
        <label for="menuDeleteConfirm">Type ${escapeHtml((worker && worker.name) || wid)} to delete</label>
        <input id="menuDeleteConfirm" type="text" autocomplete="off" placeholder="${escapeHtml((worker && worker.name) || wid)}" />
        <button type="button" class="ghost-btn danger" data-menu="remove-worker" data-project="${escapeHtml(pid)}" data-worker="${escapeHtml(wid)}">Delete helper</button>
      </div>`;
  }
  menu.innerHTML = html;
  menu.classList.remove("hidden");
  const left = Math.min(x, window.innerWidth - 340);
  const top = Math.min(y, window.innerHeight - 80);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
  menuJustOpened = true;
  setTimeout(() => { menuJustOpened = false; }, 0);
  menu.querySelectorAll("[data-menu]").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const action = btn.dataset.menu;
      if (action === "add-project") {
        const folderInput = $("menuProjectFolder");
        const nameInput = $("menuCeoAddName");
        const folderValue = folderInput ? folderInput.value.trim() : "";
        const name = nameInput ? nameInput.value.trim() : "";
        if (name || folderValue) await postProject(folderValue, name);
      } else if (action === "save-index") {
        const input = $("menuIndexEdit");
        await saveStaffIndex(input ? input.value : "");
      } else if (action === "save-folder") {
        const input = $("menuCeoFolder");
        const value = input ? input.value.trim() : "";
        if (value) await saveProjectFolder(btn.dataset.project, value);
      } else if (action === "rename-ceo") {
        const input = $("menuCeoName");
        await renameNode("ceo", btn.dataset.project, "", input ? input.value : "");
      } else if (action === "rename-worker") {
        const input = $("menuWorkerRename");
        await renameNode("worker", btn.dataset.project, btn.dataset.worker, input ? input.value : "");
      } else if (action === "configure") {
        hideNodeMenu();
        setSettings(true, kind === "staff" ? "you" : "ceo");
      } else if (action === "opencode") {
        hideNodeMenu();
        openWorkspace("opencode");
      } else if (action === "hermes") {
        hideNodeMenu();
        openWorkspace("hermes");
      } else if (action === "remove-project") {
        const typed = $("menuDeleteConfirm") ? $("menuDeleteConfirm").value : "";
        await deleteProject(btn.dataset.project, typed);
      } else if (action === "remove-worker") {
        const typed = $("menuDeleteConfirm") ? $("menuDeleteConfirm").value : "";
        await deleteWorker(btn.dataset.project, btn.dataset.worker, typed);
      }
    });
  });
}

async function saveStaffIndex(text) {
  const res = await fetch("/api/index", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  const data = await res.json();
  if (res.ok) {
    hideNodeMenu();
    if (data.index) renderIndex(data.index);
    fetch("/api/org").then((r) => r.json()).then(applyOrg);
  } else if ($("orgStatus")) {
    $("orgStatus").textContent = data.error || "brief save failed";
  }
}

async function saveCeoTools(pid) {
  if (!pid) return;
  
  // Collect seats
  const seats = {};
  document.querySelectorAll("[data-ceo-seat]").forEach((input) => {
    seats[input.dataset.ceoSeat] = { model: input.value };
  });
  
  // Collect connectors
  const connectors = { skills: {}, mcp: {} };
  document.querySelectorAll("[data-ceo-skill][data-seat]").forEach((input) => {
    const skill = input.dataset.ceoSkill;
    const seat = input.dataset.seat;
    if (!connectors.skills[skill]) connectors.skills[skill] = {};
    connectors.skills[skill][seat] = input.checked;
  });
  document.querySelectorAll("[data-ceo-mcp][data-seat]").forEach((input) => {
    const mcpId = input.dataset.ceoMcp;
    const seat = input.dataset.seat;
    if (!connectors.mcp[mcpId]) connectors.mcp[mcpId] = {};
    connectors.mcp[mcpId][seat] = input.checked;
  });
  
  const capInput = $("ceoSpendCap");
  const capRaw = capInput ? capInput.value.trim() : "";
  const account = $("ceoAccountId");
  const site = $("ceoSiteUrl");
  const folder = $("ceoFolder");
  const fallbackInput = $("ceoFallback");
  const fallback = fallbackInput ? fallbackInput.value.split(",").map(s => s.trim()).filter(Boolean) : [];
  
  const res = await fetch(`/api/org/projects/${pid}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      folder: folder ? folder.value.trim() : undefined,
      spend_cap_usd: capRaw === "" ? "" : Number(capRaw),
      account_id: account ? account.value : "",
      fallback,
      site_url: site ? site.value.trim() : "",
      connectors,
      seats
    })
  });
  const data = await res.json();
  if ($("ceoToolsStatus")) $("ceoToolsStatus").textContent = res.ok ? "CEO saved" : (data.error || "save failed");
  if (res.ok) {
    applyOrg(data);
    loadSpend();
  }
}

function accountSelectOptions(selected, blank) {
  const rows = (cfg.keyring && cfg.keyring.accounts) || [];
  const inheritFromStaff = /inherit/i.test(blank || "");
  const def = defaultKeyAccount(inheritFromStaff);
  const blankLabel = def ? `${def.label} (first in keyring)` : (blank || "inherit Chief of Staff");
  return [`<option value="">${escapeHtml(blankLabel)}</option>`].concat(rows.map((row) => (
    `<option value="${escapeHtml(row.id)}"${row.id === selected ? " selected" : ""}>${escapeHtml(row.label)}</option>`
  ))).join("");
}

async function saveStaffProfile() {
  const seats = {};
  document.querySelectorAll("#menuStaffSeatList [data-profile-seat]").forEach((input) => {
    seats[input.dataset.profileSeat] = { model: input.value };
  });
  const account = $("staffAccount");
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile_account_id: account ? account.value : "",
      seats
    })
  });
  const data = await res.json();
  if ($("staffProfileStatus")) $("staffProfileStatus").textContent = res.ok ? "profile saved" : (data.error || "save failed");
  if (res.ok) {
    applyConfig(data);
    hideNodeMenu();
  }
}

function accountBackupChecks(primary, fallback) {
  const rows = (cfg.keyring && cfg.keyring.accounts) || [];
  const chosen = new Set(fallback || []);
  return rows.filter((row) => row.id !== primary).map((row) => (
    `<label class="check"><input type="checkbox" data-ceo-backup value="${escapeHtml(row.id)}"${chosen.has(row.id) ? " checked" : ""} /> ${escapeHtml(row.label)}</label>`
  )).join("") || "<p class=\"muted\">Add keys in Settings → Keys.</p>";
}

function fillCeoPanel() {
  const hint = $("ceoPanelHint");
  const body = $("ceoPanelBody");
  if (!body) return;
  const project = currentProject();
  if (!project) {
    if (hint) hint.textContent = "Select a CEO in the sidebar. Keys, spend, seats, connectors, and Hermes home live here.";
    body.innerHTML = "";
    return;
  }
  const tools = project.tools || {};
  const git = project.git || {};
  const remote = git.remote || (git.is_repo ? "local git, no origin" : "not a git folder");
  const folder = project.folder || "";
  const mcp = tools.mcp_github;
  const spend = tools.spend_cap_usd;
  const hermesHome = tools.hermes_home || "";
  const hermesSessionId = tools.hermes_session_id || "";
  const sessionCount = tools.session_count || 0;
  const sessionTitle = tools.session_title || "";
  const accountId = tools.account_id || "";
  const fallback = (tools.fallback || []).join(", ") || "—";
  const siteUrl = tools.site_url || "";
  const seats = tools.seats || {};
  const connectors = tools.connectors || { skills: {}, mcp: {} };
  
  // Compute Available tools strip
  const globalConnectors = cfg.connectors || { skills: {}, mcp: {} };
  const mergedSkills = {...(globalConnectors.skills || {}), ...(connectors.skills || {})};
  const mergedMcp = {...(globalConnectors.mcp || {}), ...(connectors.mcp || {})};
  
  const availableSkills = {
    think: [],
    research: [],
    ops: []
  };
  const availableMcp = {
    think: [],
    research: [],
    ops: [],
    code: []
  };
  
  // Collect enabled skills per seat
  for (const [skill, seatToggles] of Object.entries(mergedSkills)) {
    if (seatToggles.think) availableSkills.think.push(skill);
    if (seatToggles.research) availableSkills.research.push(skill);
    if (seatToggles.ops) availableSkills.ops.push(skill);
  }
  
  // Collect enabled MCP per seat
  for (const [mcpId, seatToggles] of Object.entries(mergedMcp)) {
    if (seatToggles.think) availableMcp.think.push(mcpId);
    if (seatToggles.research) availableMcp.research.push(mcpId);
    if (seatToggles.ops) availableMcp.ops.push(mcpId);
    if (seatToggles.code) availableMcp.code.push(mcpId);
  }
  
  const toolsStrip = `
    <div class="usage-card">
      <h4>Available Tools (Effective)</h4>
      <div class="kv">
        <div><dt>Chat</dt><dd>Tools off (explains + routes only)</dd></div>
        <div><dt>Think</dt><dd>Skills: ${availableSkills.think.join(", ") || "none"}</dd></div>
        <div><dt>Research</dt><dd>Skills: ${availableSkills.research.join(", ") || "none"}</dd></div>
        <div><dt>Ops</dt><dd>Skills: ${availableSkills.ops.join(", ") || "none"}</dd></div>
        <div><dt>Code</dt><dd>MCP: ${availableMcp.code.join(", ") || "none"}</dd></div>
      </div>
      <p class="muted">Configure in Settings → Connectors (global) or below (CEO overrides)</p>
    </div>
  `;
  
  if (hint) hint.textContent = `${project.name} — Keys, spend, seats, connectors, and Hermes home`;
  body.innerHTML = `
    ${toolsStrip}
    <div class="usage-card">
      <h4>Code</h4>
      <div class="kv">
        <div><dt>Folder</dt><dd>${escapeHtml(folder)}</dd></div>
        <div><dt>Git</dt><dd>${escapeHtml(remote)}</dd></div>
      </div>
    </div>
    <div class="usage-card">
      <h4>Hermes</h4>
      <div class="kv">
        <div><dt>Home</dt><dd>${escapeHtml(hermesHome)}</dd></div>
        <div><dt>Telegram ID</dt><dd>${escapeHtml(hermesSessionId)}</dd></div>
        <div><dt>Sessions</dt><dd>${sessionCount}</dd></div>
        ${sessionTitle ? `<div><dt>Last</dt><dd>${escapeHtml(sessionTitle)}</dd></div>` : ""}
      </div>
    </div>
    <div class="field">
      <label for="ceoFolder">Code folder</label>
      <input id="ceoFolder" type="text" value="${escapeHtml(folder)}" placeholder="C:\\path\\to\\repo" />
    </div>
    <div class="field">
      <label for="ceoSiteUrl">Site URL</label>
      <input id="ceoSiteUrl" type="text" value="${escapeHtml(siteUrl)}" placeholder="https://example.com" />
      <p class="muted">For Research snapshot jobs</p>
    </div>
    <div class="field">
      <label for="ceoSpendCap">Spend cap USD (per ${cfg.spend_cap_period || "week"})</label>
      <input id="ceoSpendCap" type="number" min="0" step="0.5" value="${spend || ""}" placeholder="empty = use instance cap" />
    </div>
    <div class="field">
      <label for="ceoAccountId">Preferred account</label>
      <select id="ceoAccountId">
        <option value="">Auto (instance default)</option>
        ${(cfg.keys || []).map(k => `<option value="${escapeHtml(k.id)}"${k.id === accountId ? " selected" : ""}>${escapeHtml(k.label || k.id)}</option>`).join("")}
      </select>
    </div>
    <div class="field">
      <label for="ceoFallback">Fallback chain</label>
      <input id="ceoFallback" type="text" value="${escapeHtml(fallback)}" placeholder="id1, id2" />
      <p class="muted">Comma-separated account IDs. Auto walks full keyring if empty.</p>
    </div>
    <h3 class="drawer-sub">Seats (per-CEO model pins)</h3>
    ${["chat", "think", "code", "research", "ops"].map(seat => {
      const seatData = seats[seat] || {};
      const seatModel = seatData.model || "";
      return `
        <div class="field">
          <label for="ceoSeat-${seat}">${seat.charAt(0).toUpperCase() + seat.slice(1)}</label>
          <select id="ceoSeat-${seat}" data-ceo-seat="${seat}">
            <option value="">Auto</option>
            ${(cfg.catalog?.models || []).map(m => `<option value="${escapeHtml(m.id)}"${m.id === seatModel ? " selected" : ""}>${escapeHtml(m.name || m.id)}</option>`).join("")}
          </select>
        </div>
      `;
    }).join("")}
    <h3 class="drawer-sub">Connectors (CEO overrides)</h3>
    <p class="muted">Leave unconfigured to use global Settings → Connectors. Toggle here to override for this CEO only.</p>
    <div id="ceoConnectorsMatrix"></div>
    <div class="actions">
      <button type="button" class="send" id="saveCeoTools">Save</button>
      <p class="muted" id="ceoToolsStatus"></p>
    </div>
  `;
  
  paintCeoConnectorsMatrix(connectors);
  
  // Set up event listeners
  const save = $("saveCeoTools");
  if (save) save.addEventListener("click", () => saveCeoTools(project.id));
}

function paintCeoConnectorsMatrix(connectors) {
  const matrix = $("ceoConnectorsMatrix");
  if (!matrix || !connectorsCatalog) return;
  
  const skills = connectors.skills || {};
  const mcp = connectors.mcp || {};
  
  let html = `<p class="muted">Skills:</p>`;
  if (connectorsCatalog.skills && connectorsCatalog.skills.length > 0) {
    html += `<div class="connector-matrix">`;
    html += `<div class="connector-row connector-row-header">
      <div class="connector-name">Skill</div>
      <div class="connector-cell">Think</div>
      <div class="connector-cell">Research</div>
      <div class="connector-cell">Ops</div>
    </div>`;
    connectorsCatalog.skills.forEach(skill => {
      const skillConfig = skills[skill] || {};
      html += `<div class="connector-row">
        <div class="connector-name">${escapeHtml(skill)}</div>`;
      ["think", "research", "ops"].forEach(seat => {
        const checked = skillConfig[seat] === true ? " checked" : "";
        html += `<div class="connector-cell">
          <label>
            <input type="checkbox" data-ceo-skill="${escapeHtml(skill)}" data-seat="${seat}"${checked} />
          </label>
        </div>`;
      });
      html += `</div>`;
    });
    html += `</div>`;
  } else {
    html += `<p class="muted">No skills available.</p>`;
  }
  
  html += `<p class="muted">MCP:</p>`;
  if (connectorsCatalog.mcp && connectorsCatalog.mcp.length > 0) {
    html += `<div class="connector-matrix">`;
    html += `<div class="connector-row connector-row-header">
      <div class="connector-name">MCP</div>
      <div class="connector-cell">Think</div>
      <div class="connector-cell">Research</div>
      <div class="connector-cell">Ops</div>
      <div class="connector-cell">Code</div>
    </div>`;
    connectorsCatalog.mcp.forEach(item => {
      const mcpId = item.id || "";
      const mcpConfig = mcp[mcpId] || {};
      html += `<div class="connector-row">
        <div class="connector-name">${escapeHtml(mcpId)}</div>`;
      ["think", "research", "ops", "code"].forEach(seat => {
        const checked = mcpConfig[seat] === true ? " checked" : "";
        html += `<div class="connector-cell">
          <label>
            <input type="checkbox" data-ceo-mcp="${escapeHtml(mcpId)}" data-seat="${seat}"${checked} />
          </label>
        </div>`;
      });
      html += `</div>`;
    });
    html += `</div>`;
  } else {
    html += `<p class="muted">No MCP servers available.</p>`;
  }
  
  matrix.innerHTML = html;
}

function fillChannels() {
  const status = $("channelStatus");
  const card = $("channelCard");
  const project = currentProject();
  if (!status || !card) return;
  if (!project) {
    status.textContent = "Select a CEO to see Chat vs Telegram.";
    card.classList.add("hidden");
    card.innerHTML = "";
    return;
  }
  const tools = project.tools || {};
  const sid = tools.hermes_session_id || "";
  status.textContent = sid
    ? `${project.name}: Chat / Think / Ops resume the imported Telegram session. Replies here do not post into Telegram.`
    : `${project.name}: no Telegram session bound yet. Chat still works locally.`;
  card.classList.remove("hidden");
  card.innerHTML = `
    <div><dt>Hermes home</dt><dd>${escapeHtml(tools.hermes_home || "—")}</dd></div>
    <div><dt>Session</dt><dd>${escapeHtml(sid || "—")}</dd></div>
    <div><dt>Live Telegram</dt><dd>This OpenBot instance owns the bots. Reply in Telegram for that thread.</dd></div>
  `;
}

function bindNodeMenu(el, kind, pid, wid) {
  el.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (kind === "staff") setOrgNode("", "");
    else setOrgNode(pid || "", wid || "");
    showNodeMenu(event.clientX, event.clientY, kind, pid || "", wid || "");
  });
}

function ceoWire(project) {
  const now = (project.index_now || "").trim();
  const blocker = (project.index_blocker || "").trim();
  const parts = [];
  
  if (now && now !== "source of truth" && now !== "—") {
    const truncated = now.length > 50 ? now.substring(0, 47) + "..." : now;
    parts.push(truncated);
  }
  
  if (blocker && blocker !== "—") {
    const truncated = blocker.length > 40 ? blocker.substring(0, 37) + "..." : blocker;
    parts.push(`🚫 ${truncated}`);
  }
  
  return parts.join(" · ");
}

function ceoInitials(name) {
  if (!name) return "??";
  const words = String(name).trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "??";
  if (words.length === 1) {
    const w = words[0].toUpperCase();
    return w.length >= 2 ? w.substring(0, 2) : w;
  }
  return (words[0][0] + words[1][0]).toUpperCase();
}

function inboxHtml() {
  const rows = ((cfg.activity || {}).needs_you) || [];
  const unread = rows.filter((row) => !inboxSeen.has(row.id)).length;
  const items = rows.length ? rows.map((row) => {
    const ping = inboxSeen.has(row.id) ? "" : " ping";
    return `<button type="button" class="org-inbox-item${ping}" data-inbox="${escapeHtml(row.id)}" data-project="${escapeHtml(row.project_id || "")}" data-preset="${escapeHtml(row.preset || "")}">
      <b>${escapeHtml(row.name || "CEO")}</b>
      <span>${escapeHtml(row.label || "needs you")}</span>
    </button>`;
  }).join("") : `<p class="org-inbox-empty">Empty. Login walls and Code Accept/Reject land here.</p>`;
  return `<div class="org-inbox">
    <div class="org-inbox-head">Inbox${unread ? ` · ${unread}` : ""}</div>
    ${items}
  </div>`;
}

function projectNeedsYou(pid) {
  return (((cfg.activity || {}).needs_you) || []).some(
    (row) => String(row.project_id || "") === String(pid || "") && !inboxSeen.has(row.id)
  );
}

function renderOrg(data) {
  org = data || {};
  const tree = $("orgTree");
  if (!tree) return;
  const projects = org.projects || [];
  if (!expanded.size) {
    const primary = projects.find((row) => row.primary) || projects[0];
    if (primary) expanded.add(primary.id);
  }
  
  // Fetch queue status asynchronously
  let queueData = { queue_status: [], active_workers: [], total_queued: 0 };
  fetch("/api/queue/status")
    .then(r => r.json())
    .then(data => {
      queueData = data;
      // Re-render with queue data
      renderOrgWithQueue(org, queueData);
    })
    .catch(() => {
      // Fallback to render without queue data
      renderOrgWithQueue(org, queueData);
    });
}

function renderOrgWithQueue(org, queueData) {
  const tree = $("orgTree");
  if (!tree) return;
  const projects = org.projects || [];
  const queueByProject = new Map();
  
  // Index queue data by project_id
  for (const q of queueData.queue_status || []) {
    queueByProject.set(q.project_id || "_staff", q.queued_count || 0);
  }
  
  const projectBits = projects.map((project) => {
    const open = expanded.has(project.id);
    const workers = (project.workers || []).map((worker) => `
        <div class="org-row worker-row">
          <button type="button" class="org-btn worker${projectId === project.id && workerId === worker.id ? " on" : ""}" data-project="${escapeHtml(project.id)}" data-worker="${escapeHtml(worker.id)}" data-kind="worker">
            <span class="org-avatar" aria-hidden="true">${escapeHtml(ceoInitials(worker.name))}</span>
            <span class="org-btn-text">
              <b>${escapeHtml(worker.name)}</b>
            </span>
          </button>
          <span class="org-role">helper</span>
        </div>`).join("");
    const wire = ceoWire(project);
    const busy = lives.has(aimKey(project.id, ""));
    const ping = (projectNeedsYou(project.id) || busy) ? " ping" : "";
    const initials = ceoInitials(project.name);
    const hasBlocker = (project.index_blocker || "").trim() && (project.index_blocker || "").trim() !== "—";
    const queuedCount = queueByProject.get(project.id) || 0;
    const queueChip = queuedCount > 0 ? `<span class="queue-chip" title="${queuedCount} task(s) queued">${queuedCount}</span>` : "";
    return `
      <div class="org-project${open ? " open" : ""}" data-project-wrap="${escapeHtml(project.id)}">
        <div class="org-row">
          <button type="button" class="org-twist" data-toggle="${escapeHtml(project.id)}" aria-label="${open ? "Collapse" : "Expand"} ${escapeHtml(project.name)}">${open ? "▾" : "▸"}</button>
          <button type="button" class="org-btn${projectId === project.id && !workerId ? " on" : ""}${ping}${busy ? " working" : ""}${hasBlocker ? " has-blocker" : ""}" data-project="${escapeHtml(project.id)}" data-worker="" data-kind="ceo" title="${escapeHtml(project.name)}${busy ? " · working" : ""}">
            <span class="org-avatar" aria-hidden="true">${escapeHtml(initials)}</span>
            <span class="org-btn-text">
              <b>${escapeHtml(project.name)}${queueChip}</b>
              ${wire ? `<span class="org-now">${escapeHtml(wire)}</span>` : ""}
            </span>
          </button>
          <span class="org-role">CEO</span>
        </div>
        ${workers ? `<div class="org-workers">${workers}</div>` : ""}
      </div>`;
  }).join("");
  const staffBusy = lives.has(aimKey("", ""));
  const cosInitials = ceoInitials("Chief of Staff");
  const staffQueuedCount = queueByProject.get("_staff") || 0;
  const staffQueueChip = staffQueuedCount > 0 ? `<span class="queue-chip" title="${staffQueuedCount} task(s) queued">${staffQueuedCount}</span>` : "";
  tree.innerHTML = `
    <button type="button" class="org-btn org-staff${!projectId ? " on" : ""}${staffBusy ? " ping working" : ""}" data-project="" data-worker="" data-kind="staff" title="Chief of Staff${staffBusy ? " · working" : ""}">
      <span class="org-avatar" aria-hidden="true">${escapeHtml(cosInitials)}</span>
      <span class="org-btn-text">
        <b>Chief of Staff${staffQueueChip}</b>
        <span class="org-now">runs the CEOs</span>
      </span>
    </button>
    ${inboxHtml()}
    ${projectBits}
    <button type="button" class="org-add" id="addCeoBtn">Add CEO</button>
  `;
  tree.querySelectorAll(".org-btn").forEach((btn) => {
    btn.addEventListener("click", () => setOrgNode(btn.dataset.project || "", btn.dataset.worker || ""));
    bindNodeMenu(btn, btn.dataset.kind, btn.dataset.project || "", btn.dataset.worker || "");
  });
  tree.querySelectorAll("[data-inbox]").forEach((btn) => {
    btn.addEventListener("click", () => {
      inboxSeen.add(btn.dataset.inbox);
      const pid = btn.dataset.project || "";
      const lane = btn.dataset.preset || "";
      setOrgNode(pid, "");
      if (lane && lane !== "cos") focusLane(lane);
      renderOrg(org);
    });
  });
  const addCeo = $("addCeoBtn");
  if (addCeo) {
    addCeo.addEventListener("click", (event) => {
      event.preventDefault();
      setOrgNode("", "");
      showNodeMenu(event.clientX, event.clientY, "staff", "", "");
    });
  }
  tree.querySelectorAll("[data-toggle]").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      const id = btn.dataset.toggle;
      if (expanded.has(id)) expanded.delete(id);
      else expanded.add(id);
      renderOrg(org);
    });
  });
}

function currentProject() {
  if (!projectId) return null;
  return (org.projects || []).find((row) => row.id === projectId) || null;
}

function currentWorker() {
  const project = currentProject();
  if (!project || !workerId) return null;
  return (project.workers || []).find((row) => row.id === workerId) || null;
}

function whereLabel() {
  const project = currentProject();
  const worker = currentWorker();
  if (worker && project) return `${project.name} · ${worker.name}`;
  if (project) return `${project.name} · CEO`;
  return "Chief of Staff";
}

function chatModelLabel() {
  const id = String((cfg.seats && cfg.seats.chat && cfg.seats.chat.model) || (cfg.catalog && cfg.catalog.recommended_chat) || "").trim();
  if (!id) return "Board · brief";
  const row = ((cfg.catalog && cfg.catalog.models) || []).find((model) => model.id === id);
  return (row && row.label) || id.split("/").filter(Boolean).slice(-1)[0] || id;
}

function selectedIndexText() {
  const worker = currentWorker();
  if (worker) return worker.brain || "";
  const project = currentProject();
  if (project) return project.index || "";
  return org.staff || org.index || "";
}

function renderBotMeta() {
  const text = selectedIndexText();
  if ($("indexCard")) $("indexCard").textContent = text || "(empty)";
  const worker = currentWorker();
  const project = currentProject();
  const label = worker ? `${worker.name} brief` : project ? `${project.name} brief` : "Chief of Staff brief";
  if ($("indexSummary")) {
    $("indexSummary").textContent = `${label} · ${indexNow(text)}`;
  }
  if ($("chatWhere")) $("chatWhere").textContent = whereLabel();
  if ($("chatFolder")) {
    if (!project) {
      $("chatFolder").textContent = "You → Chief of Staff → CEOs";
    } else {
      const tools = project.tools || {};
      const bits = [];
      const n = Number(tools.session_count || 0);
      if (n) bits.push(`${n.toLocaleString()} chats`);
      if (tools.session_title) bits.push(tools.session_title);
      $("chatFolder").textContent = bits.join(" · ") || "CEO";
    }
  }
  const folder = currentAim().folder || "";
  if ($("folder")) $("folder").value = folder;
  syncComposerWho();
  paintLanes();
  renderSchedules(project);
  loadSpend();
}

function renderSchedules(project) {
  const el = $("scheduleList");
  if (!el) return;
  const rows = (project && project.schedules) || [];
  if (!project || !rows.length) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  el.hidden = false;
  el.innerHTML = rows.map((row) => `
    <div class="schedule-row">
      <b>${escapeHtml(row.schedule || "")}</b>
      <span>${escapeHtml(row.text || "")}</span>
    </div>`).join("");
}

function fillProfile(data) {
  const name = (data.operator_name || "").trim() || "You";
  if ($("profileName")) $("profileName").textContent = name;
  if ($("operatorName") && document.activeElement !== $("operatorName")) {
    $("operatorName").value = data.operator_name || "";
  }
  if ($("pinNote")) {
    $("pinNote").textContent = data.has_pin
      ? "PIN is set. Leave blank to keep it. Unlock is once per board session."
      : "Optional. Unlock is once per board session.";
  }
  if ($("licenseNote")) {
    $("licenseNote").textContent = data.has_license
      ? "A license key is stored on this machine."
      : "Stored on this machine. Billing check comes later.";
  }
}

function fillSettings(data) {
  fillProfile(data);
  if ($("settingsFolder")) $("settingsFolder").value = data.work_dir || "";
  if ($("hostedFolderNote")) $("hostedFolderNote").classList.toggle("hidden", !data.hosted);
  if ($("spendCap")) $("spendCap").value = data.spend_cap_usd || 5;
  if ($("spendPeriod")) $("spendPeriod").value = data.spend_cap_period || "week";
  const policy = data.spend_policy || (data.spend && data.spend.policy) || {};
  if ($("spendBind")) $("spendBind").value = policy.bind || "payg";
  if ($("spendMode")) $("spendMode").value = policy.mode || "hard";
  if ($("spendFallback")) $("spendFallback").checked = policy.allow_zen_fallback !== false;
  if ($("hermesSkills") && document.activeElement !== $("hermesSkills")) {
    $("hermesSkills").value = data.hermes_skills || "";
  }
  if (data.org) renderOrg(data.org);
  fillKeys(data.keyring || {});
  fillImport(data.hermes_instances || []);
  fillCeoPanel();
  fillChannels();
  renderSeats(data.catalog, data.seats);
  if ($("profileAccount")) {
    $("profileAccount").innerHTML = accountSelectOptions(data.profile_account_id || cfg.profile_account_id, "keyring order");
  }
  if (!data.providers) return;
  const providers = data.providers;
  const list = providers.providers || [];
  const selected = data.default_provider || providers.default_provider || "opencode";
  const select = $("defaultProvider");
  if (select && (list.length || !select.options.length)) {
    const options = list.length ? list : [{ id: "opencode", label: "OpenCode" }];
    select.innerHTML = options.map((p) => (
      `<option value="${escapeHtml(p.id)}"${p.id === selected ? " selected" : ""}>${escapeHtml(p.label)}</option>`
    )).join("");
  }
  $("providerList").innerHTML = list.map((p) => `
    <article class="provider">
      <div class="provider-top">
        <b>${escapeHtml(p.label)}</b>
        <div class="pills">
          ${p.id === selected ? '<span class="pill default">default</span>' : ""}
          ${p.connected ? '<span class="pill on">on</span>' : ""}
        </div>
      </div>
      <div class="actions">
        <button type="button" class="ghost-btn" data-open-stage="${PROVIDER_STAGE[p.id] || (p.id === "nous" ? "hermes" : "opencode")}">${p.connected ? "Open" : "Connect"}</button>
        <a class="muted" href="${escapeHtml(p.connect)}" target="_blank" rel="noreferrer">${escapeHtml(p.id)}</a>
      </div>
    </article>
  `).join("");
  renderKv($("zenUsage"), zenRows(providers.zen));
  const stats = providers.local_stats || {};
  $("localStats").textContent = stats.text || stats.error || "No local OpenCode stats yet.";
}

function fillKeys(keyring) {
  if (keyring && Array.isArray(keyring.accounts)) cfg.keyring = keyring;
  const select = $("keyProvider");
  if (!select) return;
  const catalog = keyring.catalog || [];
  if (catalog.length) {
    const options = catalog.map((item) => (
      `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`
    )).join("");
    if (select) select.innerHTML = options;
    if ($("wizardProvider")) $("wizardProvider").innerHTML = options;
    if (catalog.some((item) => item.id === "nous")) {
      if (!select.value) select.value = "nous";
      if ($("wizardProvider")) $("wizardProvider").value = "nous";
    }
  }
  syncProviderHint("keyProvider", "keyProviderHint");
  syncProviderHint("wizardProvider", "wizardKeyHint");
  const portal = $("nousPortalStatus");
  if (portal) {
    portal.textContent = keyring.nous_portal
      ? "Hermes already has a Nous Portal login on this machine."
      : "No Portal login yet. Subscribe, then paste a key or connect in the Hermes tab.";
  }
  const accounts = keyring.accounts || [];
  const order = keyring.fallback || accounts.map((row) => row.id);
  const ranked = new Map(order.map((id, i) => [id, i]));
  const sorted = accounts.slice().sort((a, b) => (ranked.get(a.id) ?? 99) - (ranked.get(b.id) ?? 99));
  $("keyList").innerHTML = sorted.length ? sorted.map((row, index) => `
    <article class="provider">
      <div class="provider-top">
        <b>${escapeHtml(row.label)}</b>
        <div class="pills">
          <span class="pill">${escapeHtml(row.provider)}</span>
          ${index === 0 ? '<span class="pill on">primary</span>' : '<span class="pill">backup</span>'}
          ${row.has_key ? '<span class="pill on">on</span>' : ""}
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <input data-key-label="${escapeHtml(row.id)}" type="text" value="${escapeHtml(row.label)}" autocomplete="off" />
        </div>
      </div>
      <div class="actions">
        <button type="button" class="ghost-btn" data-save-label="${escapeHtml(row.id)}">Rename</button>
        <button type="button" class="ghost-btn" data-fallback-up="${escapeHtml(row.id)}">Up</button>
        <button type="button" class="ghost-btn" data-fallback-down="${escapeHtml(row.id)}">Down</button>
        <button type="button" class="ghost-btn" data-del-key="${escapeHtml(row.id)}">Remove</button>
      </div>
    </article>
  `).join("") : "";
  $("blockedList").innerHTML = (keyring.blocked || []).map((row) => (
    `<p class="hint"><b>${escapeHtml(row.label)}</b> — ${escapeHtml(row.note)}</p>`
  )).join("");
  const loginCeo = $("loginCeo");
  if (loginCeo) {
    const ceos = (org.projects || []).map((row) => (
      `<option value="${escapeHtml(row.id)}">${escapeHtml(row.name)}</option>`
    )).join("");
    loginCeo.innerHTML = `<option value="">All CEOs</option>${ceos}`;
  }
  const loginList = $("loginList");
  if (loginList) {
    const names = Object.fromEntries((org.projects || []).map((row) => [row.id, row.name]));
    const logins = keyring.logins || [];
    loginList.innerHTML = logins.length ? logins.map((row) => `
      <article class="provider">
        <div class="provider-top">
          <b>${escapeHtml(row.label || row.username || "login")}</b>
          <div class="pills">
            ${row.auto ? '<span class="pill on">auto</span>' : '<span class="pill">ask</span>'}
            ${row.has_password ? '<span class="pill on">on</span>' : ""}
          </div>
        </div>
        <p class="muted">${escapeHtml([row.username, row.site, names[row.project_id] || ""].filter(Boolean).join(" · "))}</p>
        <div class="actions">
          <button type="button" class="ghost-btn" data-del-login="${escapeHtml(row.id)}">Remove</button>
        </div>
      </article>
    `).join("") : "";
  }
}

function fillImport(instances) {
  const list = $("hermesInstanceList");
  if (!list) return;
  const rows = instances || [];
  list.innerHTML = rows.length ? rows.map((row) => `
    <article class="provider">
      <div class="provider-top">
        <b>${escapeHtml(row.label)}</b>
        <div class="pills">
          ${row.has_key ? '<span class="pill on">on</span>' : ""}
        </div>
      </div>
      <p class="hint">${escapeHtml(row.url || "")}</p>
      <div class="actions">
        <button type="button" class="ghost-btn" data-list-sessions="${escapeHtml(row.id)}">List sessions</button>
        <button type="button" class="ghost-btn" data-del-instance="${escapeHtml(row.id)}">Remove</button>
      </div>
    </article>
  `).join("") : "";
}

function applyConfig(data) {
  cfg = data;
  if (data.org) {
    org = data.org;
    renderOrg(org);
  }
  if (data.engines) renderEngines(data.engines, "firstEngines");
  renderSpend(data.spend);
  renderActivity(data.activity);
  if (data.work_dir) {
    $("folder").value = data.work_dir;
    if ($("workDir")) $("workDir").value = data.work_dir;
  }
  if (data.brains) brains = data.brains;
  try {
    fillSettings(data);
  } catch (_err) {
    /* keys/seats are optional; org already painted */
  }
  renderBotMeta();
}

function syncHermesHint() {
  const hint = $("hermesHint");
  if (hint) hint.classList.toggle("hidden", stage !== "hermes");
  const retry = $("retryHermes");
  if (retry) retry.classList.toggle("hidden", stage !== "hermes" || !hermesFailed);
}

let applyingHash = false;

function syncHash() {
  if (applyingHash) return;
  const settings = $("settings");
  const open = settings && !settings.classList.contains("hidden");
  let next = "#";
  if (open) {
    const panel = document.querySelector(".drawer-tab.on");
    next = `#settings/${(panel && panel.dataset.panel) || "you"}`;
  } else if (stage && stage !== "chat") {
    next = `#${stage}`;
  }
  const current = location.hash || "#";
  if (current === next || (next === "#" && current === "")) return;
  history.replaceState(null, "", next === "#" ? `${location.pathname}${location.search}` : next);
}

function applyHash() {
  applyingHash = true;
  try {
    const raw = (location.hash || "").replace(/^#/, "");
    if (raw.startsWith("settings")) {
      const panel = raw.split("/")[1] || "you";
      setSettings(true, panel);
      return;
    }
    if ($("settings") && !$("settings").classList.contains("hidden")) setSettings(false);
    if (raw === "opencode" || raw === "hermes") setStage(raw);
    else setStage("chat");
  } finally {
    applyingHash = false;
  }
}

function setStage(name) {
  stage = name;
  document.querySelectorAll(".stage-btn").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.stage === name);
  });
  document.querySelectorAll(".workspace").forEach((el) => {
    el.classList.toggle("on", el.id === `stage-${name}`);
  });
  syncHermesHint();
  if (name === "opencode") startOpenCode();
  if (name === "hermes") startHermes();
  syncHash();
}

function setMenu(_open) {
  return;
}

function setSettings(open, panel) {
  if (panel) setSettingsPanel(panel);
  else if (open) setSettingsPanel("you");
  $("settings").classList.toggle("hidden", !open);
  if (open) {
    loadJobs();
    refreshProviders();
    loadGit();
    $("closeSettings").focus();
  }
  syncHash();
}

function setSettingsPanel(name) {
  const title = PANEL_TITLES[name] || "Settings";
  $("settingsTitle").textContent = title;
  document.querySelectorAll(".drawer-tab").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.panel === name);
  });
  document.querySelectorAll(".drawer-panel").forEach((el) => {
    el.classList.toggle("on", el.id === `panel-${name}`);
  });
  if (name === "models") refreshCatalog();
  if (name === "connectors") loadConnectorsCatalog();
  if (name === "memory") fetchOpenHandoffs();
  if (name === "git") loadGit();
  if (name === "keys") refreshProviders();
  if (name === "import") fillImport(cfg.hermes_instances || []);
  if (name === "ceo") fillCeoPanel();
  if (name === "channels") fillChannels();
  if (name === "memory") loadMemory();
  if (name === "usage") loadJobs();
  if ($("settings") && !$("settings").classList.contains("hidden")) syncHash();
}

async function refreshCatalog() {
  try {
    const res = await fetch("/api/catalog");
    const catalog = await res.json();
    cfg.catalog = catalog;
    renderSeats(catalog, cfg.seats);
  } catch (_err) {
    /* keep last catalog */
  }
}

function openWorkspace(name) {
  setSettings(false);
  setStage(name);
}

async function setOrgNode(project, worker) {
  projectId = project || "";
  workerId = worker || "";
  preset = "cos";
  focusedLane = "";
  unreadLanes = new Set();
  if (projectId) expanded.add(projectId);
  syncLiveFromAim();
  renderOrg(org);
  renderBotMeta();
  await loadThread();
  syncComposerWho();
  scrollChatBottom();
  if (projectId) {
    startOpenCode();
    startHermes();
  }
  if (!liveRunId) await drainQueue();
}

function setRoute(name) {
  preset = name || "cos";
  if (preset && preset !== "cos") unreadLanes.delete(preset);
  renderBotMeta();
  scrollChatBottom();
}

function card(kind, body, meta) {
  const el = document.createElement("article");
  el.className = `card ${kind}`;
  el.innerHTML = `<div class="meta">${escapeHtml(meta || kind)}</div><pre>${escapeHtml(body)}</pre>`;
  stream.appendChild(el);
  stream.scrollTop = stream.scrollHeight;
  return el;
}

function bubble(kind, body) {
  const el = document.createElement("article");
  el.className = `bubble ${kind}`;
  const text = document.createElement("div");
  text.className = "bubble-text";
  text.textContent = body || "";
  el.appendChild(text);
  stream.appendChild(el);
  stream.scrollTop = stream.scrollHeight;
  return el;
}

function renderAttachments(el, attachments) {
  if (!el || !attachments || !attachments.length) return;
  const attDiv = document.createElement("div");
  attDiv.className = "bubble-attachments";
  attachments.forEach((att) => {
    const filename = att.filename || "";
    const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(filename);
    if (isImage) {
      const imgWrap = document.createElement("div");
      imgWrap.className = "bubble-attachment";
      const img = document.createElement("img");
      img.src = att.id ? `/api/attachments/${att.id}` : "";
      img.alt = filename;
      imgWrap.appendChild(img);
      attDiv.appendChild(imgWrap);
    } else {
      const fileWrap = document.createElement("div");
      fileWrap.className = "bubble-attachment";
      const fileDiv = document.createElement("div");
      fileDiv.className = "bubble-attachment-file";
      fileDiv.innerHTML = `<span class="bubble-attachment-icon">📄</span><span class="bubble-attachment-name">${escapeHtml(filename)}</span>`;
      fileWrap.appendChild(fileDiv);
      attDiv.appendChild(fileWrap);
    }
  });
  el.appendChild(attDiv);
}

function appendWorkDetails(el, job) {
  if (!el || el.querySelector(".bubble-work")) return;
  const engine = job.engine || "board";
  if (engine === "board" || job.preset === "cos") return;
  const details = document.createElement("details");
  details.className = "bubble-work";
  const summary = document.createElement("summary");
  const cost = Number(job.usd_estimate || 0);
  summary.textContent = [
    job.engine || "board",
    job.preset || "",
    job.model && job.model !== "none" ? job.model : "",
    cost ? `$${cost.toFixed(4)}` : ""
  ].filter(Boolean).join(" · ");
  details.appendChild(summary);
  const bits = document.createElement("div");
  bits.className = "muted";
  bits.textContent = [
    job.id ? `job ${job.id}` : "",
    job.session ? `session ${job.session}` : "",
    job.blocker ? `blocker ${job.blocker}` : ""
  ].filter(Boolean).join(" · ");
  if (bits.textContent) details.appendChild(bits);
  if ((job.engine || "") === "Hermes Agent") {
    const open = document.createElement("button");
    open.type = "button";
    open.className = "ghost-btn";
    open.textContent = "Open Hermes";
    open.addEventListener("click", () => setStage("hermes"));
    details.appendChild(open);
  }
  el.appendChild(details);
}

function settleLive(live, job) {
  if (job && job.id) seenJobIds.add(job.id);
  if (!live || !job) {
    if (job) renderJob(job);
    return;
  }
  if (isTalk(job)) {
    live.classList.remove("live");
    const think = live.querySelector(".thinking");
    if (think) think.remove();
    const text = live.querySelector(".bubble-text");
    if (text) text.textContent = job.text || "";
    stampLane(live, job, true);
    appendWorkDetails(live, job);
    // Add report card to settled live bubble
    if (!live.querySelector(".report-card")) {
      const reportCard = renderReportCard(job);
      if (reportCard) live.appendChild(reportCard);
    }
    scrollChatBottom();
    return;
  }
  live.remove();
  renderJob(job);
  scrollChatBottom();
}

function thinkingBubble() {
  const el = document.createElement("article");
  el.className = "bubble bot live";
  el.dataset.liveKey = aimKey();
  const think = document.createElement("div");
  think.className = "thinking";
  think.innerHTML = `<span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="thinking-label">${escapeHtml(talkName())} is working…</span>`;
  const text = document.createElement("div");
  text.className = "bubble-text";
  el.appendChild(think);
  el.appendChild(text);
  stream.appendChild(el);
  stream.scrollTop = stream.scrollHeight;
  return el;
}

function liveBubbleFor(key) {
  if (!stream) return null;
  return stream.querySelector(`.bubble.live[data-live-key="${CSS.escape(key)}"]`);
}

function jobMeta(job) {
  return [
    job.cron ? "cron" : "",
    `job ${job.id}`,
    `preset ${job.preset}`,
    `engine ${job.engine}`,
    job.handoff && job.handoff.length > 1 ? `handoff ${job.handoff.join(" → ")}` : "",
    job.gate && job.gate.label ? job.gate.label : "",
    job.handoff_path ? job.handoff_path : "",
    `model ${job.model || "none"}`,
    `$${Number(job.usd_estimate || 0).toFixed(4)}`,
    job.stopped ? "stopped" : "",
    job.blocker ? `blocker: ${job.blocker}` : "ok"
  ].filter(Boolean).join(" · ");
}

function isTalk(job) {
  if (!job) return false;
  if (job.login_wall) return false;
  const hasDiff = Boolean((job.diff && String(job.diff).trim()) || (job.untracked && job.untracked.length));
  if (hasDiff) return false;
  return Boolean(job.talk) || job.preset === "cos";
}

function renderTalk(job) {
  const el = bubble("bot", job.text || "");
  stampLane(el, job);
  appendWorkDetails(el, job);
  // Add report card for talk jobs too
  const reportCard = renderReportCard(job);
  if (reportCard) el.appendChild(reportCard);
  return el;
}

function continueAfterLogin(job) {
  const lane = (job && job.preset && job.preset !== "cos") ? job.preset : "think";
  sendMessage(
    "Continue. An approved site login is in .openbot-logins.json in this Hermes home. Fill the page from that file. Never print the file or any password. If TOTP or CAPTCHA appears, stop with LOGIN_WALL.",
    { preset: lane, allowSecret: true }
  );
}

function parseComposerLogin(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const pass = raw.match(/(?:password|passwd|pwd)\s*(?:is|=|:)\s*(\S+)/i);
  const email = raw.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  if (email && pass) {
    return { username: email[0], password: pass[1].replace(/[.,;]+$/, ""), site: "" };
  }
  const lines = raw.split(/\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.length === 2 && /@/.test(lines[0]) && lines[1].length >= 4 && !/\s/.test(lines[1])) {
    return { username: lines[0], password: lines[1], site: "" };
  }
  return null;
}

function mountLoginForm(el, job) {
  const form = document.createElement("div");
  form.className = "login-form";
  const offers = (job && job.logins) || [];
  const saved = offers.map((row) => (
    `<button type="button" class="ghost-btn" data-use-login="${escapeHtml(row.id)}">Approve ${escapeHtml(row.label || row.username || "saved login")}</button>`
  )).join("");
  form.innerHTML = `
    ${saved ? `<div class="login-saved">${saved}</div>` : ""}
    <div class="field">
      <label>Username</label>
      <input data-login-user type="text" autocomplete="username" value="${escapeHtml((offers[0] && offers[0].username) || "")}" />
    </div>
    <div class="field">
      <label>Password</label>
      <input data-login-pass type="password" autocomplete="current-password" />
    </div>
    <div class="field">
      <label>Site</label>
      <input data-login-site type="text" value="${escapeHtml((job && job.url) || "")}" autocomplete="off" />
    </div>
    <label class="check-line">
      <input data-login-save type="checkbox" checked />
      Save in vault for this CEO
    </label>
    <label class="check-line">
      <input data-login-auto type="checkbox" />
      Let agents use it next time without asking
    </label>
    <div class="job-actions">
      <button type="button" class="send" data-login-once>Use once</button>
      <button type="button" class="ghost-btn" data-login-save-go>Save and continue</button>
    </div>
    <p class="muted">This does not go into chat. TOTP and CAPTCHA still stop on your screen.</p>
  `;
  async function postUse(payload) {
    const res = await fetch("/api/logins/use", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      const note = form.querySelector(".muted");
      if (note) note.textContent = data.error || "login not saved";
      return false;
    }
    if (data.keyring) fillKeys(data.keyring);
    return true;
  }
  form.addEventListener("click", async (event) => {
    const savedBtn = event.target.closest("[data-use-login]");
    if (savedBtn) {
      const ok = await postUse({
        login_id: savedBtn.dataset.useLogin,
        project_id: (job && job.project_id) || projectId || null
      });
      if (ok) continueAfterLogin(job);
      return;
    }
    const once = event.target.closest("[data-login-once]");
    const saveGo = event.target.closest("[data-login-save-go]");
    if (!once && !saveGo) return;
    const user = form.querySelector("[data-login-user]");
    const pass = form.querySelector("[data-login-pass]");
    const site = form.querySelector("[data-login-site]");
    const saveBox = form.querySelector("[data-login-save]");
    const autoBox = form.querySelector("[data-login-auto]");
    const ok = await postUse({
      username: user ? user.value.trim() : "",
      password: pass ? pass.value : "",
      site: site ? site.value.trim() : "",
      label: "",
      project_id: (job && job.project_id) || projectId || null,
      save: Boolean(saveGo) || Boolean(saveBox && saveBox.checked),
      auto: Boolean(autoBox && autoBox.checked)
    });
    if (ok) continueAfterLogin(job);
  });
  el.appendChild(form);
}

function fillLoginOffer(parsed) {
  const form = stream.querySelector(".login-form");
  if (form) {
    const user = form.querySelector("[data-login-user]");
    const pass = form.querySelector("[data-login-pass]");
    if (user && parsed.username) user.value = parsed.username;
    if (pass && parsed.password) pass.value = parsed.password;
    return true;
  }
  renderJob({
    login_wall: true,
    project_id: projectId || "",
    preset: (preset && preset !== "cos") ? preset : "think",
    url: parsed.site || "",
    logins: ((cfg.keyring || {}).logins || []).filter((row) => !row.project_id || row.project_id === projectId),
    text: "This looks like a login. It will not go into chat. Approve it for this job, or save it in the vault.",
    engine: "board",
    keep_going: true
  });
  const next = stream.querySelector(".login-form");
  if (next) {
    const user = next.querySelector("[data-login-user]");
    const pass = next.querySelector("[data-login-pass]");
    if (user) user.value = parsed.username || "";
    if (pass) pass.value = parsed.password || "";
  }
  return true;
}

function renderReportCard(job) {
  if (!job) return null;
  const card = document.createElement("div");
  card.className = "report-card";
  
  // Header: engine · model · $ · preset
  const header = document.createElement("div");
  header.className = "report-card-header";
  const engine = escapeHtml(job.engine || "board");
  const model = escapeHtml(modelName(job.model) || job.model || "none");
  const cost = Number(job.usd_estimate || 0);
  const costStr = cost > 0 ? `$${cost.toFixed(4)}` : "$0";
  const presetLabel = escapeHtml(job.preset || "cos");
  header.innerHTML = `<span><b>${engine}</b> · ${model} · <i>${costStr}</i> · ${presetLabel}</span>`;
  card.appendChild(header);
  
  // RESULT section (≤20 lines or clear empty/error)
  const result = document.createElement("div");
  result.className = "report-result";
  const text = String(job.text || "").trim();
  if (text) {
    const lines = text.split("\n");
    const displayLines = lines.slice(0, 20);
    result.textContent = displayLines.join("\n");
    if (lines.length > 20) {
      result.textContent += `\n… (${lines.length - 20} more lines)`;
    }
  } else if (job.blocker) {
    result.textContent = `Error: ${job.blocker}`;
  }
  card.appendChild(result);
  
  // INDEX delta: Now / Last / Next / Blocker
  const hasIndexDelta = job.index_now || job.index_last || job.next || job.index_blocker;
  if (hasIndexDelta) {
    const delta = document.createElement("div");
    delta.className = "report-index-delta";
    const rows = [];
    if (job.index_now) {
      const val = String(job.index_now).trim();
      rows.push(`<div><dt>Now</dt><dd class="${val === "—" ? "empty" : ""}">${escapeHtml(val)}</dd></div>`);
    }
    if (job.index_last) {
      const val = String(job.index_last).trim();
      rows.push(`<div><dt>Last</dt><dd class="${val === "—" ? "empty" : ""}">${escapeHtml(val)}</dd></div>`);
    }
    if (job.next) {
      const val = String(job.next).trim();
      rows.push(`<div><dt>Next</dt><dd class="${val === "—" ? "empty" : ""}">${escapeHtml(val)}</dd></div>`);
    }
    if (job.index_blocker) {
      const val = String(job.index_blocker).trim();
      const isBlocked = val && val !== "—";
      rows.push(`<div><dt>Blocker</dt><dd class="${isBlocked ? "blocker" : "empty"}">${escapeHtml(val)}</dd></div>`);
    }
    delta.innerHTML = rows.join("");
    card.appendChild(delta);
  }
  
  return card;
}

function renderHandoffCard(job) {
  if (!job.handoff_to || !job.handoff_from) return null;
  const handoffCard = document.createElement("div");
  handoffCard.className = "handoff-card";
  const fromLabel = jobLabel(job.handoff_from) || job.handoff_from;
  const toLabel = jobLabel(job.handoff_to) || job.handoff_to;
  const status = job.handoff_status || "complete";
  const task = job.handoff_task || job.message || "—";
  const output = job.handoff_output || job.text || "—";
  const nextOwner = job.handoff_next_owner || "operator";
  handoffCard.innerHTML = `
    <div class="handoff-header">
      <b>Handoff</b>
      <span class="handoff-route">${escapeHtml(fromLabel)} → ${escapeHtml(toLabel)}</span>
    </div>
    <div class="handoff-body">
      <div class="handoff-row">
        <div class="handoff-label">Task</div>
        <div class="handoff-value">${escapeHtml(task.slice(0, 200))}</div>
      </div>
      <div class="handoff-row">
        <div class="handoff-label">Status</div>
        <div class="handoff-value status-${escapeHtml(status)}">${escapeHtml(status)}</div>
      </div>
      <div class="handoff-row">
        <div class="handoff-label">Output</div>
        <div class="handoff-value">${escapeHtml(output.slice(0, 300))}</div>
      </div>
      <div class="handoff-row">
        <div class="handoff-label">Next Owner</div>
        <div class="handoff-value">${escapeHtml(nextOwner)}</div>
      </div>
    </div>
  `;
  return handoffCard;
}

function renderJob(job) {
  if (job && job.id) {
    seenCron.add(job.id);
    seenJobIds.add(job.id);
  }
  if (isTalk(job)) {
    renderTalk(job);
    return;
  }
  const kind = job.login_wall ? "bot wall" : "bot";
  const body = job.login_wall && !job.text
    ? "This page needs a login. Approve a vault login, type it on this card, or sign in on your screen."
    : (job.text || JSON.stringify(job, null, 2));
  const el = card(kind, body, jobMeta(job));
  if (job.id) {
    el.setAttribute("data-job-id", job.id);
  }
  stampLane(el, job);
  if (job.step_count && job.total_steps) {
    const stepChip = document.createElement("div");
    stepChip.className = "step-chip";
    stepChip.textContent = `Step ${job.step_count}/${job.total_steps}`;
    const meta = el.querySelector(".meta");
    if (meta) {
      meta.appendChild(document.createTextNode(" · "));
      meta.appendChild(stepChip);
    }
  }
  const actions = document.createElement("div");
  actions.className = "job-actions";
  if (job.login_wall && job.url) {
    const open = document.createElement("a");
    open.className = "send";
    open.href = job.url;
    open.target = "_blank";
    open.rel = "noreferrer";
    open.textContent = "Open page";
    actions.appendChild(open);
  }
  if (job.keep_going && !job.stopped) {
    const go = document.createElement("button");
    go.type = "button";
    go.className = "ghost-btn";
    const stepCounter = (job.step_count && job.total_steps) 
      ? ` (${job.step_count}/${job.total_steps})` 
      : "";
    go.textContent = job.login_wall ? "I already logged in" : `Continue${stepCounter}`;
    go.addEventListener("click", () => {
      const lane = (job.preset && job.preset !== "cos") ? job.preset : "";
      if (job.login_wall) {
        sendMessage("Continue. I logged in on my screen.", { preset: lane || "think", allowSecret: true });
        return;
      }
      const aim = aimKey();
      const next = job.next && job.next !== "—" ? job.next : "Continue from Last and Next on the brief.";
      const lastResult = (job.text || "").trim();
      const resultSnippet = lastResult.slice(-600);
      const continueMsg = `Continue. Last RESULT:\n${resultSnippet}\n\nNext: ${next}`;
      
      // ALWAYS increment: step = (job.step_count||0)+1, total = max
      const step = (job.step_count || 0) + 1;
      const ctx = {
        step: step,
        total: Math.max(job.total_steps || 0, step),
        last_result: resultSnippet
      };
      chainContexts.set(aim, ctx);
      
      sendMessage(continueMsg, lane ? { preset: lane, chain_context: ctx } : { chain_context: ctx });
    });
    actions.appendChild(go);
  }
  if (actions.childNodes.length) el.appendChild(actions);
  if (job.login_wall) mountLoginForm(el, job);
  const handoffCard = renderHandoffCard(job);
  if (handoffCard) el.appendChild(handoffCard);
  const gate = job.gate || {};
  if (gate.label || job.handoff_path) {
    const line = document.createElement("p");
    line.className = `gate-line ${gate.action || ""}`;
    line.textContent = [gate.label, job.handoff_path ? `file ${job.handoff_path}` : ""].filter(Boolean).join(" · ");
    el.appendChild(line);
  }
  // Add report card for non-talk jobs
  if (!isTalk(job)) {
    const reportCard = renderReportCard(job);
    if (reportCard) el.appendChild(reportCard);
  }
  const hasDiff = Boolean((job.diff && job.diff.trim()) || (job.untracked && job.untracked.length));
  if (!hasDiff) return;
  const diffBlock = document.createElement("div");
  diffBlock.className = "diff-wrap";
  diffBlock.innerHTML = `<div class="meta">action gate · Accept keeps the local diff · Reject restores</div><pre class="diff">${escapeHtml(job.diff || "(untracked files only)")}</pre>`;
  if (job.diff_pending) {
    const diffActions = document.createElement("div");
    diffActions.className = "diff-actions";
    const accept = document.createElement("button");
    accept.type = "button";
    accept.className = "send";
    accept.textContent = "Accept";
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "ghost-btn";
    reject.textContent = "Reject";
    accept.addEventListener("click", () => decide(job.id, "accept", diffActions));
    reject.addEventListener("click", () => decide(job.id, "reject", diffActions));
    diffActions.appendChild(accept);
    diffActions.appendChild(reject);
    diffBlock.appendChild(diffActions);
  }
  el.appendChild(diffBlock);
}

function emptyStreamHtml() {
  const project = currentProject();
  const worker = currentWorker();
  const text = selectedIndexText();
  const now = indexNow(text);
  const nxt = (text.match(/^Next:\s*(.*)$/m) || [])[1] || "";
  const blocked = (text.match(/^Blocker:\s*(.*)$/m) || [])[1] || "";
  const stuck = blocked && blocked !== "—" ? blocked : "";
  const title = worker ? worker.name : project ? project.name : "Chief of Staff";
  let lead = "You are talking to Chief of Staff — the bot under you. CEOs report here. Click a CEO for their own chat.";
  if (worker && project) {
    lead = `You are talking to ${worker.name} on ${project.name}. Work still reports in this chat.`;
  } else if (project) {
    lead = `You are talking to ${project.name}. Pin Code, Think, Research, or Ops below when you want that engine next. A CEO can propose a helper here if one is actually needed.`;
  }
  return `
    <div class="empty-stream" id="streamEmpty">
      <p class="empty-kicker">${escapeHtml(whereLabel())}</p>
      <h1>${escapeHtml(title)}</h1>
      <p><b>Now</b> ${escapeHtml(now === "source of truth" ? "—" : now)}</p>
      ${nxt ? `<p><b>Next</b> ${escapeHtml(nxt)}</p>` : ""}
      ${stuck ? `<p><b>Blocked</b> ${escapeHtml(stuck)}</p>` : "<p>Nothing blocked on the brief.</p>"}
      <p>${lead}</p>
    </div>`;
}

function renderTurns(turns, extras) {
  extras = extras || {};
  const telegram = extras.telegram || [];
  const note = extras.note || "";
  const rows = turns || [];
  hydratingHistory = true;
  unreadLanes = new Set();
  focusedLane = "";
  if (!rows.length && !telegram.length) {
    stream.innerHTML = emptyStreamHtml();
    hydratingHistory = false;
    paintLanes();
    return;
  }
  stream.innerHTML = "";
  if (telegram.length) {
    const banner = document.createElement("p");
    banner.className = "channel-banner";
    banner.textContent = note || "Hermes Telegram history. This instance owns the live bots.";
    stream.appendChild(banner);
    telegram.forEach((turn) => {
      const el = bubble(turn.role === "user" ? "user" : "bot", turn.text || "");
      if (turn.role !== "user") el.classList.add("from-telegram");
    });
  }
  let lastBot = "";
  rows.forEach((turn, index) => {
    if (turn.role === "user") {
      lastBot = "";
      const el = bubble("user", turn.text || "");
      if (turn.quote) attachQuotePreview(el, turn.quote);
      if (turn.attachments) renderAttachments(el, turn.attachments);
      const next = rows[index + 1];
      const nextLane = next && next.job ? workLane(next.job) : "";
      el.dataset.lane = nextLane || "cos";
      return;
    }
    if (turn.source === "telegram") {
      lastBot = "";
      const el = bubble("bot", turn.text || "");
      el.classList.add("from-telegram");
      return;
    }
    if (!turn.job) return;
    const text = String(turn.job.text || "");
    if (turn.job.talk && text && text === lastBot) return;
    lastBot = text;
    renderJob(turn.job);
  });
  hydratingHistory = false;
  paintLanes();
  scrollChatBottom();
}

async function loadThread() {
  const key = aimKey();
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
    if (workerId) params.set("worker_id", workerId);
  }
  const res = await fetch(`/api/thread?${params.toString()}`);
  const data = await res.json();
  const turns = data.turns || [];
  let telegram = [];
  let note = "";
  if (projectId && !workerId) {
    try {
      const channelRes = await fetch(`/api/org/projects/${encodeURIComponent(projectId)}/channel`);
      const channel = await channelRes.json();
      telegram = channel.turns || [];
      note = channel.note || "";
    } catch (_err) {
      telegram = [];
    }
  }
  renderTurns(turns, { telegram, note });
  if (liveFor(key)) {
    const el = thinkingBubble();
    el.dataset.liveKey = key;
  }
}

async function refreshThreadTail() {
  if (liveFor(aimKey())) return;
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
    if (workerId) params.set("worker_id", workerId);
  }
  const res = await fetch(`/api/thread?${params.toString()}`);
  const data = await res.json();
  hydratingHistory = true;
  (data.turns || []).forEach((turn) => {
    if (!turn || !turn.job || !turn.job.id || seenJobIds.has(turn.job.id)) return;
    renderJob(turn.job);
  });
  hydratingHistory = false;
  paintLanes();
  scrollChatBottom();
}

async function decide(jobId, action, actionsEl, force = false) {
  actionsEl.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const res = await fetch(`/api/jobs/${jobId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: force })
  });
  const data = await res.json();
  
  // Handle validation failure
  if (!data.ok && data.validation_failed) {
    // Show validation error card with Force Accept option
    actionsEl.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    
    const errorCard = document.createElement("div");
    errorCard.className = "card card-blocker";
    errorCard.innerHTML = `
      <div class="meta">validation failed · syntax/lint errors block Accept</div>
      <pre class="validation-error">${escapeHtml(data.validation_error || "validation failed")}</pre>
      <div class="actions">
        <button type="button" class="send" id="forceAccept-${jobId}">Force Accept</button>
        <button type="button" class="ghost-btn" id="fixFirst-${jobId}">Fix First</button>
      </div>
    `;
    
    // Insert error card after the diff card
    const diffCard = actionsEl.closest(".card");
    if (diffCard && diffCard.parentNode) {
      diffCard.parentNode.insertBefore(errorCard, diffCard.nextSibling);
    } else {
      stream.appendChild(errorCard);
    }
    
    // Wire up Force Accept button
    const forceBtn = document.getElementById(`forceAccept-${jobId}`);
    const fixBtn = document.getElementById(`fixFirst-${jobId}`);
    if (forceBtn) {
      forceBtn.addEventListener("click", () => {
        errorCard.remove();
        decide(jobId, "accept", actionsEl, true);
      });
    }
    if (fixBtn) {
      fixBtn.addEventListener("click", () => {
        errorCard.remove();
        actionsEl.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      });
    }
    
    return;
  }
  
  if (data.index) renderIndex(data.index);
  if (data.spend) renderSpend(data.spend);
  
  const statusText = data.ok
    ? (action === "accept" ? (force ? "diff force accepted" : "diff accepted") : "diff rejected · restored")
    : (data.error || "diff action failed");
  card("bot", statusText, `job ${jobId}`);
  
  // Show inline Brief update after Accept/Reject
  if (data.ok && data.index) {
    const now = indexField(data.index, "Now");
    const last = indexField(data.index, "Last");
    const next = indexField(data.index, "Next");
    const blocker = indexField(data.index, "Blocker");
    
    let briefLines = [`Now: ${now}`];
    if (last !== "—") briefLines.push(`Last: ${last}`);
    if (next !== "—") briefLines.push(`Next: ${next}`);
    if (blocker !== "—") briefLines.push(`Blocker: ${blocker}`);
    
    card("bot brief", briefLines.join("\n"), "Brief updated");
  }
}

async function loadJobs() {
  const res = await fetch("/api/jobs");
  const data = await res.json();
  const jobs = data.jobs || [];
  if (!jobs.length) {
    $("jobLog").innerHTML = "";
    return;
  }
  $("jobLog").innerHTML = jobs.map((job) => `
    <article class="job-row">
      <div class="job-id">${escapeHtml(job.id || "")}</div>
      <div>${escapeHtml(job.preset || "")} · ${escapeHtml(job.engine || "")}</div>
      <div class="muted">${escapeHtml(job.model || "no model")} · $${Number(job.usd_estimate || 0).toFixed(4)}</div>
      <div class="muted">${job.blocker ? escapeHtml(job.blocker) : "ok"}${job.at ? ` · ${escapeHtml(job.at)}` : ""}</div>
    </article>
  `).join("");
}

async function refreshProviders() {
  const res = await fetch("/api/providers");
  const data = await res.json();
  cfg.providers = data;
  fillSettings({ ...cfg, providers: data });
}

function currentAim() {
  const project = currentProject();
  if (!project) {
    return { name: "Chief of Staff", folder: "", hermesHome: "", sessionId: "", idle: true };
  }
  return {
    name: project.name,
    folder: project.folder || "",
    hermesHome: (project.tools && project.tools.hermes_home) || "",
    sessionId: (project.tools && project.tools.hermes_session_id) || "",
    idle: false
  };
}

function reloadEngineFrame(frameId, url, token) {
  const frame = $(frameId);
  if (!frame || !url) return;
  const prev = frame.getAttribute("data-aim") || "";
  if (prev === token && frame.src && frame.src.indexOf("127.0.0.1") !== -1) return;
  frame.setAttribute("data-aim", token);
  frame.src = "about:blank";
  window.setTimeout(() => {
    const next = $(frameId);
    if (next) next.src = url;
  }, 40);
}

async function startOpenCode() {
  const aim = currentAim();
  if (aim.idle) {
    if ($("ocTitle")) $("ocTitle").textContent = "OpenCode";
    $("ocStatus").textContent = lastOcFolder
      ? `Still on last CEO folder · ${lastOcFolder}. Click a CEO so Chat, OpenCode, and Hermes match.`
      : "Click a CEO so OpenCode opens that folder.";
    return;
  }
  const folder = aim.folder || (($("folder") && $("folder").value.trim()) || null);
  if ($("ocTitle")) $("ocTitle").textContent = `OpenCode · ${aim.name}`;
  $("ocStatus").textContent = folder
    ? `Aiming OpenCode at ${folder}…`
    : "Starting official OpenCode web…";
  const res = await fetch("/api/engines/opencode/web", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder })
  });
  const data = await res.json();
  if (!data.ok && !data.url) {
    $("ocStatus").innerHTML = `${escapeHtml(data.error || "OpenCode missing")}${data.install ? ` · <a href="${data.install}">install</a>` : ""}`;
    return;
  }
  const url = data.url || "http://127.0.0.1:4096";
  const aimed = data.folder || folder || "";
  $("ocStatus").innerHTML = `Workspace <a href="${url}" target="_blank" rel="noreferrer">${url}</a>${aimed ? ` · ${escapeHtml(aimed)}` : ""} · OpenCode chats are OpenCode’s own history, not Hermes.`;
  reloadEngineFrame("ocFrame", url, aimed || aim.name);
  lastOcFolder = aimed;
  ocStarted = true;
}

async function startHermes() {
  const aim = currentAim();
  if (aim.idle) {
    if ($("hermesTitle")) $("hermesTitle").textContent = "Hermes";
    $("hermesStatus").textContent = lastHermesHome
      ? `Still on last CEO home · ${lastHermesHome}. Click a CEO so Chat, OpenCode, and Hermes match.`
      : "Click a CEO so Hermes opens that home.";
    if ($("hermesAim")) $("hermesAim").textContent = lastHermesHome || "—";
    return;
  }
  hermesFailed = false;
  if ($("hermesTitle")) $("hermesTitle").textContent = `Hermes · ${aim.name}`;
  $("hermesStatus").textContent = "Starting…";
  if ($("hermesAim")) $("hermesAim").textContent = aim.hermesHome || "machine Hermes home";
  syncHermesHint();
  const res = await fetch("/api/engines/hermes/dashboard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hermes_home: aim.hermesHome || "" })
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    hermesFailed = true;
    const docs = data.install ? ` · <a href="${data.install}" target="_blank" rel="noreferrer">docs</a>` : "";
    $("hermesStatus").innerHTML = `${escapeHtml(data.error || "Hermes Agent missing")}${docs}`;
    syncHermesHint();
    return;
  }
  const base = data.url || "http://127.0.0.1:9119";
  const aimed = data.home || aim.hermesHome || "";
  const sid = data.session_id || aim.sessionId || "";
  const url = sid ? `${base.replace(/\/$/, "")}/chat?resume=${encodeURIComponent(sid)}` : base;
  hermesFailed = false;
  $("hermesStatus").innerHTML = `<a href="${url}" target="_blank" rel="noreferrer">${base}</a>`;
  if ($("hermesAim")) {
    const count = Number(data.session_count || 0);
    const title = data.session_title || "";
    const bits = [aimed || "machine Hermes home"];
    if (count) bits.push(`${count.toLocaleString()} sessions`);
    if (title) bits.push(`Telegram ${title}`);
    $("hermesAim").textContent = bits.join(" · ");
  }
  syncHermesHint();
  reloadEngineFrame("hermesFrame", url, `${aimed}|${sid}`);
  lastHermesHome = aimed;
  hermesStarted = true;
}

function attachEngineFrames(data) {
  const ocUrl = data.opencode_web && data.opencode_web.url;
  if (ocUrl) {
    $("ocStatus").innerHTML = `Running at <a href="${ocUrl}" target="_blank" rel="noreferrer">${ocUrl}</a>`;
    if ($("ocFrame").src !== ocUrl) $("ocFrame").src = ocUrl;
    ocStarted = true;
  }
  const hermesUrl = data.hermes_dash && data.hermes_dash.url;
  if (hermesUrl) {
    hermesFailed = false;
    $("hermesStatus").innerHTML = `<a href="${hermesUrl}" target="_blank" rel="noreferrer">${hermesUrl}</a>`;
    syncHermesHint();
    if ($("hermesFrame").src !== hermesUrl) $("hermesFrame").src = hermesUrl;
    hermesStarted = true;
  }
}

async function waitForUnlock() {
  const gate = $("unlockGate");
  if (!gate) {
    const res = await fetch("/api/index");
    return res.json();
  }
  gate.classList.remove("hidden");
  if ($("unlockPin")) $("unlockPin").focus();
  return new Promise((resolve) => {
    const submit = async () => {
      const res = await fetch("/api/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: ($("unlockPin") && $("unlockPin").value) || "" })
      });
      const data = await res.json();
      if (res.ok && !data.needs_unlock) {
        gate.classList.add("hidden");
        resolve(data);
        return;
      }
      if ($("unlockError")) $("unlockError").textContent = data.error || "wrong PIN";
    };
    if ($("unlockBtn")) $("unlockBtn").addEventListener("click", submit);
    if ($("unlockPin")) {
      $("unlockPin").addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          submit();
        }
      });
    }
  });
}

async function loadOrgTree() {
  try {
    const res = await fetch("/api/org");
    if (!res.ok) return;
    const data = await res.json();
    if (data && Array.isArray(data.projects)) await applyOrg(data);
  } catch (_err) {
    /* paint from /api/index if this fails */
  }
}

async function boot() {
  await loadOrgTree();
  let data = await (await fetch("/api/index")).json();
  if (data.needs_unlock) data = await waitForUnlock();
  applyConfig(data);
  showWizard(data);
  await loadThread();
  pollActivity();
  loadSkillHints();
  window.setTimeout(refreshCatalog, 400);
  sizeComposer();
  if (location.hash) applyHash();
  window.addEventListener("hashchange", applyHash);
}

function setWizardStep(name) {
  const labels = {
    engines: "Engines",
    folder: "Folder",
    key: "Key"
  };
  document.querySelectorAll(".wizard-step").forEach((el) => {
    el.classList.toggle("hidden", el.dataset.step !== name);
  });
  if ($("wizardStepLabel")) $("wizardStepLabel").textContent = labels[name] || "";
}

function showWizard(data) {
  const overlay = $("firstRun");
  if (!overlay) return;
  const needsFolder = !data.first_run_done && !data.hosted;
  const needsKey = !data.has_key;
  if (!needsFolder && !needsKey) {
    overlay.classList.add("hidden");
    return;
  }
  overlay.classList.remove("hidden");
  if (needsFolder) setWizardStep("engines");
  else setWizardStep("key");
}

async function pollActivity() {
  try {
    const res = await fetch("/api/activity");
    const data = await res.json();
    cfg.has_key = data.has_key;
    renderActivity(data);
    await loadSpend();
    if (projectId && !workerId) {
      (data.cron_jobs || []).forEach((job) => {
        if (job.project_id === projectId && job.id && !seenCron.has(job.id)) renderJob(job);
      });
    }
    if (!liveRunId) {
      const fresh = (data.jobs || []).some((job) => {
        if (!job || !job.id || seenJobIds.has(job.id)) return false;
        return String(job.project_id || "") === String(projectId || "");
      });
      if (fresh) await refreshThreadTail();
    }
  } catch (_err) {
    /* board still usable */
  }
  window.setTimeout(pollActivity, liveRunId ? 4000 : 8000);
}

document.querySelectorAll(".stage-btn").forEach((btn) => {
  btn.addEventListener("click", () => setStage(btn.dataset.stage));
});
document.querySelectorAll(".route-btn").forEach((btn) => {
  btn.addEventListener("click", () => setRoute(btn.dataset.preset));
});
document.querySelectorAll(".lane").forEach((btn) => {
  btn.addEventListener("click", () => focusLane(btn.dataset.lane));
});
document.querySelectorAll(".drawer-tab").forEach((btn) => {
  btn.addEventListener("click", () => setSettingsPanel(btn.dataset.panel));
});
if ($("modelSearch")) {
  $("modelSearch").addEventListener("input", () => {
    modelQuery = $("modelSearch").value;
    renderSeats(cfg.catalog, cfg.seats);
  });
}
if ($("openSpend")) {
  $("openSpend").addEventListener("click", () => setSettings(true, "usage"));
}
$("openSettings").addEventListener("click", (event) => {
  event.stopPropagation();
  setSettings(true, "you");
});
$("closeSettings").addEventListener("click", () => setSettings(false));
$("settingsScrim").addEventListener("click", () => setSettings(false));
$("gotoOpenCode").addEventListener("click", () => openWorkspace("opencode"));
$("gotoHermes").addEventListener("click", () => openWorkspace("hermes"));
if ($("aboutOpenCode")) {
  $("aboutOpenCode").addEventListener("click", () => openWorkspace("opencode"));
}
$("retryHermes").addEventListener("click", () => {
  hermesStarted = false;
  startHermes();
});
$("providerList").addEventListener("click", (event) => {
  const btn = event.target.closest("[data-open-stage]");
  if (!btn) return;
  openWorkspace(btn.dataset.openStage);
});
$("defaultProvider").addEventListener("change", async () => {
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_provider: $("defaultProvider").value })
  });
  const data = await res.json();
  $("providerStatus").textContent = res.ok ? "default provider saved" : (data.error || "save failed");
  if (res.ok) {
    applyConfig(data);
    refreshProviders();
  }
});
document.addEventListener("click", (event) => {
  if (menuJustOpened || event.target.closest("#nodeMenu, #msgMenu")) return;
  hideNodeMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!$("nodeMenu").classList.contains("hidden") || ($("msgMenu") && !$("msgMenu").classList.contains("hidden"))) {
    hideNodeMenu();
    return;
  }
  if (!$("settings").classList.contains("hidden")) setSettings(false);
});

$("saveWorkspace").addEventListener("click", async () => {
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      work_dir: $("settingsFolder").value.trim()
    })
  });
  const data = await res.json();
  $("workspaceStatus").textContent = res.ok ? "folder saved" : (data.error || "save failed");
  if (res.ok) applyConfig(data);
});

if ($("saveYou")) {
  $("saveYou").addEventListener("click", async () => {
    const pin = $("operatorPin").value;
    const confirmPin = $("operatorPinConfirm").value;
    if (pin && pin !== confirmPin) {
      $("youStatus").textContent = "PIN confirmation does not match";
      return;
    }
    const body = { operator_name: $("operatorName").value.trim() };
    if (pin) body.pin = pin;
    const license = $("licenseKey").value.trim();
    if (license) body.license_key = license;
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    $("youStatus").textContent = res.ok ? "profile saved" : (data.error || "save failed");
    if (res.ok) {
      $("operatorPin").value = "";
      $("operatorPinConfirm").value = "";
      $("licenseKey").value = "";
      applyConfig(data);
    }
  });
}

if ($("clearPin")) {
  $("clearPin").addEventListener("click", async () => {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear_pin: true })
    });
    const data = await res.json();
    $("youStatus").textContent = res.ok ? "PIN cleared" : (data.error || "save failed");
    if (res.ok) applyConfig(data);
  });
}

if ($("clearLicense")) {
  $("clearLicense").addEventListener("click", async () => {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear_license: true })
    });
    const data = await res.json();
    $("youStatus").textContent = res.ok ? "license cleared" : (data.error || "save failed");
    if (res.ok) applyConfig(data);
  });
}

if ($("saveUsage")) {
  $("saveUsage").addEventListener("click", async () => {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        spend_cap_usd: Number($("spendCap").value),
        spend_cap_period: $("spendPeriod").value,
        spend_policy: {
          bind: $("spendBind") ? $("spendBind").value : "payg",
          mode: $("spendMode") ? $("spendMode").value : "hard",
          allow_zen_fallback: $("spendFallback") ? $("spendFallback").checked : true
        }
      })
    });
    const data = await res.json();
    $("usageStatus").textContent = res.ok ? "policy saved" : (data.error || "save failed");
    if (res.ok) applyConfig(data);
  });
}

if ($("saveGit")) {
  $("saveGit").addEventListener("click", async () => {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if ($("gitStatusNote")) $("gitStatusNote").textContent = res.ok ? "git access saved" : (data.error || "save failed");
    if (res.ok) applyConfig(data);
  });
}

$("saveModels").addEventListener("click", async () => {
  const seats = {};
  document.querySelectorAll("select[data-seat]").forEach((input) => {
    seats[input.dataset.seat] = { model: input.value };
  });
  const account = $("profileAccount");
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      default_provider: ($("defaultProvider") && $("defaultProvider").value) || "opencode",
      profile_account_id: account ? account.value : "",
      hermes_skills: $("hermesSkills") ? $("hermesSkills").value.trim() : "",
      seats
    })
  });
  const data = await res.json();
  $("modelStatus").textContent = res.ok ? "models saved" : (data.error || "save failed");
  if (res.ok) applyConfig(data);
});

let connectorsCatalog = { skills: [], mcp: [] };

async function loadConnectorsCatalog() {
  try {
    const res = await fetch("/api/connectors/catalog");
    const data = await res.json();
    connectorsCatalog = {
      skills: data.skills || [],
      mcp: data.mcp || []
    };
    paintConnectorsPanel();
  } catch (err) {
    console.error("Failed to load connectors catalog:", err);
  }
}

function paintConnectorsPanel() {
  const skillMatrix = $("skillMatrix");
  const mcpMatrix = $("mcpMatrix");
  if (!skillMatrix || !mcpMatrix) return;

  const globalConnectors = cfg.connectors || { skills: {}, mcp: {} };
  const seats = ["think", "research", "ops"];

  // Hermes Skills Matrix
  if (connectorsCatalog.skills.length === 0) {
    skillMatrix.innerHTML = `<p class="muted">No Hermes skills found. Run <code>hermes skills list</code> to see available skills.</p>`;
  } else {
    let skillHtml = `<div class="connector-row connector-row-header">
      <div class="connector-name">Skill</div>
      <div class="connector-cell">Think</div>
      <div class="connector-cell">Research</div>
      <div class="connector-cell">Ops</div>
      <div class="connector-cell">Chat</div>
    </div>`;
    
    connectorsCatalog.skills.forEach((skill) => {
      const skillConfig = globalConnectors.skills[skill] || {};
      skillHtml += `<div class="connector-row">
        <div class="connector-name">${escapeHtml(skill)}</div>`;
      
      seats.forEach((seat) => {
        const checked = skillConfig[seat] === true ? " checked" : "";
        skillHtml += `<div class="connector-cell">
          <label>
            <input type="checkbox" data-skill="${escapeHtml(skill)}" data-seat="${seat}"${checked} />
          </label>
        </div>`;
      });
      
      skillHtml += `<div class="connector-cell connector-cell-disabled">
        <label title="Chat never has tools">
          <input type="checkbox" disabled />
        </label>
      </div>`;
      skillHtml += `</div>`;
    });
    skillMatrix.innerHTML = skillHtml;
  }

  // MCP Matrix
  if (connectorsCatalog.mcp.length === 0) {
    mcpMatrix.innerHTML = `<p class="muted">No MCP servers found. Run <code>hermes mcp catalog</code> to see available servers.</p>`;
  } else {
    let mcpHtml = `<div class="connector-row connector-row-header">
      <div class="connector-name">MCP Server</div>
      <div class="connector-cell">Think</div>
      <div class="connector-cell">Research</div>
      <div class="connector-cell">Ops</div>
      <div class="connector-cell">Code</div>
    </div>`;
    
    connectorsCatalog.mcp.forEach((item) => {
      const mcpId = item.id || "";
      const mcpConfig = globalConnectors.mcp[mcpId] || {};
      mcpHtml += `<div class="connector-row">
        <div class="connector-name" title="${escapeHtml(item.label || mcpId)}">${escapeHtml(mcpId)}</div>`;
      
      ["think", "research", "ops", "code"].forEach((seat) => {
        const checked = mcpConfig[seat] === true ? " checked" : "";
        mcpHtml += `<div class="connector-cell">
          <label>
            <input type="checkbox" data-mcp="${escapeHtml(mcpId)}" data-seat="${seat}"${checked} />
          </label>
        </div>`;
      });
      
      mcpHtml += `</div>`;
    });
    mcpMatrix.innerHTML = mcpHtml;
  }
}

$("saveConnectors").addEventListener("click", async () => {
  const connectors = { skills: {}, mcp: {} };
  
  // Collect skill settings
  document.querySelectorAll("#skillMatrix input[data-skill][data-seat]").forEach((input) => {
    const skill = input.dataset.skill;
    const seat = input.dataset.seat;
    if (!connectors.skills[skill]) connectors.skills[skill] = {};
    connectors.skills[skill][seat] = input.checked;
  });
  
  // Collect MCP settings
  document.querySelectorAll("#mcpMatrix input[data-mcp][data-seat]").forEach((input) => {
    const mcp = input.dataset.mcp;
    const seat = input.dataset.seat;
    if (!connectors.mcp[mcp]) connectors.mcp[mcp] = {};
    connectors.mcp[mcp][seat] = input.checked;
  });
  
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ connectors })
  });
  const data = await res.json();
  if ($("connectorStatus")) {
    $("connectorStatus").textContent = res.ok ? "connectors saved" : (data.error || "save failed");
  }
  if (res.ok) applyConfig(data);
});

$("refreshConnectors").addEventListener("click", () => {
  loadConnectorsCatalog();
  if ($("connectorStatus")) {
    $("connectorStatus").textContent = "refreshing catalog...";
  }
});

$("saveWork").addEventListener("click", async () => {
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ work_dir: $("workDir").value.trim() })
  });
  const data = await res.json();
  if (!res.ok) {
    $("firstRunError").textContent = data.error || "folder not saved";
    return;
  }
  applyConfig(data);
  $("firstRunError").textContent = "";
  if (!data.has_key) setWizardStep("key");
  else $("firstRun").classList.add("hidden");
});

$("wizardEnginesNext").addEventListener("click", () => {
  if (cfg.hosted || cfg.first_run_done) {
    if (!cfg.has_key) setWizardStep("key");
    else $("firstRun").classList.add("hidden");
    return;
  }
  setWizardStep("folder");
});
if ($("keyProvider")) {
  $("keyProvider").addEventListener("change", () => syncProviderHint("keyProvider", "keyProviderHint"));
}
if ($("wizardProvider")) {
  $("wizardProvider").addEventListener("change", () => syncProviderHint("wizardProvider", "wizardKeyHint"));
}
$("saveWizardKey").addEventListener("click", async () => {
  const res = await fetch("/api/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: $("wizardProvider").value,
      label: "first run",
      key: $("wizardKey").value.trim()
    })
  });
  const data = await res.json();
  if (!res.ok) {
    $("firstRunError").textContent = data.error || "key not saved";
    return;
  }
  $("wizardKey").value = "";
  fillKeys(data);
  cfg.has_key = true;
  lockComposer(true);
  $("firstRun").classList.add("hidden");
  fetch("/api/index").then((r) => r.json()).then(applyConfig);
});
$("skipWizardKey").addEventListener("click", () => {
  $("firstRun").classList.add("hidden");
  lockComposer(false);
});
$("saveKey").addEventListener("click", async () => {
  const res = await fetch("/api/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: $("keyProvider").value,
      label: $("keyLabel").value.trim(),
      key: $("keyValue").value.trim()
    })
  });
  const data = await res.json();
  $("keyStatus").textContent = res.ok ? "saved" : (data.error || "save failed");
  if (res.ok) {
    $("keyValue").value = "";
    fillKeys(data);
    lockComposer(true);
    cfg.has_key = true;
    fetch("/api/index").then((r) => r.json()).then(applyConfig);
  }
});
if ($("saveLogin")) {
  $("saveLogin").addEventListener("click", async () => {
    const res = await fetch("/api/logins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: $("loginLabel").value.trim(),
        site: $("loginSite").value.trim(),
        username: $("loginUser").value.trim(),
        password: $("loginPass").value,
        project_id: $("loginCeo").value || null,
        auto: Boolean($("loginAuto") && $("loginAuto").checked)
      })
    });
    const data = await res.json();
    if ($("loginStatus")) $("loginStatus").textContent = res.ok ? "saved" : (data.error || "save failed");
    if (res.ok) {
      $("loginPass").value = "";
      fillKeys(data);
    }
  });
}
if ($("loginList")) {
  $("loginList").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-del-login]");
    if (!btn) return;
    const res = await fetch(`/api/logins/${btn.dataset.delLogin}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) fillKeys(data);
    else if ($("loginStatus")) $("loginStatus").textContent = data.error || "remove failed";
  });
}
$("keyList").addEventListener("click", async (event) => {
  const move = event.target.closest("[data-fallback-up], [data-fallback-down]");
  if (move) {
    const order = ((cfg.keyring && cfg.keyring.fallback) || (cfg.keyring && cfg.keyring.accounts || []).map((row) => row.id)).slice();
    const id = move.dataset.fallbackUp || move.dataset.fallbackDown;
    const at = order.indexOf(id);
    if (at < 0) return;
    const swap = move.dataset.fallbackUp ? at - 1 : at + 1;
    if (swap < 0 || swap >= order.length) return;
    const tmp = order[at];
    order[at] = order[swap];
    order[swap] = tmp;
    const res = await fetch("/api/keys/fallback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order })
    });
    const data = await res.json();
    if (res.ok) {
      cfg.keyring = data;
      fillKeys(data);
    }
    return;
  }
  const rename = event.target.closest("[data-save-label]");
  if (rename) {
    const id = rename.dataset.saveLabel;
    const input = $("keyList").querySelector(`[data-key-label="${id}"]`);
    const res = await fetch(`/api/keys/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: input ? input.value.trim() : "" })
    });
    const data = await res.json();
    $("keyStatus").textContent = res.ok ? "renamed" : (data.error || "rename failed");
    if (res.ok) {
      cfg.keyring = data;
      fillKeys(data);
    }
    return;
  }
  const btn = event.target.closest("[data-del-key]");
  if (!btn) return;
  const res = await fetch(`/api/keys/${btn.dataset.delKey}`, { method: "DELETE" });
  const data = await res.json();
  if (res.ok) fillKeys(data);
});
if ($("peekHermesZip")) {
  $("peekHermesZip").addEventListener("click", async () => {
    const res = await fetch("/api/hermes/import/peek", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: $("hermesZip").value.trim() })
    });
    const data = await res.json();
    $("importZipStatus").textContent = res.ok ? "zip looks like a Hermes backup" : (data.error || "peek failed");
    const preview = $("hermesZipPreview");
    if (!res.ok) {
      preview.classList.add("hidden");
      preview.innerHTML = "";
      return;
    }
    if ($("hermesImportName") && !$("hermesImportName").value.trim()) {
      $("hermesImportName").value = data.title || "";
    }
    preview.classList.remove("hidden");
    preview.innerHTML = `
      <h4>${escapeHtml(data.title || "Hermes backup")}</h4>
      <p class="hint">${escapeHtml((data.files || []).join(" · ") || "no SOUL/MEMORY files")}</p>
      <p class="hint">skills: ${Number(data.skill_count) || 0}${data.session_hint ? " · sessions present" : ""}</p>
      <pre class="stats">${escapeHtml(data.soul || "")}</pre>
    `;
  });
}
if ($("importHermesZip")) {
  $("importHermesZip").addEventListener("click", async () => {
    $("importZipStatus").textContent = "importing…";
    const res = await fetch("/api/hermes/import/backup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: $("hermesZip").value.trim(),
        name: $("hermesImportName").value.trim(),
        folder: $("hermesImportFolder").value.trim()
      })
    });
    const data = await res.json();
    const imported = data.hermes_import || {};
    $("importZipStatus").textContent = res.ok
      ? (imported.ok ? "CEO imported" : `CEO added. hermes import: ${imported.text || "INDEX only"}`)
      : (data.error || "import failed");
    if (res.ok && data.org) {
      org = data.org;
      renderOrg(org);
      if (data.project_id) setOrgNode(data.project_id, "");
    }
  });
}
if ($("saveHermesInstance")) {
  $("saveHermesInstance").addEventListener("click", async () => {
    const res = await fetch("/api/hermes/instances", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: $("hermesInstanceUrl").value.trim(),
        key: $("hermesInstanceKey").value.trim(),
        label: $("hermesInstanceLabel").value.trim()
      })
    });
    const data = await res.json();
    $("importInstanceStatus").textContent = res.ok ? "instance saved" : (data.error || "save failed");
    if (res.ok) {
      $("hermesInstanceKey").value = "";
      cfg.hermes_instances = data.instances || [];
      fillImport(cfg.hermes_instances);
    }
  });
}
if ($("hermesInstanceList")) {
  $("hermesInstanceList").addEventListener("click", async (event) => {
    const del = event.target.closest("[data-del-instance]");
    if (del) {
      const res = await fetch(`/api/hermes/instances/${del.dataset.delInstance}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        cfg.hermes_instances = data.instances || [];
        fillImport(cfg.hermes_instances);
        $("hermesSessionList").innerHTML = "";
      }
      return;
    }
    const listBtn = event.target.closest("[data-list-sessions]");
    if (!listBtn) return;
    $("importInstanceStatus").textContent = "listing sessions…";
    const res = await fetch(`/api/hermes/instances/${listBtn.dataset.listSessions}/sessions`);
    const data = await res.json();
    $("importInstanceStatus").textContent = res.ok ? "" : (data.error || "list failed");
    const sessions = data.sessions || [];
    $("hermesSessionList").innerHTML = sessions.length ? sessions.map((row) => `
      <article class="provider">
        <div class="provider-top">
          <b>${escapeHtml(row.title)}</b>
        </div>
        <div class="actions">
          <button type="button" class="send" data-import-session="${escapeHtml(row.id)}" data-instance="${escapeHtml(listBtn.dataset.listSessions)}" data-title="${escapeHtml(row.title)}">Import CEO</button>
        </div>
      </article>
    `).join("") : "<p class=\"muted\">No sessions on that instance.</p>";
  });
}
if ($("hermesSessionList")) {
  $("hermesSessionList").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-import-session]");
    if (!btn) return;
    $("importInstanceStatus").textContent = "importing session…";
    const res = await fetch(`/api/hermes/instances/${btn.dataset.instance}/sessions/${encodeURIComponent(btn.dataset.importSession)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: btn.dataset.title || "",
        folder: $("hermesImportFolder").value.trim()
      })
    });
    const data = await res.json();
    $("importInstanceStatus").textContent = res.ok ? "CEO imported from session" : (data.error || "import failed");
    if (res.ok && data.org) {
      org = data.org;
      renderOrg(org);
      if (data.project_id) setOrgNode(data.project_id, "");
    }
  });
}
if (stream) {
  stream.addEventListener("contextmenu", (event) => {
    const article = event.target.closest("article.bubble, article.card");
    if (!article || article.classList.contains("live")) return;
    if (event.target.closest("a, button, input, textarea, select")) return;
    event.preventDefault();
    showMsgMenu(event.clientX, event.clientY, article);
  });
}
let seatAutocompleteActive = false;
let seatAutocompleteIndex = -1;
let seatAutocompleteStart = -1;
let seatAutocompleteQuery = "";

function showSeatAutocomplete(query, start) {
  const dropdown = $("seatAutocomplete");
  if (!dropdown) return;
  const seats = allSeats().filter(seat => 
    seat.label.toLowerCase().includes(query.toLowerCase()) ||
    seat.id.toLowerCase().includes(query.toLowerCase())
  );
  if (!seats.length) {
    hideSeatAutocomplete();
    return;
  }
  seatAutocompleteActive = true;
  seatAutocompleteStart = start;
  seatAutocompleteQuery = query;
  seatAutocompleteIndex = 0;
  dropdown.innerHTML = seats.map((seat, idx) => `
    <div class="seat-option${idx === 0 ? " selected" : ""}" data-seat-id="${escapeHtml(seat.id)}" data-seat-label="${escapeHtml(seat.label)}">
      <div class="seat-option-label">${escapeHtml(seat.label)}</div>
      <div class="seat-option-desc">${escapeHtml(seat.description)}</div>
    </div>
  `).join("");
  dropdown.classList.remove("hidden");
}

function hideSeatAutocomplete() {
  const dropdown = $("seatAutocomplete");
  if (!dropdown) return;
  dropdown.classList.add("hidden");
  dropdown.innerHTML = "";
  seatAutocompleteActive = false;
  seatAutocompleteIndex = -1;
  seatAutocompleteStart = -1;
  seatAutocompleteQuery = "";
}

function selectSeat(seatId, seatLabel) {
  const msg = $("msg");
  if (!msg || seatAutocompleteStart === -1) return;
  const value = msg.value;
  const before = value.slice(0, seatAutocompleteStart);
  const after = value.slice(msg.selectionStart);
  // Insert clean token (@builder, @think, etc.) not pretty label
  const token = seatId.startsWith("ceo:") ? seatId.split(":")[1] : seatId;
  msg.value = before + "@" + token + " " + after;
  msg.selectionStart = msg.selectionEnd = before.length + token.length + 2;
  hideSeatAutocomplete();
  const preset = seatId.startsWith("ceo:") ? "cos" : seatId;
  if (preset !== "cos" && PRESET_ENGINE[preset]) setRoute(preset);
  msg.focus();
  sizeComposer();
}

function moveSeatSelection(direction) {
  const dropdown = $("seatAutocomplete");
  if (!dropdown || !seatAutocompleteActive) return;
  const options = dropdown.querySelectorAll(".seat-option");
  if (!options.length) return;
  options[seatAutocompleteIndex]?.classList.remove("selected");
  seatAutocompleteIndex = (seatAutocompleteIndex + direction + options.length) % options.length;
  options[seatAutocompleteIndex]?.classList.add("selected");
  options[seatAutocompleteIndex]?.scrollIntoView({ block: "nearest" });
}

function acceptSeatSelection() {
  const dropdown = $("seatAutocomplete");
  if (!dropdown || !seatAutocompleteActive) return false;
  const options = dropdown.querySelectorAll(".seat-option");
  const selected = options[seatAutocompleteIndex];
  if (selected) {
    selectSeat(selected.dataset.seatId, selected.dataset.seatLabel);
    return true;
  }
  return false;
}

if ($("seatAutocomplete")) {
  $("seatAutocomplete").addEventListener("click", (event) => {
    const option = event.target.closest(".seat-option");
    if (option) {
      selectSeat(option.dataset.seatId, option.dataset.seatLabel);
    }
  });
}

if ($("replyChipClear")) {
  $("replyChipClear").addEventListener("click", (event) => {
    event.preventDefault();
    clearReply();
  });
}
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = $("msg").value.trim();
  const hasAttach = pendingAttachments.length > 0;
  if (liveRunId) {
    if (message || hasAttach) {
      $("msg").value = "";
      sizeComposer();
      enqueueMessage(message);
      return;
    }
    await stopLive();
    return;
  }
  if (!message && !hasAttach) return;
  $("msg").value = "";
  sizeComposer();
  await sendMessage(message);
});
if ($("msg")) {
  $("msg").addEventListener("input", (event) => {
    sizeComposer();
    const msg = event.target;
    const value = msg.value;
    const pos = msg.selectionStart;
    const beforeCursor = value.slice(0, pos);
    const atMatch = beforeCursor.match(/@(\w*)$/);
    if (atMatch) {
      const query = atMatch[1];
      const start = pos - atMatch[0].length + 1;
      showSeatAutocomplete(query, start);
    } else {
      hideSeatAutocomplete();
    }
  });
  $("msg").addEventListener("keydown", (event) => {
    if (seatAutocompleteActive) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveSeatSelection(1);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        moveSeatSelection(-1);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        if (acceptSeatSelection()) {
          event.preventDefault();
          return;
        }
      }
      if (event.key === "Escape") {
        event.preventDefault();
        hideSeatAutocomplete();
        return;
      }
    }
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    const message = $("msg").value.trim();
    const hasAttach = pendingAttachments.length > 0;
    if ((!message && !hasAttach) || $("msg").disabled) return;
    $("msg").value = "";
    sizeComposer();
    if (liveRunId) {
      enqueueMessage(message);
      return;
    }
    sendMessage(message);
  });
  $("msg").addEventListener("blur", () => {
    setTimeout(() => hideSeatAutocomplete(), 200);
  });
}
if ($("sendBtn")) {
  $("sendBtn").addEventListener("click", async (event) => {
    if (!liveRunId) return;
    const message = $("msg") ? $("msg").value.trim() : "";
    if (message) return; // submit handler queues
    event.preventDefault();
    await stopLive();
  });
}
if ($("queueChipClear")) {
  $("queueChipClear").addEventListener("click", (event) => {
    event.preventDefault();
    messageQueues.set(aimKey(), []);
    paintQueueChip();
    lockComposer(Boolean(cfg.has_key));
  });
}
if ($("attachBtn")) {
  $("attachBtn").addEventListener("click", () => {
    const input = $("attachInput");
    if (input) input.click();
  });
}
if ($("attachInput")) {
  $("attachInput").addEventListener("change", (event) => {
    const files = Array.from(event.target.files || []);
    files.forEach((file) => addAttachment(file));
    event.target.value = "";
  });
}
if ($("form")) {
  const form = $("form");
  form.addEventListener("dragover", (event) => {
    event.preventDefault();
    form.classList.add("drag-over");
  });
  form.addEventListener("dragleave", (event) => {
    if (event.target === form) {
      form.classList.remove("drag-over");
    }
  });
  form.addEventListener("drop", (event) => {
    event.preventDefault();
    form.classList.remove("drag-over");
    const files = Array.from(event.dataTransfer.files || []);
    files.forEach((file) => addAttachment(file));
  });
}
if ($("msg")) {
  $("msg").addEventListener("paste", (event) => {
    const items = Array.from(event.clipboardData.items || []);
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        event.preventDefault();
        const file = item.getAsFile();
        if (file) addAttachment(file);
      }
    }
  });
}

async function sendMessage(message, opts) {
  const attachmentsToSend = [...pendingAttachments];
  if (!message && !attachmentsToSend.length) return;
  if (liveRunId) {
    enqueueMessage(message, opts);
    return;
  }
  const parsed = (!opts || !opts.allowSecret) ? parseComposerLogin(message) : null;
  if (parsed) {
    fillLoginOffer(parsed);
    return;
  }
  // Strip leading @seat tokens (route already set, don't send junk to Hermes/OpenCode)
  const cleanMessage = message.replace(/^@(builder|think|research|ops|cos|[\w-]+)\s+/i, "");
  const aim = aimKey();
  const sendProjectId = projectId || "";
  const sendWorkerId = workerId || "";
  const folder = $("folder").value.trim() || null;
  const empty = $("streamEmpty");
  if (empty) empty.remove();
  const pendingQuote = (opts && opts.quote != null) ? opts.quote : replyQuote;
  clearReply();
  const displayMessage = message || "(attachment)";
  const userEl = bubble("user", displayMessage);
  if (pendingQuote) attachQuotePreview(userEl, pendingQuote);
  if (attachmentsToSend.length) {
    const attDiv = document.createElement("div");
    attDiv.className = "bubble-attachments";
    attachmentsToSend.forEach((att) => {
      const isImage = att.file.type.startsWith("image/");
      if (isImage) {
        const imgWrap = document.createElement("div");
        imgWrap.className = "bubble-attachment";
        const img = document.createElement("img");
        img.src = URL.createObjectURL(att.file);
        img.alt = att.file.name;
        imgWrap.appendChild(img);
        attDiv.appendChild(imgWrap);
      } else {
        const fileWrap = document.createElement("div");
        fileWrap.className = "bubble-attachment";
        const fileDiv = document.createElement("div");
        fileDiv.className = "bubble-attachment-file";
        fileDiv.innerHTML = `<span class="bubble-attachment-icon">📄</span><span class="bubble-attachment-name">${escapeHtml(att.file.name)}</span>`;
        fileWrap.appendChild(fileDiv);
        attDiv.appendChild(fileWrap);
      }
    });
    userEl.appendChild(attDiv);
  }
  clearAttachments();
  let liveBubble = thinkingBubble();
  liveBubble.dataset.liveKey = aim;
  const ac = new AbortController();
  const lane = (opts && opts.preset) || preset || "cos";
  const laneTag = (lane && lane !== "cos") ? lane : "";
  userEl.dataset.lane = laneTag || "cos";
  if (laneTag) liveBubble.dataset.lane = laneTag;
  setLive("pending", {
    key: aim,
    projectId: sendProjectId,
    workerId: sendWorkerId,
    abort: ac,
    lane: laneTag
  });
  // Watchdog: abort if no progress for 90s (tracks last activity)
  let lastActivity = Date.now();
  let progressWatchdog = null;
  function resetProgressWatchdog() {
    lastActivity = Date.now();
    if (progressWatchdog) clearTimeout(progressWatchdog);
    progressWatchdog = setTimeout(() => {
      if (Date.now() - lastActivity > 90000 && stillHere()) {
        try { ac.abort(); } catch (_err) { /* already aborted */ }
      }
    }, 90000);
  }
  resetProgressWatchdog();
  const maxWatchdog = setTimeout(() => {
    try { ac.abort(); } catch (_err) { /* already aborted */ }
  }, 600000); // Hard 10min max
  let job = null;
  let liveText = "";
  const stillHere = () => aimKey() === aim;

  function activeBubble() {
    return liveBubbleFor(aim) || (stillHere() && liveBubble && liveBubble.isConnected ? liveBubble : null);
  }

  try {
    let body, headers;
    if (attachmentsToSend.length) {
      const formData = new FormData();
      formData.append("message", cleanMessage);
      if (folder) formData.append("folder", folder);
      formData.append("preset", lane);
      if (sendProjectId) formData.append("project_id", sendProjectId);
      if (sendWorkerId) formData.append("worker_id", sendWorkerId);
      if (pendingQuote) formData.append("quote", pendingQuote);
      attachmentsToSend.forEach((att) => {
        formData.append("attachments", att.file);
      });
      body = formData;
      headers = {};
    } else {
      body = JSON.stringify({
        message: cleanMessage,
        folder,
        preset: lane,
        project_id: sendProjectId || null,
        worker_id: sendWorkerId || null,
        quote: pendingQuote || "",
        chain_context: (opts && opts.chain_context) || null
      });
      headers = { "Content-Type": "application/json" };
    }
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers,
      body,
      signal: ac.signal
    });
    const ctype = (res.headers.get("content-type") || "").toLowerCase();
    if (!res.ok || !res.body || !ctype.includes("event-stream")) {
      const fallback = await res.text().catch(() => "");
      if (stillHere()) {
        const el = activeBubble();
        if (el) el.remove();
        renderJob({
          id: "err",
          text: fallback.slice(0, 800) || `Chat stream failed (${res.status || 0}). Try again.`,
          keep_going: false,
          talk: true,
          engine: "board",
          preset: "cos"
        });
      }
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        let event = "message";
        let payload = "";
        part.split("\n").forEach((line) => {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) payload += line.slice(5).trim();
        });
        if (!payload) continue;
        let data = {};
        try { data = JSON.parse(payload); } catch (_err) { continue; }
        if (event === "start" && data.id) {
          setLive(data.id, {
            key: aim,
            projectId: sendProjectId,
            workerId: sendWorkerId,
            abort: ac,
            lane: laneTag
          });
        }
        if (event === "progress" && (data.text || data.lane)) {
          resetProgressWatchdog(); // Reset on any progress
          if (data.lane) {
            const cur = liveFor(aim);
            if (cur) cur.lane = data.lane;
            if (stillHere()) {
              liveLane = data.lane;
              paintLanes();
              const el = activeBubble();
              if (el) el.dataset.lane = data.lane;
              scrollChatBottom();
            }
          }
          if (data.text && stillHere()) {
            const el = activeBubble();
            const label = el && el.querySelector(".thinking-label");
            if (label) label.textContent = data.text;
            const hint = $("workHint");
            if (hint) {
              hint.textContent = data.text;
              hint.classList.remove("hidden");
            }
          }
        }
        if (event === "delta" && data.text) {
          liveText += data.text;
          if (liveText.length > 16000) liveText = liveText.slice(-10000);
          if (stillHere()) {
            const el = activeBubble();
            const textEl = el && el.querySelector(".bubble-text");
            const thinkEl = el && el.querySelector(".thinking");
            if (textEl) textEl.textContent = liveText;
            if (thinkEl) thinkEl.classList.add("hidden");
            stream.scrollTop = stream.scrollHeight;
          }
        }
        if (event === "done") job = data;
        if (event === "error" && stillHere()) {
          const el = activeBubble();
          const textEl = el && el.querySelector(".bubble-text");
          const thinkEl = el && el.querySelector(".thinking");
          if (textEl) textEl.textContent = data.error || "error";
          if (thinkEl) thinkEl.classList.add("hidden");
        }
      }
      if (job) break;
    }
    clearTimeout(maxWatchdog);
    if (progressWatchdog) clearTimeout(progressWatchdog);
    if (stillHere()) {
      const el = activeBubble();
      if (job) {
        settleLive(el, job);
        if (job.activity) renderActivity(job.activity);
        if (job.spend) renderSpend(job.spend);
        if (job.index) renderIndex(job.index);
        fetch("/api/org").then((r) => r.json()).then(applyOrg);
      } else if (liveText) {
        settleLive(el, { id: "live", text: liveText, keep_going: false, talk: true, engine: "board", preset: "cos" });
      } else if (el) {
        // Empty response - should not happen with reliability fixes, but handle gracefully
        const thinkEl = el.querySelector(".thinking");
        const textEl = el.querySelector(".bubble-text");
        if (thinkEl) thinkEl.classList.add("hidden");
        if (textEl) {
          textEl.textContent = "Chat didn't return a response. This shouldn't happen — check that Hermes is running and a Chat model is seated in Settings → Models.";
        }
        settleLive(el, {
          id: "empty",
          text: "Chat didn't return a response. Check Hermes / Chat model settings.",
          keep_going: false,
          talk: true,
          engine: "board",
          preset: "cos",
          blocker: "empty response"
        });
      }
    } else if (job && job.id) {
      seenJobIds.add(job.id);
    }
  } catch (err) {
    clearTimeout(maxWatchdog);
    if (progressWatchdog) clearTimeout(progressWatchdog);
    const stopped = err && (err.name === "AbortError" || /abort/i.test(String(err)));
    if (stillHere()) {
      const el = activeBubble();
      const textEl = el && el.querySelector(".bubble-text");
      const thinkEl = el && el.querySelector(".thinking");
      if (thinkEl) thinkEl.classList.add("hidden");
      if (stopped) {
        if (textEl) textEl.textContent = "Stopped.";
        settleLive(el, {
          id: "stopped",
          text: "Stopped.",
          keep_going: false,
          talk: true,
          engine: "board",
          preset: lane || "cos",
          stopped: true
        });
      } else {
        if (textEl) textEl.textContent = String(err);
        settleLive(el, {
          id: "err",
          text: String(err),
          keep_going: true,
          talk: true,
          engine: "board",
          preset: lane || "cos"
        });
      }
    }
  } finally {
    clearTimeout(watchdog);
    setLive("", { key: aim, projectId: sendProjectId, workerId: sendWorkerId });
    if (stillHere()) {
      if (!job) {
        try { await refreshThreadTail(); } catch (_load) { /* already painted */ }
      }
      await drainQueue();
    } else {
      renderOrg(org);
    }
  }
}

async function loadSkillHints() {
  const list = $("skillHints");
  if (!list) return;
  try {
    const res = await fetch("/api/skills");
    const data = await res.json();
    (data.skills || []).forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      list.appendChild(opt);
    });
  } catch (_err) {
    /* optional */
  }
}

async function loadMemory() {
  const query = $("memorySearch") ? $("memorySearch").value.trim() : "";
  try {
    const params = new URLSearchParams({ q: query });
    if (projectId) params.set("project_id", projectId);
    const res = await fetch(`/api/memory/search?${params}`);
    const data = await res.json();
    renderMemoryCards(data.index_fields || {});
    renderMemoryResults(data.results || [], query);
  } catch (_err) {
    if ($("memoryCards")) $("memoryCards").innerHTML = `<p class="muted">Failed to load memory</p>`;
  }
}

function renderMemoryCards(fields) {
  const el = $("memoryCards");
  if (!el) return;
  const entries = [
    ["Now", fields.now || "—"],
    ["Last", fields.last || "—"],
    ["Next", fields.next || "—"],
    ["Blocker", fields.blocker || "—"]
  ];
  el.innerHTML = entries.map(([label, value]) => {
    const isBlocked = label === "Blocker" && value !== "—";
    const className = isBlocked ? "memory-card blocked" : "memory-card";
    const fieldId = `memory${label}`;
    return `<div class="${className}">
      <label for="${fieldId}">${escapeHtml(label)}</label>
      <textarea id="${fieldId}" rows="2" data-label="${label}">${escapeHtml(value)}</textarea>
    </div>`;
  }).join("");
}

function renderMemoryResults(results, query) {
  const el = $("memoryResults");
  if (!el) return;
  if (!query) {
    el.innerHTML = "";
    return;
  }
  if (results.length === 0) {
    el.innerHTML = `<p class="muted">No results for "${escapeHtml(query)}"</p>`;
    return;
  }
  el.innerHTML = `<h4>Search results (${results.length})</h4>` + results.map((result) => {
    const sourceLabel = result.type === "index" ? "INDEX" : result.source;
    const jobId = result.job_id || "";
    const clickable = result.type === "job" && jobId ? "memory-result-clickable" : "";
    return `<div class="memory-result ${clickable}" data-job-id="${escapeHtml(jobId)}">
      <div class="memory-result-meta">${escapeHtml(sourceLabel)}</div>
      <div class="memory-result-snippet">${escapeHtml(result.snippet)}</div>
    </div>`;
  }).join("");
  
  // Add click handlers to job results
  el.querySelectorAll(".memory-result-clickable").forEach((card) => {
    card.addEventListener("click", () => {
      const jobId = card.dataset.jobId;
      if (!jobId) return;
      // Try to find the job in the stream and scroll to it
      const jobEl = document.querySelector(`[data-job-id="${jobId}"]`);
      if (jobEl) {
        setSettings(false);
        jobEl.scrollIntoView({ behavior: "smooth", block: "center" });
        jobEl.classList.add("highlight");
        setTimeout(() => jobEl.classList.remove("highlight"), 2000);
      } else {
        // Job not in current stream, open Usage panel to show jobs
        setSettings(true, "usage");
      }
    });
  });
}

async function fetchOpenHandoffs() {
  try {
    const res = await fetch("/api/handoffs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId || null })
    });
    if (!res.ok) return;
    const data = await res.json();
    renderMemoryHandoffs(data.handoffs || []);
  } catch (err) {
    console.error("Failed to fetch handoffs:", err);
  }
}

async function createHandoff() {
  const task = $("handoffTask").value.trim();
  const toSeat = $("handoffToSeat").value;
  if (!task || !toSeat) {
    showHint("Task and seat required");
    return;
  }
  try {
    const res = await fetch("/api/handoff/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task,
        to_seat: toSeat,
        from_seat: "cos",
        project_id: projectId || null,
        next_owner: toSeat
      })
    });
    const data = await res.json();
    if (res.ok) {
      showHint(`Handoff created: ${data.handoff_id}`);
      $("handoffTask").value = "";
      $("handoffToSeat").value = "";
      fetchOpenHandoffs();
    } else {
      showHint(data.message || "Create failed");
    }
  } catch (err) {
    showHint("Create failed");
  }
}

function renderMemoryHandoffs(handoffs) {
  const el = $("memoryHandoffs");
  if (!el) return;
  if (handoffs.length === 0) {
    el.innerHTML = `<p class="muted">No open handoffs</p>`;
    return;
  }
  el.innerHTML = handoffs.map((h) => {
    const statusClass = h.status === "blocked" ? "status-blocked" : 
                        h.status === "claimed" ? "status-claimed" : "status-open";
    const taskBrief = h.task.length > 100 ? h.task.slice(0, 100) + "..." : h.task;
    return `<div class="handoff-item" data-handoff-id="${escapeHtml(h.id)}">
      <div class="handoff-item-header">
        <span class="handoff-item-id">${escapeHtml(h.id)}</span>
        <span class="handoff-item-status ${statusClass}">${escapeHtml(h.status)}</span>
      </div>
      <div class="handoff-item-task">${escapeHtml(taskBrief)}</div>
      <div class="handoff-item-meta">
        <span>${escapeHtml(h.from_seat || "—")} → ${escapeHtml(h.to_seat || "—")}</span>
        <span>Next: ${escapeHtml(h.next_owner)}</span>
      </div>
      ${h.status === "open" ? `<button type="button" class="ghost-btn claim-handoff" data-handoff-id="${escapeHtml(h.id)}">Claim</button>` : ""}
    </div>`;
  }).join("");
  
  // Add claim button handlers
  el.querySelectorAll(".claim-handoff").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const handoffId = btn.dataset.handoffId;
      const claimant = projectId || "staff";
      try {
        const res = await fetch("/api/handoff/claim", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ handoff_id: handoffId, project_id: projectId || null, claimant })
        });
        if (res.ok) {
          showHint(`Handoff ${handoffId} claimed`);
          fetchOpenHandoffs();
        } else {
          const data = await res.json();
          showHint(data.message || "Claim failed");
        }
      } catch (err) {
        showHint("Claim failed");
      }
    });
  });
}

if ($("memorySearch")) {
  let memorySearchTimeout = null;
  $("memorySearch").addEventListener("input", () => {
    if (memorySearchTimeout) clearTimeout(memorySearchTimeout);
    memorySearchTimeout = setTimeout(() => loadMemory(), 300);
  });
}

if ($("saveMemory")) {
  $("saveMemory").addEventListener("click", async () => {
    const labels = ["Now", "Last", "Next", "Blocker"];
    const updates = [];
    for (const label of labels) {
      const field = $(`memory${label}`);
      if (field) {
        const value = field.value.trim();
        updates.push({ label, value });
      }
    }
    const status = $("memoryStatus");
    try {
      for (const { label, value } of updates) {
        const res = await fetch("/api/memory/fields", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label, value, project_id: projectId || null })
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.error || "save failed");
        }
      }
      if (status) status.textContent = "INDEX saved";
      await loadMemory();
    } catch (err) {
      if (status) status.textContent = String(err);
    }
  });
  
  $("createHandoff").addEventListener("click", createHandoff);
  
  // Routines management
  let routineSteps = [];
  
  async function loadRoutines() {
    try {
      const res = await fetch(`/api/routines?project_id=${projectId || ""}`);
      if (!res.ok) throw new Error("load failed");
      const data = await res.json();
      renderRoutineList(data.routines || []);
    } catch (err) {
      console.error("load routines failed:", err);
    }
  }
  
  let lastRoutineResult = null;
  
  function renderRoutineList(routines) {
    const el = $("routineList");
    if (!el) return;
    if (routines.length === 0) {
      el.innerHTML = `<p class="muted">No routines yet</p>`;
      return;
    }
    el.innerHTML = routines.map((r) => {
      const stepCount = (r.steps || []).length;
      const enabledBadge = r.enabled ? `<span class="badge">enabled</span>` : `<span class="badge muted">disabled</span>`;
      return `<div class="routine-item" data-routine-id="${escapeHtml(r.id)}">
        <div class="routine-item-header">
          <strong>${escapeHtml(r.name)}</strong>
          ${enabledBadge}
        </div>
        <div class="routine-item-meta muted">
          ${escapeHtml(r.schedule)} · ${stepCount} step${stepCount !== 1 ? "s" : ""}
        </div>
        <button type="button" class="ghost-btn execute-routine" data-routine-id="${escapeHtml(r.id)}">Run Now</button>
        <button type="button" class="ghost-btn delete-routine" data-routine-id="${escapeHtml(r.id)}">Delete</button>
        <div class="routine-resume hidden" data-routine-id="${escapeHtml(r.id)}"></div>
      </div>`;
    }).join("");
    
    el.querySelectorAll(".execute-routine").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const routineId = btn.dataset.routineId;
        if (!routineId) return;
        btn.disabled = true;
        btn.textContent = "Running...";
        const resumeEl = el.querySelector(`.routine-resume[data-routine-id="${routineId}"]`);
        if (resumeEl) resumeEl.classList.add("hidden");
        try {
          const res = await fetch(`/api/routines/${routineId}/execute`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project_id: projectId || null }),
          });
          const data = await res.json();
          if (data.ok) {
            showHint(`Routine completed (${data.completed_steps}/${data.total_steps} steps)`);
            lastRoutineResult = null;
          } else {
            const failedStep = data.failed_at_step || "?";
            const blocker = data.blocker || data.error || "failed";
            showHint(`Routine failed at step ${failedStep}: ${blocker}`);
            lastRoutineResult = data;
            if (resumeEl && data.resume_step) {
              resumeEl.innerHTML = `<p class="muted">Failed at step ${data.resume_step}/${data.total_steps}: ${escapeHtml(blocker)}</p>
<button type="button" class="ghost-btn resume-routine" data-routine-id="${routineId}">Resume from Step ${data.resume_step}</button>`;
              resumeEl.classList.remove("hidden");
              const resumeBtn = resumeEl.querySelector(".resume-routine");
              if (resumeBtn) {
                resumeBtn.addEventListener("click", async () => {
                  resumeBtn.disabled = true;
                  resumeBtn.textContent = "Resuming...";
                  try {
                    const resumeRes = await fetch(`/api/routines/${routineId}/resume`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        project_id: projectId || null,
                        resume_step: data.resume_step,
                        resume_result: (data.results || []).slice(-1)[0]?.text || "",
                      }),
                    });
                    const resumeData = await resumeRes.json();
                    if (resumeData.ok) {
                      showHint(`Routine completed (${resumeData.completed_steps}/${resumeData.total_steps} steps)`);
                      resumeEl.classList.add("hidden");
                    } else {
                      showHint(`Resume failed: ${resumeData.error || resumeData.blocker}`);
                    }
                  } catch (err) {
                    showHint(String(err));
                  }
                  resumeBtn.disabled = false;
                  resumeBtn.textContent = `Resume from Step ${data.resume_step}`;
                });
              }
            }
          }
        } catch (err) {
          showHint(String(err));
        }
        btn.disabled = false;
        btn.textContent = "Run Now";
      });
    });
    
    el.querySelectorAll(".delete-routine").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const routineId = btn.dataset.routineId;
        if (!routineId || !confirm("Delete this routine?")) return;
        try {
          const res = await fetch(`/api/routines/${routineId}?project_id=${projectId || ""}`, {
            method: "DELETE",
          });
          if (res.ok) {
            await loadRoutines();
          } else {
            showHint("Delete failed");
          }
        } catch (err) {
          showHint(String(err));
        }
      });
    });
  }
  
  function renderRoutineSteps() {
    const el = $("routineSteps");
    if (!el) return;
    if (routineSteps.length === 0) {
      el.innerHTML = `<p class="muted">No steps yet. Add one below.</p>`;
      return;
    }
    el.innerHTML = routineSteps.map((s, idx) => {
      return `<div class="routine-step">
        <span>${idx + 1}. <strong>${escapeHtml(s.seat)}</strong> - ${escapeHtml(s.instruction)}</span>
        <button type="button" class="ghost-btn remove-step" data-idx="${idx}">Remove</button>
      </div>`;
    }).join("");
    
    el.querySelectorAll(".remove-step").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.idx, 10);
        routineSteps.splice(idx, 1);
        renderRoutineSteps();
      });
    });
  }
  
  $("addRoutineStep").addEventListener("click", () => {
    const seat = $("routineStepSeat").value.trim();
    const instr = $("routineStepInstr").value.trim();
    if (!seat || !instr) {
      showHint("Select seat and enter instruction");
      return;
    }
    routineSteps.push({ seat, instruction: instr });
    $("routineStepInstr").value = "";
    renderRoutineSteps();
  });
  
  $("saveRoutine").addEventListener("click", async () => {
    const name = $("routineName").value.trim();
    const schedule = $("routineSchedule").value.trim();
    const enabled = $("routineEnabled").checked;
    const status = $("routineStatus");
    
    if (!name || !schedule || routineSteps.length === 0) {
      if (status) status.textContent = "Name, schedule, and steps required";
      return;
    }
    
    try {
      const res = await fetch("/api/routines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          schedule,
          steps: routineSteps,
          project_id: projectId || null,
          enabled,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "save failed");
      }
      if (status) status.textContent = "Routine created";
      $("routineName").value = "";
      $("routineSchedule").value = "";
      routineSteps = [];
      renderRoutineSteps();
      await loadRoutines();
    } catch (err) {
      if (status) status.textContent = String(err);
    }
  });
  
  renderRoutineSteps();
  loadRoutines();
}

boot().catch((err) => {
  renderIndex(String(err));
  loadOrgTree();
});
