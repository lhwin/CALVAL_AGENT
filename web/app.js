/**
 * Cal/Val Agent — Web 前端逻辑
 */
const $ = (id) => document.getElementById(id);

const state = {
  mode: "local",
  dataSummary: null,
  satellite: [],
  parsed: null,
  recommendation: null,
  paramBody: null,
  confirmed: false,
  jobId: null,
  pollTimer: null,
};

// ───────────── 基础工具 ─────────────

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function jsonBlock(obj) {
  let txt;
  try { txt = JSON.stringify(obj, null, 2); } catch { txt = String(obj); }
  return `<pre class="json">${esc(txt)}</pre>`;
}

function tag(text, kind = "info") {
  return `<span class="tag ${kind}">${esc(text)}</span>`;
}

function kvTable(obj) {
  const rows = Object.entries(obj).map(
    ([k, v]) => `<div class="k">${esc(k)}</div><div class="v">${esc(
      typeof v === "object" ? JSON.stringify(v) : v
    )}</div>`
  ).join("");
  return `<div class="kv">${rows}</div>`;
}

function gridTable(headers, rows) {
  const th = headers.map((h) => `<th>${esc(h)}</th>`).join("");
  const tr = rows.map(
    (r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`
  ).join("");
  return `<table class="grid"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function busy(btn, on, label) {
  btn.disabled = on;
  if (on) {
    btn.dataset.orig = btn.dataset.orig || btn.textContent;
    btn.innerHTML = `<span class="spinner"></span>${esc(label || "处理中…")}`;
  } else if (btn.dataset.orig) {
    btn.textContent = btn.dataset.orig;
  }
}

function fileUrl(p) {
  if (!p) return "";
  if (/^https?:/.test(p)) return p;
  return `/api/file?path=${encodeURIComponent(p)}`;
}

// ───────────── 健康检查 ─────────────

async function checkHealth() {
  const dot = $("health");
  try {
    await api("/api/health");
    dot.classList.add("ok");
    dot.classList.remove("bad");
    dot.title = "后端已连接";
  } catch {
    dot.classList.add("bad");
    dot.classList.remove("ok");
    dot.title = "后端未连接";
  }
}

// ───────────── 1. 数据发现 ─────────────

async function doDiscover() {
  const btn = $("btn-discover");
  const box = $("discover-result");
  state.mode = $("mode").value;
  busy(btn, true, "扫描中…");
  box.innerHTML = `<span class="spinner"></span>正在扫描 ${esc(state.mode)} 数据…`;
  try {
    const d = await api(`/api/discover?mode=${encodeURIComponent(state.mode)}`);
    state.dataSummary = d.data_summary;
    state.satellite = d.satellite || [];

    const ts = d.tide_summary || {};
    const stations = ts.stations || {};
    const stationKeys = Object.keys(stations);
    const fes = ts.fes2014_info || {};
    const mss = ts.mss_info || {};
    const hy2b = ts.hy2bgdr || {};

    let html = `<div>${tag("卫星 " + state.satellite.length + " 组", "info")}${tag(
      "NC 文件 " + d.total_nc_files, "ok"
    )}${tag(
      "验潮站 " + stationKeys.length + " 个",
      stationKeys.length ? "ok" : "warn"
    )}${tag(
      "验潮 txt " + (ts.txt_count ?? 0), "info"
    )}${tag(
      "FES2014 " + (fes.count ?? 0) + " 分潮",
      fes.exists && !(fes.required_missing || []).length ? "ok" : "warn"
    )}${tag(
      "MSS " + (mss.exists ? mss.size_mb + " MB" : "缺失"),
      mss.exists ? "ok" : "err"
    )}</div>`;

    // —— 卫星表 ——
    if (state.satellite.length) {
      html += `<h3 class="sub-h">卫星数据</h3>`;
      html += gridTable(
        ["卫星", "文件数", "起始", "结束", "路径"],
        state.satellite.map((s) => [
          s.sat_id, s.nc_count, s.start_date, s.end_date, s.path,
        ])
      );
    } else {
      html += `<p class="log-line err">未发现卫星数据目录</p>`;
    }

    // —— 验潮站表 ——
    if (stationKeys.length) {
      html += `<h3 class="sub-h">验潮站数据</h3>`;
      html += gridTable(
        ["站点", "站名", "纬度", "经度", "日文件", "起始", "结束", "大小(MB)", "推荐"],
        stationKeys.map((k) => {
          const st = stations[k] || {};
          return [
            k,
            st.header_station || "-",
            st.lat ?? "-",
            st.lon ?? "-",
            st.file_count ?? 0,
            st.date_start || "-",
            st.date_end || "-",
            st.total_size_mb ?? "-",
            k === ts.recommended_station ? "★" : "",
          ];
        })
      );
      if (ts.recommended_station) {
        html += `<p class="log-line">推荐验潮站：<b>${esc(ts.recommended_station)}</b>（任务日期范围内可用文件最多）</p>`;
      }
    } else {
      html += `<p class="log-line err">未发现验潮站 txt 数据</p>`;
    }

    // —— HY-2B GDR ——
    const hyYears = Object.keys(hy2b);
    if (hyYears.length) {
      html += `<h3 class="sub-h">HY-2B GDR</h3>`;
      html += gridTable(
        ["年份", "文件数", "起始", "结束"],
        hyYears.map((y) => [
          y, hy2b[y].count, hy2b[y].date_start || "-", hy2b[y].date_end || "-",
        ])
      );
    }

    // —— 辅助模型 ——
    html += `<h3 class="sub-h">辅助模型</h3>`;
    html += kvTable({
      "FES2014 目录": fes.path || "-",
      "分潮数量": (fes.count ?? 0) + "（必需：" + ((fes.required || []).join(",") || "-") + "）",
      "缺失必需分潮": (fes.required_missing || []).length ? fes.required_missing.join(", ") : "无",
      "MSS 文件": mss.path || "-",
      "MSS 状态": mss.exists ? `就绪（${mss.size_mb} MB）` : "缺失",
    });

    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = `<p class="log-line err">扫描失败: ${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

// ───────────── 2. 任务相关 ─────────────

function taskText() {
  return $("task-text").value.trim();
}

async function doParse() {
  const btn = $("btn-parse");
  const box = $("task-result");
  if (!taskText()) return (box.innerHTML = `<p class="log-line err">请先填写任务描述</p>`);
  busy(btn, true, "解析中…");
  box.innerHTML = `<span class="spinner"></span>LLM 解析任务…`;
  try {
    const d = await api("/api/parse", {
      method: "POST",
      body: JSON.stringify({ task_text: taskText(), data_summary: state.dataSummary || {} }),
    });
    state.parsed = d.parsed;
    const p = d.parsed;
    const missing = ["method", "primary_sat", "start_date", "end_date"].filter((k) => !p[k]);
    const desc = d.data_describe || (state.dataSummary && state.dataSummary.data_describe) || "";
    box.innerHTML =
      `<div>${tag("method: " + (p.method || "?"), p.method ? "ok" : "warn")}` +
      `${tag("主星: " + (p.primary_sat || "?"), p.primary_sat ? "ok" : "warn")}` +
      `${tag("辅星: " + (p.aux_data_type || "-"), "info")}` +
      `${tag("日期: " + (p.start_date || "?") + " ~ " + (p.end_date || "?"), p.start_date && p.end_date ? "info" : "err")}</div>` +
      (missing.length ? `<p class="log-line err">缺失字段: ${esc(missing.join(", "))}</p>` : "") +
      (d.warning ? `<p class="log-line warn">⚠ ${esc(d.warning)}</p>` : "") +
      (d.auto_discovered ? `<p class="log-line">ℹ 已自动扫描本地数据以确定可用范围</p>` : "") +
      (desc
        ? `<details style="margin-top:10px"><summary class="log-line">📊 本次解析依据的数据描述（点击展开）</summary><pre class="json">${esc(desc)}</pre></details>`
        : `<p class="log-line warn">⚠ 未获取到数据描述，LLM 无法判断真实数据范围，日期可能不准。请先在第 1 步点击「扫描数据」。</p>`) +
      jsonBlock(p);
  } catch (e) {
    box.innerHTML = `<p class="log-line err">${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

async function doKb() {
  const btn = $("btn-kb");
  const box = $("task-result");
  busy(btn, true, "查询中…");
  box.innerHTML = `<span class="spinner"></span>查询知识库…`;
  try {
    const d = await api("/api/kb", {
      method: "POST",
      body: JSON.stringify({ parsed_task: state.parsed || {} }),
    });
    let html = `<div>${tag("匹配案例 " + d.kb_cases.length, "info")}${tag(
      "失败警告 " + d.kb_warnings.length,
      d.kb_warnings.length ? "warn" : "ok"
    )}</div>`;
    if (d.kb_cases.length) {
      html += gridTable(
        ["case_id", "method", "卫星", "日期", "状态"],
        d.kb_cases.map((c) => [
          c.case_id, c.method, c.primary_sat,
          `${c.start_date}~${c.end_date}`, c.status,
        ])
      );
    }
    if (d.kb_warnings.length) {
      html += `<p class="log-line err">历史失败原因：</p>` +
        d.kb_warnings.map((w) => `<p class="log-line">· ${esc(w.reason)}</p>`).join("");
    }
    if (Object.keys(d.kb_suggestions || {}).length) {
      html += `<p class="log-line">建议参数：</p>` + jsonBlock(d.kb_suggestions);
    }
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = `<p class="log-line err">${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

async function doRecommend() {
  const btn = $("btn-recommend");
  const box = $("task-result");
  busy(btn, true, "推荐中…");
  box.innerHTML = `<span class="spinner"></span>推荐定标方法…`;
  try {
    const d = await api("/api/recommend", {
      method: "POST",
      body: JSON.stringify({
        parsed_task: state.parsed || {},
        available_datasets: state.satellite,
        data_summary: state.dataSummary || {},
      }),
    });
    const r = d.recommendation;
    state.recommendation = r;
    box.innerHTML =
      `<div>${tag("方法: " + r.method, "ok")}${tag(
        "置信度: " + r.confidence,
        r.confidence === "high" ? "ok" : r.confidence === "medium" ? "warn" : "err"
      )}${tag("action: " + r.action, r.action === "proceed" ? "ok" : "warn")}</div>` +
      `<p class="log-line">依据：</p>` +
      (r.reasoning || []).map((x) => `<p class="log-line">· ${esc(x)}</p>`).join("");
  } catch (e) {
    box.innerHTML = `<p class="log-line err">${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

async function doParamFill() {
  const btn = $("btn-paramfill");
  const box = $("task-result");
  busy(btn, true, "智能化填充中…");
  box.innerHTML = `<span class="spinner"></span>正在匹配相似历史案例…`;
  try {
    // 先查询知识库（内部已含相似案例匹配逻辑）
    const kb = await api("/api/kb", {
      method: "POST",
      body: JSON.stringify({ parsed_task: state.parsed || {} }),
    });
    // 再生成参数体（含 LLM 微调）
    box.innerHTML = `<span class="spinner"></span>根据历史案例智能化填充参数…`;
    const d = await api("/api/param_fill", {
      method: "POST",
      body: JSON.stringify({
        parsed_task: state.parsed || {},
        available_datasets: state.satellite,
        selected_data: state.satellite[0] || {},
        data_summary: state.dataSummary || {},
        use_llm: true,
      }),
    });
    state.paramBody = d.param_body;
    $("param-body").value = JSON.stringify(d.param_body, null, 2);
    setConfirmed(false);
    box.innerHTML = `<p class="log-line ok">✔ 参数体已智能化生成（参考 ${kb.kb_cases.length} 个相似案例），请在下方确认/修改后执行。</p>`;
  } catch (e) {
    box.innerHTML = `<p class="log-line err">${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

function setConfirmed(v) {
  state.confirmed = v;
  const badge = $("confirm-badge");
  const tip = $("confirm-tip");
  const btn = $("btn-execute");
  if (v) {
    badge.className = "tag ok";
    badge.textContent = "已确认";
    btn.disabled = false;
    if (tip) tip.textContent = "参数已确认，可执行定标";
  } else {
    badge.className = "tag warn";
    badge.textContent = "未确认";
    btn.disabled = true;
    if (tip) tip.textContent = "参数体生成后可手动编辑、按自然语言修改，然后点击「确认参数」";
  }
}

async function doConfirm() {
  const btn = $("btn-confirm");
  const box = $("exec-status");
  let paramBody;
  try {
    paramBody = JSON.parse($("param-body").value);
  } catch (e) {
    return (box.innerHTML = `<p class="log-line err">参数体不是合法 JSON: ${esc(e.message)}</p>`);
  }
  state.paramBody = paramBody;
  setConfirmed(true);
  box.innerHTML = `<p class="log-line ok">✔ 参数已确认（${Object.keys(paramBody).length} 个字段），可执行定标。</p>`;
}

async function doModify() {
  const btn = $("btn-modify");
  const box = $("exec-status");
  const hint = $("modify-hint").value.trim();
  if (!hint) return (box.innerHTML = `<p class="log-line err">请先填写修改说明</p>`);
  let paramBody;
  try {
    paramBody = JSON.parse($("param-body").value);
  } catch (e) {
    return (box.innerHTML = `<p class="log-line err">参数体不是合法 JSON: ${esc(e.message)}</p>`);
  }
  busy(btn, true, "修改中…");
  box.innerHTML = `<span class="spinner"></span>LLM 修改参数…`;
  try {
    const d = await api("/api/param_modify", {
      method: "POST",
      body: JSON.stringify({ param_body: paramBody, user_reply: hint }),
    });
    state.paramBody = d.param_body;
    $("param-body").value = JSON.stringify(d.param_body, null, 2);
    setConfirmed(false);
    let html = `<p class="log-line ok">✔ 参数已按说明修改</p>`;
    if (d.patch && Object.keys(d.patch).length) {
      html += `<p class="log-line">修改字段：</p>`;
      html += Object.entries(d.patch).map(([k, v]) =>
        `<p class="log-line">· ${esc(k)} → ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</p>`
      ).join("");
    }
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = `<p class="log-line err">${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

// ───────────── 3. 执行 ─────────────

async function doExecute() {
  const btn = $("btn-execute");
  const box = $("exec-status");
  const method = (state.recommendation && state.recommendation.method) ||
    (state.parsed && state.parsed.method);

  if (!method) return (box.innerHTML = `<p class="log-line err">未确定方法，请先解析/推荐</p>`);
  if (!state.confirmed) {
    return (box.innerHTML = `<p class="log-line err">请先点击「确认参数 (yes)」再执行</p>`);
  }
  let paramBody;
  try {
    paramBody = JSON.parse($("param-body").value);
  } catch (e) {
    return (box.innerHTML = `<p class="log-line err">参数体不是合法 JSON: ${esc(e.message)}</p>`);
  }

  busy(btn, true, "提交中…");
  box.innerHTML = `<span class="spinner"></span>提交执行任务…`;
  try {
    const d = await api("/api/execute", {
      method: "POST",
      body: JSON.stringify({ method, param_body: paramBody, mode: state.mode }),
    });
    state.jobId = d.job_id;
    box.innerHTML = `<p class="log-line">任务已提交: <code>${esc(d.job_id)}</code>（method=${esc(method)}）</p>`;
    pollJob();
  } catch (e) {
    box.innerHTML = `<p class="log-line err">${esc(e.message)}</p>`;
  } finally {
    busy(btn, false);
  }
}

function pollJob() {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  const box = $("exec-status");

  const tick = async () => {
    try {
      const j = await api(`/api/jobs/${state.jobId}`);
      const elapsed = j.started_at ? Math.round(performance.now() / 1000) : 0;
      if (j.status === "running" || j.status === "queued") {
        box.innerHTML = `<span class="spinner"></span><span class="log-line">${
          j.status === "queued" ? "排队中" : "执行中"
        } … 方法 ${esc(j.method)}</span>`;
        state.pollTimer = setTimeout(tick, 2500);
      } else if (j.status === "done") {
        box.innerHTML = `<p class="log-line ok">✔ 执行完成</p>`;
        renderResult(j.result);
      } else {
        box.innerHTML = `<p class="log-line err">✘ 执行失败: ${esc(j.error || "未知错误")}</p>` +
          (j.traceback ? `<pre class="json">${esc(j.traceback)}</pre>` : "");
      }
    } catch (e) {
      box.innerHTML = `<p class="log-line err">轮询失败: ${esc(e.message)}</p>`;
    }
  };
  tick();
}

// ───────────── 4. 结果渲染 ─────────────

function renderStats(stats, title) {
  if (!stats) return "";
  const rows = [];
  const push = (k, v) => {
    if (v === undefined || v === null) return;
    rows.push([k, typeof v === "object" ? JSON.stringify(v) : v]);
  };
  push("有效点数", stats.num_valid_points);
  push("均值偏差 (m)", stats.mean_diff_m);
  push("均值偏差 (cm)", stats.mean_diff_cm);
  push("标准差 (m)", stats.std_diff_m);
  push("RMSE (m)", stats.rmse_m);
  push("离群点", stats.num_outliers);
  if (stats.regression) {
    push("斜率", stats.regression.slope);
    push("截距", stats.regression.intercept);
    push("R²", stats.regression.r_squared);
  }
  // match 统计
  push("总匹配点", stats.total_match);
  push("通过区域", stats.pass_area);
  push("通过距海", stats.pass_coast);
  push("通过水深", stats.pass_depth);
  push("通过风速", stats.pass_wind);
  push("全条件通过", stats.pass_all);

  if (!rows.length) return "";
  return `<h3 style="font-size:13px;color:var(--muted);margin:14px 0 0">${esc(title)}</h3>` +
    gridTable(["指标", "数值"], rows);
}

function collectImages(obj, acc = []) {
  if (!obj) return acc;
  if (typeof obj === "string") {
    if (/\.(png|jpg|jpeg|webp|svg)$/i.test(obj)) acc.push(obj);
    return acc;
  }
  if (Array.isArray(obj)) { obj.forEach((x) => collectImages(x, acc)); return acc; }
  if (typeof obj === "object") {
    Object.values(obj).forEach((v) => collectImages(v, acc));
  }
  return acc;
}

function collectLinks(obj, acc = []) {
  if (!obj) return acc;
  if (typeof obj === "string") {
    if (/\.(txt|json|csv|npz|docx|parquet|xml|h5)$/i.test(obj)) acc.push(obj);
    return acc;
  }
  if (Array.isArray(obj)) { obj.forEach((x) => collectLinks(x, acc)); return acc; }
  if (typeof obj === "object") Object.values(obj).forEach((v) => collectLinks(v, acc));
  return acc;
}

function renderResult(res) {
  const view = $("result-view");
  if (!res) { view.innerHTML = `<p class="log-line">无结果</p>`; return; }

  let html = "";

  if (res.status) {
    html += `<div>${tag("status: " + res.status, res.status === "success" ? "ok" : "err")}` +
      (res.execution_time ? tag("耗时 " + Number(res.execution_time).toFixed(1) + " s", "info") : "") +
      `</div>`;
  }

  html += renderStats(res.match_result && res.match_result.statistics, "MATCH 统计");
  html += renderStats(res.cal_result && res.cal_result.statistics, "CAL 统计");

  const imgs = [...new Set(collectImages(res))];
  if (imgs.length) {
    html += `<div class="imgs">` + imgs.map((p) =>
      `<figure><img src="${fileUrl(p)}" alt="${esc(p)}" onclick="zoomImg(this.src)" loading="lazy" />` +
      `<figcaption>${esc(p)}</figcaption></figure>`
    ).join("") + `</div>`;
  }

  const links = [...new Set(collectLinks(res))];
  if (links.length) {
    html += `<h3 style="font-size:13px;color:var(--muted);margin:16px 0 6px">输出文件</h3>`;
    html += links.map((p) =>
      `<p class="log-line">📄 <a href="${fileUrl(p)}" target="_blank" style="color:var(--accent-2)">${esc(p)}</a></p>`
    ).join("");
  }

  html += `<details style="margin-top:14px"><summary class="log-line">查看完整 JSON</summary>${jsonBlock(res)}</details>`;

  view.innerHTML = html;
}

function zoomImg(src) {
  const m = document.createElement("div");
  m.className = "modal show";
  m.innerHTML = `<img src="${src}" />`;
  m.onclick = () => m.remove();
  document.body.appendChild(m);
}

// ─── 参数体手动编辑重置确认 ───
const paramBodyEl = $("param-body");
if (paramBodyEl) paramBodyEl.addEventListener("input", () => {
  if (state.confirmed) setConfirmed(false);
});

// ───────────── 事件绑定 ─────────────
// 容错绑定：元素缺失时跳过，避免单个按钮缺失导致后续绑定全部中断
function bind(id, handler) {
  const el = $(id);
  if (el) el.onclick = handler;
}

bind("btn-discover", doDiscover);
bind("btn-parse", doParse);
bind("btn-kb", doKb);
bind("btn-recommend", doRecommend);
bind("btn-paramfill", doParamFill);
bind("btn-confirm", doConfirm);
bind("btn-modify", doModify);
bind("btn-execute", doExecute);

const modeSel = $("mode");
if (modeSel) modeSel.onchange = (e) => (state.mode = e.target.value);

checkHealth();
setInterval(checkHealth, 30000);