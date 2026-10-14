"use strict";
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ORDER = ["skills", "experience", "education", "responsibilities", "certifications"];
const BATCH = 10;               // files per request, so progress is real
let CFG = { weights: {}, labels: {}, max_file_mb: 10 };
let jobs = [];
let activeId = null;
let candidates = [];

// ------------------------------------------------------------ helpers
async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { /* non-JSON */ }
  if (!res.ok) throw new Error((body && body.error) || `Request failed (${res.status})`);
  return body;
}
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3200);
}
const atsBand = (s) => (s >= 75 ? "good" : s >= 55 ? "mid" : "low");
const atsText = { good: "Likely to pass", mid: "Borderline", low: "At risk" };
const band = (s) => (s >= 75 ? "good" : s >= 50 ? "mid" : "low");
const bandText = { good: "Strong", mid: "Moderate", low: "Low" };
function meter(score) {
  const b = band(score);
  return `<span class="meter" aria-hidden="true"><i class="m-${b}" style="width:${Math.max(0, Math.min(100, score))}%"></i></span>`;
}
const fmtPct = (v) => (v === null || v === undefined ? "n/a" : `${Math.round(v)}%`);
const list = (a) => (a && a.length ? a.map(esc).join(", ") : "—");

function wireDrop(zone, input, onFiles) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", (e) => onFiles([...e.dataTransfer.files]));
  input.addEventListener("change", () => { onFiles([...input.files]); input.value = ""; });
}

// --------------------------------------------------------------- jobs
async function loadJobs(selectId) {
  const data = await api("/api/jobs");
  jobs = data.jobs;
  $("st-all").textContent = data.counts.applicants;
  $("pool-n").textContent = data.counts.distinct_resumes;
  $("st-jobs").textContent = jobs.length;
  const sel = $("job-select");
  sel.innerHTML = jobs.length
    ? jobs.map((j) => `<option value="${j.id}">${esc(j.title)} (${j.candidate_count})</option>`).join("")
    : `<option value="">No jobs yet - upload a JDE</option>`;
  if (selectId) activeId = selectId;
  if (!jobs.some((j) => j.id === activeId)) activeId = jobs.length ? jobs[0].id : null;
  if (activeId) sel.value = String(activeId);
  $("job-delete").disabled = !activeId;
  $("cv-drop").style.opacity = activeId ? 1 : 0.5;
  await loadJob();
}
function activeJob() { return jobs.find((j) => j.id === activeId) || null; }

async function loadJob() {
  const job = activeJob();
  $("editor-card").hidden = !job;
  if (!job) { candidates = []; renderTable(); return; }
  fillEditor(job);
  await loadCandidates();
}

