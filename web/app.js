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
let lastTool = "opencode";
let lastCeoId = "";
let gatewayRunning = true;
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
const threadCache = new Map();
const digestCache = new Map();
const failHandling = new Map();
const FAIL_HANDLING_MS = 12 * 60 * 1000;


function isCollaborator() {
  return cfg.actor === "collaborator";
}

function canAddCeo() {
  // Collaborators never Add CEO. Owner/operator can on laptop and hosted.
  if (isCollaborator()) return false;
  if (cfg && typeof cfg.can_add_ceo === "boolean") return cfg.can_add_ceo;
  return true;
}

function isLiveBoard() {
  if (cfg && cfg.hosted) return true;
  const host = String((location && location.hostname) || "").toLowerCase();
  return host.endsWith(".railway.app") || host.includes("railway.app");
}

function paintBoardMark() {
  const live = isLiveBoard();
  const mark = live ? "ottobot" : "ottobot · On it.";
  const el = $("boardMark");
  if (el) el.textContent = mark;
  const about = $("aboutMark");
  if (about) {
    about.textContent = live
      ? "ottobot. You run the instance. You hold the keys. Work moves as files — INDEX, inbox, bus/handoffs. Chat is not memory. Humans approve send, publish, pay, delete, and sign."
      : "ottobot · On it. You run the instance. You hold the keys. Work moves as files — INDEX, inbox, bus/handoffs. Chat is not memory. Humans approve send, publish, pay, delete, and sign.";
  }
  const credit = $("aboutCredit");
  if (credit && cfg && cfg.credit) credit.textContent = cfg.credit;
  const sub = document.querySelector(".sub");
  if (sub) sub.hidden = live;
  document.title = live ? "OttoBot" : "OttoBot · On it.";
}

function sharePerm(name) {
  if (!isCollaborator()) return true;
  const perms = (cfg.share && cfg.share.member && cfg.share.member.permissions) || {};
  return Boolean(perms[name]);
}

const SHARE_PERM_LABELS = [
  ["chat_read", "View chat"],
  ["chat_write", "Send chat"],
  ["jobs_view", "View jobs"],
  ["jobs_run", "Trigger jobs"],
  ["index_edit", "Edit INDEX / inbox"],
  ["approve_needs_you", "Approve needs-you cards"],
  ["engines_view", "View OpenCode / Hermes"],
  ["workers_manage", "Manage workers"],
  ["wiring_edit", "Change CEO wiring"]
];

function sharePermChecks(perms) {
  const row = perms || {};
  return SHARE_PERM_LABELS.map(([key, label]) => (
    `<label><input type="checkbox" data-share-perm="${key}"${row[key] ? " checked" : ""} /> ${label}</label>`
  )).join("");
}

function readSharePerms(root) {
  const out = {};
  (root || document).querySelectorAll("[data-share-perm]").forEach((el) => {
    out[el.dataset.sharePerm] = el.checked;
  });
  return out;
}

function actorLabel(actor) {
  if (!actor || typeof actor !== "object") return "";
  if (actor.kind === "collaborator") return actor.label || "Collaborator";
  return actor.label || "Owner";
}

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
  paintCeoLive(digestCache.get(projectId));
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
  about: "About",
  help: "Help"
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

