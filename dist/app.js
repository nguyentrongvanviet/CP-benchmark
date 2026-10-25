"use strict";
const icons = {
  database:
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
  chart: '<path d="M4 3v17h17M9 15v-4m5 4V6m5 9V9"/>',
  folder: '<path d="M3 7V4h6l2 3h10v13H3z"/>',
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1v15"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 4 3c-1 0-1 1-1 2m0 3h.01"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  external: '<path d="M14 3h7v7m0-7L11 13m-1-8H3v16h16v-7"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  file: '<path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8m-8 4h5"/>',
  shield: '<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6zM8 11l3 3 5-6"/>',
  refresh:
    '<path d="M20 7A9 9 0 0 0 4 6m0-4v5h5m-5 10a9 9 0 0 0 16 1m0 4v-5h-5"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
};
const icon = (n) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[n] || icons.file}</svg>`;
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (n) => Number(n || 0).toLocaleString("en-US");
const date = (v) =>
  v
    ? new Date(v).toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
const state = {
  local: false,
  stats: null,
  items: [],
  page: "corpus",
  q: "",
  rating: "",
  tag: "",
  status: "",
  sort: "newest",
  offset: 0,
  size: 10,
  selected: new Set(),
  chunks: new Map(),
  jobs: [],
  events: [],
  detail: null,
  detailTab: "statement",
};
const labels = {
  corpus: "Kho bài toán",
  crawler: "Thu thập dữ liệu",
  benchmark: "Benchmark",
  exports: "Dataset & export",
  methodology: "Phương pháp",
  api: "API & tích hợp",
};
function hydrateIcons(root = document) {
  root
    .querySelectorAll("[data-icon]")
    .forEach((el) => (el.innerHTML = icon(el.dataset.icon)));
}
function toast(message) {
  let el = document.querySelector("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3800);
}
async function json(url, options) {
  const r = await fetch(url, options);
  if (!r.ok) {
    let b;
    try {
      b = await r.json();
    } catch {}
    throw Error(typeof b?.detail === "string" ? b.detail : `HTTP ${r.status}`);
  }
  return r.json();
}
function saveFile(name, body, type = "application/x-ndjson") {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function badge(status) {
  const text = {
    complete: "Đã lấy trực tiếp",
    imported: "Open R1 import",
    missing: "Chưa thu thập",
    metadata_only: "Có AC · thiếu code",
    blocked: "Bị chặn",
    running: "Đang chạy",
    queued: "Đang đợi",
    paused: "Tạm dừng",
    completed: "Hoàn thành",
    completed_with_errors: "Còn thiếu / lỗi",
    partial: "Một phần",
    done: "Thành công",
    pending: "Chưa xử lý",
    failed: "Lỗi",
  };
  return `<span class="badge ${esc(status)}"><i></i>${text[status] || esc(status)}</span>`;
}
function rating(v) {
  return v == null
    ? '<span class="muted">—</span>'
    : `<span class="rating ${v < 1300 ? "easy" : v < 2000 ? "medium" : v < 2600 ? "hard" : "expert"}">${v}</span>`;
}
function head(title, desc, buttons = "") {
  return `<div class="page-heading"><div><div class="eyebrow">COMPETITIVE PROGRAMMING / LLM RESEARCH</div><h1>${title}</h1><p class="subtext">${desc}</p></div><div class="header-buttons">${buttons}</div></div>`;
}
function filters() {
  return {
    q: state.q,
    ...(state.rating
      ? {
          min_rating: Number(state.rating.split("-")[0]),
          max_rating: Number(state.rating.split("-")[1]),
        }
      : {}),
    tag: state.tag,
    status: state.status,
  };
}
function filtered() {
  let rows = state.items.filter(
    (p) =>
      (!state.q ||
        [p.id, p.name, p.contest_name]
          .join(" ")
          .toLowerCase()
          .includes(state.q.toLowerCase())) &&
      (!state.rating ||
        (p.rating != null &&
          p.rating >= Number(state.rating.split("-")[0]) &&
          p.rating <= Number(state.rating.split("-")[1]))) &&
      (!state.tag || p.tags.includes(state.tag)) &&
      (!state.status ||
        (state.status === "available"
          ? ["complete", "imported"].includes(p.statement_status)
          : p.statement_status === state.status)),
  );
  if (state.sort === "rating-up")
    rows.sort((a, b) => (a.rating ?? 9999) - (b.rating ?? 9999));
  if (state.sort === "rating-down")
    rows.sort((a, b) => (b.rating ?? -1) - (a.rating ?? -1));
  if (state.sort === "solved")
    rows.sort((a, b) => b.solved_count - a.solved_count);
  return rows;
}
function corpus() {
  const s = state.stats;
  const available = (s.statements.complete || 0) + (s.statements.imported || 0);
  return (
    head(
      "Kho bài toán",
      "Từ bài toán đến dữ liệu nghiên cứu. Khám phá, thu thập và xây dựng corpus của bạn.",
      `<button class="button" data-action="export">${icon("download")} Xuất dữ liệu</button><a href="#crawler" class="button primary">${icon("plus")} Thu thập dữ liệu</a>`,
    ) +
    `<div class="stats">${[
      [
        "Tổng số bài toán",
        fmt(s.total),
        "database",
        "Catalog từ API Codeforces",
        "Toàn bộ problemset",
      ],
      [
        "Bài toán có rating",
        fmt(s.rated),
        "chart",
        `${fmt(s.unrated)} bài chưa có rating`,
        "800–3500+",
      ],
      [
        "Statement đã có",
        fmt(available),
        "file",
        `${((available / Math.max(s.total, 1)) * 100).toFixed(1)}% độ phủ corpus`,
        "Có phân biệt nguồn",
      ],
      [
        "Source C++ AC",
        fmt(s.references),
        "shield",
        `${fmt(s.reference_metadata)} bài có metadata AC · provenance theo submission`,
        "Reference solutions",
      ],
    ]
      .map(
        ([label, value, ic, note, hint]) =>
          `<div class="stat"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon(ic)}</span></div><div class="stat-value">${value}<small>bài</small></div><div class="stat-note"><span class="green">${icon("check").replace("<svg ", '<svg style="width:10px;height:10px" ')}</span>${note}</div></div>`,
      )
      .join(
        "",
      )}</div><div class="middle-grid"><section class="card"><div class="card-head"><div><h2>Phân bố độ khó</h2><div class="card-sub">Số bài toán theo rating Codeforces</div></div><button class="text-link" data-action="reset-chart">Tất cả rating ⌄</button></div>${histogram()}<div class="chart-bottom"><span class="legend"><i></i> Số bài toán</span><span>Nhấn cột để lọc</span><span class="right">${fmt(s.rated)} rated problems</span></div></section><section class="card"><div class="card-head"><div><h2>Data pipeline</h2><div class="card-sub">Mỗi bước đều có bằng chứng nguồn</div></div><a href="#methodology" class="text-link">Chi tiết ${icon("arrow")}</a></div><div class="pipeline">${[
      [
        "done",
        "✓",
        "Metadata & rating",
        "Codeforces API · catalog đầy đủ",
        fmt(s.total),
      ],
      [
        "current",
        "2",
        "Statement & samples",
        "Direct HTML / Open R1 có gắn nguồn",
        fmt(available),
      ],
      [
        "",
        "3",
        "Accepted C++ sources",
        "Lưu verdict, submission ID & source hash",
        fmt(s.references),
      ],
      [
        "",
        "4",
        "Benchmark-ready",
        "Cần generator, oracle và kiểm chứng",
        String(s.benchmark_ready || 0),
      ],
    ]
      .map(
        ([cl, num, title, desc, n]) =>
          `<div class="pipeline-step"><span class="step-icon ${cl}">${num}</span><span class="step-text">${title}<small>${desc}</small></span><span class="step-value">${n}</span></div>`,
      )
      .join(
        "",
      )}</div></section></div><section class="card table-card"><div class="table-top"><div class="table-title"><h2>Danh mục bài toán</h2><span id="table-count" class="count-badge">${fmt(s.total)} bài</span></div><button class="text-link" data-action="export-selected">${icon("download")} <span id="selection-label">Xuất đã chọn</span></button></div><div class="table-tabs"><button class="tab ${state.status === "" ? "active" : ""}" data-status="">Tất cả bài toán</button><button class="tab ${state.status === "available" ? "active" : ""}" data-status="available">Có statement <span class="muted">${fmt(available)}</span></button><button class="tab ${state.status === "missing" ? "active" : ""}" data-status="missing">Cần bổ sung</button><button class="tab ${state.status === "imported" ? "active" : ""}" data-status="imported">Nguồn Open R1</button></div><div class="filters"><div class="searchbox">${icon("search")}<input id="search" aria-label="Tìm bài toán" placeholder="Tìm ID, tên bài toán hoặc contest…" value="${esc(state.q)}"></div><select id="rating-filter" aria-label="Lọc rating"><option value="">Tất cả rating</option>${state.rating && !["800-1199", "1200-1599", "1600-1999", "2000-2399", "2400-2799", "2800-3999"].includes(state.rating) ? `<option value="${state.rating}" selected>${state.rating.replace("-", " – ")}</option>` : ""}${[
      [800, 1199],
      [1200, 1599],
      [1600, 1999],
      [2000, 2399],
      [2400, 2799],
      [2800, 3999],
    ]
      .map(
        ([a, b]) =>
          `<option value="${a}-${b}" ${state.rating === `${a}-${b}` ? "selected" : ""}>${a} – ${b}</option>`,
      )
      .join(
        "",
      )}</select><select id="tag-filter" aria-label="Lọc loại bài"><option value="">Tất cả chủ đề</option>${s.tags.map((t) => `<option ${state.tag === t.tag ? "selected" : ""}>${esc(t.tag)}</option>`).join("")}</select><select id="sort-filter" aria-label="Sắp xếp">${[
      ["newest", "Contest mới nhất"],
      ["rating-up", "Rating tăng dần"],
      ["rating-down", "Rating giảm dần"],
      ["solved", "Nhiều người giải nhất"],
    ]
      .map(
        ([v, t]) =>
          `<option value="${v}" ${state.sort === v ? "selected" : ""}>${t}</option>`,
      )
      .join(
        "",
      )}</select><button class="filter-reset" title="Xóa bộ lọc" data-action="reset">↺</button></div><div id="problem-table"></div></section><div class="bottom-note">${icon("shield")} AC trên bộ test độc lập không đồng nghĩa AC trên Codeforces. Mọi kết quả benchmark cần công bố độ phủ và phương pháp kiểm chứng.</div>`
  );
}
function histogram() {
  let bins = [];
  for (let low = 800; low <= 3200; low += 300)
    bins.push({
      low,
      high: low === 3200 ? 3999 : low + 299,
      count: state.stats.histogram
        .filter(
          (x) =>
            x.rating >= low && x.rating <= (low === 3200 ? 3999 : low + 299),
        )
        .reduce((a, b) => a + b.count, 0),
    });
  const max = Math.max(1, ...bins.map((x) => x.count));
  return `<div class="chart"><div class="chart-y"><span>${fmt(max)}</span><span>${fmt(Math.round(max / 2))}</span><span>0</span></div><div class="bars">${bins.map((b, i) => `<div class="bar-column"><button class="bar ${i === 3 ? "highlight" : ""}" style="height:${Math.max(2, (b.count / max) * 100)}%" title="Rating ${b.low}–${b.high}: ${fmt(b.count)} bài" aria-label="Lọc rating ${b.low} đến ${b.high}, ${b.count} bài" data-range="${b.low}-${b.high}"></button><span class="bar-label">${b.low}${i === bins.length - 1 ? "+" : ""}</span></div>`).join("")}</div></div>`;
}
function drawTable() {
  const rows = filtered();
  state.offset = Math.min(
    state.offset,
    Math.max(0, Math.floor((rows.length - 1) / state.size) * state.size),
  );
  const page = rows.slice(state.offset, state.offset + state.size);
  document.querySelector("#table-count").textContent =
    `${fmt(rows.length)} bài`;
  document.querySelector("#selection-label").textContent = state.selected.size
    ? `Xuất ${state.selected.size} đã chọn`
    : "Xuất đã chọn";
  document.querySelector("#problem-table").innerHTML =
    `<div class="table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Chọn trang hiện tại" id="select-page" ${page.length && page.every((p) => state.selected.has(p.id)) ? "checked" : ""}></th><th>ID</th><th>BÀI TOÁN</th><th>RATING</th><th class="tags-column">CHỦ ĐỀ</th><th>STATEMENT</th><th>ĐÃ GIẢI</th><th></th></tr></thead><tbody>${page
      .map(
        (p) =>
          `<tr><td><input type="checkbox" aria-label="Chọn ${esc(p.id)}" data-select="${esc(p.id)}" ${state.selected.has(p.id) ? "checked" : ""}></td><td class="pid">${esc(p.id)}</td><td><button class="problem-name" data-problem="${esc(p.id)}">${esc(p.name)}</button><div class="contest-name">${esc(p.contest_name || `Contest ${p.contest_id}`)}</div></td><td>${rating(p.rating)}</td><td class="tags-column">${p.tags
            .slice(0, 2)
            .map((t) => `<span class="tag">${esc(t)}</span>`)
            .join(
              "",
            )}${p.tags.length > 2 ? `<span class="tag">+${p.tags.length - 2}</span>` : ""}</td><td>${badge(p.statement_status)}</td><td class="mono">${fmt(p.solved_count)}</td><td><button class="row-action" data-problem="${esc(p.id)}" aria-label="Mở ${esc(p.id)}">${icon("arrow")}</button></td></tr>`,
      )
      .join(
        "",
      )}</tbody></table>${!rows.length ? '<div class="empty"><strong>Không tìm thấy bài toán</strong>Thử đổi rating, chủ đề hoặc từ khóa tìm kiếm.</div>' : ""}</div><div class="table-bottom"><span>Hiển thị ${rows.length ? state.offset + 1 : 0}–${Math.min(state.offset + state.size, rows.length)} trong ${fmt(rows.length)} bài toán</span><div class="pagination"><button data-page-step="-1" ${state.offset === 0 ? "disabled" : ""}>‹</button><button class="active">${Math.floor(state.offset / state.size) + 1}</button><span>/ ${Math.max(1, Math.ceil(rows.length / state.size))}</span><button data-page-step="1" ${state.offset + state.size >= rows.length ? "disabled" : ""}>›</button></div></div>`;
  document.querySelector("#select-page").onchange = (e) => {
    page.forEach((p) =>
      e.target.checked ? state.selected.add(p.id) : state.selected.delete(p.id),
    );
    drawTable();
  };
}
function crawler() {
  return (
    head(
      "Thu thập dữ liệu",
      "Một catalog thống nhất. Thu thập có kiểm soát, tiếp tục từ checkpoint.",
      `<button class="button" data-action="reload">${icon("refresh")} Làm mới</button>`,
    ) +
    (!state.local
      ? `<div class="notice">${icon("help")}<div><strong>Đang xem bản snapshot đã xuất.</strong> Tác vụ cào chạy trong ứng dụng local để lưu raw data và checkpoint. Mở <a href="http://127.0.0.1:8765" target="_blank" rel="noopener"><u>localhost:8765</u></a> sau khi chạy backend, hoặc xem hướng dẫn trong API & tích hợp.</div></div>`
      : "") +
    `<div class="two-col"><section class="card pad"><h3>Tạo tác vụ thu thập</h3><p class="subtext" style="margin-bottom:22px">Chọn nguồn dữ liệu và phạm vi. Giá trị 0 sẽ lấy tất cả bài phù hợp.</p><form id="crawl-form"><div class="form-grid"><div class="field full"><label for="crawl-kind">LOẠI DỮ LIỆU</label><select id="crawl-kind" name="kind"><option value="metadata">Metadata · đồng bộ toàn bộ problemset</option><option value="statements">Statement & samples · HTML công khai còn thiếu</option><option value="references">Lời giải C++ · metadata AC và source công khai</option></select></div><div class="field"><label for="crawl-min">RATING TỪ</label><input type="number" id="crawl-min" name="min_rating" min="0" max="4000" placeholder="Không giới hạn"></div><div class="field"><label for="crawl-max">RATING ĐẾN</label><input type="number" id="crawl-max" name="max_rating" min="0" max="4000" placeholder="Không giới hạn"></div><div class="field"><label for="crawl-limit">SỐ BÀI TỐI ĐA</label><input type="number" id="crawl-limit" name="limit" min="0" max="100000" value="0"><small>0 = tất cả · chỉ áp dụng cho statement/source</small></div><div class="field"><label for="crawl-tag">CHỦ ĐỀ</label><select id="crawl-tag" name="tag"><option value="">Tất cả chủ đề</option>${state.stats.tags.map((t) => `<option>${esc(t.tag)}</option>`).join("")}</select></div><div class="field full"><label for="crawl-reference-mode">THU THẬP LỜI GIẢI</label><select id="crawl-reference-mode" name="metadata_only"><option value="true">Chỉ metadata AC · nhanh, không cần trang source</option><option value="false">Metadata AC + thử lấy source công khai</option></select><small>Chỉ áp dụng cho lời giải. Metadata AC không có nghĩa đã lấy được code.</small></div><div class="field full"><label for="crawl-verify">THU THẬP STATEMENT</label><select id="crawl-verify" name="verify_imported"><option value="false">Chỉ bổ sung các bài còn thiếu</option><option value="true">Thêm đối chiếu statement Open R1 với trang gốc</option></select></div><div class="field"><label for="crawl-pages">TRANG SUBMISSION / CONTEST</label><input type="number" id="crawl-pages" name="max_pages" value="20" min="1" max="1000"><small>1 trang = tối đa 1.000 submission.</small></div></div><div class="form-actions"><button class="button primary" type="submit">${icon("plus")} Bắt đầu thu thập</button></div></form></section><section class="card pad"><h3>Cấu hình collector</h3><div class="fact-row"><span>Codeforces API</span><strong>1 request / 2,2 giây</strong></div><div class="fact-row"><span>Retry cho 429 / 5xx</span><strong>Backoff · tối đa 4 lần</strong></div><div class="fact-row"><span>Lưu trữ</span><strong>SQLite WAL + raw SHA-256</strong></div><div class="fact-row"><span>Checkpoint</span><strong>Sau từng bài toán</strong></div><div class="fact-row"><span>HTTP 403 / robots.txt</span><strong>Giữ dữ liệu đã lấy, ghi rõ hạn chế</strong></div><div class="fact-row"><span>Chế độ hiện tại</span><strong>${state.local ? "Local worker đã kết nối" : "Snapshot · chỉ đọc"}</strong></div><p class="subtext" style="margin-top:18px">Metadata lấy trong 2 API request. Source C++ được tìm theo nhóm contest, phân trang và cache 24 giờ. Không cần tài khoản để lấy dữ liệu công khai.</p></section></div><div class="two-col section-gap"><section class="card pad"><h3>Lịch sử tác vụ</h3><div id="jobs">${jobList()}</div></section><section class="card pad"><h3>Nhật ký thu thập</h3><div class="log" id="events">${eventList()}</div></section></div>`
  );
}
function jobList() {
  if (!state.jobs.length)
    return '<div class="empty"><strong>Chưa có tác vụ từ giao diện</strong>Catalog ban đầu được nhập từ raw API. Tạo một tác vụ để theo dõi tại đây.</div>';
  return state.jobs
    .map(
      (j) =>
        `<div class="job-row"><div class="job-title"><strong>${esc({ metadata: "Đồng bộ catalog", statements: "Thu thập statement", references: "Tìm C++ AC" }[j.kind] || j.kind)}</strong>${badge(j.state)}</div><span class="subtext mono">${esc(j.id)} · ${date(j.created_at)}</span><div class="progress"><span style="width:${Math.min(100, (j.completed / Math.max(j.total, 1)) * 100)}%"></span></div><div class="job-title"><span class="subtext">${fmt(j.completed)} / ${fmt(j.total)} mục đã xử lý</span>${["running", "queued", "paused", "failed", "blocked", "completed_with_errors"].includes(j.state) ? `<button class="button small" data-job="${esc(j.id)}" data-job-action="${["running", "queued"].includes(j.state) ? "pause" : "resume"}">${["running", "queued"].includes(j.state) ? "Tạm dừng" : "Tiếp tục"}</button>` : ""}</div>${j.kind !== "metadata" ? `<p class="subtext">${fmt(j.succeeded)} thành công · ${fmt(j.partial)} một phần · ${fmt(j.failed)} lỗi</p><button class="button small" data-job-details="${esc(j.id)}">Xem kết quả từng bài</button>` : ""}${j.error ? `<p class="subtext" style="color:#c28d6b">${esc(j.error)}</p>` : ""}</div>`,
    )
    .join("");
}
function eventList() {
  return state.events.length
    ? state.events
        .map(
          (e) =>
            `<div class="log-line ${esc(e.level)}"><span>${date(e.at)}</span><br>${esc(e.message)}</div>`,
        )
        .join("")
    : "Chưa có sự kiện.";
}
function benchmark() {
  return window.labPage
    ? window.labPage()
    : head("Benchmark lab", "Đang tải công cụ benchmark…");
}
function exportsPage() {
  return (
    head(
      "Dataset & export",
      "Đóng băng dữ liệu, giữ nguồn gốc và chuẩn bị các phân tích có thể tái lập.",
    ) +
    `<div class="two-col"><section class="card pad"><h3>Xuất dữ liệu</h3><p class="subtext">Bộ lọc trong Kho bài toán cũng áp dụng cho bản xuất metadata.</p><div class="export-choice">${icon("database")}<div><strong>Metadata JSONL</strong><p>${fmt(filtered().length)} bài phù hợp · ID, rating, tags, link, contest</p></div><button class="button" data-action="export">Tải JSONL</button></div><div class="export-choice">${icon("folder")}<div><strong>Corpus snapshot</strong><p>Statement, provenance, manifest & SHA-256</p></div><a class="button" href="/corpus.zip" download>Tải ZIP</a></div><div class="export-choice">${icon("code")}<div><strong>Mã nguồn nền tảng</strong><p>API, crawler, importer, tests & phương pháp</p></div><a class="button" href="/cpbench-source.zip" download>Tải source</a></div></section><section class="card pad prose"><h3>Research manifest</h3><p>Mỗi snapshot có schema version, thời điểm đóng băng, SHA-256 của corpus và thống kê độ phủ. Dữ liệu thiếu giữ nguyên trạng thái, không được điền bằng lời giải sinh tự động.</p><div class="codeblock">schema_version: 1.1.0<br>source: codeforces + open-r1/codeforces<br>split_seed: cpbench-v1<br>split_unit: contest + alias + exact description<br>judge_validated: false</div><p>Split gom cùng contest, alias và mô tả trùng vào một nhóm trước khi lọc. Đóng băng snapshot cho mỗi thí nghiệm; vẫn cần rà bài tương đương về ngữ nghĩa và contamination. API <code>prompts_only=true</code> loại editorial và reference khỏi input của model.</p><a href="#methodology">Đọc phương pháp và giới hạn →</a></section></div>`
  );
}
function methodology() {
  return (
    head(
      "Phương pháp thu thập",
      "Tách nguồn dữ liệu, bằng chứng xác minh và mức độ sẵn sàng benchmark.",
    ) +
    `<div class="feature-grid">${[
      [
        "01",
        "Discover",
        "Lấy toàn bộ problemset và contest từ API chính thức. Dùng contestId + index làm ID ổn định; không loại bỏ bài chưa có rating.",
      ],
      [
        "02",
        "Enrich",
        "Đọc HTML công khai khi được phép. Nếu bị chặn, dừng collector. Import Open R1 có revision cố định là nguồn bổ sung được đánh dấu riêng.",
      ],
      [
        "03",
        "Freeze & audit",
        "Giữ raw evidence, thời điểm, URL và SHA-256. Xuất snapshot có manifest. Báo cáo coverage, missingness và hạn chế trước khi benchmark.",
      ],
    ]
      .map(
        ([n, t, p]) =>
          `<section class="card feature"><div class="number">${n}</div><h3>${t}</h3><p>${p}</p></section>`,
      )
      .join(
        "",
      )}</div><section class="card pad prose section-gap"><h3>“Có dữ liệu” và “đã kiểm chứng” là hai trạng thái riêng</h3><p><b>Metadata chính thức:</b> lấy từ Codeforces API. <b>Statement imported:</b> được nhập từ Open R1, chưa đối chiếu trực tiếp với HTML hiện tại. <b>Reference AC:</b> submission cộng đồng có verdict OK từ API, kèm source nếu trang công khai cho phép; không tự nhận là lời giải chính thức của tác giả.</p><h3>Chưa có cam kết về test tương đương Codeforces</h3><p>v0.3 có generator và Docker judge cho các gói bài pilot được kiểm chứng. Để công bố kết quả, cần đặc tả theo từng bài, validator, oracle độc lập, boundary tests, random seeds, kiểm tra bằng nhiều reference và đo khả năng loại lời giải sai. Không thể đảm bảo độ đầy đủ của bộ test tự sinh chỉ từ statement và một source AC.</p><h3>Chống rò rỉ và thiên lệch đánh giá</h3><p>Đã gom cùng contest, alias và mô tả trùng trước khi chia tập. Cần audit alias, bài trùng, thời gian xuất hiện và khả năng corpus đã nằm trong dữ liệu huấn luyện của model. Báo cáo riêng theo rating, tag, năm, nguồn statement, số reference và tỷ lệ bài chưa đủ dữ liệu. Không đưa editorial/source vào prompt sinh lời giải.</p><h3>Tài liệu nguồn</h3><p><a href="https://codeforces.com/apiHelp" target="_blank" rel="noopener">Codeforces API & giới hạn truy cập</a> · <a href="https://codeforces.com/apiHelp/methods" target="_blank" rel="noopener">Các phương thức API</a> · <a href="https://huggingface.co/datasets/open-r1/codeforces" target="_blank" rel="noopener">Open R1 corpus & attribution</a> · <a href="https://codeforces.com/blog/entry/121114" target="_blank" rel="noopener">Compiler command lines</a></p><p>Bản triển khai này có luồng benchmark pilot chạy được; độ đại diện khoa học phụ thuộc bộ bài và quy trình thí nghiệm được chọn.</p></section>`
  );
}
function apiPage() {
  return (
    head(
      "API & tích hợp",
      "API local cho việc tự động hóa. Giao diện và CLI dùng chung một kho dữ liệu.",
    ) +
    `<div class="two-col"><section class="card pad"><h3>Khởi chạy local</h3><p class="subtext">Giải nén source, cài dependency và khởi động từ thư mục dự án.</p><pre class="codeblock">python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m cpbench sync