async function uploadJde(files) {
  const f = files[0]; if (!f) return;
  const msg = $("jde-msg"); msg.className = "msg"; msg.textContent = `Reading ${f.name}…`;
  const fd = new FormData(); fd.append("file", f);
  fd.append("reuse_resumes", $("reuse").checked ? "1" : "0");
  try {
    const { job, carried } = await api("/api/jobs/upload", { method: "POST", body: fd });
    msg.className = "msg ok";
    msg.textContent = "Job created and now active." + (carried ? ` ${carried} existing resume(s) were matched against it.` : "") + " Review the extracted requirements, then save.";
    await loadJobs(job.id);
    $("editor-card").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { msg.className = "msg err"; msg.textContent = e.message; }
}

// ------------------------------------------------------------- editor
function fillEditor(job) {
  const r = job.requirements;
  $("e-title").value = r.title || job.title;
  $("e-dept").value = r.department || "";
  // alternatives (same group) are written "SQL or MySQL or PostgreSQL" = any one is enough
  const skillText = (level) => {
    const out = []; const seenG = new Set();
    for (const s of r.skills.filter((x) => x.level === level)) {
      if (!s.group) { out.push(s.display || s.name); continue; }
      if (seenG.has(s.group)) continue;
      seenG.add(s.group);
      out.push(r.skills.filter((x) => x.group === s.group && x.level === level).map((x) => x.display || x.name).join(" or "));
    }
    return out.join(", ");
  };
  $("e-mand").value = skillText("mandatory");
  $("e-pref").value = skillText("preferred");
  $("e-years").value = r.min_experience_years ?? "";
  $("e-years-m").checked = r.experience_mandatory !== false;
  $("e-maxyears").value = r.max_experience_years ?? "";
  const rules = Object.assign({}, CFG.counting, r.experience_counting || {});
  $("counting").innerHTML = Object.keys(CFG.type_labels).map((k) =>
    `<label>${esc(CFG.type_labels[k])}<select data-c="${k}">${[[1, "Counts fully"], [0.5, "Counts half"], [0, "Not counted"]].map(([v, t]) => `<option value="${v}" ${Number(rules[k]) === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>`).join("");
  $("e-edu").value = r.education ? r.education.min_level : "";
  $("e-edu-m").checked = r.education ? r.education.mandatory !== false : true;
  $("e-field").value = (r.education && r.education.field) || "";
  $("e-cert-m").value = r.certifications.filter((c) => c.mandatory).map((c) => c.name).join("\n");
  $("e-cert-p").value = r.certifications.filter((c) => !c.mandatory).map((c) => c.name).join("\n");
  $("e-resp").value = (r.responsibilities || []).join("\n");
  const w = $("weights");
  w.innerHTML = ORDER.map((k) =>
    `<label>${esc(CFG.labels[k])} %<input type="number" min="0" max="100" step="1" data-w="${k}" value="${job.weights[k] ?? CFG.weights[k]}"></label>`).join("");
  w.querySelectorAll("input").forEach((i) => i.addEventListener("input", sumWeights));
  sumWeights();
  const fl = $("editor-flags");
  const flags = job.reviewed ? [] : r.flags || [];
  fl.hidden = !flags.length;
  fl.innerHTML = flags.length ? `<b>Please review before matching — some items could not be extracted confidently:</b><ul>${flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : "";
  $("editor-msg").textContent = job.reviewed ? "" : "Not yet reviewed - check the fields, then save.";
  $("editor-body").hidden = job.reviewed;
  $("editor-toggle").textContent = job.reviewed ? "Show / edit" : "Hide";
  $("editor-toggle").setAttribute("aria-expanded", String(!job.reviewed));
}
function sumWeights() {
  const t = [...document.querySelectorAll("[data-w]")].reduce((a, i) => a + (parseFloat(i.value) || 0), 0);
  $("w-total").textContent = t;
}
const csv = (s) => s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);

async function saveEditor(e) {
  e.preventDefault();
  const skills = [
    ...csv($("e-mand").value).map((name) => ({ name, level: "mandatory" })),
    ...csv($("e-pref").value).map((name) => ({ name, level: "preferred" })),
  ];
  const edu = $("e-edu").value;
  const requirements = {
    title: $("e-title").value, department: $("e-dept").value, skills,
    min_experience_years: $("e-years").value, experience_mandatory: $("e-years-m").checked,
    max_experience_years: $("e-maxyears").value,
    experience_counting: Object.fromEntries([...document.querySelectorAll("[data-c]")].map((s) => [s.dataset.c, parseFloat(s.value)])),
    education: edu ? { min_level: +edu, mandatory: $("e-edu-m").checked, field: $("e-field").value } : null,
    certifications: [
      ...$("e-cert-m").value.split("\n").filter((x) => x.trim()).map((name) => ({ name, mandatory: true })),
      ...$("e-cert-p").value.split("\n").filter((x) => x.trim()).map((name) => ({ name, mandatory: false })),
    ],
    responsibilities: $("e-resp").value.split("\n").map((x) => x.trim()).filter(Boolean),
  };
  const weights = {}; document.querySelectorAll("[data-w]").forEach((i) => (weights[i.dataset.w] = parseFloat(i.value) || 0));
  const msg = $("editor-msg"); msg.className = "msg"; msg.textContent = "Saving…";
  try {
    const out = await api(`/api/jobs/${activeId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requirements, weights }) });
    msg.className = "msg ok"; msg.textContent = `Saved. ${out.rematched} candidate(s) re-matched.`;
    await loadJobs(activeId);
  } catch (err) { msg.className = "msg err"; msg.textContent = err.message; }
}

// ------------------------------------------------------------ resumes
async function uploadResumes(files) {
  if (!activeId) { toast("Upload or select a job description first."); return; }
  const log = $("cv-log"); log.innerHTML = "";
  const ok = [], rejected = [];
  const maxBytes = CFG.max_file_mb * 1024 * 1024;
  for (const f of files) {
    const ext = f.name.toLowerCase().match(/\.[^.]+$/)?.[0];
    if (![".pdf", ".docx"].includes(ext)) rejected.push([f.name, "Unsupported file type (PDF or DOCX only)."]);
    else if (f.size > maxBytes) rejected.push([f.name, `Larger than ${CFG.max_file_mb} MB.`]);
    else ok.push(f);
  }
  const jobAtStart = activeId;
  const total = ok.length + rejected.length;
  if (!total) return;
  $("cv-progress").hidden = false;
  let done = rejected.length, added = 0, dups = 0, errs = rejected.length;
  rejected.forEach(([n, m]) => log.insertAdjacentHTML("beforeend", `<div class="bad">✕ ${esc(n)} — ${esc(m)}</div>`));
  const update = () => {
    $("cv-bar").style.width = `${Math.round((done / total) * 100)}%`;
    $("cv-ptext").textContent = `${done} of ${total} processed · ${added} added · ${dups} duplicate · ${errs} failed`;
  };
  update();
  for (let i = 0; i < ok.length; i += BATCH) {
    const chunk = ok.slice(i, i + BATCH);
    const fd = new FormData(); chunk.forEach((f) => fd.append("files", f, f.name));
    try {
      const { results } = await api(`/api/jobs/${jobAtStart}/resumes`, { method: "POST", body: fd });
      for (const r of results) {
        if (r.status === "ok") { added++; log.insertAdjacentHTML("beforeend", `<div>✓ ${esc(r.filename)} — ${r.overall}%${r.message ? " · " + esc(r.message) : ""}</div>`); }
        else if (r.status === "duplicate") { dups++; log.insertAdjacentHTML("beforeend", `<div class="dup">≈ ${esc(r.filename)} — ${esc(r.message)}</div>`); }
        else { errs++; log.insertAdjacentHTML("beforeend", `<div class="bad">✕ ${esc(r.filename)} — ${esc(r.message)}</div>`); }
      }
    } catch (e) {
      errs += chunk.length;
      chunk.forEach((f) => log.insertAdjacentHTML("beforeend", `<div class="bad">✕ ${esc(f.name)} — ${esc(e.message)}</div>`));
    }
    done += chunk.length; update();
    if (activeId === jobAtStart) await refreshStats();
  }
  $("cv-ptext").textContent += " · done";
  await loadJobs(jobAtStart);
}

// -------------------------------------------------------------- table
async function loadCandidates() {
  if (!activeId) return;
  const data = await api(`/api/jobs/${activeId}/candidates`);
  candidates = data.candidates;
  renderTable();
}
function missingList(c) { return (c.result && c.result.missing_mandatory) || []; }

function atsCell(a) {
  if (!a) return `<span class="none">n/a</span>`;
  const b = atsBand(a.score);
  const tip = a.issues.length ? a.issues.join(" | ") : "No ATS problems found";
  return `<div class="score" title="${esc(tip)}"><b class="s-${b}">${a.score.toFixed(0)}</b>${meter(a.score)}</div>` +
    `<span class="band ${b}">${atsText[b]}</span>` + (a.knockouts && a.knockouts.length ? ` <span class="chip miss" title="${esc(a.knockouts.join(" | "))}">${a.knockouts.length} knockout risk</span>` : "") + (a.layout_assessed ? "" : ` <small class="none" title="Original file unavailable">layout not checked</small>`);
}

function gradCell(p) {
  if (!p || !p.graduation_year) return `<span class="none">Not found</span>`;
  return `<b>${p.graduation_year}</b>${p.graduation_expected ? ' <small>(expected)</small>' : ""}<div class="cfile">${esc((p.highest_education || "").replace(/ \(.*$/, ""))}</div>`;
}
function expTotalCell(p) {
  if (!p) return "—";
  const parts = [];
  if (p.experience_years > 0) parts.push(`<b>${p.experience_years.toFixed(1)} yrs</b>`);
  if (p.stated_months > 0) parts.push(`<span class="chip rel" title="Duration stated on the resume without dates - not verified">+${p.stated_months} mo stated, undated</span>`);
  if (!parts.length) return `<span class="chip">Fresher / none found</span>`;
  const r0 = (p.roles || [])[0];
  const more = (p.roles || []).length > 1 ? ` <small class="none">+${p.roles.length - 1} more</small>` : "";
  return parts.join(" ") + (r0 ? `<div class="cfile clip" title="${esc(p.roles.join(" · "))}">${esc(r0.length > 48 ? r0.slice(0, 45) + "…" : r0)}${more}</div>` : "");
}
function certCell(p) {
  const c = (p && p.certifications) || [];
  if (!c.length) return `<span class="none">None listed</span>`;
  const x = c[0];
  return `<div class="certline" title="${esc(c.join(" · "))}">${esc(x.length > 52 ? x.slice(0, 49) + "…" : x)}</div>` +
    (c.length > 1 ? `<small class="none">+${c.length - 1} more (see Details)</small>` : "");
}

function renderTable() {
  const q = $("f-search").value.trim().toLowerCase();
  const miss = $("f-missing").value.trim().toLowerCase();
  const lo = parseFloat($("f-min").value); const hi = parseFloat($("f-max").value);
  const revOnly = $("f-review").checked;
  const sort = $("f-sort").value;
  const cat = (c, k) => (c.result && c.result.categories[k].applicable ? c.result.categories[k].score : -1);
  let rows = candidates.filter((c) => {
    const o = c.overall ?? 0;
    if (q && !(c.name || c.filename || "").toLowerCase().includes(q)) return false;
    if (!Number.isNaN(lo) && o < lo) return false;
    if (!Number.isNaN(hi) && o > hi) return false;
    if (miss && !missingList(c).some((m) => m.toLowerCase().includes(miss))) return false;
    if (revOnly && !(c.result && c.result.needs_review)) return false;
    return true;
  });
  const rank = new Map([...candidates].sort((a, b) => (b.overall ?? -1) - (a.overall ?? -1)).map((c, i) => [c.id, i + 1]));
  const prof = (c) => (c.result && c.result.profile) || {};
  rows.sort((a, b) => sort === "grad" ? (prof(b).graduation_year || 0) - (prof(a).graduation_year || 0)
    : sort === "totalexp" ? (prof(b).experience_years || 0) - (prof(a).experience_years || 0)
    : sort === "name" ? (a.name || "~").localeCompare(b.name || "~")
    : sort === "experience" ? (a.result?.experience.relevant_years ?? -1) < (b.result?.experience.relevant_years ?? -1) ? 1 : -1
    : sort === "skills" ? cat(b, "skills") - cat(a, "skills")
    : sort === "ats" ? (b.result?.ats_mnc?.score ?? -1) - (a.result?.ats_mnc?.score ?? -1)
    : (b.overall ?? -1) - (a.overall ?? -1));

  const reviewN = candidates.filter((c) => c.result && c.result.needs_review).length;
  $("st-job").textContent = candidates.length;
  $("st-review").textContent = reviewN;
  $("f-count").textContent = candidates.length ? `Showing ${rows.length} of ${candidates.length} candidates` : "";
  $("empty").hidden = rows.length > 0;
  $("empty").textContent = candidates.length ? "No candidates match the current filters." :
    (activeId ? "No resumes yet. Upload resumes to see the ranked results." : "Upload a job description, then add resumes to see the ranked results.");
  $("tbody").innerHTML = rows.map((c) => {
    const r = c.result; if (!r) return "";
    const o = c.overall, b = band(o);
    const e = r.experience;
    const expCell = e.required_months
      ? `<b>${e.relevant_months}</b> / ${e.required_months} mo <span class="band ${band(r.categories.experience.score)}">${fmtPct(r.categories.experience.score)}</span>` +
        (e.missing_months ? `<div class="cfile">${e.missing_months} months short</div>` : `<div class="cfile">requirement met</div>`)
      : `${e.relevant_months} mo relevant<div class="cfile">job sets no minimum</div>`;
    const chips = [
      ...r.missing_mandatory.map((m) => `<span class="chip miss">${esc(m)}</span>`),
      ...r.related_mandatory.map((m) => `<span class="chip rel" title="Related experience only">${esc(m)} (related)</span>`),
    ];
    const miss = chips.slice(0, 4).join("") +
      (chips.length > 4 ? `<span class="chip" title="${esc([...r.missing_mandatory, ...r.related_mandatory].join(", "))}">+${chips.length - 4} more</span>` : "");
    return `<tr>
      <td>${rank.get(c.id)}</td>
      <td><div class="cname">${esc(c.name || "(name not detected)")}</div><div class="cfile">${esc(c.filename)}</div>
        ${r.needs_review ? `<span class="chip rev" title="${esc(r.review_reasons.join('; '))}">Needs manual review</span>` : ""}
        ${c.stale ? `<span class="chip rel">Re-run needed</span>` : ""}</td>
      <td>${gradCell(r.profile)}</td>
      <td>${expTotalCell(r.profile)}</td>
      <td>${certCell(r.profile)}</td>
      <td><div class="score"><b class="s-${b}">${o.toFixed(1)}</b>${meter(o)}<span class="band ${b}">${bandText[b]}</span></div></td>
      <td class="col-ats">${atsCell(r.ats_mnc)}</td>
      <td>${fmtPct(r.categories.skills.applicable ? r.categories.skills.score : null)}</td>
      <td>${expCell}</td>
      <td>${miss || '<span class="none">None</span>'}</td>
      <td class="acts"><button class="btn ghost small" data-act="detail" data-id="${c.id}">Details</button>
        <a class="btn ghost small" href="/api/candidates/${c.id}/file" target="_blank" rel="noopener">Resume</a>
        <button class="btn danger ghost small" data-act="del" data-id="${c.id}" aria-label="Delete ${esc(c.name || c.filename)}">Delete</button></td></tr>`;
  }).join("");
}

// ------------------------------------------------------------- detail
async function showDetail(id) {
  const { candidate: c } = await api(`/api/candidates/${id}`);
  const r = c.result, p = c.parsed;
  $("d-title").textContent = c.name || "(name not detected)";
  $("d-sub").textContent = [c.email, c.phone, c.filename].filter(Boolean).join(" · ");
  const b = band(r.overall);
  const cats = ORDER.map((k) => [k, r.categories[k]]).map(([k, v]) => v.applicable
    ? `<div class="cat"><span>${esc(v.label)} <small>(${v.effective_weight}% of total)</small></span><span class="score">${meter(v.score)}<b>${Math.round(v.score)}%</b></span><span class="pts">${v.points.toFixed(1)} pts</span></div>`
    : `<div class="cat na"><span>${esc(v.label)}</span><span>Not scored — ${esc(v.note || "")}</span><span class="pts">0 pts</span></div>`).join("");
  const stLabel = { exact: "Exact", equivalent: "Equivalent", related: "Related (not identical)", partial: "Partial", missing: "Missing" };
  const stChip = { exact: "ok", equivalent: "ok", related: "rel", partial: "rel", missing: "miss" };
  const skillRows = r.skills.map((s) => `<tr><td>${esc(s.display)}</td><td>${s.level === "mandatory" ? "Mandatory" : "Preferred"}</td>
    <td><span class="chip ${stChip[s.status]}">${stLabel[s.status]}</span>${s.unverified && s.status !== "missing" ? '<span class="chip rev">Listed only — verify</span>' : ""}</td>
    <td>${s.via && s.status !== "exact" ? `via ${esc(s.via)}<br>` : ""}<span class="ev">${s.evidence ? "“" + esc(s.evidence) + "”" : ""}</span></td></tr>`).join("");
  const e = r.experience;
  const mo = (v) => (v === null || v === undefined ? "—" : `${v} mo <small>(${(v / 12).toFixed(1)} yrs)</small>`);
  const typeLbl = CFG.type_labels || {};
  const summary = `<table class="dtable"><tbody>
      <tr><td>Total work experience</td><td><b>${mo(e.total_months)}</b> <small>all roles, overlapping months counted once</small></td></tr>
      <tr><td>Relevant experience</td><td><b>${mo(e.relevant_months)}</b> <small>only roles evidencing the job's skills/duties, weighted by employment type</small></td></tr>
      <tr><td>Required experience</td><td><b>${e.required_months ? mo(e.required_months) : "not specified"}</b>${e.max_months ? ` <small>(maximum ${e.max_years} yrs, info only)</small>` : ""}</td></tr>
      ${e.required_months ? `<tr><td>Difference</td><td>${e.difference_months >= 0 ? "+" : ""}${e.difference_months} months · <b>${e.missing_months ? e.missing_months + " months missing" : "requirement met"}</b></td></tr>
      <tr><td>Experience match</td><td><b>${e.match_pct}%</b> <small>= min(100, ${e.relevant_months} ÷ ${e.required_months} × 100)</small></td></tr>` : ""}
      ${e.claimed_years ? `<tr><td>Resume claims</td><td>${e.claimed_years} yrs <small>(stated, not verified)</small></td></tr>` : ""}
      ${Object.keys(e.by_type || {}).length ? `<tr><td>By employment type</td><td>${Object.entries(e.by_type).map(([k, v]) => `${esc(typeLbl[k] || k)}: ${v} mo`).join(" · ")}</td></tr>` : ""}
    </tbody></table>`;
  const roleRows = (e.entries || []).map((x) => `<tr>
      <td><b>${esc(x.job_title || x.title)}</b><div class="ev">${esc(x.company || "company not detected")}</div></td>
      <td>${esc(typeLbl[x.type] || x.type)}</td>
      <td>${x.start ? esc(x.start) + " → " + esc(x.end) : "—"}</td>
      <td>${x.months === null ? "—" : x.months + " mo"}</td>
      <td>${x.relevance_weight === null ? "—" : (x.relevance_weight * 100) + "% relevant × " + (x.type_weight * 100) + "% type"}</td>
      <td><b>${x.counted_months}</b></td>
      <td>${esc(x.note)}${x.evidence && x.evidence.skills && x.evidence.skills.length ? `<div class="ev">Skills used: ${x.evidence.skills.map(esc).join(", ")}</div>` : ""}${x.evidence && x.evidence.duties && x.evidence.duties.length ? `<div class="ev">Duty match: “${esc(x.evidence.duties[0])}”</div>` : ""}</td></tr>`).join("");
  const expHtml = summary + (roleRows
    ? `<div class="table-wrap" style="margin-top:10px"><table class="dtable"><thead><tr><th>Role</th><th>Type</th><th>Period</th><th>Months</th><th>Weighting</th><th>Counted</th><th>Why</th></tr></thead><tbody>${roleRows}</tbody></table></div>`
    : "<p class='none'>No dated employment found.</p>") +
    ((e.gaps || []).length ? `<p class="ev">Gaps between jobs (not counted as work, and not penalised): ${e.gaps.map((g) => `${g.from} to ${g.to} (${g.months} mo)`).join("; ")}</p>` : "") +
    ((e.warnings || []).length ? `<div class="banner" style="margin-top:10px"><b>Uncertainty / notes</b><ul>${e.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : "") +
    `<p class="ev">Estimated from the resume's own dates and descriptions; actual employment needs separate verification.</p>`;
  const ed = r.education;
  const eduHtml = ed.required ? `<p>Required: <b>${esc(ed.required)}</b>${ed.mandatory ? " (mandatory)" : " (preferred)"} · Candidate: <b>${esc(ed.candidate || "not detected")}</b> · ${esc(ed.status)}</p>${(ed.lines || []).map((l) => `<div class="ev">“${esc(l)}”</div>`).join("")}` : "<p class='none'>No education requirement set.</p>";
  const respHtml = r.responsibilities.length ? `<table class="dtable"><tbody>${r.responsibilities.map((x) => `<tr><td>${esc(x.text)}</td><td><span class="chip ${x.status === "covered" ? "ok" : x.status === "partial" ? "rel" : "miss"}">${esc(x.status)}</span></td><td class="ev">${x.evidence ? "“" + esc(x.evidence) + "”" : ""}</td></tr>`).join("")}</tbody></table>` : "<p class='none'>No responsibilities defined.</p>";
  const certHtml = r.certifications.length ? r.certifications.map((x) => `<span class="chip ${x.found ? "ok" : "miss"}">${esc(x.name)} — ${x.found ? "found" : "not found"}${x.mandatory ? " (mandatory)" : ""}</span>`).join("") : "<span class='none'>No certifications required.</span>";
  $("d-body").innerHTML = `
    <div class="sec" style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">
      <div><div class="big s-${b}">${r.overall.toFixed(1)}<small style="font-size:18px">/100</small></div><span class="band ${b}">${bandText[b]} match</span></div>
      <div style="flex:1;min-width:240px">${r.needs_review ? `<div class="banner"><b>Needs manual review:</b> ${r.review_reasons.map(esc).join("; ")}</div>` : ""}</div>
    </div>
    <div class="sec"><h3>Candidate profile</h3>
      <table class="dtable"><tbody>
        <tr><td>Highest education</td><td>${esc((r.profile && r.profile.highest_education) || "not detected")}</td></tr>
        <tr><td>Year passed out</td><td>${r.profile && r.profile.graduation_year ? r.profile.graduation_year + (r.profile.graduation_expected ? " (expected)" : "") : "not found"}</td></tr>
        <tr><td>Work experience (dated)</td><td>${r.profile ? r.profile.experience_years.toFixed(1) + " yrs" : "—"}${r.profile && r.profile.fresher ? " - fresher / no work history found" : ""}${r.profile && r.profile.stated_months ? ` · plus ${r.profile.stated_months} months stated without dates (unverified)` : ""}</td></tr>
        <tr><td>Roles</td><td>${r.profile && r.profile.roles.length ? r.profile.roles.map(esc).join("<br>") : "—"}</td></tr>
        <tr><td>Certifications</td><td>${r.profile && r.profile.certifications.length ? r.profile.certifications.map(esc).join("<br>") : "None listed"}</td></tr>
      </tbody></table></div>
    <div class="sec"><h3>ATS score (MNC / enterprise-ATS model)</h3>${atsMncHtml(r.ats_mnc, r.ats)}</div>
    <div class="sec"><h3>Score breakdown</h3>${cats}</div>
    <div class="sec"><h3>Why this score</h3><ul class="plain">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    <div class="sec"><h3>Requirements</h3>
      <p><b>Matched mandatory:</b> ${list(r.matched_mandatory)}<br><b>Related only (mandatory):</b> ${list(r.related_mandatory)}<br><b>Missing mandatory:</b> ${list(r.missing_mandatory)}<br>
      <b>Matched preferred:</b> ${list(r.matched_preferred)}<br><b>Missing / related preferred:</b> ${list(r.missing_preferred)}</p></div>
    <div class="sec"><h3>Skills analysis</h3><div class="table-wrap"><table class="dtable"><thead><tr><th>Skill</th><th>Level</th><th>Result</th><th>Evidence</th></tr></thead><tbody>${skillRows}</tbody></table></div></div>
    <div class="sec"><h3>Experience</h3>${expHtml}</div>
    <div class="sec"><h3>Education</h3>${eduHtml}</div>
    <div class="sec"><h3>Responsibilities</h3>${respHtml}</div>
    <div class="sec"><h3>Certifications</h3>${certHtml}</div>
    <div class="sec"><h3>HR should verify during screening</h3>${r.verify.length ? `<ul class="plain">${r.verify.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "<p class='none'>Nothing specific flagged.</p>"}</div>
    ${p.flags && p.flags.length ? `<div class="sec"><h3>Resume parsing notes</h3><ul class="plain">${p.flags.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    <p class="note">${esc(r.disclaimer)}</p>`;
  $("detail").showModal();
}

function atsHtml(a) {
  if (!a) return "<p class='none'>Not available — click Save &amp; re-run matching.</p>";
  const b = atsBand(a.score);
  const chip = { pass: "ok", warn: "rel", fail: "miss", unknown: "" };
  const lbl = { pass: "OK", warn: "Improve", fail: "Problem", unknown: "Not checked" };
  const rows = a.checks.map((c) => `<tr><td>${esc(c.label)}</td><td><span class="chip ${chip[c.status]}">${lbl[c.status]}</span></td>
      <td><b>${c.status === "unknown" ? "—" : c.points + " / " + c.max}</b></td>
      <td>${esc(c.detail)}${c.fix ? `<div class="ev">Fix: ${esc(c.fix)}</div>` : ""}</td></tr>`).join("");
  const k = a.keywords;
  return `<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
      <div><span class="big s-${b}">${a.score.toFixed(0)}</span><small style="font-size:16px">/100</small></div>
      <span class="band ${b}">${atsText[b]} ATS readability</span>
      <small class="none">${a.assessed_points} of 100 points could be assessed${a.layout_assessed ? "" : " (layout needs the original file)"}</small></div>
    <div class="table-wrap"><table class="dtable"><thead><tr><th>Check</th><th>Result</th><th>Points</th><th>What was found</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${k ? `<p style="margin-top:8px"><b>Job keywords found in the resume:</b> ${k.found} of ${k.total} (${k.pct}%)${k.missing.length ? " · not found: " + k.missing.map(esc).join(", ") : ""}
      <span class="ev">— only add a keyword if you genuinely have that skill.</span></p>` : ""}
    <p class="ev">${esc(a.note)} This is separate from the job-match score above.</p>`;
}

function atsMncHtml(m, std) {
  if (!m) return "<p class='none'>Not available — click Save &amp; re-run matching.</p>";
  const b = atsBand(m.score);
  const chip = { pass: "ok", warn: "rel", fail: "miss", na: "" };
  const lbl = { pass: "OK", warn: "Improve", fail: "Problem", na: "n/a" };
  const rows = m.checks.map((c) => `<tr><td>${esc(c.label)}</td><td><span class="chip ${chip[c.status]}">${lbl[c.status]}</span></td>
      <td><b>${c.status === "na" ? "—" : c.points + " / " + c.max}</b></td>
      <td>${esc(c.detail)}${c.fix ? `<div class="ev">Fix: ${esc(c.fix)}</div>` : ""}</td></tr>`).join("");
  const kw = (m.keywords || []);
  const kwRows = kw.map((k) => `<span class="chip ${k.found ? "ok" : k.related_only ? "rel" : "miss"}" title="${k.found ? "found" : k.related_only ? "only a related skill - an ATS will not match it" : "not found"}">${esc(k.term)}${k.level === "mandatory" ? " ★" : ""}</span>`).join("");
  const kwFound = kw.filter((k) => k.found).length;
  return `<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
      <div><span class="big s-${b}">${m.score.toFixed(0)}</span><small style="font-size:16px">/100</small></div>
      <span class="band ${b}">${atsText[b]}</span>
      <div class="ev" style="font-style:normal"><b>${m.parse_score}</b> / 50 resume parsing &nbsp;+&nbsp; <b>${m.keyword_score === null ? "n/a" : m.keyword_score}</b> / 50 keyword match with the job</div></div>
    ${m.knockouts.length ? `<div class="banner"><b>Knockout risks</b> — an enterprise ATS may auto-filter on these (this tool does not reject anyone):<ul>${m.knockouts.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    <h4 style="margin:12px 0 4px">Keyword match (${kwFound} of ${kw.length} job keywords found; ★ = mandatory)</h4>
    <div>${kwRows || "<span class='none'>The job defines no keywords.</span>"}</div>
    <div class="ev">Green = found · Amber = only a related skill (an ATS does not count it) · Red = not found. Add a keyword only if you genuinely have the skill.</div>
    <h4 style="margin:14px 0 4px">Resume parsing (how cleanly an ATS can read the file)</h4>
    <div class="table-wrap"><table class="dtable"><thead><tr><th>Check</th><th>Result</th><th>Points</th><th>What was found</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="ev">${esc(m.note)}${std ? ` · Plain readability score (no keywords): ${std.score.toFixed(0)}/100.` : ""}${m.layout_assessed ? "" : " Layout checks need the original file."}</p>`;
}

// --------------------------------------------------------------- init
async function init() {
  CFG = await api("/api/config");
  wireDrop($("jde-drop"), $("jde-input"), uploadJde);
  wireDrop($("cv-drop"), $("cv-input"), uploadResumes);
  $("cv-folder-btn").addEventListener("click", () => $("cv-folder").click());
  $("cv-folder").addEventListener("change", () => { uploadResumes([...$("cv-folder").files]); $("cv-folder").value = ""; });
  $("job-select").addEventListener("change", (e) => { activeId = +e.target.value || null; loadJob(); });
  $("job-delete").addEventListener("click", async () => {
    const j = activeJob(); if (!j) return;
    if (!confirm(`Delete "${j.title}" and ALL ${j.candidate_count} candidate record(s) and resume files? This cannot be undone.`)) return;
    await api(`/api/jobs/${j.id}`, { method: "DELETE" }); activeId = null; await loadJobs(); toast("Job deleted.");
  });
  $("editor-form").addEventListener("submit", saveEditor);
  $("use-existing").addEventListener("click", async () => {
    if (!activeId) return;
    try {
      const { carried } = await api(`/api/jobs/${activeId}/use-existing-resumes`, { method: "POST" });
      toast(carried ? `${carried} resume(s) added and matched to this job.` : "No new resumes to add - this job already has them all.");
      await loadJobs(activeId);
    } catch (e) { toast(e.message); }
  });
  $("editor-reextract").addEventListener("click", async () => {
    if (!confirm("Re-read the uploaded document and replace the current requirements (your edits will be lost)?")) return;
    try { await api(`/api/jobs/${activeId}/reextract`, { method: "POST" }); toast("Requirements re-extracted."); await loadJobs(activeId); }
    catch (e) { toast(e.message); }
  });
  $("editor-toggle").addEventListener("click", () => {
    const body = $("editor-body"); body.hidden = !body.hidden;
    $("editor-toggle").textContent = body.hidden ? "Show / edit" : "Hide"; $("editor-toggle").setAttribute("aria-expanded", String(!body.hidden));
  });
  $("w-reset").addEventListener("click", () => document.querySelectorAll("[data-w]").forEach((i) => { i.value = CFG.weights[i.dataset.w]; sumWeights(); }));
  $("f-ats").addEventListener("change", () => document.querySelector("table").classList.toggle("hide-ats", !$("f-ats").checked));
  ["f-search", "f-missing", "f-min", "f-max", "f-sort", "f-review"].forEach((id) => $(id).addEventListener("input", renderTable));
  $("tbody").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]"); if (!btn) return;
    const id = +btn.dataset.id;
    if (btn.dataset.act === "detail") showDetail(id).catch((err) => toast(err.message));
    if (btn.dataset.act === "del") {
      if (!confirm("Delete this candidate record and the uploaded resume file? This cannot be undone.")) return;
      await api(`/api/candidates/${id}`, { method: "DELETE" }); toast("Candidate deleted."); await loadJobs(activeId);
    }
  });
  $("d-close").addEventListener("click", () => $("detail").close());
  $("detail").addEventListener("click", (e) => { if (e.target === $("detail")) $("detail").close(); });
  $("exp-csv").addEventListener("click", () => activeId && (location.href = `/api/jobs/${activeId}/export.csv`));
  $("exp-xlsx").addEventListener("click", () => activeId && (location.href = `/api/jobs/${activeId}/export.xlsx`));
  // stop the browser from opening files dropped outside a drop zone
  ["dragover", "drop"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));
  await loadJobs();
  const m = location.hash.match(/^#candidate-(\d+)$/);
  if (m) showDetail(+m[1]).catch((err) => toast(err.message));
}
init().catch((e) => toast(e.message));

// Re-read counts and the active job's candidates without resetting the editor or filters.
async function refreshStats() {
  try {
    const data = await api("/api/jobs");
    jobs = data.jobs;
    $("st-jobs").textContent = jobs.length;
    $("st-all").textContent = data.counts.applicants;
    const sel = $("job-select");
    [...sel.options].forEach((o) => {
      const j = jobs.find((x) => String(x.id) === o.value);
      if (j) o.textContent = `${j.title} (${j.candidate_count})`;
    });
    await loadCandidates();
  } catch (_) { /* stats refresh is best effort */ }
}