const PACKET_LINE = /^(You are the |You are Chief of Staff|You report to Chief of Staff|The (human )?operator |You dispatch |Ask, and you dispatch|Your job is triage|Before doing substantial|Do not hire a Bot|Reply like a person|You do not edit files|No RESULT\.|Do not mention Now|Do not print session_id|If RECENT TELEGRAM|Never ask the operator to paste|If they ask to run all existing|OpenCode edits your|You own the outcome|Chat is not memory|Report a short RESULT|Name the engine that ran|Never print passwords|Park send, publish|If TOTP|If VAULT LOGINS|Write a short RESULT|STAFF \(files|INDEX:\s*$|BRAIN:\s*$|TASK:\s*$|OPEN HANDOFFS:|VAULT LOGINS|The operator is talking|The operator is in (OpenBot|OttoBot) Chat|The operator can also open|Specialist lanes execute|Code: OpenCode in |Hermes: |Bus: org\/projects\/|Telegram: |.+ CEO — reports to Chief of Staff)/i;

function statusOnly(text) {
  const rows = String(text || "").split("\n").map((line) => line.trim()).filter(Boolean);
  return rows.length > 0 && rows.every((line) => /^(Now|Last|Next|Blocker|Blocked):/i.test(line));
}

function isLabeledRow(row) {
  return /^(Now|Last|Next|Blocker|Blocked):/i.test(row) || /^[^:]{1,40}:\s+\S/.test(row);
}

function stripPacketEcho(text) {
  let cleaned = String(text || "");
  const response = cleaned.match(/^##\s*Response\s*$/im);
  if (response) {
    const body = cleaned.slice(cleaned.search(/^##\s*Response\s*$/im)).replace(/^##\s*Response\s*/i, "").trim();
    if (body && !/^\[SILENT\]/i.test(body)) cleaned = body;
  }
  const resultAt = cleaned.search(/^RESULT(?:\s*\([^)]*\))?\s*$/im);
  if (resultAt >= 0) {
    let body = cleaned.slice(resultAt).replace(/^RESULT(?:\s*\([^)]*\))?\s*/i, "").trim();
    const handoffAt = body.search(/^HANDOFF\b/im);
    if (handoffAt >= 0) body = body.slice(0, handoffAt).trim();
    if (body) cleaned = body;
  }
  if (statusOnly(cleaned)) return cleaned;
  const kept = [];
  let skipping = false;
  cleaned.split("\n").forEach((line) => {
    const stripped = line.trim();
    if (PACKET_LINE.test(stripped)) {
      skipping = /^(INDEX|BRAIN|TASK|STAFF|OPEN HANDOFFS|VAULT LOGINS):/i.test(stripped);
      return;
    }
    if (skipping) {
      if (!stripped) skipping = false;
      return;
    }
    if (!stripped && !kept.length) return;
    kept.push(line);
  });
  return kept.join("\n").trim();
}

function splitHandoff(text) {
  const raw = String(text || "");
  const at = raw.search(/^HANDOFF\b/im);
  if (at < 0) return { answer: raw.trim(), handoff: "" };
  return { answer: raw.slice(0, at).trim(), handoff: raw.slice(at).trim() };
}

function redactSecrets(text) {
  let cleaned = String(text || "");
  cleaned = cleaned.replace(/\bsk-[A-Za-z0-9_-]{6,}/g, "key");
  cleaned = cleaned.replace(/Token prefix:\s*\S+/gi, "");
  cleaned = cleaned.replace(/Auth method:\s*[^\n.]+/gi, "");
  cleaned = cleaned.replace(/\bANTHROPIC_[A-Z0-9_]+\b/g, "provider auth");
  cleaned = cleaned.replace(/x-api-key[^\n]*/gi, "");
  cleaned = cleaned.replace(/Bearer\s+[A-Za-z0-9._\-]+/g, "Bearer");
  cleaned = cleaned.replace(/🔐\s*/g, "");
  cleaned = cleaned.replace(/\bTroubleshooting:\s*[\s\S]*/gi, "");
  cleaned = cleaned.replace(/Check provider auth in\s+\S+/gi, "Check provider auth.");
  cleaned = cleaned.replace(/(?:~|\/|[A-Za-z]:[\\/])[^\s]*hermes-homes[^\s]*/gi, "Hermes home");
  cleaned = cleaned.replace(/\bWhat to do:\s*[^\n]*/gi, "");
  cleaned = cleaned.replace(/\bRan:\s*\d{4}-\d{2}-\d{2}T[^\s]*/gi, "");
  return cleaned.replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

function cleanBotText(text) {
  if (!text) return "";
  let cleaned = redactSecrets(text);

  cleaned = cleaned.replace(/!!!?\s*CONTRIBUTOR\s+TIER[\s\S]*?(?:standard\s+v\d+[\s\S]*?(?=\n\n|Now:|Last:|Next:)|$)/gi, "");
  cleaned = cleaned.replace(/This\s+is\s+Meta'?s?\s+contributor\s+tier[\s\S]*?(?:standard\s+v\d+[\s\S]*?(?=\n\n|Now:|Last:|Next:)|$)/gi, "");
  cleaned = cleaned.replace(/CONTRIBUTOR\s+TIER\s*—\s*TRAINS?\s+ON\s+YOUR\s+DATA/gi, "");
  cleaned = cleaned.replace(/prompts\s+and\s+completions\s+to\s+train\s+future\s+Meta\s+models\.?/gi, "");
  cleaned = cleaned.replace(/See\s+current\s+pricing\s+and\s+rate\s+limits\s+for\s+the\s+Meta\s+Model\s+API[\s\S]*?https?:\/\/[^\s]+/gi, "");
  cleaned = cleaned.replace(/https?:\/\/dev\.meta\.ai\/docs\/[^\s]*/gi, "");
  cleaned = cleaned.replace(/Do\s+NOT\s+use\s+it\s+for\s+confidential,\s+proprietary,\s+personal,\s+or\s+otherwise\s+sensitive\s+data\.?/gi, "");
  cleaned = cleaned.replace(/For\s+the\s+same\s+model\s+with\s+no\s+training\s+on\s+your\s+data[\s\S]*?(?=\n\n|Now:|Last:|Next:|$)/gi, "");
  cleaned = cleaned.replace(/It\s+lowers\s+the\s+barrier\s+to\s+entry[\s\S]*?acceptable\./gi, "");
  cleaned = cleaned.replace(/security\.allow_data_training_tiers_noninteractive/gi, "");
  cleaned = cleaned.replace(/[┌┐└┘│─]+\s*Scheduled\s+Jobs\s*[┌┐└┘│─]+/gi, "");
  cleaned = cleaned.replace(/Meta\s+Model\s+API\s+is\s+free[\s\S]*?https?:\/\/dev\.meta\.ai\/docs\/pricing-rate-limits?\/?/gi, "");
  cleaned = cleaned.replace(/This\s+model\s+is\s+in\s+Meta'?s?\s+contributor\s+tier[\s\S]*?(?=\n\n|Now:|Last:|Next:|$)/gi, "");
  cleaned = cleaned.replace(/^#\s*Cron Job:[\s\S]*?(?=^##\s*Response\s*$|\Z)/gim, "");
  cleaned = cleaned.replace(/[·•]\s*#\s*Cron Job:\s*[\w.-]+/gi, "");
  cleaned = cleaned.replace(/#\s*Cron Job:\s*[\w.-]+/gi, "");
  cleaned = cleaned.replace(/\bTHINK_OK\b/g, "");
  cleaned = cleaned.replace(/\bOPS_OK\b/g, "");
  cleaned = cleaned.replace(/\bSMOKE\d+_[A-Z0-9_]+\b/g, "");
  cleaned = cleaned.replace(/^Reply with exactly[^\n]*$/gmi, "");
  cleaned = cleaned.replace(/^Ignore (?:any )?banners[^\n]*$/gmi, "");

  const lines = cleaned.split("\n").map((line) => line.trim()).filter((line) => line.length > 0);
  if (lines.length === 1 && /^SMOKE\d+_[A-Z_]+$/i.test(lines[0])) {
    return "";
  }

  cleaned = stripPacketEcho(cleaned);
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

function humanFailReason(blob) {
  let text = String(blob || "").replace(/\s+/g, " ").trim();
  text = text.replace(/\b(?:THINK_OK|OPS_OK)\b/g, "").trim();
  const low = text.toLowerCase();
  if (/\b401\b|unauthorized|authentication failed|invalid.?api.?key|x-api-key/.test(low)) {
    return "API key rejected (401)";
  }
  if (/busy.?session|session.?busy|already running|locked by another/.test(low)) {
    return "Session busy";
  }
  if (/gateway shutdown|gateway stopped mid-run/.test(low)) {
    return "Hermes gateway stopped mid-run";
  }
  if (/script[- ]?not[- ]?found|no such file.*(script|\.sh|\.py|\.js)|enoent.*scripts\//.test(low)) {
    return "Script not found";
  }
  if (/insufficient balance|wallet.?empty|out of (?:quota|credit)|billing/.test(low)) {
    return "Wallet empty";
  }
  if (/timed? ?out|timeout/.test(low)) return "Timed out";
  if (/exited 130\b|\bsigint\b|cancelled by (the )?operator/.test(low)) return "Cancelled";
  if (/#\s*cron job:|\*\*job id:\*\*|\*\*run time:\*\*|##\s*prompt/i.test(String(blob || ""))) {
    if (/\b401\b|unauthorized|invalid.?api.?key/.test(low)) return "API key rejected (401)";
    const cronM = String(blob || "").match(/Cron Job:\s*([a-z0-9._-]+)/i);
    const title = cronM && typeof cronTitle === "function" ? cronTitle(cronM[1]) : (cronM ? cronM[1] : "Scheduled job");
    return `${title} failed`;
  }
  const exitM = low.match(/(?:hermes\s+)?(?:chat\s+|think\s+)?exit(?:ed)?\s*(\d+)/);
  if (exitM || /hermes.*(exit|fail)|exit code/.test(low)) {
    return exitM ? `Hermes exited ${exitM[1]}` : "Hermes exited";
  }
  const cronM = String(blob || "").match(/Cron Job:\s*([a-z0-9._-]+)/i);
  if (cronM && /fail/i.test(low)) {
    const title = (typeof cronTitle === "function") ? cronTitle(cronM[1]) : cronM[1];
    return `${title} failed`;
  }
  let cleaned = text
    .replace(/\*\*Job ID:\*\*\s*\S+/gi, "")
    .replace(/#\s*Cron Job:\s*\S+/gi, "")
    .replace(/\bRESULT\b/g, "")
    .replace(/(?:~|\/|[A-Za-z]:[\\/])[^\s]{16,}/g, "…")
    .replace(/^Failed\.?\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned || /^(?:\(no output\)|Failed\.?)$/i.test(cleaned)) {
    return "The last run did not finish";
  }
  return cleaned.slice(0, 120);
}

function jobIsFailed(job) {
  if (!job) return false;
  if (job.stopped) return false;
  const blob = `${job.blocker || ""} ${job.text || ""} ${job.status || ""}`;
  if (/exited 130\b|\bsigint\b/i.test(blob)) return false;
  const blocker = String(job.blocker || "").trim();
  if (blocker && blocker !== "—" && blocker !== "ok") return true;
  return /fail|error/i.test(String(job.status || job.last_status || ""));
}

function gateLineKind(job) {
  if (!job) return "";
  if (jobIsFailed(job)) return "";
  const gate = job.gate || {};
  if (!gate.label) return "";
  if (/irreversible|park/i.test(String(gate.label || ""))) return "parked";
  const hasDraft = Boolean(
    job.diff_pending
    || (job.diff && String(job.diff).trim())
    || (job.untracked && job.untracked.length)
    || job.draft_id
  );
  if (hasDraft && (gate.action === "approval" || job.diff_pending)) return "draft";
  return "";
}

function failFingerprint(row) {
  const reason = humanFailReason(failBlobOf(row) || cronFailBlob(row));
  return reason.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "failed";
}

function dedupeFailRows(rows) {
  const seen = new Set();
  return (rows || []).filter((row) => {
    const id = String((row && (row.cron_id || row.id)) || "");
    const fp = failFingerprint(row);
    const key = id ? `id:${id}` : `fp:${fp}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function failClustersHtml(rows, want) {
  const groups = new Map();
  (rows || []).forEach((row) => {
    const fp = failFingerprint(row);
    if (!groups.has(fp)) groups.set(fp, []);
    groups.get(fp).push(row);
  });
  return [...groups.values()].map((list) => {
    const primary = list[0];
    const extra = Math.max(0, list.length - 1);
    const open = list.some((row) => row.id === want);
    return cronCardHtml(primary, open, "result", extra);
  }).join("");
}

function markFailHandling(id, act) {
  const key = String(id || "").trim();
  if (!key) return;
  const status = act === "ask_cos" ? "Waiting Cos" : "Handling";
  failHandling.set(key, { at: Date.now(), act: String(act || ""), status });
}

function failHandlingStatus(id) {
  const key = String(id || "").trim();
  const row = failHandling.get(key);
  if (!row) return "";
  if ((Date.now() - Number(row.at || 0)) > FAIL_HANDLING_MS) {
    failHandling.delete(key);
    return "";
  }
  return String(row.status || "");
}

function failBlobOf(row) {
  if (!row) return "";
  if (typeof cronFailBlob === "function" && (row.last_error || row.last_status || row.outcome || row.last_result)) {
    return cronFailBlob(row);
  }
  return [
    row.last_error, row.error, row.outcome, row.cron_outcome, row.text, row.summary, row.last_result, row.last_status, row.status, row.blocker
  ].map((x) => String(x || "")).join(" ");
}

function failKindFromBlob(blob) {
  const low = String(blob || "").toLowerCase();
  if (/\b401\b|unauthorized|authentication failed|invalid.?api.?key|x-api-key|no usable credentials|missing.?api.?key/.test(low)) {
    return "key";
  }
  if (/script[- ]?not[- ]?found|script[- ]?missing|no such file.*(script|\.sh|\.py|\.js)|enoent.*scripts\/|missing.*scripts\//.test(low)) {
    return "script";
  }
  if (/exited 130\b|\bsigint\b|cancelled by (the )?operator/.test(low)) return "cancelled";
  if (/gateway shutdown|gateway stopped mid-run/.test(low)) return "gateway";
  if (/insufficient balance|wallet.?empty|out of (?:quota|credit)|billing/.test(low)) return "wallet";
  if (/busy.?session|session.?busy|already running|locked by another|timed? ?out|timeout/.test(low)) {
    return "transient";
  }
  if (/(?:hermes\s+)?(?:chat\s+|think\s+)?exit(?:ed)?\s*\d+|traceback|file ["'].*hermes/.test(low)) {
    return "hermes";
  }
  return "unknown";
}

const CEO_PRETTY = {
  listlogic: "ListLogic",
  nadia: "Nadia",
  "saa-homes": "SAA Homes",
  pmill: "Pmill.ai",
  "pmill-ai": "Pmill.ai",
  openbot: "OpenBot",
  support: "Support"
};

function prettyCeoName(pid, fallback) {
  const id = String(pid || "").toLowerCase();
  if (CEO_PRETTY[id]) return CEO_PRETTY[id];
  const raw = String(fallback || pid || "").trim();
  if (CEO_PRETTY[raw.toLowerCase()]) return CEO_PRETTY[raw.toLowerCase()];
  if (/^listlogic$/i.test(raw)) return "ListLogic";
  if (/^nadia$/i.test(raw)) return "Nadia";
  return raw;
}

function ceoMoveName(pidOrProject) {
  if (pidOrProject && typeof pidOrProject === "object") {
    return prettyCeoName(pidOrProject.id, pidOrProject.name) || talkName();
  }
  const pid = String(pidOrProject || "");
  if (!pid) return "Chief of Staff";
  const project = ((cfg.org && cfg.org.projects) || []).find((row) => String(row.id) === pid);
  return prettyCeoName(pid, project && project.name) || pid;
}

function failMoveWho(row) {
  const pid = row && (row.project_id || projectId);
  if (pid) return ceoMoveName(pid);
  return talkName();
}

function failJobTitle(row, cronId, fallbackId) {
  const cid = String(cronId || fallbackId || (row && (row.cron_id || row.id)) || "").trim();
  const pid = (row && row.project_id) || projectId;
  const pack = digestCache.get(pid) || {};
  const cron = ((pack.crons || []).find((r) => String(r.id) === cid || String(r.name) === cid));
  if (cron) return cron.title || cronTitle(cron.name || cron.id) || cid;
  const named = row && (row.title || row.subject);
  if (named && !/^[0-9a-f]{8,}$/i.test(String(named))) {
    return String(named).replace(/^[A-Za-z0-9 ._-]+ · /, "") || String(named);
  }
  if (cid && !/^[0-9a-f]{8,}$/i.test(cid)) return cronTitle(cid) || cid;
  return "failed job";
}

function failAskWhy(pid, cronId) {
  const pack = digestCache.get(pid) || {};
  const cron = ((pack.crons || []).find((r) => String(r.id) === String(cronId || "") || String(r.name) === String(cronId || "")));
  if (!cron) return "";
  const own = failOwnership(cron);
  return own.outcome || own.reason || "";
}

function failWhyLine(kind, reason) {
  if (kind === "gateway") return "Schedule stalled until the gateway recovers.";
  if (kind === "script") return "Job cannot run without its script on Hermes.";
  if (kind === "hermes") return "Hermes exited — Retry once. This is not a missing API key.";
  if (kind === "key") return "Auth rejected — retries will keep failing until the key is fixed.";
  if (kind === "wallet") return "Spend/credits blocked — only Adam can top up.";
  if (kind === "transient") return "Transient stall — auto-retry should clear it.";
  if (kind === "cancelled") return "Operator stopped this run — not a fail to retry.";
  return reason ? `Last run failed · ${reason}` : "Last run did not finish — needs a call.";
}

function failOwnership(row) {
  const id = String((row && (row.id || row.cron_id || row.job_id)) || "");
  const blob = failBlobOf(row);
  const reason = humanFailReason(blob);
  const kind = failKindFromBlob(blob);
  const local = failHandlingStatus(id);
  const live = Boolean(row && typeof cronIsLive === "function" && cronIsLive(row));
  // gatewayScar must NOT preempt 401/key (or script/wallet) — Fix key wins over Restart gateway.
  const gatewayScar = kind === "gateway" || (typeof cronIsGatewayFail === "function" && cronIsGatewayFail(row));

  if (local === "Waiting Cos") {
    return {
      owner: "cos",
      rank: 2,
      status: "Waiting Cos",
      resultStatus: "Blocked·Cos",
      kind,
      reason,
      why: "CEO stuck — Cos judgment requested.",
      next: "Waiting on Cos · thread opened.",
      outcome: `Failed · ${reason}`
    };
  }
  if (local === "Handling" || (live && (jobIsFailed(row) || /error|fail/i.test(String((row && (row.last_status || row.status)) || ""))))) {
    return {
      owner: "ceo",
      rank: 0,
      status: "Handling",
      resultStatus: "Recovering",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "Handling now · status will move when the run lands.",
      outcome: `Failed · ${reason}`
    };
  }

  // Honest ownership first — 401/key Fix key wins even when Hermes Off / gatewayScar also true.
  if (kind === "key") {
    // Never Auto-retry on 401/key — only Adam has the vault.
    return {
      owner: "adam",
      rank: 3,
      status: "Needs Adam",
      resultStatus: "Needs Adam",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "Needs Adam · Fix key in Settings. CEO cannot retry this.",
      outcome: `Failed · ${reason}`
    };
  }
  if (kind === "script") {
    return {
      owner: "ceo",
      rank: 1,
      status: "CEO",
      resultStatus: "Recovering",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "CEO handling · Restore script from bootstrap. Ask Cos if stuck.",
      outcome: `Failed · ${reason}`
    };
  }
  if (kind === "wallet") {
    return {
      owner: "adam",
      rank: 3,
      status: "Needs Adam",
      resultStatus: "Needs Adam",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "Needs Adam · add credits / fix billing.",
      outcome: `Failed · ${reason}`
    };
  }

  if (gatewayScar) {
    if (!gatewayRunning) {
      return {
        owner: "ceo",
        rank: 1,
        status: "CEO",
        resultStatus: "Recovering",
        kind: "gateway",
        reason,
        why: "Gateway is off — scheduled work waits.",
        next: "Restart gateway — do not mass-fire.",
        outcome: `Failed · ${reason}`
      };
    }
    return {
      owner: "auto",
      rank: 0,
      status: "Auto-retry",
      resultStatus: "Recovering",
      kind: "gateway",
      reason,
      why: failWhyLine("gateway", reason),
      next: "Auto-retry — gateway will pick this up. Do not mass-fire.",
      outcome: `Failed · ${reason}`
    };
  }
  if (kind === "transient") {
    return {
      owner: "auto",
      rank: 0,
      status: "Auto-retry",
      resultStatus: "Recovering",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "Auto-retry — transient. Retry once if it stays red.",
      outcome: `Failed · ${reason}`
    };
  }
  if (kind === "cancelled") {
    return {
      owner: "auto",
      rank: 4,
      status: "Cancelled",
      resultStatus: "Resolved",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "Stopped. Nothing to retry.",
      outcome: `Cancelled · ${reason}`
    };
  }
  if (kind === "hermes") {
    return {
      owner: "ceo",
      rank: 1,
      status: "CEO",
      resultStatus: "Recovering",
      kind,
      reason,
      why: failWhyLine(kind, reason),
      next: "CEO handling · Retry once. Ask Cos if it stays red.",
      outcome: `Failed · ${reason}`
    };
  }
  return {
    owner: "ceo",
    rank: 1,
    status: "CEO",
    resultStatus: "Recovering",
    kind,
    reason,
    why: failWhyLine(kind, reason),
    next: "CEO handling · Retry once. Ask Cos if stuck.",
    outcome: `Failed · ${reason}`
  };
}

function failOwnerRank(row) {
  return Number((failOwnership(row) || {}).rank || 1);
}

function ownershipSort(a, b) {
  const d = failOwnerRank(a) - failOwnerRank(b);
  if (d) return d;
  return String((b && b.last_run_at) || "").localeCompare(String((a && a.last_run_at) || ""));
}

function failChoices(row) {
  const own = failOwnership(row);
  const cronId = (row && (row.cron_id || row.id)) || "";
  const out = [];
  if (own.kind === "gateway" && !gatewayRunning) {
    out.push({ id: "restart_gateway", label: "Restart gateway" });
  } else if (own.kind === "script") {
    out.push({ id: "restore_script", label: "Restore", cron_id: cronId });
    out.push({ id: "ask_cos", label: "Ask Cos", cron_id: cronId });
  } else if (own.kind === "key") {
    out.push({ id: "fix_key", label: "Fix key", cron_id: cronId });
    if (!gatewayRunning) out.push({ id: "restart_gateway", label: "Restart gateway" });
    else out.push({ id: "ask_cos", label: "Ask Cos", cron_id: cronId });
  } else if (own.kind === "cancelled") {
    out.push({ id: "open_detail", label: "Open detail", cron_id: cronId });
  } else if (own.kind === "wallet") {
    out.push({ id: "fix_key", label: "Open Settings", cron_id: cronId });
  } else if (own.owner === "auto") {
    out.push({ id: "open_detail", label: "Open detail", cron_id: cronId });
  } else {
    // unknown / hermes-exit — Retry. Never Fix key on script-missing or crash gore.
    if (!cronSkipRetry(row)) out.push({ id: "retry", label: "Retry", cron_id: cronId });
    else out.push({ id: "open_detail", label: "Open detail", cron_id: cronId });
    out.push({ id: "ask_cos", label: "Ask Cos", cron_id: cronId });
  }
  return out.slice(0, 2);
}

function cronFailNext(row) {
  return failOwnership(row).next;
}

function clusterFailRows(rows) {
  const groups = new Map();
  (rows || []).forEach((row) => {
    const fp = failFingerprint(row);
    if (!groups.has(fp)) groups.set(fp, []);
    groups.get(fp).push(row);
  });
  return [...groups.values()].map((list) => ({ row: list[0], extra: Math.max(0, list.length - 1) }));
}

function opaqueJobName(s) {
  const t = String(s || "").trim();
  if (!t) return true;
  if (/^(ops|auto|job|failed job|last job|scheduled check|code|think|research)$/i.test(t)) return true;
  if (/^[a-f0-9]{8,32}$/i.test(t)) return true;
  return false;
}

function failCardTitle(row) {
  const named = (typeof failJobTitle === "function") ? failJobTitle(row) : "";
  if (named && !opaqueJobName(named)) return named;
  const blob = failBlobOf(row);
  const cronM = String(blob || "").match(/Cron Job:\s*([a-z0-9._-]+)/i);
  if (cronM) return cronTitle(cronM[1]);
  const fromName = row && (row.title || (typeof cronTitle === "function" ? cronTitle(row.name || row.id) : row.name));
  if (fromName && !opaqueJobName(fromName)) return fromName;
  return "Scheduled job";
}

function failChromeHtml(row, open, mark, extraCount) {
  const title = failCardTitle(row);
  const own = failOwnership(row);
  const status = mark === "live" ? "Handling" : (mark === "result" ? own.resultStatus : own.status);
  const fold = String((row && (row.id || row.cron_id || title)) || "job");
  const savedOpen = Boolean((readWorkState().folds || {})[fold]);
  const startOpen = Boolean(open);
  const extra = Number(extraCount) > 0 ? ` +${Number(extraCount)}` : "";
  const choices = failChoices(row).slice(0, 1);
  const acts = choices.length
    ? `<div class="need-actions">${choiceButtonsHtml(choices, { id: (row && row.id) || "", project_id: (row && row.project_id) || projectId || "", cron_id: (row && (row.cron_id || row.id)) || "", kind: "failed", preset: (row && row.preset) || "" })}</div>`
    : "";
  const rawDetail = String((row && (row.last_error || row.last_result || row.text || row.summary || "")) || "").trim();
  const detailFold = rawDetail && rawDetail.length > 40
    ? `<details class="cron-more" data-fold="raw-${escapeHtml(fold)}"><summary>Details</summary><pre>${escapeHtml(rawDetail.slice(0, 4000))}</pre></details>`
    : "";
  const glance = clipWire(own.outcome, 88);
  return `<details class="cron-card failed handled compact" id="cron-${escapeHtml((row && row.id) || "")}" data-fold="${escapeHtml(fold)}" data-owner="${escapeHtml(own.owner)}" data-fail-status="${escapeHtml(status)}"${startOpen ? " open" : ""}>
    <summary class="cron-head">
      <b>${escapeHtml(title)}${escapeHtml(extra)}</b>
      <span>${escapeHtml(status)}</span>
    </summary>
    <p class="cron-glance">${escapeHtml(glance)}</p>
    <p class="cron-next"><span class="cron-k">Next</span> ${escapeHtml(own.next)}</p>
    ${acts}
    ${detailFold}
  </details>`;
}

function opaqueLaneOk(text, preset) {
  const raw = String(text || "").trim();
  if (!raw) return true;
  if (/^(?:THINK_OK|OPS_OK)$/i.test(raw)) return true;
  const cleaned = cleanBotText(raw);
  return !cleaned;
}

function primaryJobBody(job) {
  const raw = String(job.text || "").trim();
  if (jobIsFailed(job)) {
    const reason = humanFailReason(`${job.blocker || ""} ${raw}`);
    return `Failed · ${reason}`;
  }
  if (opaqueLaneOk(raw, job.preset)) {
    if (job.preset === "ops") return "Ops finished. Nothing public.";
    if (job.preset === "think") return "Think finished.";
    return "Work finished. The next step is in the brief above.";
  }
  return cleanBotText(raw) || raw;
}

function inlineBotHtml(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function sentenceSplit(text) {
  const parts = String(text || "").split(/(?<=[.!?])\s+(?=[A-Z“"])/);
  return parts.map((part) => part.trim()).filter(Boolean);
}

function labeledRows(rows) {
  const hits = rows.filter((row) => /^[^:]{1,40}:\s+\S/.test(row)).length;
  return hits >= Math.min(2, rows.length);
}

function formatBotHtml(text) {
  const cleaned = cleanBotText(text);
  if (!cleaned) return "";
  const split = splitHandoff(cleaned);
  const chunks = split.answer.split(/\n{2,}/).map((chunk) => chunk.trim()).filter(Boolean);
  const html = [];
  let leadDone = false;
  chunks.forEach((chunk) => {
    const rows = chunk.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!rows.length) return;
    const leadRows = [];
    let rowIndex = 0;
    while (rowIndex < rows.length && !isLabeledRow(rows[rowIndex])) {
      leadRows.push(rows[rowIndex]);
      rowIndex += 1;
    }
    const rest = rows.slice(rowIndex);
    if (leadRows.length && rest.length && (statusOnly(rest.join("\n")) || labeledRows(rest))) {
      leadRows.forEach((row, index) => {
        html.push(`<p${leadDone || index ? "" : " class=\"bot-lead\""}>${inlineBotHtml(row)}</p>`);
      });
      const items = rest.map((row) => {
        const match = row.match(/^([^:]{1,40}):\s*(.*)$/);
        if (!match) return `<div><dd>${inlineBotHtml(row)}</dd></div>`;
        return `<div><dt>${escapeHtml(match[1])}</dt><dd>${inlineBotHtml(match[2])}</dd></div>`;
      }).join("");
      html.push(`<dl class="bot-stats">${items}</dl>`);
      leadDone = true;
      return;
    }
    if (rows.length === 1 && /^#{1,3}\s+/.test(rows[0])) {
      html.push(`<h3>${inlineBotHtml(rows[0].replace(/^#{1,3}\s+/, ""))}</h3>`);
      return;
    }
    if (rows.every((row) => /^[-*•]\s+/.test(row) || /^\d+\.\s+/.test(row))) {
      const items = rows.map((row) => `<li>${inlineBotHtml(row.replace(/^([-*•]|\d+\.)\s+/, ""))}</li>`).join("");
      html.push(`<ul>${items}</ul>`);
      leadDone = true;
      return;
    }
    if (statusOnly(chunk) || labeledRows(rows)) {
      const items = rows.map((row) => {
        const match = row.match(/^([^:]{1,40}):\s*(.*)$/);
        if (!match) return `<div><dd>${inlineBotHtml(row)}</dd></div>`;
        return `<div><dt>${escapeHtml(match[1])}</dt><dd>${inlineBotHtml(match[2])}</dd></div>`;
      }).join("");
      html.push(`<dl class="bot-stats">${items}</dl>`);
      leadDone = true;
      return;
    }
    if (rows.length > 1) {
      rows.forEach((row, index) => {
        html.push(`<p${leadDone || index ? "" : " class=\"bot-lead\""}>${inlineBotHtml(row)}</p>`);
      });
      leadDone = true;
      return;
    }
    const body = rows[0];
    if (!leadDone && body.length > 280) {
      const sentences = sentenceSplit(body);
      if (sentences.length > 1) {
        html.push(`<p class="bot-lead">${inlineBotHtml(sentences[0])}</p>`);
        sentences.slice(1).forEach((sentence) => html.push(`<p>${inlineBotHtml(sentence)}</p>`));
        leadDone = true;
        return;
      }
    }
    html.push(`<p${leadDone ? "" : " class=\"bot-lead\""}>${inlineBotHtml(body)}</p>`);
    leadDone = true;
  });
  if (split.handoff) {
    html.push(`<details class="receipt-fold"><summary>Handoff</summary><pre>${escapeHtml(split.handoff)}</pre></details>`);
  }
  return html.join("");
}

function paintBotText(el, text) {
  if (!el) return;
  const html = formatBotHtml(text);
  if (html) el.innerHTML = html;
  else el.textContent = "";
}

async function showReplayModal(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/log`);
    if (!res.ok) {
      alert("Session log not found");
      return;
    }
    const data = await res.json();
    const log = data.log || "No log available";
    
    const modal = document.createElement("div");
    modal.className = "modal-overlay";
    modal.innerHTML = `
      <div class="modal-content replay-modal">
        <div class="modal-header">
          <h2>Replay Verbose: ${escapeHtml(jobId)}</h2>
          <button type="button" class="modal-close">&times;</button>
        </div>
        <div class="modal-body">
          <pre class="session-log">${escapeHtml(log)}</pre>
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
    
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.classList.contains("modal-close")) {
        modal.remove();
      }
    });
    
    const escListener = (e) => {
      if (e.key === "Escape") {
        modal.remove();
        document.removeEventListener("keydown", escListener);
      }
    };
    document.addEventListener("keydown", escListener);
  } catch (err) {
    alert("Failed to load session log");
  }
}

async function viewRawLog(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/log`);
    if (!res.ok) {
      alert("Session log not found");
      return;
    }
    const data = await res.json();
    const log = data.log || "No log available";
    
    const win = window.open("", "_blank");
    if (!win) {
      alert("Please allow popups to view raw log");
      return;
    }
    win.document.write(`<html><head><title>Raw Log: ${escapeHtml(jobId)}</title><style>body{font-family:monospace;white-space:pre-wrap;padding:20px;background:#1a1a1a;color:#e0e0e0;}pre{margin:0;}</style></head><body><pre>${escapeHtml(log)}</pre></body></html>`);
    win.document.close();
  } catch (err) {
    alert("Failed to load session log");
  }
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

function briefHonestyLine(cleaned) {
  const counts = workCounts();
  const project = currentProject();
  const trust = scheduleTrustNowLine(counts, project);
  if (trust) return trust;
  const fromNow = indexLineUseful(project && project.index_now)
    || indexLineUseful(indexField(cleaned, "Now"));
  const fromNext = indexLineUseful(project && project.index_next)
    || indexLineUseful(indexField(cleaned, "Next"));
  const rawNow = indexNow(cleaned);
  let line = fromNow || fromNext || (rawNow !== "source of truth" ? indexLineUseful(rawNow) : "");
  line = honestWorkLine(line, counts) || line;
  if (!line && (counts.failed || 0) > 0) line = `${counts.failed} failed — open Results`;
  else if (!line && (counts.next || 0) > 0) line = `${counts.next} due · open Next`;
  return line || rawNow || "source of truth";
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
  const cleaned = cleanBotText(text);
  if ($("indexCard")) $("indexCard").textContent = cleaned || "(empty brief)";
  if ($("indexSummary")) $("indexSummary").textContent = `Brief · ${briefHonestyLine(cleaned)}`;
  paintWorkStatus();
}

function indexLineUseful(value) {
  const raw = cleanBotText(String(value || "")).trim();
  if (!raw || raw === "—" || /^source of truth$/i.test(raw)) return "";
  return raw;
}

function honestIndexNext(next) {
  const raw = String(next || "").trim();
  if (!raw || !/^on schedule\b/i.test(raw)) return raw;
  const counts = workCounts();
  if (!counts.ready) return raw;
  const trust = scheduleTrustNowLine(counts, currentProject());
  if (trust) return trust;
  if ((counts.failed || 0) > 0) {
    return counts.failed === 1 ? "1 failed · open Results" : `${counts.failed} failed · open Results`;
  }
  if ((counts.next || 0) > 0) {
    return counts.next === 1 ? "1 due · open Next" : `${counts.next} due · open Next`;
  }
  return raw;
}

function composerAliveLine() {
  // One short chrome line only — NOW/NEXT/BLOCKER lives in Doing/Next/Results/Schedule.
  const counts = workCounts();
  const story = quietStory(runningStory());
  if (story && story.on && story.line) {
    return { line: story.line, on: true, warn: false };
  }
  const move = handlingAliveLine(counts);
  if (move) {
    return { line: move, on: true, warn: true };
  }
  const trust = scheduleTrustNowLine(counts, currentProject());
  if (trust) {
    return { line: trust, on: false, warn: true };
  }
  if ((counts.failed || 0) > 0) {
    const n = counts.failed;
    return {
      line: n === 1 ? "1 failed · Open Schedule" : `${n} failed · Open Schedule`,
      on: false,
      warn: true
    };
  }
  // Quiet idle — no bare Done spam in composer chrome.
  return { line: "", on: false, warn: false };
}

function handlingAliveLine(counts) {
  // Movement only — idle Auto-retry ownership stays on cards, not composer.
  const pack = digestCache.get(projectId) || {};
  const list = (pack.crons || []).filter((row) => !cronIsNoise(row) && cronIsFailed(row));
  const adam = list.filter((row) => failOwnership(row).owner === "adam");
  if (adam.length) {
    const own = failOwnership(adam[0]);
    const title = failJobTitle(adam[0]) || "job";
    const bit = own.kind === "key" ? "Fix key" : "Open Settings";
    return `Needs Adam · ${title} · ${bit}`;
  }
  const moving = list.filter((row) => {
    const st = failOwnership(row).status;
    return st === "Handling" || st === "Waiting Cos" || st === "CEO";
  });
  const n = moving.length || (counts && counts.handling) || 0;
  if (!n) return "";
  const topRow = moving[0];
  const top = topRow ? failOwnership(topRow) : null;
  const title = failJobTitle(topRow);
  const fails = (counts && counts.failed) || list.length || n;
  if (top && top.status === "Waiting Cos") {
    return `Waiting Cos · ${title || "fail"} · next: Cos judgment`;
  }
  const bit = top
    ? (top.kind === "script" ? "restore script" : (top.kind === "gateway" ? "retry gateway" : "retry"))
    : "Open Next";
  return `Handling · ${title || (fails + " fail" + (fails === 1 ? "" : "s"))} · next: ${bit}`;
}

function ceoHandlingStoryHtml() {
  const who = projectId ? prettyCeoName(projectId, (currentProject() || {}).name) : "Chief of Staff";
  const pack = digestCache.get(projectId) || {};
  const failed = ((pack.crons || []).filter((row) => !cronIsNoise(row) && cronIsFailed(row))).slice().sort(ownershipSort);
  const top = failed[0];
  if (!top) {
    const next = String((currentProject() && currentProject().index_next) || "").trim();
    if (next && next !== "—") return `<p class="cron-story">${escapeHtml(who)} next: ${escapeHtml(clipWire(cleanBotText(next), 160))}</p>`;
    return "";
  }
  const own = failOwnership(top);
  const title = failJobTitle(top) || "a failed job";
  const because = own.reason || own.why || "last run failed";
  return `<p class="cron-story">${escapeHtml(who)} is handling ${escapeHtml(title)} because ${escapeHtml(because)}. Next: ${escapeHtml(own.next)}</p>`;
}

function paintWorkStatus() {
  const el = $("workStatus");
  const liveEl = $("workStatusLive");
  if (!el) return;
  const alive = composerAliveLine();
  const line = String(alive.line || "").trim();
  const show = Boolean(line) && !/^Done\b/i.test(line);
  el.hidden = !show;
  if (!liveEl) return;
  liveEl.hidden = !show;
  liveEl.classList.toggle("on", Boolean(show && alive.on));
  liveEl.classList.toggle("warn", Boolean(show && alive.warn));
  liveEl.textContent = show ? line : "";
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
  const pin = preset && preset !== "cos";
  const engine = pin ? (PRESET_ENGINE[preset] || "board") : "";
  let desk = "Chief of Staff";
  if (worker && project) desk = `${worker.name} · ${project.name}`;
  else if (project) desk = project.name;
  const line = pin
    ? `${desk} · ${jobLabel(preset)}${engine ? ` · ${engine}` : ""}`
    : desk;
  if ($("composerWho")) $("composerWho").textContent = line;
  if ($("msg")) {
    const prefix = pin ? `${jobLabel(preset)} · ` : "";
    $("msg").placeholder = `${prefix}Message ${who}`;
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
  const last = stream.querySelector(".bubble:last-of-type, .card:last-of-type, .cron-card:last-of-type");
  if (last && typeof last.scrollIntoView === "function") {
    last.scrollIntoView({ block: "end", inline: "nearest" });
    return;
  }
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
  const lanes = $("laneStatus");
  if (lanes) lanes.hidden = true;
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
  paintRouteHatch();
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
    } else if (live && queued) {
      send.textContent = "Send now";
      send.type = "button";
      send.classList.remove("stop");
      send.setAttribute("aria-label", "Send waiting message now");
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
        `Running · ${talkName()}${lane ? ` · ${lane}` : ""}`,
        "Your line stays in the thread",
        queued ? "Send now delivers the waiting line" : "Enter adds another",
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
  paintCeoLive(digestCache.get(projectId));
  paintPulse();
}

function engineFoundLine() {
  const h = (cfg.engines && cfg.engines.hermes) || {};
  const o = (cfg.engines && cfg.engines.opencode) || {};
  const bits = [];
  if (o.present) bits.push("OpenCode");
  if (h.present) bits.push("Hermes");
  return bits.length ? bits.join(" + ") : "board";
}

function receiptLine(job) {
  if (!job) return "board";
  const engine = String(job.engine || PRESET_ENGINE[job.preset] || "board").trim() || "board";
  const status = jobStatusWord(job);
  const model = job.model && job.model !== "none" ? (modelName(job.model) || job.model) : "";
  const cost = Number(job.usd_estimate || 0);
  const money = cost ? `$${cost.toFixed(4)}` : "";
  const named = engine === "board" ? "" : engine;
  return [status, named, model, money].filter(Boolean).join(" · ");
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
  chainContexts.delete(idKey);
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
  const empty = $("streamEmpty");
  if (empty) empty.remove();
  const userEl = bubble("user", text);
  if (quote) attachQuotePreview(userEl, quote);
  userEl.classList.add("queued");
  const wait = document.createElement("div");
  wait.className = "bubble-queued";
  wait.textContent = "Waiting until this reply finishes";
  userEl.appendChild(wait);
  queueFor(key).push({
    message: text,
    preset: (opts && opts.preset) || preset || "cos",
    quote: quote || "",
    userEl
  });
  if (!(opts && opts.keepQuote)) clearReply();
  paintQueueChip();
  lockComposer(Boolean(cfg.has_key));
}

let drainingQueue = false;

async function drainQueue() {
  if (liveRunId || drainingQueue) return;
  drainingQueue = true;
  try {
    while (!liveRunId) {
      const key = aimKey();
      const rows = queueFor(key);
      if (!rows.length) {
        paintQueueChip();
        break;
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
      await sendMessage(next.message, {
        preset: next.preset,
        allowSecret: false,
        quote: next.quote || "",
        userEl: next.userEl
      });
    }
  } finally {
    drainingQueue = false;
  }
}

async function sendQueuedNow() {
  if (liveFor(aimKey())) await stopLive();
  await drainQueue();
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
  el.textContent = `$${used} of $${cap} · ${period}${halt}`;
  paintPulse();
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
    if (org && org.projects) {
      paintOrgLife();
      const tree = $("orgTree");
      const inbox = tree && tree.querySelector(".org-inbox");
      const next = inboxHtml();
      if (inbox && next) inbox.outerHTML = next;
      else if (inbox && !next) inbox.remove();
      else if (!inbox && next) renderOrg(org);
      if (tree) {
        bindNeedActions(tree);
        bindOpenDesk(tree);
      }
    }
  }
}

function paintOrgLife() {
  document.querySelectorAll(".org-btn[data-kind]").forEach((btn) => {
    const pid = btn.dataset.project || "";
    const busy = lives.has(aimKey(pid, "")) || ((cfg.activity || {}).live_runs || []).some((row) => String(row.project_id || "") === String(pid));
    const blocked = projectNeedsYou(pid);
    const life = busy ? "working" : (blocked ? "blocked" : (((cfg.activity || {}).hermes_running || (cfg.activity || {}).opencode_running) ? "idle" : "offline"));
    const avatar = btn.querySelector(".org-avatar");
    if (avatar) avatar.setAttribute("data-life", life);
    btn.classList.toggle("working", life === "working");
    btn.classList.toggle("has-blocker", life === "blocked");
  });
}

let menuJustOpened = false;

function hideNodeMenu() {
  const menu = $("nodeMenu");
  if (menu) {
    menu.classList.add("hidden");
    menu.classList.remove("ceo-add");
    menu.style.transform = "";
  }
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
  paintWorkTabs();
}

async function postProject(folder, name, extras) {
  const body = Object.assign(
    { folder: folder || "", name: name || "" },
    extras && typeof extras === "object" ? extras : {}
  );
  const res = await fetch("/api/org/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await res.json();
  $("orgStatus").textContent = res.ok ? "" : (data.error || "add failed");
  if (res.ok) {
    hideNodeMenu();
    await applyOrg(data);
    if (data.project_id) await setOrgNode(data.project_id, "");
  }
}

const CEO_SEAT_PRESETS = {
  pmill: {
    site_url: "https://pmill.ai",
    github_repo: "adamsch0100/pmillsports",
    railway: "victorious-presence",
    goals: "profitability · pay for itself first"
  },
  nadia: {
    site_url: "https://e8solutions.ai",
    github_repo: "adamsch0100/fub-hermes",
    railway: "e8solutions.io",
    goals: "paid seats · pay for itself first"
  },
  listlogic: {
    site_url: "https://listlogic.homes",
    github_repo: "adamsch0100/saahomes",
    railway: "ListLogic",
    goals: "paid activations · pay for itself first"
  }
};

function ceoSeatPreset(name) {
  const slug = String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  if (!slug) return null;
  if (CEO_SEAT_PRESETS[slug]) return Object.assign({}, CEO_SEAT_PRESETS[slug]);
  for (const key of Object.keys(CEO_SEAT_PRESETS)) {
    if (slug.startsWith(`${key}-`)) return Object.assign({}, CEO_SEAT_PRESETS[key]);
  }
  return null;
}

function readAddCeoForm() {
  const name = ($("menuCeoAddName") && $("menuCeoAddName").value.trim()) || "";
  const folder = ($("menuProjectFolder") && $("menuProjectFolder").value.trim()) || "";
  const site = ($("menuCeoSite") && $("menuCeoSite").value.trim()) || "";
  const repo = ($("menuCeoRepo") && $("menuCeoRepo").value.trim()) || "";
  const railway = ($("menuCeoRailway") && $("menuCeoRailway").value.trim()) || "";
  const goals = ($("menuCeoGoals") && $("menuCeoGoals").value.trim()) || "";
  const mcp = Boolean($("menuCeoAuthGithub") && $("menuCeoAuthGithub").checked);
  const authSite = Boolean($("menuCeoAuthSite") && $("menuCeoAuthSite").checked);
  const authRail = Boolean($("menuCeoAuthRailway") && $("menuCeoAuthRailway").checked);
  return {
    name,
    folder,
    extras: {
      site_url: site,
      github_repo: repo,
      railway,
      goals,
      mcp_github: mcp,
      authorize_site: authSite,
      authorize_railway: authRail
    }
  };
}

function applyCeoSeatPresetToForm(name) {
  const prefs = ceoSeatPreset(name);
  if (!prefs) return;
  if ($("menuCeoSite") && !$("menuCeoSite").value.trim()) $("menuCeoSite").value = prefs.site_url || "";
  if ($("menuCeoRepo") && !$("menuCeoRepo").value.trim()) $("menuCeoRepo").value = prefs.github_repo || "";
  if ($("menuCeoRailway") && !$("menuCeoRailway").value.trim()) $("menuCeoRailway").value = prefs.railway || "";
  if ($("menuCeoGoals") && !$("menuCeoGoals").value.trim()) $("menuCeoGoals").value = prefs.goals || "";
  if ($("menuCeoAuthGithub") && prefs.github_repo) $("menuCeoAuthGithub").checked = true;
  if ($("menuCeoAuthSite") && prefs.site_url) $("menuCeoAuthSite").checked = true;
  if ($("menuCeoAuthRailway") && prefs.railway) $("menuCeoAuthRailway").checked = true;
}

function addCeoFormHtml() {
  const folderHint = escapeHtml((org && org.folder) || "default OpenCode folder");
  return `
      <p class="menu-note">Name unlocks presets (Pmill, Nadia, ListLogic). Site / GitHub / Railway wire tools on seat.</p>
      <div class="menu-field">
        <label for="menuCeoAddName">Name</label>
        <input id="menuCeoAddName" type="text" placeholder="Pmill" autocomplete="off" />
      </div>
      <div class="menu-field">
        <label for="menuProjectFolder">Folder (optional)</label>
        <input id="menuProjectFolder" type="text" placeholder="${folderHint}" autocomplete="off" />
      </div>
      <div class="menu-grid-2">
        <div class="menu-field">
          <label for="menuCeoSite">Site</label>
          <input id="menuCeoSite" type="url" placeholder="https://pmill.ai" autocomplete="off" />
        </div>
        <div class="menu-field">
          <label for="menuCeoRepo">GitHub repo</label>
          <input id="menuCeoRepo" type="text" placeholder="owner/repo" autocomplete="off" />
        </div>
      </div>
      <div class="menu-grid-2">
        <div class="menu-field">
          <label for="menuCeoRailway">Railway</label>
          <input id="menuCeoRailway" type="text" placeholder="project or service name" autocomplete="off" />
        </div>
        <div class="menu-field">
          <label for="menuCeoGoals">Goal</label>
          <input id="menuCeoGoals" type="text" placeholder="profitability" autocomplete="off" />
        </div>
      </div>
      <fieldset class="menu-field menu-auth">
        <legend>Authorize tools</legend>
        <label class="check-line"><input id="menuCeoAuthGithub" type="checkbox" /> GitHub MCP (Code)</label>
        <label class="check-line"><input id="menuCeoAuthSite" type="checkbox" /> Site research</label>
        <label class="check-line"><input id="menuCeoAuthRailway" type="checkbox" /> Railway</label>
      </fieldset>
      <div class="menu-field menu-actions">
        <button type="button" class="send" data-menu="add-project">Add CEO</button>
      </div>`;
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
  menu.classList.remove("ceo-add");
  if (kind === "add-ceo") {
    menu.classList.add("ceo-add");
    html = `
      <div class="menu-head">Add CEO</div>
      <p class="muted menu-note">Name the desk. Site, repo, Railway, and tool auth seat with it. Pmill prefills known prefs.</p>
      ${addCeoFormHtml()}`;
  } else if (kind === "staff") {
    if (canAddCeo()) menu.classList.add("ceo-add");
    html = canAddCeo()
      ? `
      <div class="menu-head">Chief of Staff</div>
      ${addCeoFormHtml()}
      <div class="menu-field">
        <label for="menuIndexEdit">Staff brief</label>
        <textarea id="menuIndexEdit" rows="6">${escapeHtml(org.index || "")}</textarea>
        <button type="button" class="ghost-btn" data-menu="save-index">Save brief</button>
      </div>
      <button type="button" role="menuitem" data-menu="configure">Open settings</button>`
      : `
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
  if (kind === "add-ceo") {
    menu.style.left = "50%";
    menu.style.top = "50%";
    menu.style.right = "auto";
    menu.style.transform = "translate(-50%, -50%)";
  } else {
    menu.style.transform = "";
    const left = Math.min(x, window.innerWidth - (kind === "staff" ? 420 : 340));
    const top = Math.min(y, window.innerHeight - 80);
    menu.style.left = `${Math.max(8, left)}px`;
    menu.style.top = `${Math.max(8, top)}px`;
    menu.style.right = "auto";
  }
  menuJustOpened = true;
  setTimeout(() => { menuJustOpened = false; }, 0);
  const nameInput = $("menuCeoAddName");
  if (nameInput) {
    nameInput.addEventListener("input", () => applyCeoSeatPresetToForm(nameInput.value));
    nameInput.addEventListener("change", () => applyCeoSeatPresetToForm(nameInput.value));
    nameInput.focus();
  }
  menu.querySelectorAll("[data-menu]").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const action = btn.dataset.menu;
      if (action === "add-project") {
        const form = readAddCeoForm();
        if (form.name || form.folder || form.extras.site_url || form.extras.github_repo) {
          await postProject(form.folder, form.name, form.extras);
        }
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
        setSettings(true, kind === "staff" || kind === "add-ceo" ? "you" : "ceo");
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
  const status = $("ceoToolsStatus");
  if (status) status.textContent = "Saving…";

  const seats = {};
  document.querySelectorAll("[data-ceo-seat]").forEach((input) => {
    seats[input.dataset.ceoSeat] = { model: input.value };
  });

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

  const project = projectById(pid) || currentProject() || {};
  const capInput = $("ceoSpendCap");
  const capRaw = capInput ? capInput.value.trim() : "";
  const account = $("ceoAccountId");
  const site = $("ceoSiteUrl");
  const folder = $("ceoFolder");
  const repo = $("ceoGithubRepo");
  const railway = $("ceoRailway");
  const fallbackInput = $("ceoFallback");
  const fallback = fallbackInput ? fallbackInput.value.split(",").map(s => s.trim()).filter(Boolean) : [];
  const folderValue = folder ? folder.value.trim() : "";
  const currentFolder = String(project.folder || "").trim();

  const body = {
    spend_cap_usd: capRaw === "" ? "" : Number(capRaw),
    account_id: account ? account.value : "",
    fallback,
    site_url: site ? site.value.trim() : "",
    github_repo: repo ? repo.value.trim() : "",
    railway: railway ? railway.value.trim() : "",
    mcp_github: Boolean($("ceoAuthGithub") && $("ceoAuthGithub").checked),
    authorize_site: Boolean($("ceoAuthSite") && $("ceoAuthSite").checked),
    authorize_railway: Boolean($("ceoAuthRailway") && $("ceoAuthRailway").checked),
    authorize_cookie_export: Boolean($("ceoAuthCookieExport") && $("ceoAuthCookieExport").checked),
    authorize_facebook: Boolean($("ceoAuthFacebook") && $("ceoAuthFacebook").checked),
    connectors,
    seats
  };
  // Only PATCH folder when it actually changed — re-posting a laptop path fails Save.
  if (folderValue && folderValue !== currentFolder) body.folder = folderValue;

  try {
    const res = await fetch(`/api/org/projects/${pid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (status) {
      status.textContent = res.ok ? "Saved" : (data.error || "Save failed");
      status.classList.toggle("error", !res.ok);
    }
    if (res.ok) {
      applyOrg(data);
      loadSpend();
      window.setTimeout(() => {
        if (status && status.textContent === "Saved") status.textContent = "";
      }, 2200);
    }
  } catch (err) {
    if (status) {
      status.textContent = "Save failed — board unreachable";
      status.classList.add("error");
    }
  }
}

function wireState(on, labelOn, labelOff) {
  return on
    ? `<span class="wire-on">${escapeHtml(labelOn || "Authorized")}</span>`
    : `<span class="wire-off">${escapeHtml(labelOff || "Off")}</span>`;
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






function shortHomeLeaf(home) {
  const raw = String(home || "").replace(/\\/g, "/").replace(/\/+$/, "");
  if (!raw) return "—";
  const parts = raw.split("/").filter(Boolean);
  return parts[parts.length - 1] || raw;
}

function paintEngineHealthCard(data) {
  const host = $("ceoEngineHealth");
  if (!host) return;
  if (!data || typeof data !== "object") {
    host.innerHTML = `<p class="muted">Engine health unavailable.</p>`;
    return;
  }
  const h = data.hermes || {};
  const o = data.opencode || {};
  const w = data.wire || {};
  const s = data.steward || {};
  const warns = Array.isArray(data.warn) ? data.warn : [];
  const hermesLine = [
    h.present ? (h.version || "found") : "missing",
    h.dash_running ? (h.dash_home_ok ? `dash · ${shortHomeLeaf(h.home || h.dash_home)}` : "dash · wrong home") : "dash off",
    h.home ? (h.gateway_running ? "gateway up" : "gateway off") : null
  ].filter(Boolean).join(" · ");
  const ocLine = [
    o.present ? (o.version || "found") : "missing",
    o.web_running ? "web up" : "web off"
  ].join(" · ");
  const wireLine = [
    `GitHub ${w.github ? "on" : "off"}`,
    `Railway ${w.railway ? "on" : "off"}`,
    `Site ${w.site ? "on" : "off"}`
  ].join(" · ");
  const pinLine = [
    s.hermes_pin ? `Hermes ${s.hermes_pin}` : null,
    s.opencode_pin ? `OpenCode ${s.opencode_pin}` : null
  ].filter(Boolean).join(" · ") || "pins unset";
  const nexts = Array.isArray(data.next) ? data.next : [];
  const action = data.action || "";
  const hermesBad = Boolean(warns.length) || (h.dash_running && !h.dash_home_ok) || (h.home && !h.gateway_running);
  const footer = warns.length
    ? `<p class="wire-error">${escapeHtml(warns[0])}</p>
       ${nexts[0] ? `<p class="muted">Next: ${escapeHtml(nexts[0])}</p>` : ""}
       ${action === "restart_gateway" ? `<div class="actions"><button type="button" class="ghost-btn" id="ceoHealthRestartGw">Restart Hermes gateway</button></div>` : ""}`
    : `<p class="muted">Engines look aligned for this CEO.</p>`;
  host.innerHTML = `
    <div class="kv">
      <div><dt>Hermes</dt><dd class="${hermesBad ? "wire-bad" : ""}">${escapeHtml(hermesLine)}</dd></div>
      <div><dt>OpenCode</dt><dd class="${o.present ? "" : "wire-bad"}">${escapeHtml(ocLine)}</dd></div>
      <div><dt>Wire</dt><dd>${escapeHtml(wireLine)}</dd></div>
      <div><dt>Steward</dt><dd>${escapeHtml(pinLine)} · Accept only</dd></div>
    </div>
    ${footer}
  `;
  const restart = $("ceoHealthRestartGw");
  if (restart) {
    restart.addEventListener("click", () => {
      if ($("ceoRetryHermes")) $("ceoRetryHermes").click();
      else if ($("retryHermes")) $("retryHermes").click();
      else setStage("hermes");
    });
  }
}

async function loadCeoEngineHealth(project) {
  const host = $("ceoEngineHealth");
  if (!host || !project || !project.id) return;
  host.innerHTML = `<p class="muted">Checking engines…</p>`;
  try {
    const res = await fetch(`/api/engines/health?project_id=${encodeURIComponent(project.id)}`);
    const data = await res.json().catch(() => ({}));
    paintEngineHealthCard(data);
  } catch (err) {
    host.innerHTML = `<p class="wire-error">Engine health failed.</p>`;
  }
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
  const spend = tools.spend_cap_usd;
  const hermesHome = tools.hermes_home || "";
  const hermesSessionId = tools.hermes_session_id || "";
  const sessionCount = tools.session_count || 0;
  const sessionTitle = tools.session_title || "";
  const accountId = tools.account_id || "";
  const fallback = (tools.fallback || []).join(", ") || "—";
  const siteUrl = tools.site_url || "";
  const githubRepo = tools.github_repo || "";
  const railway = tools.railway || "";
  const authGithub = Boolean(tools.mcp_github);
  const authSite = Boolean(tools.authorize_site);
  const authRailway = Boolean(tools.authorize_railway);
  const authCookie = Boolean(tools.authorize_cookie_export);
  const authFacebook = Boolean(tools.authorize_facebook);
  const seats = tools.seats || {};
  const connectors = tools.connectors || { skills: {}, mcp: {} };
  const noOrigin = Boolean(git.is_repo) && !git.remote;
  const isNadia = project.id === "nadia" || /nadia/i.test(String(project.name || ""));
  const isListLogic = project.id === "listlogic" || /listlogic/i.test(String(project.name || ""));
  
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
        <div><dt>Research</dt><dd>Skills: ${availableSkills.research.join(", ") || "none"} · site ${authSite ? "authorized" : "off"}</dd></div>
        <div><dt>Ops</dt><dd>Skills: ${availableSkills.ops.join(", ") || "none"} · Railway ${authRailway ? "authorized" : "off"}</dd></div>
        <div><dt>Code</dt><dd>MCP: ${availableMcp.code.join(", ") || "none"} · GitHub ${authGithub ? "authorized" : "off"}</dd></div>
      </div>
      <p class="muted">Chat never gets tools. Authorize below for Code / Research / Ops on this CEO.</p>
    </div>
  `;

  const gitCard = noOrigin
    ? `<div class="usage-card">
      <h4>Git · no origin</h4>
      <p class="lede">Local repo only. Connect GitHub — Save cannot invent a remote.</p>
      <div class="field">
        <label for="ceoGithubRepo">GitHub repo</label>
        <input id="ceoGithubRepo" type="text" value="${escapeHtml(githubRepo)}" placeholder="adamsch0100/pmillsports" />
      </div>
      <div class="actions">
        <a class="send" id="ceoConnectGithub" href="https://github.com/login" target="_blank" rel="noreferrer">Connect GitHub</a>
        <button type="button" class="ghost-btn" id="ceoOpenGitPanel">Open Git panel</button>
      </div>
      <p class="muted">After OAuth / <code>gh auth login</code>, paste owner/repo and authorize GitHub MCP.</p>
    </div>`
    : `<div class="usage-card">
      <h4>Code</h4>
      <div class="kv">
        <div><dt>Folder</dt><dd>${escapeHtml(folder)}</dd></div>
        <div><dt>Git</dt><dd>${escapeHtml(remote)}</dd></div>
        <div><dt>GitHub MCP</dt><dd>${wireState(authGithub)}</dd></div>
      </div>
      <div class="field">
        <label for="ceoGithubRepo">GitHub repo</label>
        <input id="ceoGithubRepo" type="text" value="${escapeHtml(githubRepo)}" placeholder="adamsch0100/pmillsports" />
      </div>
    </div>`;

  const hermesFail = String((cfg.engines && cfg.engines.hermes && cfg.engines.hermes.error) || "").trim();
  const hermesCard = `<div class="usage-card">
      <h4>Hermes</h4>
      <div class="kv">
        <div><dt>Home</dt><dd>${escapeHtml(hermesHome || "not attached")}</dd></div>
        <div><dt>Telegram ID</dt><dd>${escapeHtml(hermesSessionId || "—")}</dd></div>
        <div><dt>Sessions</dt><dd>${sessionCount}</dd></div>
        ${sessionTitle ? `<div><dt>Last</dt><dd>${escapeHtml(sessionTitle)}</dd></div>` : ""}
      </div>
      ${hermesFail || (!hermesHome)
        ? `<p class="wire-error">${escapeHtml(hermesFail || "No Hermes home on this CEO. Re-seat or open Tools → Hermes and Restart gateway.")}</p>
           <div class="actions"><button type="button" class="ghost-btn" id="ceoRetryHermes">Restart Hermes gateway</button></div>`
        : ""}
    </div>`;

  const riskCard = (isNadia || isListLogic)
    ? `<div class="usage-card">
      <h4>Risk · scoped consent</h4>
      <p class="muted">Secrets stay in the vault. Chat never receives cookies or Facebook tokens.</p>
      ${isNadia ? `<label class="check-line"><input id="ceoAuthCookieExport" type="checkbox"${authCookie ? " checked" : ""} /> Authorize Nadia cookie export (vault only)</label>` : `<input id="ceoAuthCookieExport" type="checkbox" hidden ${authCookie ? "checked" : ""} />`}
      ${isListLogic ? `<label class="check-line"><input id="ceoAuthFacebook" type="checkbox"${authFacebook ? " checked" : ""} /> Authorize ListLogic Facebook (vault login approve)</label>` : `<input id="ceoAuthFacebook" type="checkbox" hidden ${authFacebook ? "checked" : ""} />`}
    </div>`
    : `<input id="ceoAuthCookieExport" type="checkbox" hidden ${authCookie ? "checked" : ""} /><input id="ceoAuthFacebook" type="checkbox" hidden ${authFacebook ? "checked" : ""} />`;
  
  if (hint) hint.textContent = `${project.name} — Keys, spend, seats, connectors, and Hermes home`;
  if (isCollaborator()) {
    if (hint) hint.textContent = `${project.name} — shared with you`;
    body.innerHTML = "";
    fillCollaboratorShareCard(project);
    return;
  }
  body.innerHTML = `
    <div class="usage-card" id="ceoEngineHealthCard"><h4>Engines</h4><div id="ceoEngineHealth"><p class="muted">Checking engines…</p></div></div>
    ${toolsStrip}
    ${gitCard}
    ${hermesCard}
    <div class="field">
      <label for="ceoFolder">Code folder</label>
      <input id="ceoFolder" type="text" value="${escapeHtml(folder)}" placeholder="C:\\path\\to\\repo" />
    </div>
    <div class="field">
      <label for="ceoSiteUrl">Site URL</label>
      <input id="ceoSiteUrl" type="text" value="${escapeHtml(siteUrl)}" placeholder="https://pmill.ai" />
      <p class="muted">Research snapshots use this URL when Site research is authorized.</p>
    </div>
    <div class="field">
      <label for="ceoRailway">Railway</label>
      <input id="ceoRailway" type="text" value="${escapeHtml(railway)}" placeholder="victorious-presence" />
    </div>
    <fieldset class="usage-card ceo-auth-wire">
      <h4>Authorize tools</h4>
      <label class="check-line"><input id="ceoAuthGithub" type="checkbox"${authGithub ? " checked" : ""} /> GitHub MCP (Code) ${wireState(authGithub)}</label>
      <label class="check-line"><input id="ceoAuthSite" type="checkbox"${authSite ? " checked" : ""} /> Site research ${wireState(authSite)}</label>
      <label class="check-line"><input id="ceoAuthRailway" type="checkbox"${authRailway ? " checked" : ""} /> Railway ${wireState(authRailway)}</label>
    </fieldset>
    ${riskCard}
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
  loadCeoEngineHealth(project);
  
  // Set up event listeners
  const save = $("saveCeoTools");
  if (save) save.addEventListener("click", () => saveCeoTools(project.id));
  const openGit = $("ceoOpenGitPanel");
  if (openGit) openGit.addEventListener("click", () => setSettings(true, "git"));
  const retryH = $("ceoRetryHermes");
  if (retryH) retryH.addEventListener("click", () => {
    if ($("retryHermes")) $("retryHermes").click();
    else setStage("hermes");
  });
  fillOwnerSharePanel(project);
}

function fillCollaboratorShareCard(project) {
  const body = $("ceoPanelBody");
  if (!body) return;
  const share = cfg.share || {};
  const member = share.member || {};
  const card = document.createElement("div");
  card.className = "usage-card";
  card.innerHTML = `
    <h4>This share</h4>
    <p class="lede">Shared with you by ${escapeHtml(share.owner_name || "the owner")}. You help manage ${escapeHtml((project && project.name) || "this CEO")}.</p>
    <div class="field">
      <label for="collabName">Display name</label>
      <input id="collabName" type="text" value="${escapeHtml(member.display_name || "")}" />
    </div>
    <div class="field">
      <label for="collabSecret">New unlock secret</label>
      <input id="collabSecret" type="password" autocomplete="new-password" placeholder="leave blank to keep" />
    </div>
    <div class="actions">
      <button type="button" class="send" id="saveCollabYou">Save</button>
      <button type="button" class="ghost-btn" id="leaveShareBtn">Leave share</button>
      <p class="muted" id="collabYouStatus"></p>
    </div>
  `;
  body.appendChild(card);
  const save = $("saveCollabYou");
  if (save) save.addEventListener("click", saveCollaboratorYou);
  const leave = $("leaveShareBtn");
  if (leave) leave.addEventListener("click", leaveShare);
}

async function saveCollaboratorYou() {
  const body = {
    display_name: ($("collabName") && $("collabName").value.trim()) || ""
  };
  const secret = ($("collabSecret") && $("collabSecret").value) || "";
  if (secret) body.secret = secret;
  const res = await fetch("/api/share/me", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await res.json();
  if ($("collabYouStatus")) $("collabYouStatus").textContent = res.ok ? "saved" : (data.error || "save failed");
}

async function leaveShare() {
  const res = await fetch("/api/share/me", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ leave: true })
  });
  if (res.ok) {
    localStorage.removeItem("openbot_share_member");
    location.href = location.pathname;
  }
}

async function fillOwnerSharePanel(project) {
  const body = $("ceoPanelBody");
  if (!body || !project) return;
  const wrap = document.createElement("div");
  wrap.id = "ceoSharePanel";
  wrap.innerHTML = `<h3 class="drawer-sub">Share this CEO</h3><p class="muted">Invite a helper. You still pay. They do not see keys.</p><p class="muted" id="sharePanelStatus">Loading…</p>`;
  body.appendChild(wrap);
  let data = {};
  try {
    const res = await fetch(`/api/share?project_id=${encodeURIComponent(project.id)}`);
    data = await res.json();
  } catch (_err) {
    if ($("sharePanelStatus")) $("sharePanelStatus").textContent = "Could not load shares.";
    return;
  }
  const members = data.members || [];
  const invites = data.invites || [];
  const memberHtml = members.map((row) => `
    <div class="share-member" data-member="${escapeHtml(row.id)}">
      <b>${escapeHtml(row.display_name || "Collaborator")}</b>
      <span class="muted">${escapeHtml(row.status || "active")} · last ${escapeHtml(row.last_active_at || "—")}</span>
      <div class="share-perm">${sharePermChecks(row.permissions)}</div>
      <div class="field">
        <label>Daily spend ceiling USD</label>
        <input data-share-ceiling type="number" min="0" step="0.5" value="${row.spend_ceiling_usd_day == null ? "" : escapeHtml(String(row.spend_ceiling_usd_day))}" placeholder="CEO cap" />
      </div>
      <label><input data-share-chat-only type="checkbox"${row.seats_mode === "chat_only" ? " checked" : ""} /> Chat-only seats</label>
      <div class="actions">
        <button type="button" class="send" data-save-member="${escapeHtml(row.id)}">Save</button>
        <button type="button" class="ghost-btn" data-pause-member="${escapeHtml(row.id)}">${row.status === "paused" ? "Resume" : "Pause"}</button>
        <button type="button" class="ghost-btn" data-remove-member="${escapeHtml(row.id)}">Remove</button>
      </div>
    </div>
  `).join("") || `<p class="muted">No collaborators yet.</p>`;
  const inviteHtml = invites.map((row) => `
    <p class="muted">Invite ${escapeHtml(row.id)} · ${escapeHtml(row.status)} · uses ${escapeHtml(String(row.uses || 0))}/${escapeHtml(String(row.max_uses || 1))}
      <button type="button" class="ghost-btn" data-revoke-invite="${escapeHtml(row.id)}">Revoke</button>
    </p>
  `).join("");
  wrap.innerHTML = `
    <h3 class="drawer-sub">Share this CEO</h3>
    <p class="lede">Invite a helper to this CEO’s chat and jobs. You keep keys, PIN, and billing.</p>
    <div class="share-perm">${sharePermChecks({
      chat_read: true, chat_write: true, jobs_view: true, jobs_run: true, index_edit: true,
      approve_needs_you: false, engines_view: true, workers_manage: false, wiring_edit: false
    })}</div>
    <div class="field">
      <label for="shareInviteDays">Invite expiry (days)</label>
      <input id="shareInviteDays" type="number" min="1" max="90" value="7" />
    </div>
    <div class="actions">
      <button type="button" class="send" id="createShareInvite">Create invite link</button>
      <p class="muted" id="sharePanelStatus"></p>
    </div>
    <input id="shareInviteUrl" type="text" readonly class="hidden" />
    ${inviteHtml}
    <h3 class="drawer-sub">Members</h3>
    ${memberHtml}
  `;
  const create = $("createShareInvite");
  if (create) {
    create.addEventListener("click", async () => {
      const res = await fetch("/api/share/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: project.id,
          permissions: readSharePerms(wrap),
          expires_days: Number(($("shareInviteDays") && $("shareInviteDays").value) || 7),
          origin: location.origin
        })
      });
      const out = await res.json();
      if (!res.ok) {
        if ($("sharePanelStatus")) $("sharePanelStatus").textContent = out.error || "invite failed";
        return;
      }
      const box = $("shareInviteUrl");
      if (box) {
        box.classList.remove("hidden");
        box.value = out.url || "";
        box.select();
      }
      if ($("sharePanelStatus")) $("sharePanelStatus").textContent = "Invite link ready. Copy it.";
    });
  }
  wrap.querySelectorAll("[data-save-member]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const card = btn.closest(".share-member");
      const ceiling = card && card.querySelector("[data-share-ceiling]");
      const chatOnly = card && card.querySelector("[data-share-chat-only]");
      const res = await fetch(`/api/share/members/${btn.dataset.saveMember}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          permissions: readSharePerms(card),
          spend_ceiling_usd_day: ceiling && ceiling.value === "" ? null : Number(ceiling && ceiling.value),
          seats_mode: chatOnly && chatOnly.checked ? "chat_only" : "inherit"
        })
      });
      const out = await res.json();
      if ($("sharePanelStatus")) $("sharePanelStatus").textContent = res.ok ? "member saved" : (out.error || "save failed");
    });
  });
  wrap.querySelectorAll("[data-pause-member]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const paused = btn.textContent === "Pause";
      await fetch(`/api/share/members/${btn.dataset.pauseMember}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pause: paused })
      });
      fillCeoPanel();
    });
  });
  wrap.querySelectorAll("[data-remove-member]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/share/members/${btn.dataset.removeMember}`, { method: "DELETE" });
      fillCeoPanel();
    });
  });
  wrap.querySelectorAll("[data-revoke-invite]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`/api/share/invites/${btn.dataset.revokeInvite}`, { method: "DELETE" });
      fillCeoPanel();
    });
  });
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
    <div><dt>Live Telegram</dt><dd>This OttoBot instance owns the bots. Reply in Telegram for that thread.</dd></div>
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