python -m cpbench serve</pre><div class="detail-links"><a class="button" href="http://127.0.0.1:8765" target="_blank" rel="noopener">Mở local workspace ${icon("external")}</a><a class="button" href="/cpbench-source.zip" download>Tải source ${icon("download")}</a></div><p class="subtext section-gap">Swagger: http://127.0.0.1:8765/docs<br>Server bind loopback. Chạy một process cho mỗi thư mục data.</p></section><section class="card pad"><h3>Corpus & Judge API · v0.3</h3>${[
      ["GET", "/api/problems", "Tìm & lọc"],
      ["GET", "/api/problems/{id}", "Toàn bộ bản ghi"],
      ["POST", "/api/jobs", "Bắt đầu cào"],
      ["POST", "/api/jobs/{id}/pause", "Checkpoint"],
      ["POST", "/api/jobs/{id}/resume", "Tiếp tục"],
      ["GET", "/api/export", "Streaming JSONL"],
      ["POST", "/api/submissions", "202 · Docker judge"],
      ["POST", "/api/testsets", "Sinh & kiểm chứng test"],
      ["POST", "/api/benchmark/runs", "Chấm JSONL model"],
    ]
      .map(
        ([m, p, d]) =>
          `<div class="api-route"><span class="method ${m.toLowerCase()}">${m}</span><code>${p}</code><small>${d}</small></div>`,
      )
      .join(
        "",
      )}</section></div><section class="card pad prose section-gap"><h3>Ví dụ: lấy bài rating 1600–1900</h3><pre class="codeblock">curl 'http://127.0.0.1:8765/api/problems?min_rating=1600&max_rating=1900&tag=dp'</pre><h3>Giao thức nộp bài — đã triển khai</h3><p>Hợp đồng: <code>POST /api/submissions</code> với <code>problem_id</code>, <code>language</code>, <code>source_code</code>, <code>testset_version</code> và <code>idempotency_key</code>. Trả về HTTP 202 và job ID. GET /api/submissions/{id} để xem verdict và từng test. C++ chạy trong Docker Linux cách ly; cần tạo bộ test đã kiểm chứng trước.</p></section>`
  );
}
async function refreshCatalog() {
  const data = await json("/api/catalog");
  state.stats = data.stats;
  state.items = data.problems;
  document.querySelector("#nav-count").textContent = fmt(state.stats.total);
  document.querySelector("#footer-status").textContent =
    `Cập nhật ${date(state.stats.updated_at)} · UTC+7`;
}
async function openJobItems(id, offset = 0) {
  if (!state.local) {
    toast("Xem checkpoint từng bài tại ứng dụng local.");
    return;
  }
  const rows = await json(
    `/api/jobs/${encodeURIComponent(id)}/items?offset=${offset}&limit=100`,
  );
  const job = state.jobs.find((j) => j.id === id);
  document.querySelector("#modal-root").innerHTML =
    `<div class="modal-backdrop"><section class="drawer" role="dialog" aria-modal="true" aria-label="Kết quả thu thập"><div class="drawer-head"><div><div class="eyebrow">CHECKPOINT · ${esc(id)}</div><h2>Kết quả từng bài</h2></div><button class="close" data-action="close" aria-label="Đóng">✕</button></div><div class="detail-content"><p class="subtext">Tiếp tục chỉ thử lại bài chưa thành công. Số lần thử tính theo lượt xử lý bài, không phải số HTTP request.</p>${rows.map((r) => `<div class="job-row"><div class="job-title"><button class="problem-name" data-problem="${esc(r.item_id)}">${esc(r.item_id)}</button>${badge(r.state)}</div><p class="subtext">${r.attempts} lượt xử lý</p>${r.error ? `<p class="subtext job-error">${esc(r.error)}</p>` : ""}</div>`).join("") || "<p>Chưa có mục.</p>"}<div class="form-actions"><button class="button" data-job-details="${esc(id)}" data-item-offset="${Math.max(0, offset - 100)}" ${offset === 0 ? "disabled" : ""}>Trước</button><span>${offset + (rows.length ? 1 : 0)}–${offset + rows.length} / ${fmt(job?.total)}</span><button class="button" data-job-details="${esc(id)}" data-item-offset="${offset + 100}" ${offset + rows.length >= (job?.total || 0) ? "disabled" : ""}>Tiếp</button></div></div></section></div>`;
  document.querySelector(".close").focus();
}
async function loadActivity() {
  if (state.local) {
    const previous = JSON.stringify(
      state.jobs.map((j) => [j.id, j.state, j.completed]),
    );
    [state.jobs, state.events] = await Promise.all([
      json("/api/jobs"),
      json("/api/events"),
    ]);
    if (
      previous !==
      JSON.stringify(state.jobs.map((j) => [j.id, j.state, j.completed]))
    )
      await refreshCatalog();
  } else {
    try {
      const data = await json("/activity.json");
      state.jobs = data.jobs;
      state.events = data.events;
    } catch {}
  }
}
function render() {
  state.page = location.hash.slice(1) || "corpus";
  if (!labels[state.page]) state.page = "corpus";
  document.querySelector("#breadcrumb").textContent = labels[state.page];
  document
    .querySelectorAll("nav a")
    .forEach((a) =>
      a.classList.toggle("active", a.dataset.page === state.page),
    );
  document.querySelector(".sidebar").classList.remove("open");
  document.querySelector("#content").innerHTML = {
    corpus,
    crawler,
    benchmark,
    exports: exportsPage,
    methodology,
    api: apiPage,
  }[state.page]();
  if (state.page === "corpus") {
    drawTable();
    document.querySelector("#search").oninput = (e) => {
      state.q = e.target.value;
      state.offset = 0;
      drawTable();
    };
    for (const [id, key] of [
      ["rating-filter", "rating"],
      ["tag-filter", "tag"],
      ["sort-filter", "sort"],
    ])
      document.getElementById(id).onchange = (e) => {
        state[key] = e.target.value;
        state.offset = 0;
        drawTable();
      };
  }
  if (state.page === "benchmark") window.mountLab?.();
  if (state.page === "crawler")
    document.querySelector("#crawl-form").onsubmit = createJob;
}
async function createJob(e) {
  e.preventDefault();
  if (!state.local) {
    toast("Mở ứng dụng local để chạy crawler. Xem mục API & tích hợp.");
    return;
  }
  let data = Object.fromEntries(new FormData(e.target));
  for (let key of ["min_rating", "max_rating", "limit", "max_pages"])
    data[key] = data[key] === "" ? null : Number(data[key]);
  data.metadata_only = data.metadata_only === "true";
  data.verify_imported = data.verify_imported === "true";
  if (
    data.min_rating != null &&
    data.max_rating != null &&
    data.min_rating > data.max_rating
  ) {
    toast("Rating bắt đầu phải nhỏ hơn hoặc bằng rating kết thúc.");
    return;
  }
  try {
    await json("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    toast("Đã tạo tác vụ. Worker sẽ lưu checkpoint tự động.");
    await loadActivity();
    render();
  } catch (err) {
    toast(err.message);
  }
}
async function exportMeta(selected = false) {
  let rows = selected
    ? state.items.filter((p) => state.selected.has(p.id))
    : filtered();
  if (!rows.length) {
    toast(
      selected ? "Chọn ít nhất một bài để xuất." : "Không có dữ liệu phù hợp.",
    );
    return;
  }
  const body =
    rows
      .map((p) =>
        JSON.stringify({
          ...p,
          export_kind: "metadata_only",
          benchmark_ready: false,
        }),
      )
      .join("\n") + "\n";
  saveFile(`cpbench-metadata-${rows.length}.jsonl`, body);
  toast(`Đã xuất ${fmt(rows.length)} bản ghi metadata.`);
}
async function openProblem(pid) {
  document.querySelector("#modal-root").innerHTML =
    '<div class="modal-backdrop"><div class="drawer"><div class="loading"><span class="spinner"></span> Đang tải bài toán…</div></div></div>';
  try {
    if (state.local) {
      state.detail = await json("/api/problems/" + encodeURIComponent(pid));
    } else {
      const cid = state.items.find((p) => p.id === pid).contest_id;
      const chunk = Math.floor(cid / 100);
      if (!state.chunks.has(chunk))
        state.chunks.set(chunk, await json("/problems/" + chunk + ".json"));
      state.detail = state.chunks.get(chunk)[pid];
    }
    state.detailTab = "statement";
    drawDetail();
  } catch (err) {
    document.querySelector("#modal-root").innerHTML = "";
    toast("Không tải được chi tiết: " + err.message);
  }
}
function drawDetail() {
  const p = state.detail,
    s = p.statement;
  document.querySelector("#modal-root").innerHTML =
    `<div class="modal-backdrop"><section class="drawer" role="dialog" aria-modal="true" aria-label="Chi tiết ${esc(p.id)}"><div class="drawer-head"><div><div class="eyebrow">PROBLEM ${esc(p.id)}</div><h2>${esc(p.name)}</h2></div><button class="close" data-action="close" aria-label="Đóng chi tiết">✕</button></div><div class="drawer-meta">${rating(p.rating)}${p.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}${badge(p.statement_status)}</div><div class="detail-links"><a class="button small" href="${esc(p.url)}" target="_blank" rel="noopener">Codeforces ${icon("external")}</a><a class="button small" href="${esc(p.contest_url)}" target="_blank" rel="noopener">Contest ${p.contest_id}</a><button class="button small" data-action="export-detail">${icon("download")} Bản ghi JSON</button></div><div class="detail-tabs">${[
      ["statement", "Statement"],
      ["references", "Lời giải & editorial"],
      ["metadata", "Metadata & provenance"],
    ]
      .map(
        ([k, t]) =>
          `<button class="tab ${state.detailTab === k ? "active" : ""}" data-detail-tab="${k}">${t}</button>`,
      )
      .join("")}</div><div class="detail-content">${
      state.detailTab === "metadata"
        ? `<p class="subtext">Bản ghi đầy đủ, bao gồm dữ liệu API gốc, thời điểm và hash bằng chứng.</p><pre class="json">${esc(JSON.stringify(p, null, 2))}</pre>`
        : state.detailTab === "references"
          ? referencesDetail(p)
          : s
            ? `${s.source_kind === "open_r1_import" ? '<div class="notice">Statement từ Open R1 · chưa đối chiếu trực tiếp với phiên bản Codeforces hiện tại.</div>' : ""}<div class="drawer-meta"><span class="pill">${esc(s.time_limit || "Time limit chưa có")}</span><span class="pill">${esc(s.memory_limit || "Memory limit chưa có")}</span>${s.interaction_detected ? '<span class="badge blocked">Interactive · cần interactor</span>' : ""}</div>${[
                ["description", "Đề bài"],
                ["input_format", "Input"],
                ["output_format", "Output"],
                ["interaction_format", "Interaction"],
              ]
                .map(([key, label]) =>
                  s[key]
                    ? `<h3>${label}</h3><div class="statement-text">${readerHTML(s[key])}</div>`
                    : "",
                )
                .join(
                  "",
                )}<h3>Ví dụ</h3>${(s.examples || []).map((ex, i) => `<p class="muted">Sample ${i + 1} · Input</p><pre class="sample">${esc(ex.input)}</pre><p class="muted">Output</p><pre class="sample">${esc(ex.output)}</pre>`).join("")}${s.note ? `<h3>Ghi chú</h3><div class="statement-text">${readerHTML(s.note)}</div>` : ""}`
            : '<div class="empty"><strong>Chưa thu thập statement</strong>Metadata đã có. Chạy collector hoặc import corpus có nguồn trong ứng dụng local.</div>'
    }</div></section></div>`;
  const content = document.querySelector(".detail-content");
  if (state.detailTab === "statement" && s) {
    if (s.rich_html)
      content.innerHTML = `<div class="rich-statement">${readerHTML(s.rich_html, true)}</div>`;
    content.insertAdjacentHTML(
      "afterbegin",
      `<div class="reader-tools"><button class="button small" data-reader="wide">↔ Mở rộng</button><button class="button small" data-reader="font">Aa Cỡ chữ</button><button class="button small" data-reader="print">In / PDF</button>${state.local ? '<button class="button small" data-reader="refresh">↻ Lấy HTML gốc</button>' : ""}<span class="reader-source-note">${esc(s.source_kind)} · công thức KaTeX offline</span></div>`,
    );
    if (!s.rich_html)
      content
        .querySelectorAll("pre.sample")
        .forEach((pre, i) =>
          pre.insertAdjacentHTML(
            "beforebegin",
            `<button class="text-link sample-copy" data-copy-sample="${Math.floor(i / 2)}:${i % 2 ? "output" : "input"}">Sao chép</button>`,
          ),
        );
  }
  enhanceReader(content);
  document.querySelector(".close").focus();
}
function referencesDetail(p) {
  const refs = p.references || [];
  const editorial =
    p.statement?.editorial || p.statement?.imported_reference?.editorial;
  return `<div class="notice">Verdict Codeforces và kiểm chứng local được ghi riêng. Source nhập từ trình duyệt giữ provenance, hash và quy tắc chuẩn hóa dòng trống của trang nguồn.</div>${refs.length ? refs.map((r) => `<h3>Submission ${r.id} · ${esc(r.programmingLanguage)}</h3><p><a href="${esc(r.url)}" target="_blank" rel="noopener">Mở submission gốc ↗</a> · verdict ${esc(r.verdict)} · ${r.timeConsumedMillis ?? "—"} ms · ${r.memoryConsumedBytes ?? "—"} bytes</p>${r.local_validation?.verdict ? `<p class="badge complete">Local ${esc(r.local_validation.verdict)} · ${esc(r.local_validation.testset_version.slice(0,12))}</p>` : '<p class="subtext">Chưa có kiểm chứng local cho source này.</p>'}${r.source ? `<pre class="json">${esc(r.source)}</pre>` : '<p class="subtext">Đã lấy metadata AC; source chưa truy cập được.</p>'}`).join("") : '<div class="empty"><strong>Chưa có source C++ AC</strong>Không điền source tự sinh vào dữ liệu tham chiếu.</div>'}${editorial ? `<h3>Editorial · Open R1 import</h3><div class="statement-text editorial-rich">${readerHTML(editorial)}</div>` : ""}${(p.statement?.editorial_urls || []).map((url) => `<p><a href="${esc(url)}" target="_blank" rel="noopener">Editorial được liên kết từ trang gốc ↗</a></p>`).join("")}`;
}
document.addEventListener("click", async (e) => {
  const el = e.target.closest("button,a");
  if (!el) return;
  try {
    if (el.dataset.problem) await openProblem(el.dataset.problem);
    if (el.dataset.detailTab) {
      state.detailTab = el.dataset.detailTab;
      drawDetail();
    }
    if (el.hasAttribute("data-status")) {
      state.status = el.dataset.status;
      state.offset = 0;
      render();
    }
    if (el.dataset.range) {
      state.rating = el.dataset.range;
      state.offset = 0;
      render();
      const select = document.querySelector("#rating-filter");
      if (![...select.options].some((o) => o.value === state.rating))
        select.add(
          new Option(
            state.rating.replace("-", " – "),
            state.rating,
            true,
            true,
          ),
        );
    }
    if (el.dataset.pageStep) {
      state.offset += Number(el.dataset.pageStep) * state.size;
      drawTable();
    }
    if (el.dataset.jobDetails)
      await openJobItems(
        el.dataset.jobDetails,
        Number(el.dataset.itemOffset || 0),
      );
    if (el.dataset.job) {
      if (!state.local) {
        toast("Điều khiển tác vụ tại ứng dụng local.");
        return;
      }
      await json(`/api/jobs/${el.dataset.job}/${el.dataset.jobAction}`, {
        method: "POST",
      });
      await loadActivity();
      render();
    }
    switch (el.dataset.action) {
      case "export":
        await exportMeta();
        break;
      case "export-selected":
        await exportMeta(true);
        break;
      case "close":
        document.querySelector("#modal-root").innerHTML = "";
        break;
      case "export-detail":
        saveFile(
          state.detail.id + ".json",
          JSON.stringify(state.detail, null, 2),
          "application/json",
        );
        break;
      case "reset":
        Object.assign(state, {
          q: "",
          rating: "",
          tag: "",
          status: "",
          offset: 0,
        });
        render();
        break;
      case "reset-chart":
        state.rating = "";
        state.offset = 0;
        render();
        break;
      case "reload":
        await load();
        toast("Dữ liệu đã được cập nhật.");
        break;
    }
  } catch (err) {
    toast(err.message);
  }
});
document.addEventListener("change", (e) => {
  if (e.target.dataset.select) {
    e.target.checked
      ? state.selected.add(e.target.dataset.select)
      : state.selected.delete(e.target.dataset.select);
    drawTable();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelector("#modal-root").innerHTML = "";
  if (e.key === "Tab" && document.querySelector(".drawer")) {
    const els = [
      ...document
        .querySelector(".drawer")
        .querySelectorAll("a[href],button,input,select,textarea"),
    ];
    if (e.shiftKey && document.activeElement === els[0]) {
      e.preventDefault();
      els.at(-1).focus();
    } else if (!e.shiftKey && document.activeElement === els.at(-1)) {
      e.preventDefault();
      els[0].focus();
    }
  }
});
document.querySelector("#modal-root").addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-backdrop"))
    e.currentTarget.innerHTML = "";
});
document.querySelector(".mobile-menu").onclick = () =>
  document.querySelector(".sidebar").classList.toggle("open");
document.querySelector("#workspace").onclick = () => {
  location.hash = "api";
};
window.addEventListener("hashchange", async () => {
  if (state.stats) render();
  window.scrollTo(0, 0);
  if (state.local && state.page === "corpus") {
    try {
      await refreshCatalog();
      if (state.page === "corpus") render();
    } catch (e) {
      toast(e.message);
    }
  }
});
async function load() {
  try {
    let health;
    try {
      health = await json("/api/health");
    } catch {}
    state.local = health?.mode === "local";
    if (state.local) {
      const data = await json("/api/catalog");
      state.stats = data.stats;
      state.items = data.problems;
    } else {
      const data = await json("/snapshot.json");
      state.stats = data.stats;
      state.items = data.problems;
    }
    await loadActivity();
    document.querySelector("#mode").innerHTML =
      `<i></i>${state.local ? "Local worker connected" : "Research snapshot"}`;
    document.querySelector("#nav-count").textContent = fmt(state.stats.total);
    document.querySelector("#footer-status").textContent =
      `Cập nhật ${date(state.stats.updated_at)} · UTC+7`;
    render();
  } catch (err) {
    document.querySelector("#content").innerHTML =
      `<div class="empty"><strong>Chưa tải được corpus</strong>${esc(err.message)}<p>Chạy python -m cpbench sync hoặc tạo web snapshot.</p><button class="button" onclick="location.reload()">Thử lại</button></div>`;
  }
}
hydrateIcons();
load();
setInterval(async () => {
  if (state.local && state.page === "crawler") {
    try {
      await loadActivity();
      const j = document.querySelector("#jobs"),
        e = document.querySelector("#events");
      if (j) j.innerHTML = jobList();
      if (e) e.innerHTML = eventList();
    } catch {}
  }
}, 5000);
