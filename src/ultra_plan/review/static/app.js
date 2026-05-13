let bundle = null;

const $ = (id) => document.getElementById(id);

async function load() {
  const r = await fetch("/bundle");
  bundle = await r.json();
  render();
}

function render() {
  $("task").textContent = bundle.task || "";
  renderItems("skills", bundle.skills || [], skillFields);
  renderItems("tools", bundle.tools || [], toolFields);
  $("perms").value = JSON.stringify(bundle.permissions || {}, null, 2);
  $("plan").value = bundle.plan_markdown || "";
  $("recs").value = bundle.prompt_recommendations || "";
  updateMeta();
}

function updateMeta() {
  const skills = bundle.skills || [];
  const tools = bundle.tools || [];
  const skillsOn = skills.filter((s) => s.enabled !== false).length;
  const toolsOn = tools.filter((t) => t.enabled !== false).length;
  $("skills-meta").textContent = skills.length ? `${skillsOn}/${skills.length} enabled` : "none";
  $("tools-meta").textContent = tools.length ? `${toolsOn}/${tools.length} enabled` : "none";
  const planLines = ($("plan").value.match(/\n/g) || []).length + ($("plan").value ? 1 : 0);
  const recsLines = ($("recs").value.match(/\n/g) || []).length + ($("recs").value ? 1 : 0);
  $("plan-meta").textContent = planLines ? `${planLines} lines` : "empty";
  $("recs-meta").textContent = recsLines ? `${recsLines} lines` : "empty";
}

const skillFields = ["name", "source_url", "origin", "install", "rationale"];
const toolFields = ["name", "kind", "source_url", "install", "auth", "rationale"];

function renderItems(kind, items, fields) {
  const container = $(kind);
  container.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = `No ${kind}.`;
    container.append(empty);
    return;
  }
  items.forEach((item) => {
    if (item.enabled === undefined) item.enabled = true;
    const card = document.createElement("details");
    card.className = "card" + (item.enabled ? "" : " disabled");

    const summary = document.createElement("summary");
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = item.enabled;
    toggle.onclick = (e) => e.stopPropagation();
    toggle.onchange = () => {
      item.enabled = toggle.checked;
      card.classList.toggle("disabled", !item.enabled);
      updateMeta();
    };
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.name || "(unnamed)";
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = item.kind || item.origin || item.rationale || "";
    summary.append(toggle, name, sub);
    card.append(summary);

    const body = document.createElement("div");
    body.className = "card-body";
    fields.forEach((f) => {
      const row = document.createElement("label");
      row.className = "field";
      row.textContent = f;
      const input = document.createElement(f === "rationale" || f === "install" ? "textarea" : "input");
      input.value = item[f] == null ? "" : item[f];
      input.oninput = () => {
        item[f] = input.value;
        if (f === "name") name.textContent = input.value || "(unnamed)";
        if (f === "kind" || f === "origin" || f === "rationale") {
          sub.textContent = item.kind || item.origin || item.rationale || "";
        }
      };
      row.append(input);
      body.append(row);
    });
    card.append(body);
    container.append(card);
  });
}

function collect() {
  try {
    bundle.permissions = JSON.parse($("perms").value);
  } catch (e) {
    setStatus("permissions JSON invalid: " + e.message, true);
    throw e;
  }
  bundle.plan_markdown = $("plan").value;
  bundle.prompt_recommendations = $("recs").value;
  return bundle;
}

function setStatus(msg, err) {
  const el = $("status");
  el.textContent = msg;
  el.className = err ? "err" : "ok";
}

$("save").onclick = async () => {
  const b = collect();
  const r = await fetch("/bundle", { method: "PUT", body: JSON.stringify(b) });
  setStatus(r.ok ? "saved" : "save failed", !r.ok);
};

$("confirm").onclick = async () => {
  const b = collect();
  const r = await fetch("/confirm", { method: "POST", body: JSON.stringify(b) });
  setStatus(r.ok ? "confirmed — artifacts written, server exiting" : "confirm failed", !r.ok);
};

$("expand-all").onclick = () => {
  document.querySelectorAll("details").forEach((d) => (d.open = true));
};
$("collapse-all").onclick = () => {
  document.querySelectorAll("details").forEach((d) => (d.open = false));
};

["plan", "recs"].forEach((id) => {
  document.addEventListener("input", (e) => {
    if (e.target && e.target.id === id) updateMeta();
  });
});

load();