function clipWire(text, max) {
  const raw = redactSecrets(String(text || "")).replace(/\s+/g, " ").trim();
  if (raw.length <= max) return raw;
  return `${raw.slice(0, Math.max(0, max - 1))}…`;
}

function jobStoryTitle(job) {
  const title = String((job && job.title) || "").trim();
  if (title && !/^(auto|ops|cos|chat|code|think|research|builder)$/i.test(title)) return title;
  const engine = String((job && job.engine) || PRESET_ENGINE[(job && job.preset) || ""] || "").trim();
  if (engine && engine !== "board") return engine;
  const lane = jobLabel((job && job.preset) || "");
  if (lane && !/^(auto|ops|cos|chat)$/i.test(lane)) return lane;
  return "last job";
}

function ceoWire(project) {
  const pack = digestCache.get(project.id) || {};
  const counts = workCounts(project.id);
  const trust = scheduleTrustNowLine(counts, project);
  if (trust) return clipWire(trust, 64);
  const failed = (pack.crons || []).filter((row) => (
    cronIsFailed(row) && !cronIsGatewayFail(row) && !cronIsStaleFail(row)
  ));
  if (failed.length) {
    const title = failed[0].title || cronTitle(failed[0].name) || "job";
    if (failed.length === 1) {
      return `1 failed: ${clipWire(title, 28)} · Open Results`;
    }
    return `${failed.length} failed: ${clipWire(title, 24)} · Open Results`;
  }
  const now = cleanBotText(project.index_now || "").trim();
  const nxt = cleanBotText(project.index_next || "").trim();
  const blocker = cleanBotText(project.index_blocker || "").trim();
  const busy = lives.has(aimKey(project.id, ""));
  if (blocker && blocker !== "—") {
    const human = humanFailReason(blocker);
    if (/exited 130\b|cancelled/i.test(human) || /exited 130\b|\bsigint\b/i.test(blocker)) {
      /* cancelled is not a wall — fall through to Now / Next */
    } else if (/job id|cron job|run time/i.test(blocker)) {
      const countsLine = scheduleTrustNowLine(workCounts(project.id), project);
      return clipWire(countsLine || human || "Failed · Open Results", 64);
    } else {
      return `Blocked · ${clipWire(human || blocker, 42)}`;
    }
  }
  if (busy) {
    const line = now && now !== "—" && now !== "source of truth" ? now : "this chat";
    return `Running · ${clipWire(line, 42)}`;
  }
  // Known fails beat idle INDEX copy (Ready… / schedule fluff) once digest is ready.
  if (counts.ready && (counts.failed || 0) > 0) {
    return clipWire(`${counts.failed} failed — open Results`, 56);
  }
  let line = (now && now !== "source of truth" && now !== "—") ? now : ((nxt && nxt !== "—") ? nxt : "");
  line = honestWorkLine(line, counts) || line;
  if (!line && (counts.failed || 0) > 0) line = `${counts.failed} failed — open Results`;
  else if (!line && (counts.next || 0) > 0) line = `${counts.next} due · open Next`;
  if (line) return clipWire(line, 56);
  return "";
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

function needChoices(row) {
  if (Array.isArray(row && row.choices) && row.choices.length) return row.choices;
  const kind = row && row.kind;
  if (kind === "login") {
    const out = [];
    (row.logins || []).forEach((login) => {
      out.push({ id: "use_login", label: `Approve ${login.label || login.username || "saved login"}`, login_id: login.id });
    });
    out.push({ id: "logged_in", label: "I already logged in" });
    if (row.url) out.push({ id: "open_page", label: "Open page", url: row.url });
    out.push({ id: "open", label: "Type a login" });
    return out;
  }
  if (kind === "cookie_export") {
    return [
      { id: "allow_cookie_export", label: "Allow cookie export · Nadia vault only" },
      { id: "deny", label: "Deny" }
    ];
  }
  if (kind === "facebook_approval") {
    return [
      { id: "allow_facebook", label: "Approve Facebook · ListLogic vault only" },
      { id: "deny", label: "Deny" }
    ];
  }
  if (kind === "diff") return [{ id: "accept", label: "Accept" }, { id: "reject", label: "Reject" }, { id: "open", label: "See diff" }];
  if (kind === "gate") return [{ id: "allow", label: "Allow" }, { id: "deny", label: "Deny" }];
  if (kind === "expired") return [{ id: "dismiss", label: "Dismiss" }];
  if (kind === "continue") return [{ id: "continue", label: "Continue" }];
  if (kind === "brief") return [{ id: "open", label: "Open chat" }];
  if (kind === "failed") {
    return failChoices({
      id: row.cron_id || row.id || "",
      cron_id: row.cron_id || row.id || "",
      project_id: row.project_id || "",
      last_error: row.last_error || row.why || row.label || "",
      last_status: "error",
      name: row.subject || row.name || "",
      title: row.subject || row.name || ""
    });
  }
  return [{ id: "open", label: "Open" }];
}

function jobChoices(job) {
  if (!job) return [];
  if (job.login_wall) {
    const row = { kind: "login", url: job.url, logins: job.logins || [] };
    return needChoices(row);
  }
  if (job.diff_pending) return needChoices({ kind: "diff" });
  if (job.keep_going && !job.stopped && !job.cron && !jobIsFailed(job)) {
    const n = job.step_count && job.total_steps ? `Keep going (${job.step_count}/${job.total_steps})` : "Continue";
    return [{ id: "continue", label: n }];
  }
  const status = String(job.status || job.last_status || "").toLowerCase();
  const cronId = job.cron_id || "";
  const failed = jobIsFailed(job) || /error|fail/.test(status);
  if (job.cron || cronId) {
    if (failed) return failChoices(job);
    return [{ id: "schedule", label: "Open schedule", cron_id: cronId }];
  }
  if (failed && !isTalk(job)) return failChoices(job);
  return [];
}

function choiceButtonsHtml(choices, row) {
  return (choices || []).map((choice) => {
    const primary = choice.id === "accept" || choice.id === "allow" || choice.id === "use_login" || choice.id === "logged_in" || choice.id === "continue" || choice.id === "allow_cookie_export" || choice.id === "allow_facebook" || choice.id === "fix_model" || choice.id === "fix_key" || choice.id === "retry" || choice.id === "restore_script" || choice.id === "restart_gateway" || choice.id === "ask_cos";
    const danger = choice.id === "reject" || choice.id === "deny";
    return `<button type="button" class="${primary ? "send" : "ghost-btn"}${danger ? " danger" : ""}" data-need-act="${escapeHtml(choice.id)}" data-need-id="${escapeHtml(row.id || "")}" data-need-project="${escapeHtml(row.project_id || "")}" data-need-preset="${escapeHtml(row.preset || "")}" data-need-approval="${escapeHtml(row.approval_id || row.id || "")}" data-need-login="${escapeHtml(choice.login_id || "")}" data-need-url="${escapeHtml(choice.url || row.url || "")}" data-need-cron="${escapeHtml(choice.cron_id || row.cron_id || "")}">${escapeHtml(choice.label || choice.id)}</button>`;
  }).join("");
}

async function runNeedChoice(btn) {
  const act = btn.dataset.needAct || "";
  const id = btn.dataset.needId || "";
  const pid = btn.dataset.needProject || "";
  const presetLane = btn.dataset.needPreset || "";
  const approvalId = btn.dataset.needApproval || "";
  const loginId = btn.dataset.needLogin || "";
  const url = btn.dataset.needUrl || "";
  const cronId = btn.dataset.needCron || "";
  if (act === "open_page" && url) {
    window.open(url, "_blank", "noreferrer");
    return;
  }
  if (act === "open" || act === "schedule" || act === "open_detail") {
    if (pid) await setOrgNode(pid, "");
    if (presetLane && presetLane !== "cos") focusLane(presetLane);
    if (act === "schedule" || act === "open_detail") openSchedule(cronId || id || "");
    return;
  }
  if (act === "fix_model" || act === "fix_key") {
    markFailHandling(cronId || id, "fix_key");
    if (pid) await setOrgNode(pid, "");
    // Deep-link Settings → Keys / keyring (Engines wire lives on This CEO + Keys).
    // Do not re-open schedule — activity sheet must not swallow the keys drawer.
    setSettings(true, "keys");
    const keysPanel = $("panel-keys") || $("keyList") || $("saveKey");
    if (keysPanel && typeof keysPanel.scrollIntoView === "function") {
      requestAnimationFrame(() => keysPanel.scrollIntoView({ block: "start", behavior: "smooth" }));
    }
    paintWorkTabs();
    return;
  }
  if (act === "restart_gateway") {
    markFailHandling(cronId || id || "gateway", "restart_gateway");
    restartGateway();
    return;
  }
  if (act === "restore_script") {
    markFailHandling(cronId || id, "restore_script");
    if (pid) await setOrgNode(pid, "");
    sendMessage(
      "Restore the missing Hermes script for this failed job from bootstrap/<ceo>/scripts onto the live Hermes home scripts/. Do not invent a new script body — copy the bootstrap file. Then Retry the job once.",
      { preset: "ops" }
    );
    paintWorkTabs();
    openWork("doing", cronId || id || "");
    return;
  }
  if (act === "ask_cos") {
    markFailHandling(cronId || id, "ask_cos");
    const who = ceoMoveName(pid);
    const title = failJobTitle({ project_id: pid, id, cron_id: cronId }, cronId, id);
    const why = failAskWhy(pid, cronId || id);
    // Cos desk — never ride a live SAA Code/Think run, never send a hex job id.
    await setOrgNode("", "");
    if (typeof syncLiveFromAim === "function") syncLiveFromAim();
    focusLane("cos");
    sendMessage(
      `Ask Cos: ${who} is stuck on ${title}${why ? ` (${why})` : ""}. Judge the fail, pick Retry / Restore / Fix key / Restart gateway, or escalate to Adam only if money/secret/irreversible.`,
      { preset: "cos", forceNew: true }
    );
    paintWorkTabs();
    openWork("doing", cronId || id || "");
    return;
  }
  if (act === "dismiss") {
    inboxSeen.add(id);
    renderOrg(org);
    return;
  }
  if (act === "allow" || act === "deny" || act === "allow_cookie_export" || act === "allow_facebook") {
    const scoped = act === "allow_cookie_export" || act === "allow_facebook";
    if (scoped && act === "allow_cookie_export" && pid && pid !== "nadia") {
      if ($("orgStatus")) $("orgStatus").textContent = "Cookie export is Nadia-scoped only.";
      return;
    }
    if (scoped && act === "allow_facebook" && pid && pid !== "listlogic") {
      if ($("orgStatus")) $("orgStatus").textContent = "Facebook approval is ListLogic-scoped only.";
      return;
    }
    await fetch(`/api/approvals/${encodeURIComponent(approvalId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        accept: act !== "deny",
        scope: act === "allow_cookie_export" ? "cookie_export" : (act === "allow_facebook" ? "facebook" : ""),
        project_id: pid || ""
      })
    });
    // Never surface vault secrets into chat — consent stays on the card + vault.
    if (pid) await setOrgNode(pid, "");
    const data = await (await fetch("/api/config")).json();
    applyConfig(data);
    return;
  }
  if (act === "accept" || act === "reject") {
    await decide(id, act);
    return;
  }
  if (act === "use_login" && loginId) {
    const res = await fetch("/api/logins/use", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login_id: loginId, project_id: pid || null })
    });
    if (!res.ok) return;
    if (pid) await setOrgNode(pid, "");
    sendMessage(
      "Continue. An approved site login is in .openbot-logins.json in this Hermes home. Fill the page from that file. Never print the file or any password. If TOTP or CAPTCHA appears, stop with LOGIN_WALL.",
      { preset: presetLane && presetLane !== "cos" ? presetLane : "think", allowSecret: true }
    );
    return;
  }
  if (act === "logged_in") {
    if (pid) await setOrgNode(pid, "");
    sendMessage("Continue. I logged in on my screen.", { preset: presetLane && presetLane !== "cos" ? presetLane : "think", allowSecret: true });
    return;
  }
  if (act === "continue") {
    if (pid) await setOrgNode(pid, "");
    sendMessage("Continue from Last and Next on the brief.", presetLane && presetLane !== "cos" ? { preset: presetLane } : {});
    return;
  }
  if (act === "retry" && cronId && pid) {
    markFailHandling(cronId, "retry");
    await setOrgNode(pid, "");
    await fetch("/api/crons/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: pid, job_id: cronId })
    });
    await loadCeoDigest(true);
    paintWorkTabs();
    openWork("doing", cronId);
    return;
  }
  if (act === "retry") {
    markFailHandling(cronId || id, "retry");
    if (pid) await setOrgNode(pid, "");
    openWork("doing", cronId || id || "");
  }
}

function bindNeedActions(root) {
  if (!root) return;
  root.querySelectorAll("[data-need-act]").forEach((btn) => {
    if (btn.dataset.needBound) return;
    btn.dataset.needBound = "1";
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      runNeedChoice(btn);
    });
  });
  bindGatewayRestart(root);
  bindOpenDesk(root);
}

function bindOpenDesk(root) {
  if (!root) return;
  root.querySelectorAll("[data-open-desk]").forEach((btn) => {
    if (btn.dataset.deskBound) return;
    btn.dataset.deskBound = "1";
    btn.addEventListener("click", () => {
      const pid = btn.dataset.openDesk || "";
      setOrgNode(pid, "");
      scheduleView = "next";
      writeWorkState({ view: "next", open: true });
      openSchedule("");
    });
  });
}

function bindGatewayRestart(root) {
  const host = root || document;
  host.querySelectorAll(".gateway-restart, [data-restart-gateway]").forEach((btn) => {
    if (btn.dataset.restartBound) return;
    btn.dataset.restartBound = "1";
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      restartGateway();
    });
  });
}

async function refreshGatewayStatus() {
  const aim = currentAim();
  const pid = aim.projectId || projectId || "";
  if (!pid) return;
  try {
    const res = await Promise.race([
      fetch(`/api/hermes/gateway/status?project_id=${encodeURIComponent(pid)}`),
      new Promise((_, reject) => window.setTimeout(() => reject(new Error("gateway-status-timeout")), 2500))
    ]);
    const data = await res.json();
    gatewayRunning = data.running !== false;
  } catch (_err) {
    /* keep last */
  }
  syncHermesHint();
}

async function restartGateway() {
  const aim = currentAim();
  const retry = $("retryHermes");
  const healthBtn = $("ceoHealthRestartGw");
  if (retry) retry.textContent = "Restarting…";
  if (healthBtn) healthBtn.textContent = "Restarting…";
  let data = {};
  try {
    // force=true → stop + clear stale sock/state even when pid looks alive (post-redeploy 502).
    const res = await fetch("/api/hermes/gateway/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: aim.projectId || projectId || "",
        wait: false,
        force: true
      })
    });
    data = await res.json().catch(() => ({}));
    // Proxy HTML 502 should never be the Restart response — treat non-JSON as soft fail.
    if (!res.ok && !data.error) {
      data.error = res.status === 502
        ? "Gateway restart hit a proxy blip — cleared stale state; try Restart once more."
        : (data.text || data.error || `Restart failed (${res.status})`);
    }
    gatewayRunning = Boolean(data.running || data.ok);
    hermesFailed = !gatewayRunning;
    const note = gatewayRunning
      ? (data.cleared_stale_forced || (data.cleared_stale || []).length
        ? "Gateway up (stale state cleared)."
        : "")
      : (data.error || data.text || "Gateway still off — Next: Restart again or check Hermes home.");
    if ($("hermesStatus")) $("hermesStatus").textContent = note;
  } catch (_err) {
    gatewayRunning = false;
    hermesFailed = true;
    if ($("hermesStatus")) $("hermesStatus").textContent = "Restart failed — Next: try again in a few seconds.";
  }
  if (retry) retry.textContent = "Restart";
  if (healthBtn) healthBtn.textContent = "Restart Hermes gateway";
  syncHermesHint();
  hermesStarted = false;
  // Brief pad so dash proxy is not slammed while gateway is still binding.
  await new Promise((r) => setTimeout(r, gatewayRunning ? 400 : 900));
  startHermes();
  if (typeof loadCeoEngineHealth === "function" && aim.projectId) {
    loadCeoEngineHealth({ id: aim.projectId, name: aim.name || "" });
  }
  if (scheduleOpen) openSchedule(scheduleFocusId);
}

function visibleNeedsYou() {
  return (((cfg.activity || {}).needs_you) || []).filter((row) => {
    if (row.kind === "brief") return !inboxSeen.has(row.id);
    return true;
  });
}

function ceoHasFailedWork(pid) {
  if (!pid) return false;
  const counts = workCounts(pid);
  return (Number(counts.failed || 0) + Number(counts.trustFailed || 0)) > 0;
}

function anyCeoHasFailedWork() {
  return ((cfg.org && cfg.org.projects) || []).some((row) => row && row.id && ceoHasFailedWork(row.id));
}

function topDigestFailNeed(pid) {
  if (!pid) return null;
  const pack = digestCache.get(pid) || {};
  const failed = ((pack.crons || []).filter((row) => !cronIsNoise(row) && cronIsFailed(row))).slice().sort(ownershipSort);
  if (!failed.length) return null;
  const row = failed[0];
  const own = failOwnership(row);
  const who = ceoMoveName(pid);
  const title = row.title || cronTitle(row.name || row.id);
  return {
    id: `digest-fail-${pid}-${row.id || row.name || "job"}`,
    kind: "failed",
    name: who,
    subject: `${who} · ${title}`,
    why: own.why || own.outcome || "failed",
    project_id: pid,
    cron_id: row.id,
    last_error: failBlobOf(row),
    last_status: "error",
    last_result: row.last_result || ""
  };
}

function isE2eNeed(row) {
  const blob = [
    row && row.subject, row && row.why, row && row.path, row && row.title,
    row && row.file, row && row.id, row && row.diff
  ].join(" ");
  return typeof isE2ePing === "function" && isE2ePing(blob);
}

function adamMustSee(row) {
  if (isE2eNeed(row)) return false;
  const k = String((row && row.kind) || "");
  if (k === "login" || k === "cookie_export" || k === "facebook_approval" || k === "diff" || k === "gate") return true;
  if (k === "failed") {
    const blob = String((row && (row.last_error || row.why || row.last_result || "")) || "");
    const kind = typeof failKindFromBlob === "function" ? failKindFromBlob(blob) : "";
    return kind === "key" || kind === "wallet";
  }
  return false;
}

function adamRailChoice(row) {
  const choices = needChoices(row);
  const preferred = choices.filter((c) => c && !/^(open_page|open|see_diff)$/i.test(String(c.id || "")));
  return preferred[0] || choices[0] || null;
}

function adamNeedRank(row) {
  const k = String((row && row.kind) || "");
  if (k === "facebook_approval" || k === "login") return 0;
  if (k === "cookie_export") return 1;
  if (k === "key" || (k === "failed" && failKindFromBlob(row.last_error || row.why || "") === "key")) return 2;
  if (k === "wallet") return 3;
  if (k === "gate") return 4;
  if (k === "diff") return 5;
  return 9;
}

function operatorMoveRows() {
  const filtered = visibleNeedsYou()
    .filter((row) => {
      if (row.kind === "continue" || row.kind === "brief") return false;
      if (isE2eNeed(row)) return false;
      if (!row.project_id && row.kind === "failed" && anyCeoHasFailedWork()) return false;
      return adamMustSee(row);
    })
    .map((row) => {
      const who = prettyCeoName(row.project_id, (row.name && row.name !== "this CEO") ? row.name : ceoMoveName(row.project_id));
      const subject = String(row.subject || "").replace(/^this CEO\b/i, who) || `${who} · ${row.why || row.kind || "Decide"}`;
      return Object.assign({}, row, { name: who, subject });
    });
  const haveFail = new Set(filtered.filter((row) => row.kind === "failed").map((row) => String(row.project_id || "")));
  const extra = [];
  const pids = [];
  if (projectId) pids.push(projectId);
  ((cfg.org && cfg.org.projects) || []).forEach((row) => {
    if (row && row.id && pids.indexOf(row.id) < 0) pids.push(row.id);
  });
  pids.forEach((pid) => {
    if (haveFail.has(String(pid))) return;
    if (!ceoHasFailedWork(pid)) return;
    const need = topDigestFailNeed(pid);
    if (need && adamMustSee(need)) extra.push(need);
  });
  return filtered.concat(extra).sort((a, b) => adamNeedRank(a) - adamNeedRank(b)).slice(0, 1);
}

function moveHeadLabel(rows) {
  const names = [...new Set((rows || []).map((row) => row.name || ceoMoveName(row.project_id)))].filter(Boolean);
  if (names.length === 1) return `Your move · ${names[0]}`;
  if (names.length > 1) return `Your move · ${names.length} CEOs`;
  return "Your move";
}

function inboxHtml() {
  const rows = operatorMoveRows();
  if (!rows.length) return "";
  const row = rows[0];
  const who = row.name || ceoMoveName(row.project_id);
  const why = clipWire(row.why || row.label || "Needs you", 72);
  const choice = adamRailChoice(row);
  const acts = choice
    ? `<div class="org-inbox-actions need-actions">${choiceButtonsHtml([choice], row)}</div>`
    : "";
  return `<div class="org-inbox adam">
    <div class="org-inbox-head">Your move</div>
    <div class="org-inbox-item" data-inbox="${escapeHtml(row.id)}" data-kind="${escapeHtml(row.kind || "")}" data-project="${escapeHtml(row.project_id || "")}">
      <b>${escapeHtml(who)}</b>
      <span>${escapeHtml(why)}</span>
      ${acts}
    </div>
  </div>`;
}

function handlingInboxHtml() {
  return "";
}

function paintHelpPanel() {
  const host = $("helpWorkingOn");
  if (!host) return;
  const work = (cfg.activity || {}).working_on || {};
  const open = work.open || [];
  const chip = (cfg.activity || {}).eval || {};
  const expired = Number(chip.expired_approvals || 0);
  const needs = operatorMoveRows();
  const ticketItems = open.map((row) => {
    const phase = escapeHtml(row.phase || "received");
    return `<div class="org-inbox-item">
      <b>${escapeHtml(row.title || row.id || "ticket")}</b>
      <span class="phase-chip">${phase}${row.engine ? " · " + escapeHtml(row.engine) : ""}</span>
      <span>${escapeHtml(row.now || row.next || "")}</span>
    </div>`;
  }).join("");
  const needItems = needs.map((row) => {
    const subject = row.subject || row.name || "CEO";
    const why = row.why || row.label || "";
    return `<div class="org-inbox-item ping" data-inbox="${escapeHtml(row.id)}" data-kind="${escapeHtml(row.kind || "")}" data-project="${escapeHtml(row.project_id || "")}">
      <b>${escapeHtml(subject)}</b>
      <span>${escapeHtml(why)}</span>
      <div class="org-inbox-actions need-actions">
        ${choiceButtonsHtml(needChoices(row).slice(0, 2), row)}
      </div>
    </div>`;
  }).join("");
  // Inbox mirrors needs_you rows — never claim empty while Results NEED.
  const body = needItems || ticketItems
    || `<p class="org-inbox-empty">No open tickets.</p>`;
  const warn = expired ? `<p class="org-inbox-empty">Expired approvals: ${expired} (did not auto-approve)</p>` : "";
  const headCount = open.length;
  host.innerHTML = `
    <div class="org-inbox working-on">
      <div class="org-inbox-head">${open.length ? `Tickets · ${open.length}` : (needs.length ? `${escapeHtml(moveHeadLabel(needs))} · ${needs.length}` : "Working on · 0")}</div>
      ${body}
      ${warn}
    </div>`;
  const helpChip = $("helpChip");
  if (helpChip) helpChip.textContent = headCount ? `· ${headCount}` : "";
  bindNeedActions(host);
}

function capNoticesHtml() {
  const notices = ((cfg.activity || {}).cap_notices) || [];
  if (!notices.length) return "";
  
  const items = notices.map((notice) => {
    const badge = notice.level === "cap_exceeded" ? "🔴" : "⚠️";
    const className = notice.level === "cap_exceeded" ? "cap-notice-error" : "cap-notice-warning";
    return `<div class="org-cap-notice ${className}">
      <span class="cap-notice-badge">${badge}</span>
      <span>${escapeHtml(notice.message)}</span>
    </div>`;
  }).join("");
  
  return `<div class="org-cap-notices">
    <div class="org-inbox-head">Spend Alerts</div>
    ${items}
  </div>`;
}

function projectNeedsYou(pid) {
  return (((cfg.activity || {}).needs_you) || []).some((row) => {
    if (String(row.project_id || "") !== String(pid || "")) return false;
    if (row.kind === "brief") return !inboxSeen.has(row.id);
    return true;
  });
}

function paintOrgSelection() {
  document.querySelectorAll(".org-btn").forEach((btn) => {
    const on = (btn.dataset.project || "") === projectId && (btn.dataset.worker || "") === workerId;
    btn.classList.toggle("on", on);
  });
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

  let queueData = { queue_status: [], active_workers: [], total_queued: 0 };
  let spendAlerts = { alerts: [] };

  Promise.all([
    fetch("/api/queue/status").then((r) => r.json()).catch(() => queueData),
    fetch("/api/spend/dashboard").then((r) => r.json()).catch(() => ({ alerts: { alerts: [] } }))
  ]).then(([qData, sData]) => {
    queueData = qData;
    spendAlerts = sData.alerts || { alerts: [] };
    renderOrgWithQueue(org, queueData, spendAlerts);
  }).catch(() => {
    renderOrgWithQueue(org, queueData, spendAlerts);
  });
}

function renderOrgWithQueue(org, queueData, spendAlerts) {
  const tree = $("orgTree");
  if (!tree) return;
  const projects = org.projects || [];
  const queueByProject = new Map();
  const alertsByCeo = new Map();
  
  // Index spend alerts by CEO id
  spendAlerts = spendAlerts || { alerts: [] };
  for (const alert of (spendAlerts.alerts || [])) {
    const ceoId = alert.ceo_id;
    if (!alertsByCeo.has(ceoId)) alertsByCeo.set(ceoId, []);
    alertsByCeo.get(ceoId).push(alert);
  }
  
  // Index queue data by project_id
  for (const q of queueData.queue_status || []) {
    queueByProject.set(q.project_id || "_staff", q.queued_count || 0);
  }
  
  // Count active workers per project (from lives map)
  const activeByProject = new Map();
  for (const [key, live] of lives.entries()) {
    const parts = key.split("::");
    const pid = parts[0] || "_staff";
    activeByProject.set(pid, (activeByProject.get(pid) || 0) + 1);
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
    const initials = ceoInitials(prettyCeoName(project.id, project.name));
    const hasBlocker = (project.index_blocker || "").trim() && (project.index_blocker || "").trim() !== "—";
    const queuedCount = queueByProject.get(project.id) || 0;
    const activeCount = activeByProject.get(project.id) || 0;
    const ceoAlerts = alertsByCeo.get(project.id) || [];
    
    // Show queue chip if queued, or active workers chip if running, or spend alert
    let statusChip = "";
    if (activeCount > 0) {
      statusChip = `<span class="active-chip" title="${activeCount} worker(s) running">▸ ${activeCount}</span>`;
    } else if (queuedCount > 0) {
      statusChip = `<span class="queue-chip" title="${queuedCount} task(s) queued">${queuedCount}</span>`;
    }
    
    // Add spend alert badge
    if (ceoAlerts.length > 0) {
      const alert = ceoAlerts[0];
      const badge = alert.level === "cap_exceeded" ? "🔴" : "⚠️";
      const className = alert.level === "cap_exceeded" ? "spend-alert-badge-error" : "spend-alert-badge-warning";
      statusChip += ` <span class="${className}" title="${escapeHtml(alert.message)}">${badge}</span>`;
    }
    
    return `
      <div class="org-project${open ? " open" : ""}" data-project-wrap="${escapeHtml(project.id)}">
        <div class="org-row">
          <button type="button" class="org-twist" data-toggle="${escapeHtml(project.id)}" aria-label="${open ? "Collapse" : "Expand"} ${escapeHtml(prettyCeoName(project.id, project.name))}">${open ? "▾" : "▸"}</button>
          <button type="button" class="org-btn${projectId === project.id && !workerId ? " on" : ""}${ping}${busy ? " working" : ""}${hasBlocker ? " has-blocker" : ""}" data-project="${escapeHtml(project.id)}" data-worker="" data-kind="ceo" title="${escapeHtml(prettyCeoName(project.id, project.name))}${busy ? " · working" : ""}">
            <span class="org-avatar" data-life="${busy ? "working" : (hasBlocker || projectNeedsYou(project.id) ? "blocked" : "idle")}" aria-hidden="true">${escapeHtml(initials)}</span>
            <span class="org-btn-text">
              <b>${escapeHtml(prettyCeoName(project.id, project.name))}${statusChip}</b>
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
  const staffActiveCount = activeByProject.get("_staff") || 0;
  
  // Show active or queue chip for staff
  let staffStatusChip = "";
  if (staffActiveCount > 0) {
    staffStatusChip = `<span class="active-chip" title="${staffActiveCount} worker(s) running">▸ ${staffActiveCount}</span>`;
  } else if (staffQueuedCount > 0) {
    staffStatusChip = `<span class="queue-chip" title="${staffQueuedCount} task(s) queued">${staffQueuedCount}</span>`;
  }
  
  tree.innerHTML = `
    ${isCollaborator() ? `<p class="share-banner">Shared with you by ${escapeHtml((cfg.share && cfg.share.owner_name) || "the owner")} · you are a collaborator</p>` : `<button type="button" class="org-btn org-staff${!projectId ? " on" : ""}${staffBusy ? " ping working" : ""}" data-project="" data-worker="" data-kind="staff" title="Chief of Staff${staffBusy ? " · working" : ""}">
      <span class="org-avatar" data-life="${staffBusy ? "working" : "idle"}" aria-hidden="true">${escapeHtml(cosInitials)}</span>
      <span class="org-btn-text">
        <b>Chief of Staff${staffStatusChip}</b>
        <span class="org-now">runs the CEOs</span>
      </span>
    </button>`}
    ${inboxHtml()}
    ${capNoticesHtml()}
    ${projectBits}
  `;
  tree.querySelectorAll(".org-btn").forEach((btn) => {
    btn.addEventListener("click", () => setOrgNode(btn.dataset.project || "", btn.dataset.worker || ""));
    bindNodeMenu(btn, btn.dataset.kind, btn.dataset.project || "", btn.dataset.worker || "");
  });
  bindNeedActions(tree);
  bindOpenDesk(tree);
  paintAddCeoControls();
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

function openAddCeoMenu(event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }
  setOrgNode("", "");
  showNodeMenu(0, 0, "add-ceo", "", "");
}

function paintAddCeoControls() {
  const slot = $("orgAddCeoSlot");
  if (slot) {
    if (canAddCeo()) {
      slot.innerHTML = `<button type="button" class="org-add" id="addCeoBtn">Add CEO</button>`;
      const addCeo = $("addCeoBtn");
      if (addCeo) addCeo.addEventListener("click", openAddCeoMenu);
    } else {
      slot.innerHTML = "";
    }
  }
  const settingsRow = $("addCeoSettingsRow");
  if (settingsRow) settingsRow.classList.toggle("hidden", !canAddCeo());
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

function renderBotMeta(opts) {
  const text = selectedIndexText();
  const cleaned = cleanBotText(text);
  if ($("indexCard")) $("indexCard").textContent = cleaned || "(empty)";
  const worker = currentWorker();
  const project = currentProject();
  const label = worker ? `${worker.name} brief` : project ? `${project.name} brief` : "Chief of Staff brief";
  if ($("indexSummary")) {
    $("indexSummary").textContent = `${label} · ${briefHonestyLine(cleaned)}`;
  }
  if ($("chatWhere")) $("chatWhere").textContent = whereLabel();
  if ($("chatFolder")) {
    if (!project) {
      $("chatFolder").textContent = "One chat. Cos routes. Open a CEO in the rail for that desk.";
    } else {
      const nxt = honestIndexNext(String(project.index_next || "").trim());
      const now = String(project.index_now || "").trim();
      const counts = workCounts();
      let ask = (nxt && nxt !== "—") ? nxt : ((now && now !== "—") ? now : "");
      ask = honestWorkLine(ask, counts) || ask;
      const trustAsk = scheduleTrustNowLine(counts, project);
      if (trustAsk && (!ask || isScheduleFluff(ask))) ask = trustAsk;
      if (!ask && trustAsk) ask = trustAsk;
      if (!ask && (counts.failed || 0) > 0) ask = `${counts.failed} failed — open Results`;
      else if (!ask && (counts.next || 0) > 0) ask = `${counts.next} due · open Next`;
      $("chatFolder").textContent = ask || "This CEO is idle.";
    }
  }
  const folder = currentAim().folder || "";
  if ($("folder")) $("folder").value = folder;
  syncComposerWho();
  paintLanes();
  renderSchedules(project);
  paintScheduleButton();
  const cachedPack = digestCache.get(projectId) || {};
  paintCeoBrief(cachedPack.digest || cachedPack);
  paintWorkStatus();
  paintCeoLive(cachedPack);
  if (!opts || !opts.skipSpend) loadSpend();
}

function renderSchedules(project) {
  const el = $("scheduleList");
  if (!el) return;
  el.hidden = true;
  el.innerHTML = "";
}

let scheduleOpen = false;
let scheduleFocusId = "";
let scheduleView = "doing";
let lastSchedulePid = "";
const digestKnown = new Set(); // projectIds whose cron digest finished loading

function workStateKey() {
  return `ob-work:${projectId || "cos"}`;
}

function readWorkState() {
  try {
    return JSON.parse(sessionStorage.getItem(workStateKey()) || "{}") || {};
  } catch (_err) {
    return {};
  }
}

function writeWorkState(patch) {
  sessionStorage.setItem(workStateKey(), JSON.stringify(Object.assign({}, readWorkState(), patch || {})));
}

function rememberWorkFolds(root) {
  if (!root) return;
  const folds = {};
  root.querySelectorAll("details[data-fold]").forEach((el) => {
    const id = el.getAttribute("data-fold");
    if (id && el.open) folds[id] = true;
  });
  writeWorkState({ folds });
}

function restoreWorkFolds(root) {
  if (!root) return;
  const folds = readWorkState().folds || {};
  root.querySelectorAll("details[data-fold]").forEach((el) => {
    const id = el.getAttribute("data-fold");
    if (id && folds[id]) el.open = true;
  });
}

function bindWorkFolds(root) {
  if (!root) return;
  restoreWorkFolds(root);
  if (root.dataset.foldBound) return;
  root.dataset.foldBound = "1";
  root.addEventListener("toggle", (event) => {
    const target = event.target;
    if (target && target.matches && target.matches("details[data-fold]")) rememberWorkFolds(root);
  }, true);
}

function activityBody() {
  return $("activityBody") || $("chatSchedule");
}

function paintActivityTitle() {
  const el = $("activityTitle");
  if (!el) return;
  el.textContent = scheduleView === "next" ? "Next"
    : (scheduleView === "results" ? "Results"
      : (scheduleView === "schedule" ? "Schedule" : "Doing"));
}

function applySavedWork() {
  const saved = readWorkState();
  if (saved.view) scheduleView = saved.view;
  return Boolean(saved.open);
}

function cronTitle(name) {
  const map = {
    "form-pipeline-health": "Site and form check",
    "conversion-surge": "Conversion fixes",
    "monthly-market-blog": "Monthly market blog",
    "geo-citation-audit": "Citation audit",
    "indexation-patrol": "Indexation patrol",
    "daily-ranking-strike": "Daily rankings",
    "competitor-content-watch": "Competitor watch",
    "daily-done-digest": "Daily wrap-up",
    "seo-execute-queue": "SEO fix queue",
    "gbp-local-pack-audit": "Google Business Profile",
    "saved-search-alerts": "Saved search alerts",
    "saved-search-alerts-immediate": "Saved search alerts"
  };
  const raw = String(name || "").trim();
  if (map[raw]) return map[raw];
  return raw.replace(/[-_]+/g, " ").replace(/^\w/, (ch) => ch.toUpperCase()) || "Scheduled check";
}

function cronWhen(value) {
  const raw = String(value || "").trim();
  if (!raw) return "not yet";
  const stamp = new Date(raw);
  if (Number.isNaN(stamp.getTime())) return raw.slice(0, 16);
  const ms = Date.now() - stamp.getTime();
  if (ms < 36e5) return "in the last hour";
  if (ms < 864e5) return "today";
  if (ms < 1728e5) return "yesterday";
  return stamp.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function cronWhenNext(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const stamp = new Date(raw);
  if (Number.isNaN(stamp.getTime())) return "";
  const ms = stamp.getTime() - Date.now();
  if (ms >= -20 * 60 * 1000 && ms <= 30 * 60 * 1000) return "due now";
  if (ms < 0 && ms > -36e5) return "a bit late";
  if (ms < 0) return "";
  if (ms < 36e5) return `in ${Math.max(1, Math.round(ms / 60000))} min`;
  return stamp.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function cronWhenClock(value) {
  const raw = String(value || "").trim();
  if (!raw) return "unscheduled";
  const stamp = new Date(raw);
  if (Number.isNaN(stamp.getTime())) return raw.slice(0, 16);
  const due = cronWhenNext(raw);
  if (due) return due;
  return stamp.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function paintScheduleButton() {
  paintWorkTabs();
  const btn = $("openSchedule");
  if (btn) btn.hidden = true;
}

function ceoShortName(project) {
  const pretty = prettyCeoName(project && project.id, project && project.name);
  const raw = String(pretty || "").trim();
  if (!raw) return "CEO";
  if (/^saa(\b|$|[\s-])/i.test(raw) || /saa.?homes/i.test(raw)) return "SAA";
  const words = raw.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 12);
  return words.map((w) => w[0]).join("").slice(0, 6).toUpperCase() || "CEO";
}

function cronIsPaused(row) {
  return !row || row.enabled === false || /paused/i.test(String(row.state || ""));
}

function cronIsNeverRun(row) {
  if (!row || cronIsPaused(row) || cronIsLive(row)) return false;
  return !String(row.last_run_at || "").trim();
}

function cronIsOverdue(row) {
  if (!row || cronIsPaused(row) || cronIsLive(row)) return false;
  const raw = String(row.next_run_at || "").trim();
  if (!raw) return false;
  const stamp = new Date(raw);
  if (Number.isNaN(stamp.getTime())) return false;
  return stamp.getTime() < Date.now() - 5 * 60 * 1000;
}

function cronRosterStatus(row) {
  if (cronIsPaused(row)) return "off";
  if (cronIsLive(row)) return "run";
  if (cronIsFailed(row) || /error|fail/i.test(String(row.last_status || ""))) return "fail";
  if (cronIsNeverRun(row)) return "never";
  if (cronIsOverdue(row)) return "late";
  if (String(row.last_status || "").toLowerCase() === "ok") return "ok";
  return String(row.last_status || "").trim() ? String(row.last_status || "").toLowerCase().slice(0, 8) : "ok";
}

function prefersScheduleTrust(counts) {
  if (!counts || !counts.ready) return false;
  const trust = (counts.trustFailed || 0) + (counts.never || 0);
  if (trust > 0) return true;
  const overdue = counts.overdue || 0;
  if (overdue >= 3 && overdue >= (counts.next || 0)) return true;
  return false;
}

function scheduleTrustNowLine(counts, project) {
  if (!counts || !counts.ready) return "";
  if (!prefersScheduleTrust(counts)) return "";
  const who = ceoShortName(project || currentProject());
  const failed = counts.trustFailed || 0;
  const never = counts.never || 0;
  const handling = counts.handling || 0;
  const waitingCos = counts.waitingCos || 0;
  // Movement verbs when CEO/Cos actively handling — else keep #100 trust counts.
  if ((handling > 0 || waitingCos > 0) && (failed > 0 || never > 0)) {
    const bits = [];
    if (handling) bits.push(`Handling ${handling}`);
    if (waitingCos) bits.push(`Waiting Cos ${waitingCos}`);
    return `${who} · ${bits.join(" · ")} · Open Schedule`;
  }
  if (failed > 0 || never > 0) {
    return `${who} · ${failed} failed · ${never} never · Open Schedule`;
  }
  if ((counts.overdue || 0) > 0) {
    return `${who} · ${counts.overdue} overdue · Open Schedule`;
  }
  return "";
}

function scheduleRosterSort(a, b) {
  const rank = (row) => {
    const st = cronRosterStatus(row);
    if (st === "fail") return 0;
    if (st === "late") return 1;
    if (st === "never") return 2;
    if (st === "run") return 3;
    return 4;
  };
  const d = rank(a) - rank(b);
  if (d) return d;
  return String(a.next_run_at || "").localeCompare(String(b.next_run_at || ""));
}

function rosterPrimaryChoice(row) {
  const status = cronRosterStatus(row);
  if (status === "never") {
    return { id: "retry", label: "Run once", cron_id: row.id || "" };
  }
  if (status === "fail") {
    const list = failChoices(row);
    return list[0] || null;
  }
  return null;
}

function scheduleRosterRowHtml(row, want) {
  const title = row.title || cronTitle(row.name || row.id);
  const status = cronRosterStatus(row);
  const enabled = cronIsPaused(row) ? "off" : "on";
  const next = cronIsNeverRun(row) && !row.next_run_at
    ? "—"
    : (cronWhenClock(row.next_run_at) || "—");
  const last = cronIsNeverRun(row)
    ? "never"
    : (row.last_run_at ? (cronFreshness(row) || cronWhen(row.last_run_at)) : "—");
  const own = status === "fail" ? failOwnership(row) : null;
  const headStatus = own ? own.status : status;
  const primary = rosterPrimaryChoice(row);
  // Collapsed glance: one CTA inside <summary>. Expanded body is Outcome/Why/Next only — no button dump.
  const primaryCta = primary
    ? `<span class="cron-roster-cta need-actions">${choiceButtonsHtml([primary], { id: row.id || "", project_id: projectId || "", cron_id: row.id || "", kind: status === "fail" ? "failed" : "run" })}</span>`
    : "";
  const failBit = own
    ? `<p class="cron-outcome"><span class="cron-k">Outcome</span> ${escapeHtml(own.outcome)}</p>
       <p class="cron-why"><span class="cron-k">Why</span> ${escapeHtml(own.why)}</p>
       <p class="cron-next"><span class="cron-k">Next</span> ${escapeHtml(own.next)}</p>
       <p class="cron-status"><span class="cron-k">Status</span> ${escapeHtml(own.status)}</p>`
    : "";
  const glance = own
    ? `<p class="cron-roster-glance"><span>${escapeHtml(own.status)}</span> · ${escapeHtml(own.next)}</p>`
    : "";
  const open = String(row.id || "") === String(want || "");
  return `<details class="cron-card schedule-roster${status === "fail" ? " failed" : ""}${status === "late" ? " late" : ""}${status === "never" ? " never" : ""}" id="cron-${escapeHtml(row.id || "")}" data-fold="sched-${escapeHtml(row.id || row.name || "job")}"${open ? " open" : ""}>
    <summary class="cron-head">
      <b>${escapeHtml(title)}</b>
      <span>${escapeHtml(headStatus)}</span>
      ${primaryCta}
    </summary>
    ${glance}
    <p class="cron-meta schedule-row"><span>enabled</span><b>${escapeHtml(enabled)}</b></p>
    <p class="cron-meta schedule-row"><span>Next</span><b>${escapeHtml(next)}</b></p>
    <p class="cron-meta schedule-row"><span>Last</span><b>${escapeHtml(last)}</b></p>
    <p class="cron-meta schedule-row"><span>Status</span><b>${escapeHtml(headStatus)}</b></p>
    ${failBit}
  </details>`;
}

function workCounts(forProjectId) {
  const aim = (forProjectId === undefined) ? projectId : forProjectId;
  const pack = digestCache.get(aim) || {};
  const all = pack.crons || [];
  const list = all.filter((row) => !cronIsNoise(row));
  const boardRuns = ((pack.live_runs || (cfg.activity || {}).live_runs) || []).filter((row) => (
    !aim || String(row.project_id || "") === String(aim)
  ));
  const liveChats = [...lives.keys()].filter((key) => {
    if (!aim) return true;
    return String(key || "").startsWith(`${aim}::`);
  }).length;
  const doing = list.filter((row) => cronIsLive(row)).length
    + boardRuns.length
    + liveChats
    + ((liveRunId && aim === projectId && !liveChats) ? 1 : 0);
  const failed = list.filter((row) => cronIsFailed(row));
  const gateway = failed.filter((row) => cronIsGatewayFail(row));
  const freshFail = failed.filter((row) => !cronIsGatewayFail(row) && !cronIsStaleFail(row));
  // Action queue honesty: count ALL ownership fails (fresh + older), matching Schedule failed set.
  const actionFails = failed.slice();
  const done = list.filter((row) => String(row.last_status || "").toLowerCase() === "ok" && row.last_run_at && !cronIsLive(row));
  // Results badge = recover loop + recent resolved — not Done-only lie.
  const recoverN = actionFails.length;
  const results = recoverN > 0
    ? recoverN + Math.min(done.length, 4)
    : Math.min(done.length, 8);
  const dueSoon = list.filter((row) => (
    row.enabled !== false && !/paused/i.test(String(row.state || "")) && !cronIsLive(row) && !cronIsFailed(row) && cronIsDueSoon(row)
  )).length;
  // Next = ownership action queue when fails exist; else due dump.
  const next = actionFails.length > 0 ? actionFails.length : dueSoon;
  let handling = 0;
  let waitingCos = 0;
  actionFails.forEach((row) => {
    const st = failOwnership(row).status;
    if (st === "Handling") handling += 1;
    if (st === "Waiting Cos") waitingCos += 1;
  });
  // Live schedule trust — operator jobs only (grok/alerts are Board internals, not SEO overdue).
  const enabledRows = list.filter((row) => !cronIsPaused(row));
  const disabledRows = list.filter((row) => cronIsPaused(row));
  const trustFailed = list.filter((row) => /error|fail/i.test(String(row.last_status || "")));
  const never = enabledRows.filter((row) => cronIsNeverRun(row));
  const overdue = enabledRows.filter((row) => cronIsOverdue(row));
  if (!aim) {
    const projects = ((cfg.org && cfg.org.projects) || []);
    const orgNext = projects.filter((row) => String(row.index_next || "").trim() && String(row.index_next || "").trim() !== "—").length;
    const jobs = (((cfg.activity || {}).jobs) || []);
    const orgFailed = jobs.filter((row) => jobIsFailed(row)).length;
    const orgLive = (((cfg.activity || {}).live_runs) || []).length + lives.size;
    const orgJobs = (((cfg.activity || {}).jobs) || []);
    const orgFailRows = orgJobs.filter((row) => jobIsFailed(row));
    let orgHandling = 0;
    let orgWaiting = 0;
    orgFailRows.forEach((row) => {
      const st = failOwnership(row).status;
      if (st === "Handling") orgHandling += 1;
      if (st === "Waiting Cos") orgWaiting += 1;
    });
    const orgAction = orgFailRows.length;
    return {
      doing: orgLive + orgHandling,
      next: orgAction > 0 ? orgAction : orgNext,
      results: orgAction > 0 ? orgAction + Math.min(orgJobs.length, 4) : Math.min(jobs.length, 12),
      failed: orgFailed,
      trustFailed: orgFailed,
      handling: orgHandling,
      waitingCos: orgWaiting,
      never: 0,
      overdue: 0,
      enabled: 0,
      disabled: 0,
      total: 0,
      schedule: 0,
      ready: Boolean(cfg.activity)
    };
  }
  return {
    doing: doing + handling,
    next,
    results,
    failed: actionFails.length,
    trustFailed: trustFailed.length,
    handling,
    waitingCos,
    never: never.length,
    overdue: overdue.length,
    enabled: enabledRows.length,
    disabled: disabledRows.length,
    total: all.length,
    schedule: enabledRows.length,
    // Ready only after a finished digest fetch — avoids 0→N flash on CEO switch.
    ready: digestKnown.has(aim)
  };
}

function paintWorkTabs() {
  const counts = workCounts();
  document.querySelectorAll(".work-tabs").forEach((tabs) => {
    tabs.hidden = false;
    tabs.querySelectorAll(".work-tab").forEach((btn) => {
      const view = btn.getAttribute("data-work") || "";
      const n = counts[view] || 0;
      const label = view === "doing" ? "Doing"
        : (view === "next" ? "Next"
          : (view === "schedule" ? "Schedule" : "Results"));
      btn.classList.toggle("on", scheduleOpen && scheduleView === view);
      btn.classList.toggle("hot", view === "doing" && n > 0);
      const scheduleNeed = prefersScheduleTrust(counts);
      btn.classList.toggle("need", (view === "results" && (counts.failed || 0) > 0)
        || (view === "next" && (counts.failed || 0) > 0)
        || (view === "doing" && ((counts.handling || 0) > 0 || (counts.waitingCos || 0) > 0))
        || (view === "schedule" && scheduleNeed));
      // Never flash a hollow "0" as if work is counted — blank until known, digit only when > 0.
      const badge = n > 0
        ? `<span class="n">${n}</span>`
        : (counts.ready ? "" : `<span class="n muted" title="Checking…">·</span>`);
      btn.innerHTML = `${label}${badge}`;
    });
  });
  paintEmbedLive();
  paintWorkStatus();
}

function cronClaimAt(row) {
  const claim = row && row.fire_claim;
  const raw = claim && claim.at;
  const ms = Date.parse(String(raw || ""));
  return Number.isFinite(ms) ? ms : 0;
}

function cronIsNoise(row) {
  const name = String((row && (row.name || row.id || row.title)) || "").trim();
  if (!name) return false;
  const slug = name.replace(/\s+/g, "-").toLowerCase();
  return /^(grok-heartbeat|grok-build-supervisor|grok-build-driver|grok-finish-notify|alerts-email-outbox)$/i.test(slug);
}

function cronNextUseful(next) {
  const raw = String(next || "").trim();
  if (!raw) return false;
  if (/no action/i.test(raw)) return false;
  if (/read the note below/i.test(raw)) return false;
  if (/retry this job on the live box/i.test(raw)) return false;
  if (/do not fire the whole set/i.test(raw)) return false;
  return true;
}

function cronSkipRetry(row) {
  return /^(conversion-surge|competitor-content-watch|city-audit-batch-4)$/i.test(String(row.name || ""));
}

const CLAIM_FRESH_MS = 25 * 60 * 1000;

function cronClaimFresh(row) {
  const at = cronClaimAt(row);
  if (!at) return false;
  return (Date.now() - at) < CLAIM_FRESH_MS;
}

function cronIsDueSoon(row) {
  const raw = String((row && row.next_run_at) || "").trim();
  if (!raw) return false;
  const stamp = new Date(raw);
  if (Number.isNaN(stamp.getTime())) return false;
  const ms = stamp.getTime() - Date.now();
  return ms <= 24 * 36e5 && ms > -2 * 36e5;
}

function isScheduleFluff(line) {
  const raw = String(line || "").trim();
  if (!raw || raw === "—") return false;
  if (/^On schedule\b/i.test(raw)) return true;
  if (/attach a schedule/i.test(raw)) return true;
  if (/Ops asked Hermes to attach/i.test(raw)) return true;
  // Idle INDEX copy must not beat real failed/due counts in the rail (#96 soft note).
  if (/^Ready\b/i.test(raw)) return true;
  if (/^Ready when you are/i.test(raw)) return true;
  if (/on this Railway board/i.test(raw)) return true;
  if (/^Idle\b/i.test(raw)) return true;
  if (/^Your move\b/i.test(raw)) return true;
  if (/Continue from Last/i.test(raw)) return true;
  if (/Retry or Ask Cos/i.test(raw)) return true;
  return false;
}

function honestWorkLine(line, counts) {
  const failed = (counts && counts.failed) || 0;
  const next = (counts && counts.next) || 0;
  const raw = String(line || "").trim();
  const trust = scheduleTrustNowLine(counts, currentProject());
  if (trust && (!raw || raw === "—" || isScheduleFluff(raw) || /open Results/i.test(raw) || /^Your move\b/i.test(raw) || /Continue from Last/i.test(raw))) {
    return trust;
  }
  if (failed > 0 && (!raw || raw === "—" || isScheduleFluff(raw))) {
    return prefersScheduleTrust(counts)
      ? (trust || `${failed} failed — open Schedule`)
      : `${failed} failed — open Results`;
  }
  if (next > 0 && isScheduleFluff(raw)) {
    return `${next} due · open Next`;
  }
  return raw;
}

function jobIsFailed(row) {
  if (!row) return false;
  if (row.stopped) return false;
  const blob = `${row.blocker || ""} ${row.text || ""} ${row.status || ""} ${row.last_error || ""}`;
  if (/exited 130\b|\bsigint\b/i.test(blob)) return false;
  const status = String(row.status || row.last_status || "").trim();
  if (/^(ok|success|done|running|live|progress)$/i.test(status)) return false;
  if (/fail|error/i.test(status)) return true;
  const body = [
    row.outcome, row.cron_outcome, row.text, row.summary, row.error, row.last_error
  ].map((x) => String(x || "")).join(" ");
  return /fail|error|traceback|exception/i.test(body);
}

function cronIsFailed(row) {
  if (!row || cronIsNoise(row) || cronIsLive(row)) return false;
  if (row.enabled === false) return false;
  return /error|fail/i.test(String(row.last_status || ""));
}

function cronFailBlob(row) {
  if (!row) return "";
  return `${row.last_error || ""} ${row.outcome || ""} ${row.last_result || ""} ${row.last_status || ""}`;
}

function cronIsGatewayFail(row) {
  return /gateway shutdown|gateway stopped mid-run/i.test(cronFailBlob(row));
}

function cronIsStaleFail(row) {
  const at = Date.parse(String((row && row.last_run_at) || ""));
  if (!Number.isFinite(at)) return true;
  return (Date.now() - at) > 48 * 3600 * 1000;
}

function quietStory(story) {
  const row = story || {};
  if (row.on) return row;
  if (/^Scheduled\b/i.test(String(row.line || ""))) return { on: false, warn: false, line: "Done" };
  return row;
}

function cronIsLive(row) {
  if (!row || cronIsNoise(row)) return false;
  if (row.enabled === false) return false;
  if (row.live) return true;
  const claimAt = cronClaimAt(row);
  const last = Date.parse(String(row.last_run_at || ""));
  if (claimAt && cronClaimFresh(row) && (!Number.isFinite(last) || claimAt > last)) return true;
  const status = String(row.last_status || "").trim().toLowerCase();
  if (/^(ok|error|fail|failed|unknown|skipped|success)$/.test(status)) return false;
  if (row.claimed && cronClaimFresh(row)) return true;
  return /running|in.?progress|started|firing/i.test(String(row.state || status));
}

function cronIsPromptDump(text) {
  const raw = String(text || "");
  if (/^#\s*Cron Job:/im.test(raw) && /^##\s*Prompt\b/im.test(raw) && !/^##\s*Response\s*$/im.test(raw)) return true;
  if (/^#\s*Cron Job:/im.test(raw) && (/\*\*Job ID:\*\*/i.test(raw) || /\*\*Mode:\*\*/i.test(raw))) return true;
  return false;
}

function cronReportText(row) {
  const report = String(row.last_result || "").trim();
  const match = report.match(/^## Response\s*$/im);
  if (match) {
    const body = report.slice(report.search(/^## Response\s*$/im)).replace(/^## Response\s*/i, "").trim();
    if (!body || /^\[SILENT\]/i.test(body)) return "";
    return body;
  }
  if (cronIsPromptDump(report)) return "";
  return report;
}

function cronChangedLine(text) {
  const raw = String(text || "");
  const urls = Array.from(raw.matchAll(/https?:\/\/[^\s)\]>'"]+/g)).map((m) => m[0]).slice(0, 6);
  if (!urls.length) return "";
  const uniq = [...new Set(urls)];
  return `Shipped / linked: ${uniq.join(" · ")}`;
}

function cronEngineName(row) {
  if (!row) return "Hermes Agent";
  if (row.no_agent) return "script";
  const kind = rowEngineKind(row);
  const model = String(row.model || "").trim();
  return model ? `${kind} · ${model}` : kind;
}

function jobStatusWord(row) {
  const raw = String((row && (row.status || row.last_status)) || "").toLowerCase();
  if (/run|live|progress|start|fir/.test(raw)) return "Running";
  if (jobIsFailed(row) || /fail|error/.test(raw)) return "Failed";
  if (/schedul|queue|due|pending|wait/.test(raw)) return "Scheduled";
  if (/ok|done|success/.test(raw)) return "Done";
  return "Done";
}

function cronKind(row, mark) {
  if (mark === "live" || cronIsLive(row)) return "Running";
  if (cronIsFailed(row) || /error|fail/i.test(String((row && row.last_status) || ""))) return "Failed";
  if (mark === "next") return cronIsDueSoon(row) ? "Due" : "Scheduled";
  if (String((row && row.last_status) || "").toLowerCase() === "ok") return "Done";
  return "Job";
}

function cronCardHtml(row, open, mark, extraCount) {
  const title = row.title || cronTitle(row.name || row.id);
  const status = String(row.last_status || "").toLowerCase();
  const failed = /error|fail/.test(status);
  if (failed && mark !== "live") {
    return failChromeHtml(row, open, mark === "next" ? "next" : (mark || "result"), extraCount);
  }
  const err = cleanBotText(String(row.last_error || "").trim());
  let outcome = cleanBotText(row.outcome || (failed ? "Failed." : "No result on this copy yet."));
  if (/^#\s*Cron Job:/i.test(outcome) || cronIsPromptDump(row.last_result || "")) {
    outcome = failed
      ? (err ? `Failed. ${err.slice(0, 160)}` : "Failed. The last run did not finish.")
      : (cronReportText(row) || "Finished on the live box.");
  }
  outcome = String(outcome).replace(/#\s*Cron Job:\s*[\w.-]+/gi, "").trim() || (failed ? "Failed." : outcome);
  const reason = failed ? humanFailReason(`${err} ${outcome} ${cronFailBlob(row)}`) : "";
  const next = failed ? cronFailNext(row) : (row.next_action || "");
  const showNext = failed || cronNextUseful(next);
  const report = cronReportText(row);
  const rawDetail = failed
    ? String(row.last_error || row.last_result || outcome || "").trim()
    : "";
  const changed = cronChangedLine(report);
  const live = mark === "live";
  const kind = failed && !live
    ? `Failed · ${reason}`
    : cronKind(row, mark);
  const fold = String(row.id || title || "job");
  const savedOpen = Boolean((readWorkState().folds || {})[fold]);
  const startOpen = Boolean(open || live || savedOpen || (failed && mark === "result"));
  const fresh = cronFreshness(row);
  const extra = Number(extraCount) > 0 ? ` +${Number(extraCount)}` : "";
  const line = live
    ? "Running now on this CEO's Hermes."
    : (failed ? `Failed · ${reason}` : outcome);
  const failActs = failed && !live && !cronSkipRetry(row)
    ? `<div class="need-actions">${choiceButtonsHtml(needChoices({ kind: "failed", cron_id: row.id || "", project_id: projectId || "" }), { id: row.id || "", project_id: projectId || "", cron_id: row.id || "", kind: "failed" })}</div>`
    : "";
  const detailFold = rawDetail && failed && rawDetail !== line
    ? `<details class="cron-more" data-fold="raw-${escapeHtml(fold)}"><summary>Details</summary><pre>${escapeHtml(rawDetail.slice(0, 4000))}</pre></details>`
    : "";
  return `<details class="cron-card${live ? " live" : ""}${failed ? " failed" : ""}" id="cron-${escapeHtml(row.id || "")}" data-fold="${escapeHtml(fold)}"${startOpen ? " open" : ""}>
    <summary class="cron-head">
      <b>${escapeHtml(title)}${escapeHtml(extra)}</b>
      <span>${escapeHtml(kind)}${fresh ? ` · ${escapeHtml(fresh)}` : ""}</span>
    </summary>
    <p class="cron-outcome">${escapeHtml(line)}</p>
    ${failActs}
    ${!failed && showNext && !live ? `<p class="cron-next">If needed: ${escapeHtml(next)}</p>` : ""}
    ${failed && showNext && !live ? `<p class="cron-next">Next: ${escapeHtml(next)}</p>` : ""}
    ${!failed && changed && !live ? `<p class="cron-next">${escapeHtml(changed)}</p>` : ""}
    ${detailFold}
    ${report && !failed ? `<details class="cron-more" data-fold="report-${escapeHtml(fold)}"><summary>Full report</summary><pre>${escapeHtml(report)}</pre></details>` : ""}
  </details>`;
}

function paintCeoBrief(digest) {
  const el = $("ceoBrief");
  if (!el) return;
  if ($("ceoLive")) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  if (!projectId) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const project = currentProject();
  const counts = workCounts();
  const nxt = String((project && project.index_next) || "").trim();
  const now = String((project && project.index_now) || "").trim();
  const blocker = String((project && project.index_blocker) || "").trim();
  const bits = [];
  if (digest && digest.story) bits.push(digest.story);
  else if (blocker && blocker !== "—") bits.push(`Blocked: ${blocker}`);
  else {
    let line = (nxt && nxt !== "—") ? nxt : ((now && now !== "—") ? now : "");
    line = honestWorkLine(line, counts) || line;
    const trust = scheduleTrustNowLine(counts, project);
    if (!line && trust) line = trust;
    if (!line && (counts.failed || 0) > 0) line = `${counts.failed} failed — open Results`;
    if (line && !isScheduleFluff(line)) bits.push(line);
  }
  if (!bits.length) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  el.hidden = false;
  el.innerHTML = bits.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

function laneLabel(name) {
  const raw = String(name || "").trim();
  if (!raw || raw === "cos") return "Chat";
  return jobLabel(raw) || raw;
}

function rowEngineKind(row) {
  if (!row) return "Hermes Agent";
  if (row.no_agent) return "script";
  const named = String(row.engine || "").trim();
  if (/^OpenCode$/i.test(named)) return "OpenCode";
  if (/Hermes/i.test(named)) return "Hermes Agent";
  if ((PRESET_ENGINE[row.preset] || "") === "OpenCode" || row.preset === "builder") return "OpenCode";
  return "Hermes Agent";
}

function engineMatches(row, kind) {
  return rowEngineKind(row) === kind;
}

function hermesScheduleSummary(crons) {
  const list = (crons || []).filter((row) => !cronIsNoise(row));
  if (list.length < 2) return null;
  const enabled = list.filter((row) => row.enabled !== false && !/paused/i.test(String(row.state || "")));
  if (!enabled.length) return null;
  const ok = enabled.filter((row) => String(row.last_status || "").toLowerCase() === "ok");
  const freshFail = enabled.filter((row) => cronIsFailed(row) && !cronIsGatewayFail(row) && !cronIsStaleFail(row));
  const next = enabled
    .filter((row) => row.next_run_at)
    .slice()
    .sort((a, b) => String(a.next_run_at || "").localeCompare(String(b.next_run_at || "")))[0];
  const due = next ? cronWhenNext(next.next_run_at) : "";
  const nextBit = next
    ? ` · next ${cronTitle(next.name)}${due ? ` ${due}` : ""}`
    : "";
  if (freshFail.length) {
    return { on: false, warn: true, line: `Schedule · ${freshFail.length} failed${nextBit}` };
  }
  return { on: false, warn: false, line: `Schedule · ${ok.length}/${enabled.length} ok${nextBit}` };
}

function engineStory(kind) {
  const label = kind === "OpenCode" ? "OpenCode" : "Hermes";
  if (liveRunId) {
    const eng = PRESET_ENGINE[liveLane || preset] || "";
    if (engineMatches({ engine: eng, preset: liveLane || preset }, kind)) {
      return { on: true, line: `Running · ${talkName()} · ${laneLabel(liveLane || preset)}` };
    }
  }
  const pack = digestCache.get(projectId) || {};
  const boardRuns = ((pack.live_runs || (cfg.activity || {}).live_runs) || []).filter((row) => (
    (!projectId || String(row.project_id || "") === String(projectId)) && engineMatches(row, kind)
  ));
  if (boardRuns.length) {
    return { on: true, line: `Running · ${laneLabel(boardRuns[0].preset)}` };
  }
  const crons = (pack.crons || []).filter((row) => !cronIsNoise(row) && engineMatches(row, kind));
  const liveCron = crons.find((row) => cronIsLive(row));
  if (liveCron) {
    return { on: true, line: `Running · ${liveCron.title || cronTitle(liveCron.name) || "job"}` };
  }
  if (kind === "Hermes Agent") {
    const schedule = hermesScheduleSummary(crons);
    if (schedule) return schedule;
  }
  const latest = crons
    .filter((row) => row.last_run_at && !cronIsLive(row))
    .slice()
    .sort((a, b) => String(b.last_run_at || "").localeCompare(String(a.last_run_at || "")))[0];
  if (latest) {
    const scar = cronIsGatewayFail(latest) && gatewayRunning;
    return {
      on: false,
      warn: cronIsFailed(latest) && !scar,
      line: scar
        ? `Schedule · gateway up · last ${latest.title || cronTitle(latest.name) || "job"}`
        : `Done · ${latest.title || cronTitle(latest.name) || "job"}`
    };
  }
  if (!projectId) {
    const jobs = (((cfg.activity || {}).jobs) || []).filter((row) => engineMatches(row, kind));
    const liveJob = jobs.find((row) => /run|live/i.test(String(row.status || "")));
    if (liveJob) return { on: true, line: `Running · ${jobStoryTitle(liveJob)}` };
    const last = jobs[0];
    if (last) {
      return { on: false, warn: /fail|error/i.test(String(last.status || "")), line: `Done · ${jobStoryTitle(last)}` };
    }
  }
  return { on: false, line: `Done · ${label}` };
}

function runningStory() {
  if (liveRunId) {
    return { on: true, line: `Running · ${talkName()} · ${laneLabel(liveLane || preset)}` };
  }
  const pack = digestCache.get(projectId) || {};
  const digest = pack.digest || pack;
  const running = (digest.running || []).filter((row) => cronIsLive(row));
  const claimed = (pack.crons || []).filter((row) => cronIsLive(row));
  const boardRuns = ((pack.live_runs || (cfg.activity || {}).live_runs) || []).filter((row) => (
    !projectId || String(row.project_id || "") === String(projectId)
  ));
  if (boardRuns.length) {
    const row = boardRuns[0];
    const who = (currentProject() && currentProject().name) || "Chat";
    return { on: true, line: `Running · ${who} · ${laneLabel(row.preset)}` };
  }
  const liveCron = running[0] || claimed[0];
  if (liveCron) {
    const who = (currentProject() && currentProject().name) || "Schedule";
    return { on: true, line: `Running · ${who} · ${liveCron.title || cronTitle(liveCron.name) || "job"}` };
  }
  if (!projectId && lives.size) {
    return { on: true, line: `Running · ${lives.size} chat${lives.size === 1 ? "" : "s"}` };
  }
  if (!projectId) {
    const jobs = (((cfg.activity || {}).jobs) || []);
    const liveJob = jobs.find((row) => /run|live/i.test(String(row.status || "")));
    if (liveJob) return { on: true, line: `Running · ${jobStoryTitle(liveJob)}` };
    const last = jobs[0];
    if (last) {
      return { on: false, warn: /fail|error/i.test(String(last.status || "")), line: `Done · ${jobStoryTitle(last)}` };
    }
    return { on: false, line: "" };
  }
  const latest = (pack.crons || [])
    .filter((row) => row.last_run_at && !cronIsNoise(row) && !cronIsLive(row))
    .slice()
    .sort((a, b) => String(b.last_run_at || "").localeCompare(String(a.last_run_at || "")))[0];
  if (latest) {
    return { on: false, warn: cronIsFailed(latest), line: `Done · ${latest.title || cronTitle(latest.name) || "job"}` };
  }
  return { on: false, line: "" };
}

function paintEmbedLive() {
  const oc = quietStory(engineStory("OpenCode"));
  const hermes = quietStory(engineStory("Hermes Agent"));
  [["ocLive", oc], ["hermesLive", hermes]].forEach(([id, story]) => {
    const el = $(id);
    if (!el) return;
    if (!story || !story.line) {
      el.hidden = true;
      return;
    }
    const idleNoise = !story.on && /^Done · (OpenCode|Hermes(?: Agent)?)\s*$/i.test(String(story.line || ""));
    el.hidden = idleNoise;
    if (el.hidden) return;
    el.classList.toggle("on", story.on);
    el.classList.toggle("warn", Boolean(story.warn) && !story.on);
    el.textContent = story.line;
  });
}

function paintPulse() {
  const el = $("pulse");
  if (!el) return;
  const story = quietStory(runningStory());
  const running = Boolean(story.on);
  el.classList.toggle("on", running);
  el.classList.toggle("ok", false);
  el.classList.toggle("warn", false);
  if (running) {
    el.hidden = false;
    // Engine names only while work is live — skip idle OpenCode/Hermes noise.
    el.innerHTML = `<i aria-hidden="true"></i><span>${escapeHtml(story.line)}</span>`;
  } else {
    // Bare Done when idle — hide the pulse entirely.
    el.hidden = true;
    el.innerHTML = `<i aria-hidden="true"></i><span>Done</span>`;
  }
  paintEmbedLive();
  paintWorkTabs();
  paintWorkStatus();
}

function paintCeoLive(pack) {
  const el = $("ceoLive");
  if (!el) return;
  const story = quietStory(runningStory());
  if (!story.on || scheduleOpen) {
    el.hidden = true;
    el.innerHTML = "";
    paintPulse();
    return;
  }
  el.hidden = false;
  el.classList.add("on");
  el.classList.remove("warn");
  el.innerHTML = `<div class="ceo-pulse">
      <i class="ceo-live-dot" aria-hidden="true"></i>
      <div class="ceo-pulse-copy">
        <b>${escapeHtml(story.line)}</b>
      </div>
    </div>`;
  paintPulse();
}

async function loadCeoDigest(refreshLive) {
  paintWorkTabs();
  if (!projectId) {
    gatewayRunning = true;
    paintCeoBrief(null);
    paintCeoLive(null);
    if (scheduleOpen) renderChatSchedule([], {}, scheduleFocusId, "");
    return null;
  }
  const cached = digestCache.get(projectId);
  if (cached) {
    if (typeof cached.gateway_running === "boolean") gatewayRunning = cached.gateway_running;
    paintCeoBrief(cached.digest || cached);
    paintCeoLive(cached);
    renderBotMeta({ skipSpend: true });
  }
  try {
    const pid = projectId;
    const res = await fetch(`/api/crons?project_id=${encodeURIComponent(pid)}`);
    const data = await res.json();
    digestCache.set(pid, data);
    digestKnown.add(pid);
    if (projectId === pid) {
      paintCeoBrief(data.digest);
      paintCeoLive(data);
      paintWorkTabs();
      paintEmbedLive();
      if (org && org.projects) renderOrg(org);
      renderBotMeta({ skipSpend: true });
      if (scheduleOpen && String(lastSchedulePid || "") === String(pid || "")) {
        renderChatSchedule(data.crons || [], data.digest || {}, scheduleFocusId, pid);
      }
    }
    fetch(`/api/hermes/gateway/status?project_id=${encodeURIComponent(pid)}`)
      .then((gwRes) => (gwRes && gwRes.ok ? gwRes.json() : null))
      .then((gw) => {
        if (!gw) return;
        gatewayRunning = gw.running !== false;
        const pack = digestCache.get(pid) || data;
        pack.gateway_running = gatewayRunning;
        digestCache.set(pid, pack);
        if (projectId === pid) {
          syncHermesHint();
          if (scheduleOpen && String(lastSchedulePid || "") === String(pid || "")) {
            renderChatSchedule(pack.crons || [], pack.digest || pack, scheduleFocusId, pid);
          }
        }
      })
      .catch(() => {});
    return data;
  } catch (_err) {
    return null;
  }
}

function liveRunCard(row) {
  const who = currentProject() ? (currentProject().name || "This CEO") : "Chat";
  const engine = String(row.engine || PRESET_ENGINE[row.preset] || "board");
  const open = [{ id: "open", label: "Open chat" }];
  const fold = `live-${row.id || row.preset || "chat"}`;
  return `<details class="cron-card live" data-fold="${escapeHtml(fold)}" open>
    <summary class="cron-head">
      <b>${escapeHtml(laneLabel(row.preset || "cos"))}</b>
      <span>Running</span>
    </summary>
    <p class="cron-outcome">${escapeHtml(row.title || "This chat is answering now.")} · ${escapeHtml(who)} · ${escapeHtml(engine)}</p>
    <div class="need-actions">${choiceButtonsHtml(open, row)}</div>
  </details>`;
}

function gatewayOffHtml() {
  return `<article class="cron-card gateway-off">
    <div class="cron-head"><b>Hermes gateway</b><span>Off</span></div>
    <p class="cron-outcome">Gateway is off. Scheduled jobs wait. Restart it — do not fire the whole set.</p>
    <button type="button" class="send gateway-restart">Restart</button>
  </article>`;
}

function emptyWorkCopy(view) {
  const who = projectId ? prettyCeoName(projectId, (currentProject() || {}).name) : "Chief of Staff";
  const why = whyIdleLine();
  if (view === "doing") {
    const counts = workCounts();
    if (prefersScheduleTrust(counts)) {
      const trust = scheduleTrustNowLine(counts, currentProject());
      return trust
        ? `Nothing running on ${who}. ${trust}.`
        : `Nothing running on ${who}. Open Schedule.`;
    }
    if ((counts.failed || 0) > 0) {
      return `Nothing running on ${who}. ${counts.failed} failed — open Results.`;
    }
    if ((counts.next || 0) > 0) {
      return `Nothing running on ${who}. ${counts.next} due in Next — open that tab.`;
    }
    return why
      ? `Idle on ${who}. ${why}`
      : `Nothing is running on ${who}. Send a message, or open Next for what’s queued.`;
  }
  if (view === "next") {
    return `Nothing queued for ${who}. When this brief has a Next, or a job is due in the next day, it shows up here.${why ? ` ${why}` : ""}`;
  }
  return `No finished jobs for ${who} yet. Results land here when work completes.${why ? ` ${why}` : ""}`;
}

function whyIdleLine() {
  if (liveRunId || lives.size) return "";
  if (!gatewayRunning && projectId) return "Why idle: Hermes gateway is off — Restart it.";
  const pack = digestCache.get(projectId) || {};
  if (projectId && !digestKnown.has(projectId)) return "Why idle: still loading schedule…";
  const counts = workCounts();
  if (prefersScheduleTrust(counts)) {
    const trust = scheduleTrustNowLine(counts, currentProject());
    return trust
      ? `Why idle: ${trust}`
      : `Why idle: schedule needs a look — open Schedule.`;
  }
  if ((counts.failed || 0) > 0) {
    return `Why idle: ${counts.failed} failed in Results — clear those to move.`;
  }
  if ((counts.next || 0) > 0) {
    const due = (pack.crons || []).find((row) => row.enabled !== false && cronIsDueSoon(row) && !cronIsLive(row));
    const when = due && due.next_run_at ? cronWhenClock(due.next_run_at) : "soon";
    return `Why idle: ${counts.next} due in Next (${when}).`;
  }
  const next = (pack.crons || []).find((row) => row.enabled !== false && cronIsDueSoon(row) && !cronIsLive(row));
  if (next && next.next_run_at) return `Why idle: next due ${cronWhenClock(next.next_run_at)}.`;
  return projectId ? "Why idle: nothing claimed on Hermes right now." : "";
}

function cronFreshness(row) {
  const at = Date.parse(String((row && (row.last_run_at || row.next_run_at)) || ""));
  if (!Number.isFinite(at)) return "";
  const mins = Math.round((Date.now() - at) / 60000);
  if (mins < 0) return `due in ${Math.abs(mins)}m`;
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function gatewayFailClusterHtml(rows, want) {
  const list = rows || [];
  const banner = !gatewayRunning ? gatewayOffHtml() : "";
  if (!list.length) return banner;
  if (list.length === 1) return `${banner}${cronCardHtml(list[0], list[0].id === want, "result")}`;
  const inner = list.map((row) => cronCardHtml(row, row.id === want, "result")).join("");
  return `${banner}<article class="cron-card cron-cluster">
    <div class="cron-head"><b>Old gateway stop scars</b><span>Stale</span></div>
    <p class="cron-outcome">A past cleanup hit ${list.length} jobs. Restart the gateway once — do not mass-retry.</p>
    <details class="cron-stale" data-fold="gateway-jobs"><summary>Show ${list.length} jobs</summary>${inner}</details>
  </article>`;
}

function paintWorkSurface() {
  const shell = document.querySelector(".chat-shell");
  if (shell) {
    shell.classList.toggle("work-open", Boolean(scheduleOpen));
    shell.classList.toggle("activity-open", Boolean(scheduleOpen));
  }
  const lanes = $("laneStatus");
  if (lanes) lanes.hidden = true;
  paintActivityTitle();
  paintWorkStatus();
}

function closeSchedule() {
  scheduleOpen = false;
  writeWorkState({ open: false, view: scheduleView });
  const panel = $("chatSchedule");
  if (panel) panel.hidden = true;
  paintWorkSurface();
  paintWorkTabs();
}

function renderChatSchedule(rows, digest, focusId, forPid) {
  const expect = String(forPid !== undefined ? forPid : projectId || "");
  if (expect !== String(projectId || "")) return;
  if (String(lastSchedulePid || "") !== String(projectId || "")) return;
  const panel = $("chatSchedule");
  const el = activityBody();
  if (!el) return;
  if (!scheduleOpen) {
    if (panel) panel.hidden = true;
    return;
  }
  if (panel) panel.hidden = false;
  paintActivityTitle();
  const want = String(focusId || scheduleFocusId || "");
  const view = scheduleView || "doing";
  if (!projectId) {
    const runs = ((cfg.activity || {}).live_runs) || [];
    const projects = ((cfg.org && cfg.org.projects) || []);
    const allJobs = (((cfg.activity || {}).jobs) || []);
    const jobs = allJobs.slice(0, 12);
    const bits = [];
    if (view === "doing") {
      if (liveRunId) bits.push(liveRunCard({ preset: liveLane || preset, title: "This chat" }));
      bits.push(runs.length ? runs.map((row) => liveRunCard(row)).join("") : "");
      if (!liveRunId && !runs.length) {
        bits.push(`<p class="cron-empty">${escapeHtml(emptyWorkCopy("doing"))}</p>`);
      }
    } else if (view === "next") {
      const story = ceoHandlingStoryHtml();
      if (story) bits.push(story);
      const failJobs = allJobs.filter((row) => jobIsFailed(row)).slice().sort(ownershipSort);
      if (failJobs.length) {
        const clustered = clusterFailRows(failJobs);
        bits.push(`<h3 class="cron-section">Action queue · ${failJobs.length}</h3>`);
        bits.push(clustered.map(({ row, extra }) => failChromeHtml({
          ...row,
          title: row.title || jobLabel(row.preset) || jobStoryTitle(row) || "Job",
          last_status: row.status || row.last_status || "error",
          last_error: row.last_error || row.error || row.blocker || row.text || row.summary || "",
          cron_id: row.cron_id || row.id || ""
        }, false, "next", extra)).join(""));
      }
      const next = projects.filter((row) => String(row.index_next || "").trim() && String(row.index_next || "").trim() !== "—");
      if (next.length) {
        bits.push(`<h3 class="cron-section">CEO next · ${next.length}</h3>`);
        bits.push(next.map((row) => `<details class="cron-card" data-fold="ceo-${escapeHtml(row.id || "")}">
          <summary class="cron-head"><b>${escapeHtml(prettyCeoName(row.id, row.name))}</b><span>Scheduled</span></summary>
          <p class="cron-outcome">${escapeHtml(clipWire(cleanBotText(row.index_next), 180))}</p>
          <div class="need-actions">${choiceButtonsHtml([{ id: "continue", label: "Continue" }, { id: "open", label: "Open chat" }], { id: row.id, project_id: row.id, preset: "cos" })}</div>
        </details>`).join(""));
      }
      if (!failJobs.length && !next.length) bits.push(`<p class="cron-empty">${escapeHtml(emptyWorkCopy("next"))}</p>`);
    } else if (view === "schedule") {
      bits.push(`<p class="cron-empty">Pick a CEO to see the full enabled schedule roster.</p>`);
    } else {
      const failJobs = jobs.filter((row) => jobIsFailed(row)).slice().sort(ownershipSort);
      const clustered = clusterFailRows(failJobs);
      const okJobs = jobs.filter((row) => !jobIsFailed(row));
      if (clustered.length) {
        bits.push(`<h3 class="cron-section">Recovering · ${failJobs.length}</h3>`);
        bits.push(clustered.map(({ row, extra }) => failChromeHtml({
          ...row,
          last_status: row.status || row.last_status || "error",
          last_error: row.last_error || row.error || row.blocker || row.text || row.summary || "",
          cron_id: row.cron_id || row.id || ""
        }, false, "result", extra)).join(""));
      }
      if (okJobs.length) {
        bits.push(`<h3 class="cron-section">Resolved · ${okJobs.length}</h3>`);
        bits.push(okJobs.map((row) => `<details class="cron-card" data-fold="job-${escapeHtml(row.id || row.title || "job")}">
          <summary class="cron-head"><b>${escapeHtml(row.title || jobLabel(row.preset) || "Job")}</b><span>Resolved</span></summary>
          <p class="cron-outcome"><span class="cron-k">Outcome</span> ${escapeHtml(clipWire(cleanBotText(row.text || row.summary || row.outcome || ""), 180) || "Done.")}</p>
          <p class="cron-status"><span class="cron-k">Status</span> Resolved</p>
          ${jobChoices(row).length ? `<div class="need-actions">${choiceButtonsHtml(jobChoices(row), row)}</div>` : ""}
        </details>`).join(""));
      }
      if (!jobs.length) bits.push(`<p class="cron-empty">${escapeHtml(emptyWorkCopy("results"))}</p>`);
    }
    el.innerHTML = bits.join("");
    bindNeedActions(el);
    bindGatewayRestart(el);
    bindWorkFolds(el);
    paintWorkSurface();
    paintWorkTabs();
    return;
  }
  const list = (rows || []).filter((row) => !cronIsNoise(row));
  if (rows && !list.length) {
    el.innerHTML = `<p class="cron-story">No scheduled checks on this CEO yet. Telegram still gets the live report.</p>`;
    return;
  }
  const cached = digestCache.get(projectId) || {};
  const pack = digest || cached.digest || cached || {};
  const boardRuns = ((cached.live_runs || pack.live_runs || (cfg.activity || {}).live_runs) || []).filter((row) => String(row.project_id || "") === String(projectId));
  const claimed = list.filter((row) => cronIsLive(row));
  const running = [...(pack.running || [])].filter((row) => cronIsLive(row) || row.live);
  const seenRun = new Set(running.map((row) => row.id));
  claimed.forEach((row) => {
    if (!seenRun.has(row.id)) running.push(row);
  });
  const latest = list
    .filter((row) => row.last_run_at && !cronIsNoise(row) && !cronIsLive(row))
    .slice()
    .sort((a, b) => String(b.last_run_at || "").localeCompare(String(a.last_run_at || "")))
    .slice(0, 12);
  const failed = list.filter((row) => cronIsFailed(row));
  const failedIds = new Set(failed.map((row) => row.id));
  const latestOk = latest.filter((row) => !failedIds.has(row.id)).slice(0, 8);
  const paused = list.filter((row) => row.enabled === false || /paused/i.test(String(row.state || "")));
  const scheduled = list
    .filter((row) => row.enabled !== false && !/paused/i.test(String(row.state || "")) && !cronIsLive(row) && !cronIsFailed(row))
    .slice()
    .sort((a, b) => String(a.next_run_at || "").localeCompare(String(b.next_run_at || "")));
  const soon = scheduled.filter((row) => cronIsDueSoon(row));
  const later = scheduled.filter((row) => {
    const stamp = new Date(String(row.next_run_at || "").trim());
    if (Number.isNaN(stamp.getTime())) return false;
    return stamp.getTime() > Date.now() && !cronIsDueSoon(row);
  });
  const sections = [];
  const waitName = running.length ? (running[0].title || cronTitle(running[0].name)) : "";
  if (view === "doing") {
    if (!gatewayRunning) sections.push(gatewayOffHtml());
    if (boardRuns.length) sections.push(boardRuns.map((row) => liveRunCard(row)).join(""));
    sections.push(running.length ? running.map((row) => cronCardHtml(row, row.id === want, "live")).join("") : "");
    if (!boardRuns.length && !running.length) {
      sections.push(`<p class="cron-empty">${escapeHtml(emptyWorkCopy("doing"))}</p>`);
    }
  } else if (view === "next") {
    const story = ceoHandlingStoryHtml();
    if (story) sections.push(story);
    if (waitName) {
      sections.push(`<p class="cron-empty">Waiting · ${escapeHtml(waitName)} is on this CEO's Hermes. Due jobs stay queued.</p>`);
    }
    // HARD: ownership-sorted action queue — ALL fails (fresh + older), never Due-dump alone.
    // Fresh first; Older (>48h) bucketed like Results so Schedule N failed matches Action queue total.
    const freshFails = dedupeFailRows(failed.filter((row) => !cronIsStaleFail(row)).slice().sort(ownershipSort));
    const olderFails = dedupeFailRows(failed.filter((row) => cronIsStaleFail(row)).slice().sort(ownershipSort));
    const actionFails = freshFails.concat(olderFails);
    if (actionFails.length) {
      const autoN = actionFails.filter((row) => failOwnership(row).owner === "auto").length;
      const ceoN = actionFails.filter((row) => failOwnership(row).owner === "ceo").length;
      const cosN = actionFails.filter((row) => failOwnership(row).owner === "cos").length;
      const adamN = actionFails.filter((row) => failOwnership(row).owner === "adam").length;
      const bits = [`Auto ${autoN}`, `CEO ${ceoN}`, `Cos ${cosN}`, `Adam ${adamN}`].filter((x) => !x.endsWith(" 0"));
      const ageBit = olderFails.length ? ` · Fresh ${freshFails.length} · Older ${olderFails.length}` : "";
      sections.push(`<h3 class="cron-section">Action queue · ${actionFails.length}${bits.length ? ` · ${bits.join(" · ")}` : ""}${ageBit}</h3>`);
      sections.push(clusterFailRows(freshFails).map(({ row, extra }) => failChromeHtml(row, row.id === want, "next", extra)).join(""));
      if (olderFails.length) {
        sections.push(`<details class="cron-stale" data-fold="older-action-fails"><summary>Older fails · ${olderFails.length}</summary>${olderFails.map((row) => failChromeHtml(row, row.id === want, "next")).join("")}</details>`);
      }
    }
    const dueShow = soon.slice(0, 6);
    const dueMore = soon.slice(6);
    sections.push(`<h3 class="cron-section">Due · ${soon.length}</h3>${dueShow.length ? dueShow.map((row) => cronCardHtml(row, row.id === want, "next")).join("") : (actionFails.length ? "" : `<p class="cron-empty">Nothing due in the next day.</p>`)}`);
    if (dueMore.length) {
      sections.push(`<details class="cron-stale" data-fold="more-due"><summary>More due · ${dueMore.length}</summary>${dueMore.map((row) => cronCardHtml(row, row.id === want, "next")).join("")}</details>`);
    }
    if (later.length) {
      sections.push(`<details class="cron-stale" data-fold="later"><summary>Later · ${later.length}</summary>${later.map((row) => cronCardHtml(row, row.id === want, "next")).join("")}</details>`);
    }
    if (paused.length) {
      sections.push(`<details class="cron-stale" data-fold="paused"><summary>Paused · ${paused.length}</summary>${paused.map((row) => cronCardHtml(row, row.id === want)).join("")}</details>`);
    }
    if (!actionFails.length && !soon.length && !later.length && !paused.length) {
      sections.push(`<p class="cron-empty">${escapeHtml(emptyWorkCopy("next"))}</p>`);
    }
  } else if (view === "schedule") {
    const counts = workCounts();
    // Operator roster is non-noise. Grok/alerts fold as Board internals — not "late" SEO work.
    const inventory = list;
    const noiseRoster = (rows || []).filter((row) => cronIsNoise(row));
    const enabledRoster = inventory
      .filter((row) => row.enabled !== false && !/paused/i.test(String(row.state || "")))
      .slice()
      .sort(scheduleRosterSort);
    const disabledRoster = inventory
      .filter((row) => row.enabled === false || /paused/i.test(String(row.state || "")))
      .slice()
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
    sections.push(`<h3 class="cron-section">Enabled · ${enabledRoster.length}${counts.ready ? ` · ${counts.trustFailed || 0} failed · ${counts.never || 0} never · ${counts.overdue || 0} overdue` : ""}</h3>`);
    if (!enabledRoster.length) {
      sections.push(`<p class="cron-empty">No enabled jobs on this CEO yet.</p>`);
    } else {
      sections.push(enabledRoster.map((row) => scheduleRosterRowHtml(row, want)).join(""));
    }
    if (disabledRoster.length) {
      sections.push(`<details class="cron-stale" data-fold="disabled-roster"><summary>Disabled · ${disabledRoster.length}</summary>${disabledRoster.map((row) => scheduleRosterRowHtml(row, want)).join("")}</details>`);
    }
    if (noiseRoster.length) {
      sections.push(`<details class="cron-stale" data-fold="internal-roster"><summary>Board internals · ${noiseRoster.length}</summary>${noiseRoster.map((row) => scheduleRosterRowHtml(row, want)).join("")}</details>`);
    }
  } else {
    if (!gatewayRunning) sections.push(gatewayOffHtml());
    const actionFails = failed.filter((row) => !cronIsStaleFail(row)).slice().sort(ownershipSort);
    const recovering = actionFails.filter((row) => {
      const st = failOwnership(row).resultStatus;
      return st === "Recovering";
    });
    const blockedCos = actionFails.filter((row) => failOwnership(row).resultStatus === "Blocked·Cos");
    const needsAdam = actionFails.filter((row) => failOwnership(row).resultStatus === "Needs Adam");
    const staleFails = failed.filter((row) => cronIsStaleFail(row));
    if (recovering.length) {
      const clustered = clusterFailRows(recovering);
      sections.push(`<h3 class="cron-section">Recovering · ${recovering.length}</h3>`);
      sections.push(clustered.map(({ row, extra }) => failChromeHtml(row, row.id === want, "result", extra)).join(""));
    }
    if (blockedCos.length) {
      sections.push(`<h3 class="cron-section">Blocked·Cos · ${blockedCos.length}</h3>`);
      sections.push(blockedCos.map((row) => failChromeHtml(row, row.id === want, "result")).join(""));
    }
    if (needsAdam.length) {
      sections.push(`<h3 class="cron-section">Needs Adam · ${needsAdam.length}</h3>`);
      sections.push(needsAdam.map((row) => failChromeHtml(row, row.id === want, "result")).join(""));
    }
    if (staleFails.length) {
      sections.push(`<details class="cron-stale" data-fold="older-fails"><summary>Older fails · ${staleFails.length}</summary>${staleFails.map((row) => failChromeHtml(row, row.id === want, "result")).join("")}</details>`);
    }
    sections.push(`<h3 class="cron-section">Resolved · ${latestOk.length}</h3>${latestOk.length ? latestOk.map((row) => {
      const title = row.title || cronTitle(row.name || row.id);
      const fold = String(row.id || title || "job");
      return `<details class="cron-card" id="cron-${escapeHtml(row.id || "")}" data-fold="${escapeHtml(fold)}">
        <summary class="cron-head"><b>${escapeHtml(title)}</b><span>Resolved${cronFreshness(row) ? ` · ${escapeHtml(cronFreshness(row))}` : ""}</span></summary>
        <p class="cron-outcome"><span class="cron-k">Outcome</span> ${escapeHtml(cleanBotText(row.outcome || cronReportText(row) || "Done.") || "Done.")}</p>
        <p class="cron-status"><span class="cron-k">Status</span> Resolved</p>
      </details>`;
    }).join("") : (actionFails.length ? "" : `<p class="cron-empty">${escapeHtml(emptyWorkCopy("results"))}</p>`)}`);
  }
  el.innerHTML = sections.join("");
  bindNeedActions(el);
  bindGatewayRestart(el);
  bindWorkFolds(el);
  paintWorkSurface();
  paintWorkTabs();
  if (want && window.CSS && CSS.escape) {
    const target = el.querySelector(`#cron-${CSS.escape(want)}`);
    if (target) target.scrollIntoView({ block: "nearest" });
  }
}

async function openWork(view, focusId) {
  // Chat is the schedule surface (Doing/Next/Results). Tools → Hermes stays the raw engine.
  const next = view || "doing";
  if (stage !== "chat") setStage("chat");
  scheduleView = next;
  await openSchedule(focusId || "");
}

async function openSchedule(focusId) {
  const pid = String(projectId || "");
  scheduleOpen = true;
  scheduleFocusId = focusId || "";
  lastSchedulePid = pid;
  writeWorkState({ open: true, view: scheduleView });
  paintWorkSurface();
  paintWorkTabs();
  const panel = $("chatSchedule");
  const body = activityBody();
  const cached = pid ? digestCache.get(pid) : null;
  if (panel) panel.hidden = false;
  if (!pid) {
    renderChatSchedule([], {}, focusId, "");
    paintWorkTabs();
    return;
  }
  if (cached) renderChatSchedule(cached.crons || null, cached.digest || cached, focusId, pid);
  else if (body) {
    const who = prettyCeoName(pid, (currentProject() || {}).name);
    body.innerHTML = `<p class="cron-empty">Loading ${escapeHtml(who)}…</p>`;
  }
  const data = await loadCeoDigest(true);
  if (String(projectId || "") !== pid) return;
  if (data) renderChatSchedule(data.crons || [], data.digest || {}, focusId, pid);
  else if (body && !cached) body.innerHTML = `<p class="cron-empty">Could not load the schedule.</p>`;
}

function fillProfile(data) {
  const name = (data.operator_name || "").trim() || (isCollaborator() ? "Collaborator" : "You");
  if ($("profileName")) $("profileName").textContent = name;
  if ($("profileRole")) {
    $("profileRole").textContent = isCollaborator()
      ? `Collaborator · ${(data.share && data.share.owner_name) || "Owner"}`
      : "Settings";
  }
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
  fillPair();
}

async function fillPair() {
  const host = $("pairUrls");
  if (!host) return;
  try {
    const data = await (await fetch("/api/pair")).json();
    const urls = data.urls || [];
    host.innerHTML = urls.length
      ? urls.map((url) => `<button type="button" class="ghost-btn pair-url" data-pair-url="${escapeHtml(url)}">${escapeHtml(url)}</button>`).join("")
      : `<p class="muted">No reachable address yet.</p>`;
    host.querySelectorAll("[data-pair-url]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const url = btn.dataset.pairUrl || "";
        try {
          await navigator.clipboard.writeText(url);
          if ($("pairStatus")) $("pairStatus").textContent = "Copied.";
        } catch (_err) {
          if ($("pairStatus")) $("pairStatus").textContent = url;
        }
      });
    });
    if ($("pairStatus") && !$("pairStatus").textContent) {
      $("pairStatus").textContent = data.pin_required
        ? (data.hint || "Paste an address on the phone.")
        : "Set a PIN before you leave this machine.";
    }
  } catch (_err) {
    host.innerHTML = `<p class="muted">Could not load addresses.</p>`;
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
  if ($("enableSelfBuild")) $("enableSelfBuild").checked = Boolean(data.enable_self_build);
  if ($("xIntakeEnabled")) $("xIntakeEnabled").checked = Boolean(data.x_intake_enabled);
  if ($("xUsername") && document.activeElement !== $("xUsername")) $("xUsername").value = data.x_username || "";
  loadSelfBuildStatus();
  if (data.org) renderOrg(data.org);
  paintHelpPanel();
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
    const options = catalog.filter((item) => item.id !== "anthropic").map((item) => (
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
  const never = new Set(keyring.never_providers || ["anthropic"]);
  const order = keyring.fallback || accounts.map((row) => row.id);
  const ranked = new Map(order.map((id, i) => [id, i]));
  const sorted = accounts.slice().sort((a, b) => (ranked.get(a.id) ?? 99) - (ranked.get(b.id) ?? 99));
  const failoverHint = $("keyFailoverHint");
  if (failoverHint) {
    const chain = sorted.filter((row) => !never.has(row.provider)).map((row) => row.label || row.provider);
    failoverHint.textContent = chain.length
      ? `Failover order (board → Hermes → OpenCode): ${chain.join(" → ")}. Anthropic never runs.`
      : "Add OpenCode Go keys (up to 3) then OpenRouter as ordered backup. Anthropic never runs.";
  }
  $("keyList").innerHTML = sorted.length ? sorted.map((row, index) => `
    <article class="provider${never.has(row.provider) ? " blocked-provider" : ""}">
      <div class="provider-top">
        <b>${escapeHtml(row.label)}</b>
        <div class="pills">
          <span class="pill">${escapeHtml(row.provider)}</span>
          ${never.has(row.provider) ? '<span class="pill warn">blocked</span>' : (index === 0 ? '<span class="pill on">primary</span>' : '<span class="pill">backup</span>')}
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
  paintBoardMark();
  if (data.org) {
    org = data.org;
    renderOrg(org);
  }
  if (data.engines) renderEngines(data.engines, "firstEngines");
  paintPulse();
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
  applyCollaboratorChrome();
  paintWorkTabs();
}

function applyCollaboratorChrome() {
  const hide = new Set(["folder", "keys", "import", "channels", "git", "models", "connectors", "routines", "advanced"]);
  document.querySelectorAll(".drawer-tab").forEach((btn) => {
    btn.classList.toggle("hidden", isCollaborator() && hide.has(btn.dataset.panel));
  });
  document.querySelectorAll(".stage-btn").forEach((btn) => {
    if (btn.dataset.stage === "tools") {
      btn.classList.toggle("hidden", isCollaborator() && !sharePerm("engines_view"));
    }
  });
  paintAddCeoControls();
}

function syncHermesHint() {
  const toolsOpen = stage === "hermes" || stage === "opencode";
  const show = toolsOpen && (!gatewayRunning || hermesFailed);
  const hint = $("hermesHint");
  if (hint) hint.classList.toggle("hidden", !show);
  const retry = $("retryHermes");
  if (retry) {
    retry.classList.toggle("hidden", !show);
    retry.textContent = "Restart";
  }
  if (show && !gatewayRunning && $("hermesStatus") && !hermesFailed) {
    $("hermesStatus").textContent = "Hermes gateway is off.";
  }
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
  } else if (stage === "opencode" || stage === "hermes") {
    next = `#tools/${stage}`;
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
    if (raw === "tools" || raw.startsWith("tools/")) {
      const tool = raw.split("/")[1] || lastTool || "opencode";
      setStage(tool === "hermes" ? "hermes" : "opencode");
      return;
    }
    if (raw === "opencode" || raw === "hermes") setStage(raw);
    else setStage("chat");
  } finally {
    applyingHash = false;
  }
}

function setStage(name) {
  if (name === "tools") name = lastTool === "hermes" ? "hermes" : "opencode";
  if (name === "opencode" || name === "hermes") lastTool = name;
  stage = name;
  document.querySelectorAll(".stage-btn").forEach((btn) => {
    const slot = btn.dataset.stage;
    btn.classList.toggle("on", slot === name || (slot === "tools" && (name === "opencode" || name === "hermes")));
  });
  document.querySelectorAll(".workspace").forEach((el) => {
    el.classList.toggle("on", el.id === `stage-${name}`);
  });
  document.querySelectorAll(".tool-tab").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.stage === name);
  });
  syncHermesHint();
  if (name === "opencode") startOpenCode();
  if (name === "hermes") startHermes();
  paintPulse();
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
  const hide = new Set(["folder", "keys", "import", "channels", "git", "models", "connectors", "routines", "advanced"]);
  if (isCollaborator() && hide.has(name)) name = "you";
  const title = PANEL_TITLES[name] || "Settings";
  $("settingsTitle").textContent = title;
  document.querySelectorAll(".drawer-tab").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.panel === name);
    const panel = btn.dataset.panel;
    btn.classList.toggle("hidden", isCollaborator() && hide.has(panel));
  });
  document.querySelectorAll(".stage-btn").forEach((btn) => {
    if (btn.dataset.stage === "tools") {
      btn.classList.toggle("hidden", isCollaborator() && !sharePerm("engines_view"));
    }
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
  if (name === "help") paintHelpPanel();
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
  lastSchedulePid = String(projectId || "");
  const desk = activityBody();
  if (desk && scheduleOpen) {
    const who = projectId ? prettyCeoName(projectId, (currentProject() || {}).name) : "Chief of Staff";
    desk.innerHTML = `<p class="cron-empty">Loading ${escapeHtml(who)}…</p>`;
  }
  preset = "cos";
  focusedLane = "";
  unreadLanes = new Set();
  if (projectId) {
    lastCeoId = projectId;
    expanded.add(projectId);
  }
  syncLiveFromAim();
  paintOrgSelection();
  renderOrg(org);
  renderBotMeta({ skipSpend: true });
  const cached = threadCache.get(aimKey());
  if (cached) renderTurns(cached.turns, { telegram: cached.telegram || [], note: cached.note || "" });
  loadCeoDigest();
  await loadThread();
  syncComposerWho();
  scrollChatBottom();
  startOpenCode();
  startHermes();
  if (applySavedWork()) openSchedule("");
  else closeSchedule();
  if (!liveRunId) await drainQueue();
}

function guessLane(text) {
  const t = String(text || "");
  if (/\b(cron|schedule|every day|daily|weekly)\b/i.test(t)) return "ops";
  if (/https?:\/\//i.test(t) || /\b(look up|research|fetch url)\b/i.test(t)) return "research";
  if (/\b(code|diff|patch|refactor|implement|fix the)\b/i.test(t)) return "builder";
  if (/\b(think|why|explain|plan)\b/i.test(t)) return "think";
  return "cos";
}

function paintRouteHatch() {
  const sum = $("routeHatchSummary");
  const menu = $("routeMenu");
  const hatch = $("routeHatch");
  const forced = Boolean(preset && preset !== "cos");
  if (menu) {
    menu.querySelectorAll("[data-route]").forEach((btn) => {
      btn.classList.toggle("on", (btn.getAttribute("data-route") || "cos") === (preset || "cos"));
    });
  }
  // Cos routes from the message. Hatch is only for an explicit force (@mention / reply lane).
  if (hatch) {
    hatch.hidden = !forced;
    if (!forced) hatch.open = false;
  }
  if (!sum) return;
  if (forced) {
    sum.textContent = jobLabel(preset);
    sum.classList.add("forced");
  } else {
    sum.textContent = "Auto";
    sum.classList.remove("forced");
  }
}

function setRoute(name) {
  preset = name || "cos";
  if (preset && preset !== "cos") unreadLanes.delete(preset);
  const hatch = $("routeHatch");
  if (hatch) hatch.open = false;
  paintRouteHatch();
  renderBotMeta();
  scrollChatBottom();
}

function card(kind, body, meta) {
  const el = document.createElement("article");
  el.className = `card ${kind}`;
  // Clean bot responses (ops/think/research jobs) before display
  const cleaned = kind.includes("bot") ? formatBotHtml(body) : `<pre>${escapeHtml(body)}</pre>`;
  const head = meta ? `<div class="meta">${escapeHtml(meta)}</div>` : "";
  el.innerHTML = `${head}${kind.includes("bot") ? `<div class="bubble-text">${cleaned}</div>` : cleaned}`;
  stream.appendChild(el);
  stream.scrollTop = stream.scrollHeight;
  return el;
}

function bubble(kind, body, actor) {
  const el = document.createElement("article");
  el.className = `bubble ${kind}`;
  const label = actorLabel(actor);
  if (kind === "user" && label) {
    const tag = document.createElement("span");
    tag.className = "actor-tag";
    tag.textContent = label;
    el.appendChild(tag);
  }
  const text = document.createElement("div");
  text.className = "bubble-text";
  if (kind === "bot") paintBotText(text, body);
  else text.textContent = body || "";
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

function appendReceipt(el, job) {
  if (!el || !job || el.querySelector(".receipt-line")) return;
  const engine = String(job.engine || PRESET_ENGINE[job.preset] || "board");
  const cost = Number(job.usd_estimate || 0);
  if ((engine === "board" || job.preset === "cos") && !cost && !job.cron) return;
  const line = receiptLine(job);
  if (!line) return;
  const rec = document.createElement("p");
  rec.className = "receipt receipt-line";
  if (/^Failed\b/.test(line)) rec.classList.add("warn");
  if (/^Running\b/.test(line)) rec.classList.add("on");
  rec.textContent = line;
  el.appendChild(rec);
}

function appendWorkDetails(el, job) {
  if (!el || !job || el.querySelector(".done-fold")) return;
  const engine = String(job.engine || PRESET_ENGINE[job.preset] || "board");
  const cost = Number(job.usd_estimate || 0);
  if ((engine === "board" || job.preset === "cos") && !cost && !job.cron) return;
  const line = receiptLine(job);
  if (!line) return;
  const failed = jobIsFailed(job) || /^Failed\b/.test(line);
  const fold = document.createElement("details");
  fold.className = "done-fold bubble-work";
  const sum = document.createElement("summary");
  sum.textContent = failed ? "Failed" : "Done";
  fold.appendChild(sum);
  const rec = document.createElement("p");
  rec.className = "receipt receipt-line";
  if (failed) rec.classList.add("warn");
  rec.textContent = line;
  fold.appendChild(rec);
  const raw = String(job.text || "").trim();
  if (failed && raw && humanFailReason(`${job.blocker || ""} ${raw}`) !== cleanBotText(raw)) {
    const more = document.createElement("details");
    more.className = "cron-more";
    more.innerHTML = `<summary>Details</summary><pre></pre>`;
    more.querySelector("pre").textContent = raw.slice(0, 4000);
    fold.appendChild(more);
  }
  el.appendChild(fold);
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
    if (text) paintBotText(text, job.text || "");
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
  think.innerHTML = `<span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="thinking-label">${escapeHtml(`Running · ${talkName()}`)}</span>`;
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
  if (!job) return "";
  if (job.login_wall) return "This site asked for a login.";
  if (jobIsFailed(job)) {
    return `Failed · ${humanFailReason(`${job.blocker || ""} ${job.text || ""}`)}`;
  }
  const hasDiff = Boolean((job.diff && String(job.diff).trim()) || (job.untracked && job.untracked.length) || job.diff_pending);
  if (hasDiff) return "A code change is ready. Accept to keep it or Reject to undo.";
  if (job.blocker && String(job.blocker) !== "ok") return String(job.blocker);
  return "";
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
  if (job.id) {
    el.setAttribute("data-job-id", job.id);
  }
  stampLane(el, job);
  appendWorkDetails(el, job);
  const choices = jobChoices(job);
  if (choices.length && !el.querySelector(".need-actions")) {
    const actions = document.createElement("div");
    actions.className = "job-actions need-actions";
    actions.innerHTML = choiceButtonsHtml(choices, job);
    actions.querySelectorAll("[data-need-act]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        runNeedChoice(btn);
      });
    });
    el.appendChild(actions);
  }
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
  pollActivity();
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
  return null;
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
  // Clean bot text before display (ops/think/research jobs can have Meta junk)
  const text = cleanBotText(String(job.text || "")).trim();
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
      const val = cleanBotText(String(job.index_now)).trim();
      rows.push(`<div><dt>Now</dt><dd class="${val === "—" ? "empty" : ""}">${escapeHtml(val)}</dd></div>`);
    }
    if (job.index_last) {
      const val = cleanBotText(String(job.index_last)).trim();
      rows.push(`<div><dt>Last</dt><dd class="${val === "—" ? "empty" : ""}">${escapeHtml(val)}</dd></div>`);
    }
    if (job.next) {
      const val = cleanBotText(String(job.next)).trim();
      rows.push(`<div><dt>Next</dt><dd class="${val === "—" ? "empty" : ""}">${escapeHtml(val)}</dd></div>`);
    }
    if (job.index_blocker) {
      const val = cleanBotText(String(job.index_blocker)).trim();
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
  if (chatLaneNoise(job)) return;
  if (isTalk(job)) {
    renderTalk(job);
    return;
  }
  if (job.cron) {
    // Chat is talk. Cron landings live in Results.
    return;
  }
  const kind = job.login_wall ? "bot wall" : "bot";
  const body = job.login_wall && !job.text
    ? "This page needs a login. Approve a vault login, type it on this card, or sign in on your screen."
    : primaryJobBody(job);
  const el = card(kind, body, jobMeta(job));
  if (job.id) {
    el.setAttribute("data-job-id", job.id);
  }
  stampLane(el, job);
  appendWorkDetails(el, job);
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
  
  // Add Replay verbose and View raw log buttons for jobs with session logs
  if (job.id && job.has_session_log) {
    const replayBtn = document.createElement("button");
    replayBtn.type = "button";
    replayBtn.className = "ghost-btn";
    replayBtn.textContent = "Replay verbose";
    replayBtn.addEventListener("click", () => showReplayModal(job.id));
    actions.appendChild(replayBtn);
    
    const viewLogBtn = document.createElement("button");
    viewLogBtn.type = "button";
    viewLogBtn.className = "ghost-btn";
    viewLogBtn.textContent = "View raw log";
    viewLogBtn.addEventListener("click", () => viewRawLog(job.id));
    actions.appendChild(viewLogBtn);
  }

  if (jobIsFailed(job)) {
    const failActs = document.createElement("div");
    failActs.className = "need-actions";
    failActs.innerHTML = choiceButtonsHtml(jobChoices(job), job);
    failActs.querySelectorAll("[data-need-act]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        runNeedChoice(btn);
      });
    });
    actions.appendChild(failActs);
  }
  
  if (job.login_wall && job.url) {
    const open = document.createElement("a");
    open.className = "send";
    open.href = job.url;
    open.target = "_blank";
    open.rel = "noreferrer";
    open.textContent = "Open page";
    actions.appendChild(open);
  }
  if (job.keep_going && !job.stopped && (job.login_wall || !hydratingHistory)) {
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
  const gateKind = gateLineKind(job);
  if (gateKind) {
    const line = document.createElement("p");
    line.className = `gate-line ${(job.gate && job.gate.action) || ""}`;
    line.textContent = gateKind === "parked"
      ? "This is parked until you say yes — send, publish, pay, or delete."
      : "A draft is ready in files. Nothing public yet.";
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
  diffBlock.innerHTML = `<div class="meta">action gate · Accept keeps the local diff · Reject restores</div><details class="diff-fold"><summary>See change</summary><pre class="diff">${escapeHtml(job.diff || "(untracked files only)")}</pre></details>`;
  if (job.diff_pending) {
    const diffActions = document.createElement("div");
    diffActions.className = "diff-actions";
    
    // Optional controls
    const controls = document.createElement("div");
    controls.className = "diff-controls";
    controls.style.marginBottom = "10px";
    controls.style.fontSize = "14px";
    
    const pushLabel = document.createElement("label");
    pushLabel.style.marginRight = "15px";
    pushLabel.style.cursor = "pointer";
    const pushCheck = document.createElement("input");
    pushCheck.type = "checkbox";
    pushCheck.id = `push-${job.id}`;
    pushCheck.style.marginRight = "5px";
    pushLabel.appendChild(pushCheck);
    pushLabel.appendChild(document.createTextNode("Push branch + open PR"));
    
    const testLabel = document.createElement("label");
    testLabel.style.cursor = "pointer";
    const testCheck = document.createElement("input");
    testCheck.type = "checkbox";
    testCheck.id = `test-${job.id}`;
    testCheck.style.marginRight = "5px";
    testLabel.appendChild(testCheck);
    testLabel.appendChild(document.createTextNode("Run tests after Accept"));
    
    controls.appendChild(pushLabel);
    controls.appendChild(testLabel);
    
    const accept = document.createElement("button");
    accept.type = "button";
    accept.className = "send";
    accept.textContent = "Accept";
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "ghost-btn";
    reject.textContent = "Reject";
    accept.addEventListener("click", () => {
      const pushBranch = document.getElementById(`push-${job.id}`).checked;
      const runTests = document.getElementById(`test-${job.id}`).checked;
      decide(job.id, "accept", diffActions, false, pushBranch, runTests);
    });
    reject.addEventListener("click", () => decide(job.id, "reject", diffActions));
    diffActions.appendChild(controls);
    diffActions.appendChild(accept);
    diffActions.appendChild(reject);
    diffBlock.appendChild(diffActions);
  } else if (job.accepted && !job.reverted && !job.rejected) {
    // Show Revert button for accepted diffs (not yet reverted)
    const revertActions = document.createElement("div");
    revertActions.className = "diff-actions";
    const revert = document.createElement("button");
    revert.type = "button";
    revert.className = "ghost-btn revert-btn";
    revert.textContent = "Revert Accept";
    revert.addEventListener("click", () => revertDiff(job.id, revertActions));
    revertActions.appendChild(revert);
    diffBlock.appendChild(revertActions);
  }
  el.appendChild(diffBlock);
}

function chatLaneNoise(job) {
  if (!job) return false;
  if (job.cron || cronJobIsNoise(job)) return true;
  if (job.login_wall || job.diff_pending) return false;
  if (jobIsFailed(job)) return false;
  if ((job.preset === "ops" || job.preset === "think") && opaqueLaneOk(job.text, job.preset)) return true;
  return false;
}

function cronJobIsNoise(job) {
  const name = String((job && (job.cron_name || job.name)) || "").trim();
  const slug = name.replace(/\s+/g, "-").toLowerCase();
  return cronIsNoise({ name }) || cronIsNoise({ name: slug })
    || /^(grok heartbeat|grok finish notify|grok build supervisor|grok build driver|alerts email outbox)$/i.test(name);
}

function isE2ePing(text) {
  const raw = String(text || "");
  if (!raw.trim()) return false;
  if (/SMOKE\d+_/i.test(raw)) return true;
  if (/Reply with exactly/i.test(raw)) return true;
  if (/Ignore (?:any )?banners/i.test(raw) && /_OK|SMOKE/i.test(raw)) return true;
  if (/https?:\/\/example\.com/i.test(raw) && /SMOKE|_OK|look at this site/i.test(raw)) return true;
  if (/e2e_wc8_|e2e_test_routine|WC8-|Create file e2e_/i.test(raw)) return true;
  return false;
}

function isNoiseText(text) {
  const raw = String(text || "");
  if (!raw.trim()) return true;
  if (isE2ePing(raw)) return true;
  if (/Saved inbox\/ops\.md/i.test(raw)) return true;
  if (/hermes cron list/i.test(raw)) return true;
  if (/List every cron\/schedule\/routine/i.test(raw)) return true;
  if (/pipeline-health/.test(raw) && /indexation-patrol/.test(raw) && (/[┌│]/.test(raw) || /hermes cron list/i.test(raw))) return true;
  if (/Scheduled Jobs/.test(raw) && /[┌│]/.test(raw)) return true;
  if (/Gateway reports not running/i.test(raw)) return true;
  if (/raw\.githubusercontent\.com\/adamsch0100\/openbot/i.test(raw)) return true;
  if (/Nadia Marketing/i.test(raw) && /SEO pulse/i.test(raw)) return true;
  if (/need your google.{0,40}password/i.test(raw)) return true;
  if (/share your GBP login credentials/i.test(raw)) return true;
  const cleaned = cleanBotText(raw);
  if (!cleaned) return true;
  if (cleaned.length < 80 && PACKET_LINE.test(cleaned)) return true;
  return false;
}

function isNoiseTurn(turn) {
  if (!turn) return true;
  const job = turn.job || {};
  const text = job.text || turn.text || "";
  const message = job.message || "";
  if (isE2ePing(text) || isE2ePing(message)) return true;
  if (turn.role === "user") return !String(turn.text || "").trim();
  if (job.cron || cronJobIsNoise(job) || chatLaneNoise(job)) return true;
  if (projectId && job.project_id && String(job.project_id) !== String(projectId)) return true;
  return isNoiseText(text) || isNoiseText(message);
}

function emptyStreamHtml() {
  const project = currentProject();
  const worker = currentWorker();
  const text = cleanBotText(selectedIndexText());
  const now = briefHonestyLine(text);
  const blocked = (text.match(/^Blocker:\s*(.*)$/m) || [])[1] || "";
  const stuck = blocked && blocked !== "—" ? blocked : "";
  const title = worker ? worker.name : project ? project.name : "Chief of Staff";
  // Chat-as-home: no Ready fluff, no duplicate kicker chrome.
  let lead = "Ask what’s going on, or open a CEO.";
  let showCTA = !project;
  if (worker && project) {
    lead = `${worker.name} on ${project.name}. Say what you need.`;
    showCTA = false;
  } else if (project) {
    lead = "Say what you need.";
    showCTA = false;
  }
  const showNow = now && now !== "source of truth" && now !== "—" && !isScheduleFluff(now);
  const nowLine = showNow ? `<p class="empty-now">${escapeHtml(now)}</p>` : "";
  const stuckLine = stuck ? `<p class="empty-block">${escapeHtml(stuck)}</p>` : "";
  return `
    <div class="empty-stream" id="streamEmpty">
      <img class="empty-mark" src="/otto.png?v=5" alt="OttoBot" width="44" height="44" />
      <h1>${escapeHtml(title)}</h1>
      ${nowLine}
      ${stuckLine}
      <p>${escapeHtml(lead)}</p>
      ${showCTA ? '<button type="button" class="mobile-cta" id="mobileCeoPickerCTA">Open a CEO</button>' : ""}
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
    // Wire mobile CTA to open drawer
    const cta = document.getElementById("mobileCeoPickerCTA");
    if (cta) {
      cta.addEventListener("click", () => {
        const rail = $("rail");
        const scrim = $("railScrim");
        if (rail && scrim) {
          openOrgRail();
        }
      });
    }
    return;
  }
  stream.innerHTML = "";
  const telegramKeep = (telegram || []).filter((turn) => !isNoiseText(turn.text || "")).slice(-4);
  if (telegramKeep.length) {
    const banner = document.createElement("p");
    banner.className = "channel-banner";
    banner.textContent = "From Telegram. Replies stay on this board.";
    stream.appendChild(banner);
    telegramKeep.forEach((turn) => {
      const el = bubble(turn.role === "user" ? "user" : "bot", turn.text || "");
      if (turn.role !== "user") el.classList.add("from-telegram");
    });
  }
  let lastBot = "";
  rows.forEach((turn, index) => {
    if (isNoiseTurn(turn)) return;
    if (turn.role === "user") {
      lastBot = "";
      const el = bubble("user", turn.text || "", turn.actor);
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
  const prev = threadCache.get(key) || {};
  threadCache.set(key, { turns, telegram: prev.telegram || [], note: prev.note || "" });
  const keepLive = Boolean(liveFor(key));
  if (!keepLive) {
    renderTurns(turns, { telegram: prev.telegram || [], note: prev.note || "" });
  }
  if (!projectId || workerId) return;
  try {
    const channelRes = await fetch(`/api/org/projects/${encodeURIComponent(projectId)}/channel`);
    const channel = await channelRes.json();
    if (aimKey() !== key) return;
    const telegram = channel.turns || [];
    const note = channel.note || "";
    threadCache.set(key, { turns, telegram, note });
    if (!keepLive && !liveFor(key)) {
      renderTurns(turns, { telegram, note });
    }
  } catch (_err) {
    /* keep local thread */
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

async function decide(jobId, action, actionsEl, force = false, pushBranch = false, runTests = false) {
  actionsEl.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const res = await fetch(`/api/jobs/${jobId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: force, push_branch: pushBranch, run_tests: runTests })
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
  
  // Handle test failure with rollback offer
  if (data.ok && data.test_failed) {
    const testFailCard = document.createElement("div");
    testFailCard.className = "card card-blocker";
    testFailCard.innerHTML = `
      <div class="meta">tests failed · ${escapeHtml(data.test_command || "tests")}</div>
      <pre class="validation-error">${escapeHtml(data.test_output || "tests failed")}</pre>
      <div class="actions">
        <button type="button" class="send" id="revertFailed-${jobId}">Revert Accept</button>
        <button type="button" class="ghost-btn" id="keepFailed-${jobId}">Keep Anyway</button>
      </div>
    `;
    stream.appendChild(testFailCard);
    
    const revertBtn = document.getElementById(`revertFailed-${jobId}`);
    const keepBtn = document.getElementById(`keepFailed-${jobId}`);
    if (revertBtn) {
      revertBtn.addEventListener("click", () => {
        testFailCard.remove();
        revertDiff(jobId, actionsEl);
      });
    }
    if (keepBtn) {
      keepBtn.addEventListener("click", () => {
        testFailCard.remove();
      });
    }
    pollActivity();
    return;
  }
  
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
  pollActivity();
}

async function revertDiff(jobId, actionsEl) {
  actionsEl.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  const res = await fetch(`/api/jobs/${jobId}/revert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
  const data = await res.json();
  
  if (data.index) renderIndex(data.index);
  if (data.spend) renderSpend(data.spend);
  
  const statusText = data.ok
    ? "diff reverted · restored git snapshot"
    : (data.error || "revert failed");
  card("bot", statusText, `job ${jobId}`);
  
  // Show inline Brief update after Revert
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
  
  pollActivity();
}

async function loadJobs() {
  // Fetch spend dashboard data
  const dashRes = await fetch("/api/spend/dashboard");
  const dashData = await dashRes.json();
  
  // Render per-CEO breakdown
  const breakdown = dashData.breakdown || {};
  const ceos = breakdown.ceos || [];
  const alerts = dashData.alerts || {};
  const trends = dashData.trends || {};
  
  let html = "";
  
  // Alerts section
  if (alerts.has_alerts) {
    html += `<div class="spend-alerts">`;
    html += `<h4>Spend Alerts</h4>`;
    for (const alert of alerts.alerts || []) {
      const badge = alert.kind === "error" ? "🔴" : "⚠️";
      const className = alert.kind === "error" ? "spend-alert-error" : "spend-alert-warning";
      html += `<div class="${className}">${badge} ${escapeHtml(alert.message)}</div>`;
    }
    html += `</div>`;
  }
  
  // Per-CEO breakdown
  if (ceos.length > 0) {
    html += `<div class="usage-card">`;
    html += `<h4>Per-CEO Spend (${breakdown.period || "week"})</h4>`;
    html += `<table class="spend-table">`;
    html += `<thead><tr>`;
    html += `<th>CEO</th>`;
    html += `<th>Weekly</th>`;
    html += `<th>Monthly</th>`;
    html += `<th>Total</th>`;
    html += `<th>Status</th>`;
    html += `</tr></thead>`;
    html += `<tbody>`;
    for (const ceo of ceos) {
      const statusBadge = ceo.at_cap ? "🔴 Cap" : ceo.alert_50_percent ? "⚠️ 50%" : "✅";
      html += `<tr>`;
      html += `<td>${escapeHtml(ceo.name)}</td>`;
      html += `<td>$${ceo.weekly_usd.toFixed(2)}</td>`;
      html += `<td>$${ceo.monthly_usd.toFixed(2)}</td>`;
      html += `<td>$${ceo.total_usd.toFixed(2)}</td>`;
      html += `<td>${statusBadge}</td>`;
      html += `</tr>`;
    }
    html += `</tbody></table>`;
    html += `</div>`;
  }
  
  // Week-over-week trend charts
  if (Object.keys(trends).length > 0) {
    html += `<div class="usage-card">`;
    html += `<h4>Week-over-Week Trend (Last 14 Days)</h4>`;
    for (const ceoId in trends) {
      const trend = trends[ceoId];
      const ceo = ceos.find(c => c.id === ceoId);
      if (!ceo) continue;
      
      html += `<div class="trend-chart">`;
      html += `<h5>${escapeHtml(ceo.name)}</h5>`;
      html += renderTrendChart(trend.series, ceo.name);
      html += `</div>`;
    }
    html += `</div>`;
  }
  
  $("spendBreak").innerHTML = html;
  
  // Keep job log as before
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

function renderTrendChart(series, ceoName) {
  if (!series || series.length === 0) return `<p class="muted">No data</p>`;
  
  const maxUsd = Math.max(...series.map(d => d.usd), 0.01);
  const width = 600;
  const height = 120;
  const padding = { left: 50, right: 20, top: 20, bottom: 30 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  
  // Generate SVG line chart
  let svg = `<svg width="${width}" height="${height}" class="trend-svg">`;
  
  // Y-axis labels
  svg += `<text x="5" y="${padding.top}" font-size="10" fill="#666">$${maxUsd.toFixed(2)}</text>`;
  svg += `<text x="5" y="${padding.top + chartHeight}" font-size="10" fill="#666">$0</text>`;
  
  // Line path
  const points = series.map((d, i) => {
    const x = padding.left + (i / (series.length - 1)) * chartWidth;
    const y = padding.top + chartHeight - (d.usd / maxUsd) * chartHeight;
    return `${x},${y}`;
  });
  svg += `<polyline points="${points.join(' ')}" fill="none" stroke="#4A90E2" stroke-width="2"/>`;
  
  // Data points
  series.forEach((d, i) => {
    const x = padding.left + (i / (series.length - 1)) * chartWidth;
    const y = padding.top + chartHeight - (d.usd / maxUsd) * chartHeight;
    svg += `<circle cx="${x}" cy="${y}" r="3" fill="#4A90E2"/>`;
  });
  
  // X-axis labels (show every 3rd date to avoid crowding)
  series.forEach((d, i) => {
    if (i % 3 === 0 || i === series.length - 1) {
      const x = padding.left + (i / (series.length - 1)) * chartWidth;
      const dateLabel = d.date.slice(5); // MM-DD
      svg += `<text x="${x}" y="${padding.top + chartHeight + 20}" font-size="9" fill="#666" text-anchor="middle">${dateLabel}</text>`;
    }
  });
  
  svg += `</svg>`;
  return svg;
}

async function refreshProviders() {
  const res = await fetch("/api/providers");
  const data = await res.json();
  cfg.providers = data;
  fillSettings({ ...cfg, providers: data });
}

function currentAim() {
  const project = chatCeoProject();
  if (!project) {
    return { name: "Chat", folder: "", hermesHome: "", sessionId: "", idle: false, staff: false, projectId: "" };
  }
  lastCeoId = project.id || lastCeoId;
  const tools = project.tools || {};
  return {
    name: project.name,
    folder: project.folder_live || project.folder || "",
    hermesHome: tools.hermes_home_live || tools.hermes_home || "",
    sessionId: tools.hermes_session_id || "",
    idle: false,
    staff: false,
    projectId: project.id || ""
  };
}

function chatCeoProject() {
  const current = currentProject();
  if (current) {
    lastCeoId = current.id || lastCeoId;
    return current;
  }
  const list = ((org && org.projects) || []).filter((row) => row && row.id);
  if (lastCeoId) {
    const found = list.find((row) => row.id === lastCeoId);
    if (found) return found;
  }
  return list.find((row) => row.id === "saa-homes") || list.find((row) => row.id !== "support") || list[0] || null;
}

function frameUrlMatches(frame, url) {
  if (!frame || !url) return false;
  const src = frame.getAttribute("src") || "";
  if (!src || src === "about:blank") return false;
  try {
    const now = new URL(frame.src, location.href);
    const want = new URL(url, location.href);
    const trim = (path) => path.replace(/\/+$/, "") || "/";
    return trim(now.pathname) === trim(want.pathname) && now.search === want.search;
  } catch (_err) {
    return false;
  }
}

function engineFrameLive(frame) {
  if (!frame) return false;
  const src = frame.getAttribute("src") || "";
  return Boolean(src) && src !== "about:blank";
}

function shortLeaf(path) {
  const raw = String(path || "").trim().replace(/[\\/]+$/, "");
  if (!raw) return "";
  const parts = raw.split(/[\\/]/).filter(Boolean);
  const leaf = parts[parts.length - 1] || raw;
  return leaf.length > 48 ? `…${leaf.slice(-46)}` : leaf;
}

function setEmbedOpen(id, url) {
  const el = $(id);
  if (!el) return;
  if (!url) {
    el.classList.add("hidden");
    el.removeAttribute("href");
    return;
  }
  el.href = url;
  el.classList.remove("hidden");
}

function paintEmbedAim(id, line, html) {
  const el = $(id);
  if (!el) return;
  if (html) el.innerHTML = html;
  else el.textContent = line || "";
}

function reloadEngineFrame(frameId, url, token) {
  const frame = $(frameId);
  if (!frame || !url) return;
  const prev = frame.getAttribute("data-aim") || "";
  if (prev === token && frameUrlMatches(frame, url)) return;
  frame.setAttribute("data-aim", token);
  if (frameUrlMatches(frame, url)) return;
  frame.src = url;
}

function calmAimLine(name, folder) {
  const pretty = String(name || "").trim();
  const leaf = shortLeaf(folder);
  if (!leaf) return pretty || "Ready";
  if (!pretty) return leaf;
  if (pretty.toLowerCase() === leaf.toLowerCase()) return pretty;
  const slug = pretty.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (slug && (slug === leaf.toLowerCase() || leaf.toLowerCase() === slug)) return pretty;
  return pretty;
}

async function startOpenCode() {
  const aim = currentAim();
  const folder = aim.folder || (($("folder") && $("folder").value.trim()) || lastOcFolder || null);
  if ($("ocTitle")) $("ocTitle").textContent = "OpenCode";
  if (!ocStarted) {
    paintEmbedAim("ocStatus", folder ? `Starting · ${calmAimLine(aim.name, folder)}` : "Starting…");
  }
  const res = await fetch("/api/engines/opencode/web", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder, project_id: aim.projectId || projectId || "" })
  });
  const data = await res.json();
  if (!data.ok && !data.url) {
    setEmbedOpen("ocOpen", data.install || "");
    paintEmbedAim("ocStatus", "", `${escapeHtml(data.error || "OpenCode missing")}${data.install ? ` · <a href="${data.install}">install</a>` : ""}`);
    paintEmbedLive();
    return;
  }
  const url = data.url || "/engine/opencode/";
  const aimed = data.folder || folder || "";
  const sid = data.session_id || "";
  paintEmbedAim("ocStatus", aimed ? calmAimLine(aim.name, aimed) : "OpenCode is up.");
  setEmbedOpen("ocOpen", url);
  reloadEngineFrame("ocFrame", url, `${aimed}|${sid}`);
  lastOcFolder = aimed;
  ocStarted = true;
  paintPulse();
}

async function startHermes() {
  const aim = currentAim();
  const home = aim.hermesHome || "";
  const sid = aim.sessionId || "";
  if ($("hermesTitle")) $("hermesTitle").textContent = "Hermes";
  paintEmbedAim("hermesAim", "Starting…");
  hermesFailed = false;
  syncHermesHint();
  const res = await fetch("/api/engines/hermes/dashboard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hermes_home: home, project_id: aim.projectId || projectId || "" })
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    hermesFailed = true;
    const docs = data.install ? ` · <a href="${data.install}" target="_blank" rel="noreferrer">docs</a>` : "";
    if ($("hermesStatus")) $("hermesStatus").innerHTML = `${escapeHtml(data.error || "Hermes Agent missing")}${docs}`;
    setEmbedOpen("hermesOpen", data.install || "");
    paintEmbedAim("hermesAim", "", `${escapeHtml(data.error || "Hermes Agent missing")}${docs}`);
    syncHermesHint();
    paintEmbedLive();
    return;
  }
  const base = data.url || "/engine/hermes/";
  const aimed = data.home || home || "";
  const resume = data.session_id || sid || "";
  const prefix = String(base).replace(/\/+$/, "") || "/engine/hermes";
  const url = resume ? `${prefix}/chat?resume=${encodeURIComponent(resume)}` : `${prefix}/`;
  hermesFailed = false;
  if ($("hermesStatus")) $("hermesStatus").textContent = "";
  const count = Number(data.session_count || 0);
  const title = String(data.session_title || "").trim();
  const bits = [aimed ? calmAimLine(aim.name, aimed) : (aim.name || "Home attached")];
  if (count) bits.push(`${count.toLocaleString()} sessions`);
  if (title) bits.push(`Telegram · ${title}`);
  paintEmbedAim("hermesAim", bits.join(" · "));
  setEmbedOpen("hermesOpen", url);
  syncHermesHint();
  reloadEngineFrame("hermesFrame", url, `${aimed}|${resume}`);
  lastHermesHome = aimed;
  hermesStarted = true;
  paintPulse();
}

function attachEngineFrames(data) {
  const ocUrl = data.opencode_web && data.opencode_web.url;
  if (ocUrl) {
    paintEmbedAim("ocStatus", "OpenCode is up.");
    setEmbedOpen("ocOpen", ocUrl);
    if ($("ocFrame").src !== ocUrl) $("ocFrame").src = ocUrl;
    ocStarted = true;
  }
  const hermesUrl = data.hermes_dash && data.hermes_dash.url;
  if (hermesUrl) {
    hermesFailed = false;
    if ($("hermesStatus")) $("hermesStatus").textContent = "";
    paintEmbedAim("hermesAim", "Hermes is up.");
    setEmbedOpen("hermesOpen", hermesUrl);
    syncHermesHint();
    if ($("hermesFrame").src !== hermesUrl) $("hermesFrame").src = hermesUrl;
    hermesStarted = true;
  }
  paintEmbedLive();
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
        try { localStorage.removeItem("openbot_share_member"); } catch (_err) { /* ignore */ }
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

async function waitForShareInvite(token) {
  const gate = $("shareGate");
  if (!gate) return null;
  let preview = {};
  try {
    preview = await (await fetch(`/api/share/invite/${encodeURIComponent(token)}`)).json();
  } catch (_err) {
    preview = {};
  }
  if ($("shareTitle")) $("shareTitle").textContent = "Join this CEO";
  if ($("shareCopy")) {
    $("shareCopy").textContent = preview.project_name
      ? `${preview.operator_name || "Owner"} invited you to ${preview.project_name}. You help manage it; they still pay.`
      : "Someone invited you to help manage a CEO. You will not see keys or billing.";
  }
  if ($("shareSecretConfirmWrap")) $("shareSecretConfirmWrap").classList.remove("hidden");
  if ($("shareJoinBtn")) $("shareJoinBtn").textContent = "Join";
  gate.classList.remove("hidden");
  if ($("shareName")) $("shareName").focus();
  return new Promise((resolve) => {
    const submit = async () => {
      const name = ($("shareName") && $("shareName").value.trim()) || "";
      const secret = ($("shareSecret") && $("shareSecret").value) || "";
      const confirm = ($("shareSecretConfirm") && $("shareSecretConfirm").value) || "";
      if (secret.length < 4) {
        if ($("shareError")) $("shareError").textContent = "Secret must be at least 4 characters.";
        return;
      }
      if (confirm !== secret) {
        if ($("shareError")) $("shareError").textContent = "Secret and confirm do not match.";
        return;
      }
      const res = await fetch("/api/share/redeem", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, display_name: name, secret })
      });
      const data = await res.json();
      if (res.ok && !data.needs_unlock) {
        if (data.member && data.member.id) localStorage.setItem("openbot_share_member", data.member.id);
        gate.classList.add("hidden");
        history.replaceState(null, "", location.pathname);
        resolve(data);
        return;
      }
      if ($("shareError")) $("shareError").textContent = data.error || "invite failed";
    };
    if ($("shareJoinBtn")) $("shareJoinBtn").addEventListener("click", submit);
  });
}

async function waitForShareUnlock(memberId) {
  const gate = $("shareGate");
  if (!gate) return null;
  if ($("shareTitle")) $("shareTitle").textContent = "Unlock share";
  if ($("shareCopy")) $("shareCopy").textContent = "Enter the unlock secret for this shared CEO.";
  if ($("shareSecretConfirmWrap")) $("shareSecretConfirmWrap").classList.add("hidden");
  if ($("shareJoinBtn")) $("shareJoinBtn").textContent = "Open";
  const nameField = $("shareName");
  if (nameField && nameField.closest(".field")) nameField.closest(".field").classList.add("hidden");
  gate.classList.remove("hidden");
  if ($("shareSecret")) $("shareSecret").focus();
  return new Promise((resolve) => {
    const submit = async () => {
      const secret = ($("shareSecret") && $("shareSecret").value) || "";
      const res = await fetch("/api/share/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_id: memberId, secret })
      });
      const data = await res.json();
      if (res.ok && !data.needs_unlock) {
        gate.classList.add("hidden");
        resolve(data);
        return;
      }
      if ($("shareError")) $("shareError").textContent = data.error || "wrong secret";
    };
    if ($("shareJoinBtn")) $("shareJoinBtn").addEventListener("click", submit);
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

let digestTimer = 0;

function digestPollMs() {
  if (scheduleOpen || liveRunId) return 4000;
  const pack = digestCache.get(projectId) || {};
  if ((pack.crons || []).some((row) => cronIsLive(row))) return 4000;
  return 8000;
}

function startDigestPoll() {
  if (digestTimer) return;
  const tick = () => {
    loadCeoDigest(scheduleOpen);
    paintWorkTabs();
    digestTimer = window.setTimeout(tick, digestPollMs());
  };
  digestTimer = window.setTimeout(tick, 400);
}

function startLiveTick() {
  if (window.openbotLive || !window.EventSource) return;
  try {
    const es = new EventSource("/api/live");
    window.openbotLive = es;
    es.addEventListener("tick", (ev) => {
      let data = {};
      try { data = JSON.parse(ev.data); } catch (_err) { return; }
      if (data.activity) renderActivity(data.activity);
      if (data.people) cfg.people = data.people;
      paintPulse();
      paintWorkTabs();
      if (scheduleOpen) {
        const pack = digestCache.get(projectId) || {};
        if (String(lastSchedulePid || "") === String(projectId || "")) {
          renderChatSchedule(pack.crons || [], pack.digest || pack, scheduleFocusId, projectId);
        }
      }
    });
  } catch (_err) {
    window.openbotLive = null;
  }
}

async function boot() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  startDigestPoll();
  startLiveTick();
  const invite = new URLSearchParams(location.search).get("invite");
  if (invite) {
    const joined = await waitForShareInvite(invite);
    if (joined) {
      applyConfig(joined);
      showWizard({ first_run_done: true });
      const projects = (joined.org && joined.org.projects) || [];
      if (projects[0]) await setOrgNode(projects[0].id, "");
      await loadThread();
      pollActivity();
      sizeComposer();
      return;
    }
  }
  const memberId = localStorage.getItem("openbot_share_member");
  if (memberId) {
    let data = await (await fetch("/api/index")).json();
    if (data.actor === "collaborator") {
      applyConfig(data);
      showWizard({ first_run_done: true });
      const projects = (data.org && data.org.projects) || [];
      if (projects[0]) await setOrgNode(projects[0].id, "");
      await loadThread();
      pollActivity();
      sizeComposer();
      return;
    }
    if (data.needs_unlock) {
      const unlocked = await waitForShareUnlock(memberId);
      if (unlocked) {
        applyConfig(unlocked);
        showWizard({ first_run_done: true });
        const projects = (unlocked.org && unlocked.org.projects) || [];
        if (projects[0]) await setOrgNode(projects[0].id, "");
        await loadThread();
        pollActivity();
        sizeComposer();
        return;
      }
    }
  }
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
  paintRouteHatch();
  if (applySavedWork()) openSchedule("");
  if (location.hash) applyHash();
  window.addEventListener("hashchange", applyHash);
  window.setTimeout(() => {
    startOpenCode();
    startHermes();
  }, 200);
}

function setWizardStep(name) {
  const labels = {
    engines: "Engines",
    folder: "Folder",
    key: "Key",
    auth: "Authentication",
    test: "Test"
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
      const freshCron = [];
      (data.cron_jobs || []).forEach((job) => {
        if (job.project_id === projectId && job.id && !seenCron.has(job.id)) {
          renderJob(job);
          freshCron.push(job);
        }
      });
      if (freshCron.length) loadCeoDigest();
    }
    if (Array.isArray(data.live_runs)) {
      const pack = digestCache.get(projectId) || {};
      digestCache.set(projectId, Object.assign({}, pack, { live_runs: data.live_runs }));
      paintCeoLive(digestCache.get(projectId));
      paintWorkTabs();
      if (scheduleOpen && String(lastSchedulePid || "") === String(projectId || "")) {
        renderChatSchedule(pack.crons || [], pack.digest || pack, scheduleFocusId, projectId);
      }
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
  window.setTimeout(pollActivity, liveRunId ? 4000 : (window.openbotLive ? 12000 : 8000));
}

document.querySelectorAll(".stage-btn").forEach((btn) => {
  btn.addEventListener("click", () => setStage(btn.dataset.stage));
});
document.querySelectorAll(".tool-tab").forEach((btn) => {
  btn.addEventListener("click", () => setStage(btn.dataset.stage));
});
if ($("routeMenu")) {
  $("routeMenu").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-route]");
    if (!btn) return;
    event.preventDefault();
    setRoute(btn.getAttribute("data-route") || "cos");
  });
}
if ($("closeActivity")) {
  $("closeActivity").addEventListener("click", () => closeSchedule());
}
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
document.querySelectorAll(".work-tabs").forEach((tabs) => {
  if (tabs.dataset.workBound) return;
  tabs.dataset.workBound = "1";
  tabs.addEventListener("click", (event) => {
    const btn = event.target.closest(".work-tab");
    if (!btn) return;
    openWork(btn.getAttribute("data-work") || "doing");
  });
});
if ($("ceoLive") && !$("ceoLive").dataset.workBound) {
  $("ceoLive").dataset.workBound = "1";
  $("ceoLive").addEventListener("click", () => {
    const pack = digestCache.get(projectId) || {};
    const live = (pack.crons || []).some((row) => cronIsLive(row)) || (pack.live_runs || []).length || liveRunId;
    const counts = workCounts();
    if (live) openWork("doing");
    else if (prefersScheduleTrust(counts)) openWork("schedule");
    else openWork("results");
  });
}
if ($("chatSchedule") && !$("chatSchedule").dataset.retryBound) {
  $("chatSchedule").dataset.retryBound = "1";
  $("chatSchedule").addEventListener("click", async (event) => {
    const btn = event.target.closest(".cron-retry");
    if (!btn || !projectId) return;
    const jobId = btn.getAttribute("data-cron-id") || "";
    if (!jobId) return;
    btn.disabled = true;
    btn.textContent = "Retrying…";
    try {
      const res = await fetch("/api/crons/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId, job_id: jobId }),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        btn.textContent = data.error || data.text || "Retry failed";
        btn.disabled = false;
        return;
      }
      btn.textContent = "Running on live Hermes";
      await loadCeoDigest(true);
    } catch (_err) {
      btn.textContent = "Retry failed";
      btn.disabled = false;
    }
  });
}
$("openSettings").addEventListener("click", (event) => {
  event.stopPropagation();
  setSettings(true, "you");
});
if ($("settingsAddCeo")) {
  $("settingsAddCeo").addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    setSettings(false);
    openAddCeoMenu(event);
  });
}
if ($("openHelp")) {
  $("openHelp").addEventListener("click", (event) => {
    event.stopPropagation();
    setSettings(true, "help");
    setOrgNode("support", "");
  });
}
if ($("suggestForm")) {
  $("suggestForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = ($("suggestTitle") && $("suggestTitle").value) || "";
    const body = ($("suggestBody") && $("suggestBody").value) || "";
    const status = $("suggestStatus");
    try {
      const res = await fetch("/api/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body, source: "suggest" })
      });
      const data = await res.json();
      if (status) status.textContent = res.ok ? `ticket ${data.id} · ${data.phase}` : (data.error || "failed");
      if (res.ok) {
        if ($("suggestTitle")) $("suggestTitle").value = "";
        if ($("suggestBody")) $("suggestBody").value = "";
        const cfgRes = await fetch("/api/config");
        if (cfgRes.ok) applyConfig(await cfgRes.json());
      }
    } catch (err) {
      if (status) status.textContent = "failed";
    }
  });
}
$("closeSettings").addEventListener("click", () => setSettings(false));
$("settingsScrim").addEventListener("click", () => setSettings(false));
$("gotoOpenCode").addEventListener("click", () => openWorkspace("opencode"));
$("gotoHermes").addEventListener("click", () => openWorkspace("hermes"));
if ($("aboutOpenCode")) {
  $("aboutOpenCode").addEventListener("click", () => openWorkspace("opencode"));
}
$("retryHermes").addEventListener("click", () => {
  restartGateway();
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

if ($("refreshPair")) {
  $("refreshPair").addEventListener("click", () => {
    if ($("pairStatus")) $("pairStatus").textContent = "";
    fillPair();
  });
}
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

async function loadSelfBuildStatus() {
  try {
    const res = await fetch(`/api/selfbuild/status?project_id=`);
    if (!res.ok) return;
    const data = await res.json();
    const statusEl = $("selfBuildStatus");
    if (statusEl) {
      const parts = [];
      if (data.next_item) {
        parts.push(`Next: ${data.next_item.id} - ${data.next_item.name}`);
      } else {
        parts.push("Next: No unshipped ROADMAP items");
      }
      if (data.routine_exists) {
        parts.push(data.routine_enabled ? "Routine enabled" : "Routine disabled");
      } else {
        parts.push("Routine not created");
      }
      statusEl.textContent = parts.join(" · ");
    }
  } catch (err) {
    console.error("load self-build status failed:", err);
  }
}

if ($("saveAdvanced")) {
  $("saveAdvanced").addEventListener("click", async () => {
    const statusEl = $("advancedStatus");
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enable_self_build: $("enableSelfBuild").checked,
        x_intake_enabled: $("xIntakeEnabled") ? $("xIntakeEnabled").checked : false,
        x_username: $("xUsername") ? $("xUsername").value : ""
      })
    });
    const data = await res.json();
    if (statusEl) statusEl.textContent = res.ok ? "saved" : (data.error || "save failed");
    if (res.ok) {
      applyConfig(data);
      loadSelfBuildStatus();
    }
  });
}

if ($("ingestX")) {
  $("ingestX").addEventListener("click", async () => {
    const statusEl = $("xIntakeStatus");
    const res = await fetch("/api/x/ingest", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json();
    if (statusEl) {
      statusEl.textContent = data.ok
        ? `created ${(data.created || []).length}`
        : (data.reason || data.error || "failed");
    }
    if (data.ok) {
      const cfgRes = await fetch("/api/config");
      if (cfgRes.ok) applyConfig(await cfgRes.json());
    }
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

let connectorsCatalog = { skills: [], mcp: [], popularSkills: [] };

async function loadConnectorsCatalog() {
  try {
    const res = await fetch("/api/connectors/catalog");
    const data = await res.json();
    connectorsCatalog = {
      skills: data.skills || [],
      mcp: data.mcp || [],
      popularSkills: data.popular_skills || []
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
    let skillHtml = "";
    
    // Popular Skills section
    if (connectorsCatalog.popularSkills && connectorsCatalog.popularSkills.length > 0) {
      skillHtml += `<div class="popular-skills-section">
        <h4 class="drawer-sub">Popular Skills</h4>
        <p class="muted">Recommended for Think, Research, and Ops agents</p>
      </div>`;
      
      skillHtml += `<div class="connector-row connector-row-header">
        <div class="connector-name">Skill</div>
        <div class="connector-name-desc">Description</div>
        <div class="connector-cell">Think</div>
        <div class="connector-cell">Research</div>
        <div class="connector-cell">Ops</div>
        <div class="connector-cell">Chat</div>
      </div>`;
      
      connectorsCatalog.skills.forEach((skillObj) => {
        const skillName = typeof skillObj === 'string' ? skillObj : skillObj.name;
        const skillDesc = typeof skillObj === 'object' ? skillObj.description : '';
        if (!connectorsCatalog.popularSkills.includes(skillName)) return;
        
        const skillConfig = globalConnectors.skills[skillName] || {};
        skillHtml += `<div class="connector-row connector-row-popular">
          <div class="connector-name">${escapeHtml(skillName)}</div>
          <div class="connector-name-desc">${escapeHtml(skillDesc)}</div>`;
        
        seats.forEach((seat) => {
          const checked = skillConfig[seat] === true ? " checked" : "";
          skillHtml += `<div class="connector-cell">
            <label>
              <input type="checkbox" data-skill="${escapeHtml(skillName)}" data-seat="${seat}"${checked} />
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
      
      skillHtml += `<div class="popular-skills-divider">
        <h4 class="drawer-sub">All Skills</h4>
      </div>`;
    }
    
    // All skills section with header
    skillHtml += `<div class="connector-row connector-row-header">
      <div class="connector-name">Skill</div>
      <div class="connector-name-desc">Description</div>
      <div class="connector-cell">Think</div>
      <div class="connector-cell">Research</div>
      <div class="connector-cell">Ops</div>
      <div class="connector-cell">Chat</div>
    </div>`;
    
    connectorsCatalog.skills.forEach((skillObj) => {
      const skillName = typeof skillObj === 'string' ? skillObj : skillObj.name;
      const skillDesc = typeof skillObj === 'object' ? skillObj.description : '';
      const skillConfig = globalConnectors.skills[skillName] || {};
      
      skillHtml += `<div class="connector-row">
        <div class="connector-name">${escapeHtml(skillName)}</div>
        <div class="connector-name-desc">${escapeHtml(skillDesc)}</div>`;
      
      seats.forEach((seat) => {
        const checked = skillConfig[seat] === true ? " checked" : "";
        skillHtml += `<div class="connector-cell">
          <label>
            <input type="checkbox" data-skill="${escapeHtml(skillName)}" data-seat="${seat}"${checked} />
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
  const boardList = $("boardSkillsList");
  if (boardList) {
    fetch("/api/skills/board").then((r) => r.json()).then((data) => {
      const skills = data.skills || [];
      if (!skills.length) {
        boardList.innerHTML = `<p class="muted">No board Skills yet. Dogfood Skills seed on first org load.</p>`;
        return;
      }
      boardList.innerHTML = skills.map((skill) => `
        <div class="connector-row">
          <div class="connector-name">${escapeHtml(skill.name || "")}</div>
          <div class="connector-name-desc">${escapeHtml(skill.description || "")} · ${escapeHtml(skill.whenToUse || "")}</div>
        </div>`).join("");
    }).catch(() => {
      boardList.innerHTML = `<p class="muted">Board Skills unavailable.</p>`;
    });
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
  setWizardStep("auth");
  checkEngineAuth();
});
$("skipWizardKey").addEventListener("click", () => {
  setWizardStep("auth");
  checkEngineAuth();
});

async function checkEngineAuth() {
  try {
    const res = await fetch("/api/onboarding/status");
    const data = await res.json();
    
    const hermesCard = $("hermesAuthStatus");
    const opencodeCard = $("opencodeAuthStatus");
    
    if (data.hermes && data.hermes.authenticated) {
      hermesCard.innerHTML = `
        <div class="auth-status-icon">✅</div>
        <div class="auth-status-content">
          <div class="auth-status-label">Hermes Agent: Authenticated</div>
        </div>
      `;
    } else {
      hermesCard.innerHTML = `
        <div class="auth-status-icon">❌</div>
        <div class="auth-status-content">
          <div class="auth-status-label">Hermes Agent: Not Authenticated</div>
          <p class="muted">Run <code>hermes portal</code> in your terminal to authenticate with Nous Portal.</p>
          <button type="button" class="ghost-btn" onclick="window.open('https://portal.nousresearch.com', '_blank')">Authenticate Now</button>
        </div>
      `;
    }
    
    if (data.opencode && data.opencode.authenticated) {
      opencodeCard.innerHTML = `
        <div class="auth-status-icon">✅</div>
        <div class="auth-status-content">
          <div class="auth-status-label">OpenCode: Authenticated</div>
        </div>
      `;
    } else {
      opencodeCard.innerHTML = `
        <div class="auth-status-icon">❌</div>
        <div class="auth-status-content">
          <div class="auth-status-label">OpenCode: Not Authenticated</div>
          <p class="muted">Run <code>opencode auth login</code> in your terminal to authenticate with OpenCode.</p>
          <button type="button" class="ghost-btn" onclick="alert('Please open your terminal and run: opencode auth login')">Authenticate Now</button>
        </div>
      `;
    }
    
    if (data.ready) {
      $("wizardAuthNext").classList.remove("hidden");
    } else {
      $("wizardAuthNext").classList.add("hidden");
    }
  } catch (err) {
    console.error("[onboarding] auth check failed:", err);
  }
}

$("wizardAuthNext").addEventListener("click", () => {
  setWizardStep("test");
});

$("wizardAuthSkip").addEventListener("click", () => {
  setWizardStep("test");
});

$("runTestJob").addEventListener("click", async () => {
  $("testJobStatus").textContent = "Starting test job...";
  try {
    const res = await fetch("/api/onboarding/test-job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: projectId,
        worker_id: "builder"
      })
    });
    const data = await res.json();
    if (data.ok) {
      $("testJobStatus").textContent = "Test job running! Check the activity feed for results.";
      setTimeout(() => {
        $("firstRun").classList.add("hidden");
        init();
      }, 2000);
    } else {
      $("testJobStatus").textContent = data.error || "Test job failed";
    }
  } catch (err) {
    $("testJobStatus").textContent = "Network error: " + err.message;
  }
});

$("skipTestJob").addEventListener("click", () => {
  $("firstRun").classList.add("hidden");
  init();
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
    paintRouteHatch();
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
    if (queueFor().length) {
      await sendQueuedNow();
      return;
    }
    await stopLive();
  });
}
if ($("queueChipSend")) {
  $("queueChipSend").addEventListener("click", async (event) => {
    event.preventDefault();
    await sendQueuedNow();
  });
}
if ($("queueChipClear")) {
  $("queueChipClear").addEventListener("click", (event) => {
    event.preventDefault();
    const rows = queueFor();
    rows.forEach((row) => {
      if (row.userEl && row.userEl.isConnected) row.userEl.remove();
    });
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
  if (liveRunId && !(opts && opts.forceNew)) {
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
  let userEl = opts && opts.userEl;
  if (userEl) {
    userEl.classList.remove("queued");
    const wait = userEl.querySelector(".bubble-queued");
    if (wait) wait.remove();
  } else {
    userEl = bubble("user", displayMessage);
    if (pendingQuote) attachQuotePreview(userEl, pendingQuote);
  }
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
            if (textEl) paintBotText(textEl, liveText);
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
    try {
      if (progressWatchdog) clearTimeout(progressWatchdog);
      clearTimeout(maxWatchdog);
    } catch (_err) {
      /* timers already cleared */
    }
    const cur = liveFor(aim);
    if (!cur || cur.abort === ac) {
      setLive("", { key: aim, projectId: sendProjectId, workerId: sendWorkerId });
    }
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
  let routineTemplates = [];
  
  async function loadRoutineTemplates() {
    try {
      const res = await fetch("/api/routines/templates");
      if (!res.ok) throw new Error("load templates failed");
      const data = await res.json();
      routineTemplates = data.templates || [];
      renderTemplateDropdown();
    } catch (err) {
      console.error("load routine templates failed:", err);
    }
  }
  
  function renderTemplateDropdown() {
    const select = $("routineTemplate");
    if (!select) return;
    
    let html = '<option value="">Start from scratch...</option>';
    routineTemplates.forEach((template) => {
      html += `<option value="${escapeHtml(template.id)}">${escapeHtml(template.name)}</option>`;
    });
    select.innerHTML = html;
  }
  
  $("routineTemplate").addEventListener("change", () => {
    const templateId = $("routineTemplate").value;
    const descEl = $("routineTemplateDesc");
    
    if (!templateId) {
      if (descEl) descEl.textContent = "";
      return;
    }
    
    const template = routineTemplates.find((t) => t.id === templateId);
    if (!template) return;
    
    // Show template description
    if (descEl) {
      descEl.textContent = template.description || "";
    }
    
    // Load template into form
    $("routineName").value = template.name;
    $("routineSchedule").value = template.schedule;
    routineSteps = template.steps.map((step) => ({
      seat: step.seat,
      instruction: step.instruction
    }));
    renderRoutineSteps();
  });
  
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
  loadRoutineTemplates();
  loadRoutines();
}

// Mobile menu toggle
function closeOrgRail() {
  const rail = $("rail");
  const scrim = $("railScrim");
  if (rail) rail.classList.remove("open");
  if (scrim) {
    scrim.classList.remove("open");
    scrim.setAttribute("aria-hidden", "true");
  }
}

function openOrgRail() {
  const rail = $("rail");
  const scrim = $("railScrim");
  if (rail) rail.classList.add("open");
  if (scrim) {
    scrim.classList.add("open");
    scrim.setAttribute("aria-hidden", "false");
  }
}

function initMobileMenu() {
  const toggle = $("mobileOrgToggle");
  const rail = $("rail");
  const scrim = $("railScrim");
  
  if (!rail || !scrim) return;
  closeOrgRail();
  
  // Close rail when resizing to desktop — never leave scrim trapping clicks
  function updateMobileUI() {
    if (window.innerWidth > 860) closeOrgRail();
  }
  
  if (toggle) {
    toggle.addEventListener("click", () => {
      if (rail.classList.contains("open")) closeOrgRail();
      else openOrgRail();
    });
  }
  
  // Close on scrim click (immediate — no timeout trap)
  scrim.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    closeOrgRail();
  });
  
  // Close on CEO selection (so user sees chat immediately)
  const orgTree = $("orgTree");
  if (orgTree) {
    orgTree.addEventListener("click", (event) => {
      const btn = event.target.closest(".org-btn");
      if (btn && window.innerWidth <= 860) closeOrgRail();
    });
  }
  
  updateMobileUI();
  window.addEventListener("resize", updateMobileUI);
}

paintBoardMark();
boot().catch((err) => {
  renderIndex(String(err));
  loadOrgTree();
});

initMobileMenu();
