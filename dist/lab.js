"use strict";
const labState = {
  tab: "packages",
  data: null,
  job: null,
  poll: null,
  busy: false,
};
window.labPage = () =>
  head(
    "Benchmark lab",
    "Bộ thử nghiệm nhỏ, test cố định và kết quả có thể kiểm chứng.",
    '<button class="button" data-lab="refresh">↻ Làm mới</button>',
  ) +
  '<div id="lab-root"><div class="loading">Đang đọc môi trường chấm…</div></div>';
const verdict = (v) =>
  `<span class="verdict ${esc(v)}">${esc(v || "PENDING")}</span>`;
const readyPackages = () => labState.data.packages.filter((p) => p.ready);
const packageOptions = () =>
  readyPackages()
    .map(
      (p) =>
        `<option value="${esc(p.id)}">${esc(p.id)} · ${esc(p.name)} · ${p.rating}</option>`,
    )
    .join("");
const post = (url, body) =>
  json(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
window.mountLab = async function () {
  clearTimeout(labState.poll);
  try {
    labState.data = await json("/api/lab");
    drawLab();
    scheduleLab();
  } catch (e) {
    const root = document.querySelector("#lab-root");
    if (root)
      root.innerHTML = `<div class="notice">Benchmark cần backend local và Docker. ${esc(e.message)}</div>`;
  }
};
function drawLab() {
  const root = document.querySelector("#lab-root");
  if (!root) return;
  const d = labState.data,
    env = d.environment,
    ready = readyPackages();
  root.innerHTML = `<div class="lab-intro"><div><div class="eyebrow">INDEPENDENT JUDGE · GNU C++20</div><h2>Từ lời giải đến bằng chứng</h2><p>Chọn bộ bài đã kiểm chứng, nộp C++ hoặc nhập code từ model. Mọi kết quả gắn với phiên bản test và compiler; AC ở đây là AC trên CPBench.</p></div><div>${env.available ? '<span class="badge complete"><i></i> Docker sẵn sàng</span>' : '<span class="badge blocked"><i></i> Cần bật Docker</span>'}<p class="lab-hash">${esc(env.image_id?.slice(0, 24) || env.error || "")}</p></div></div><div class="lab-metrics"><div class="lab-metric">Gói bài đã cài<strong>${d.packages.length}</strong></div><div class="lab-metric">Đã kiểm chứng<strong>${ready.length}</strong></div><div class="lab-metric">Test đang dùng<strong>${ready.reduce((n, p) => n + (p.validation?.test_count || 0), 0)}</strong></div><div class="lab-metric">Lượt benchmark<strong>${d.jobs.filter((j) => j.kind === "benchmark").length}</strong></div></div><div class="lab-tabs">${[
    ["packages", "01 · Bộ bài & test"],
    ["submit", "02 · Nộp C++"],
    ["evaluate", "03 · Đánh giá model"],
    ["account", "Codeforces account"],
  ]
    .map(
      ([key, title]) =>
        `<button data-lab-tab="${key}" class="${labState.tab === key ? "active" : ""}">${title}</button>`,
    )
    .join(
      "",
    )}</div><div id="lab-panel">${{ packages: labPackages, submit: labSubmit, evaluate: labEvaluate, account: accountPanel }[labState.tab]()}</div><section class="card pad section-gap"><div class="card-head"><div><h3>Lịch sử thực thi</h3><p class="subtext">Một worker chấm tuần tự để giảm nhiễu timing. Job giữ lại sau khi tải lại trang.</p></div></div><div id="lab-jobs">${labJobs()}</div></section><section id="lab-result" class="lab-output"></section>`;
  bindLabForms();
  if (labState.job) showLabJob(labState.job);
}
function labPackages() {
  return `<div class="package-grid">${labState.data.packages.map((p) => `<section class="card package-card"><div class="package-top"><strong class="pid">${esc(p.id)}</strong>${rating(p.rating)}</div><h3><button class="problem-name" data-problem="${esc(p.id)}">${esc(p.name || p.id)}</button></h3><div>${(p.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div><p class="subtext">${p.ready ? `✓ ${p.validation.test_count} tests · ${p.validation.brute_verified} brute checks<br>Reference AC · ${p.validation.mutants.filter((m) => m.detected).length}/${p.validation.mutants.length} lỗi mẫu được bắt` : "Chưa có bộ test được kiểm chứng"}</p><span class="badge ${p.ready ? "complete" : "missing"}"><i></i>${p.ready ? "Sẵn sàng benchmark" : "Cần sinh & kiểm chứng"}</span><div class="package-actions"><button class="button small" data-lab-generate="${esc(p.id)}">${p.ready ? "Sinh phiên bản mới" : "Sinh test"}</button><button class="button small" data-lab-validation="${esc(p.id)}">Bằng chứng</button></div><div class="lab-hash">${esc(p.testset_version?.slice(0, 24) || "")} ${p.testset_version ? "…" : ""}</div></section>`).join("")}</div><div class="lab-note">Đây là bộ pilot để kiểm tra quy trình, chưa đại diện cho toàn bộ năng lực CP. Bộ test gồm sample, biên, random có seed và đối chiếu brute ở kích thước nhỏ. Các reference tự viết có nguồn riêng; không được coi là source AC Codeforces.</div><section class="card pad"><h3>Mở rộng sang bất kỳ bài nào trong corpus</h3><p class="subtext">Không giới hạn ở 6 ID có sẵn. Mỗi bài mới cần generator, validator, oracle và reference phù hợp với chính bài đó.</p><ol class="extension-steps"><li>Cào metadata và statement của bài trong Kho bài toán.</li><li>Chạy <code>python scripts/init_package.py &lt;problem_id&gt;</code> để tạo gói mới.</li><li>Hoàn thiện các file trong <code>packages/&lt;id&gt;</code>, rồi nhấn Làm mới.</li><li>Sinh test và vượt qua reference + kiểm tra lời giải sai để bật benchmark.</li></ol><p class="subtext">Giới hạn pilot: 512 test / 8 MiB mỗi phiên bản. Không tự sinh cho toàn corpus. Bài interactive, output nhiều đáp án hoặc sai số thực cần checker riêng và hiện chưa bật.</p><a href="/api/guide" target="_blank" class="text-link">Đọc hợp đồng gói bài & phương pháp ↗</a></section>`;
}
function labSubmit() {
  return `<div class="lab-grid"><section class="card pad"><h3>Nộp một lời giải C++</h3><p class="subtext">API nhận ID hoặc link bài Codeforces. Code được biên dịch và chạy trong container Linux cách ly.</p><form id="submit-code" class="lab-form"><div class="field"><label for="submit-pid">BÀI TOÁN</label><select id="submit-pid" name="problem_id" required>${packageOptions()}</select></div><div class="field"><label for="cpp-file">TẢI FILE .CPP</label><input id="cpp-file" type="file" accept=".cpp,.cc,.cxx,.txt"></div><div class="field"><label for="cpp-source">SOURCE CODE · GNU C++20</label><textarea id="cpp-source" class="code-input" name="source_code" spellcheck="false" required placeholder="#include &lt;bits/stdc++.h&gt;\nusing namespace std;\nint main() {\n  // Dán lời giải của bạn tại đây\n}"></textarea></div><button class="button primary" type="submit" ${!readyPackages().length ? "disabled" : ""}>Chấm lời giải →</button></form></section><section class="card pad"><h3>Kết quả được ghi lại</h3><div class="fact-row"><span>Verdict</span><strong>AC · WA · CE · TLE · MLE · RTE · OLE</strong></div><div class="fact-row"><span>Mỗi test</span><strong>CPU / wall time / peak RSS</strong></div><div class="fact-row"><span>Cách ly</span><strong>Không network · non-root</strong></div><div class="fact-row"><span>Tái lập</span><strong>Source + testset + image hash</strong></div><div class="lab-note">Dừng tại test đầu tiên không AC. INFRA_ERROR là lỗi môi trường, không tính là model giải sai. GNU C++20 trên Linux ARM64 không tương đương timing hoặc compiler Codeforces.</div><h3>API</h3><pre class="result-code">POST /api/submissions
{
  "problem_id": "4A",
  "source_code": "...",
  "language": "cpp20",
  "idempotency_key": "your-unique-key"
}

GET /api/submissions/{id}</pre></section></div>`;
}
function labEvaluate() {
  return `<div class="lab-grid"><section class="card pad"><h3>Đánh giá code do model tạo</h3><p class="subtext">Xuất prompt không chứa editorial/reference/test ẩn. Sau khi model trả lời, nhập JSONL để chấm tất cả mẫu.</p><form id="evaluate-code" class="lab-form"><div class="field"><label for="run-name">TÊN MODEL / THÍ NGHIỆM</label><input id="run-name" name="name" required value="my-model · pilot-01"></div><div class="field"><label for="eval-ids">BỘ BÀI ĐÁNH GIÁ · CÓ THỂ CHỌN NHIỀU</label><select id="eval-ids" multiple>${readyPackages()
    .map(
      (p) =>
        `<option selected value="${esc(p.id)}">${esc(p.id)} · ${esc(p.name)}</option>`,
    )
    .join(
      "",
    )}</select></div><button class="button" type="button" data-lab="prompts">↓ Xuất prompts JSONL</button><div class="field section-gap"><label for="eval-file">NHẬP FILE JSONL</label><input id="eval-file" type="file" accept=".jsonl,.ndjson,.txt"></div><div class="field"><label for="eval-jsonl">CODE MODEL · MỘT JSON OBJECT MỖI DÒNG</label><textarea id="eval-jsonl" name="jsonl" class="code-input" spellcheck="false" required placeholder='{"problem_id":"4A","sample_id":"0","source_code":"#include ..."}'></textarea></div><div class="form-grid"><div class="field"><label for="eval-temp">TEMPERATURE (NẾU BIẾT)</label><input id="eval-temp" name="temperature" type="number" min="0" step="0.1" placeholder="Không khai báo"></div><div class="field"><label for="eval-seed">MODEL SEED (NẾU CÓ)</label><input id="eval-seed" name="model_seed" placeholder="Không khai báo"></div></div><button class="button primary" type="submit" ${!readyPackages().length ? "disabled" : ""}>Bắt đầu benchmark →</button></form></section><section class="card pad"><h3>Đọc kết quả đúng cách</h3><p class="subtext" style="line-height:1.9">Pass@1 là trung bình tỷ lệ AC theo từng bài. Pass@k chỉ hiện khi đủ k mẫu trên bài đó. Báo cáo luôn hiển thị coverage, bài bị thiếu, lỗi hạ tầng và phân nhóm rating/chủ đề.</p><div class="lab-note">Không dùng kết quả của 6 bài công khai để kết luận model giỏi toàn bộ CP. Những bài này có thể đã nằm trong dữ liệu huấn luyện. Khi mở rộng cho paper, cần bộ bài mới, tách trùng và công bố ngày/model/prompt/budget.</div><h3>JSONL contract</h3><pre class="result-code">{"problem_id":"4A",
 "sample_id":"0",
 "source_code":"...",
 "testset_version":"hash từ prompts"}</pre><p class="subtext">Mỗi dòng là một sample độc lập. sample_id không được trùng trong cùng bài. Không tự chọn lời giải tốt nhất rồi gọi đó là pass@1.</p></section></div>`;
}
function accountPanel() {
  return `<div class="lab-grid"><section class="card pad"><h3>Lấy code AC từ tài khoản của bạn</h3><p class="subtext">Metadata công khai không cần đăng nhập. Source qua <code>user.status(includeSources=true)</code> cần API key của chính handle.</p><form id="account-import" class="lab-form" autocomplete="off"><div class="field"><label for="cf-handle">CODEFORCES HANDLE</label><input id="cf-handle" name="handle" value="Viet_love_KA" required></div><div class="field"><label for="cf-key">API KEY · TÙY CHỌN</label><input type="password" id="cf-key" name="api_key" autocomplete="new-password" placeholder="Nhập riêng trên máy"></div><div class="field"><label for="cf-secret">API SECRET · TÙY CHỌN</label><input type="password" id="cf-secret" name="api_secret" autocomplete="new-password" placeholder="Không lưu vào dataset"></div><div class="form-grid"><div class="field"><label for="cf-count">SỐ SUBMISSION ĐỌC</label><input id="cf-count" name="count" type="number" value="100" min="1" max="500"></div><div class="field"><label for="cf-offset">BẮT ĐẦU TỪ</label><input id="cf-offset" name="offset" type="number" value="1" min="1"></div></div><button class="button primary" type="submit">Nhập lời giải AC</button></form><div id="account-result" class="lab-output"></div></section><section class="card pad"><h3>Kết nối riêng tư trên localhost</h3><ol class="extension-steps"><li>Mở <a href="https://codeforces.com/settings/api" target="_blank" rel="noopener">Codeforces → Settings → API ↗</a> và tạo key.</li><li>Nhập key và secret trong form bên cạnh.</li><li>Hệ thống ký request; chỉ lưu dữ liệu trả về và provenance đã bỏ thông tin xác thực.</li></ol><div class="lab-note">Key chỉ ở bộ nhớ trong thời gian request. Không cần mật khẩu/cookie. Source AC thu được vẫn cần chạy qua testset local để kiểm chứng. <a href="/import-source.html" target="_blank">Nhập source đã đọc trên trình duyệt ↗</a></div><h3>Đối chiếu Codeforces tầng 2</h3><p class="subtext">Trang đề và link nộp gốc được giữ trong metadata. Bản này không tự nộp lên Codeforces; tránh nhầm kết quả local với verdict chính thức. Có thể xuất nguyên source để nộp bằng trình duyệt, rồi lưu link/verdict khi kiểm tra ngoài.</p></section></div>`;
}
function labJobs() {
  return (
    labState.data.jobs
      .map(
        (j) =>
          `<div class="lab-job"><div class="lab-job-top"><button class="problem-name" data-lab-job="${j.id}">${{ generate: "Sinh & kiểm chứng test", submission: "Chấm C++", benchmark: "Benchmark model" }[j.kind]} ${esc(j.result?.problem_id || j.result?.name || "")}</button><div>${verdict(j.result?.verdict || (j.result?.validation?.passed === false ? "VALIDATION_FAILED" : j.state))}</div></div><small>${date(j.created_at)} · ${esc(j.id.slice(0, 12))}${j.result?.completed ? ` · ${j.result.completed}/${j.result.total}` : ""}</small></div>`,
      )
      .join("") ||
    '<div class="empty">Chưa có tác vụ. Chọn một bài hoặc nhập code để bắt đầu.</div>'
  );
}
async function showLabJob(id) {
  labState.job = id;
  const target = document.querySelector("#lab-result");
  if (!target) return;
  try {
    const job = await json("/api/lab/jobs/" + id);
    const r = job.result;
    target.innerHTML = `<section class="card pad"><div class="card-head"><h3>Chi tiết ${esc(job.kind)} · ${esc(job.state)}</h3><a class="button small" href="/api/benchmark/runs/${id}/export" download>↓ Báo cáo JSON</a></div>${!r ? '<p class="subtext">Đang đợi worker. Kết quả tự cập nhật.</p>' : renderLabResult(r)}</section>`;
  } catch (e) {
    target.textContent = e.message;
  }
}
function renderLabResult(r) {
  if (r.validation) {
    const v = r.validation;
    return `<h3>${v.passed ? "✓ Kiểm chứng thành công" : "Kiểm chứng chưa đạt"}</h3><p>${esc(r.problem_id)} · ${v.test_count} test · ${v.sample_count} samples · ${v.brute_verified} brute checks</p>${verdict(v.reference_verdict)}<p class="lab-hash">Testset: ${esc(r.testset_version || "chưa tạo")}</p><p>Source AC Codeforces đã kiểm tra: <strong>${v.upstream_checked || 0}</strong>/${v.upstream_available || 0}</p>${(v.upstream_references || []).map(ref=>`<p><a href="${esc(ref.url)}" target="_blank" rel="noopener">Submission ${ref.submission_id} ↗</a> · local ${verdict(ref.verdict)}</p>`).join("")}<h3>Khả năng bắt code sai</h3>${v.mutants.map((m) => `<p>${esc(m.file)} · ${verdict(m.verdict)} · ${m.detected ? "bắt được" : "chưa bắt được"} tại test ${m.first_failure ?? "—"}</p>`).join("")}<details><summary>Thông số kiểm chứng</summary><pre class="result-code">${esc(JSON.stringify(v, null, 2))}</pre></details>`;
  }
  if (r.summary) {
    const s = r.summary;
    return `<div class="lab-metrics"><div class="lab-metric">Pass@1<strong>${s.pass_at_1 == null ? "—" : (s.pass_at_1 * 100).toFixed(1) + "%"}</strong></div><div class="lab-metric">Coverage<strong>${s.evaluated_problems}/${s.problem_count}</strong></div><div class="lab-metric">Số samples<strong>${s.attempts}</strong></div><div class="lab-metric">Lỗi hạ tầng<strong>${s.infrastructure_errors}</strong></div></div>${s.missing_problem_ids.length ? `<div class="lab-note">Chưa đánh giá: ${esc(s.missing_problem_ids.join(", "))}. Pass@1 ở trên chỉ tính các bài đã có kết quả hợp lệ.</div>` : ""}<table class="lab-table"><thead><tr><th>Bài / sample</th><th>Verdict</th><th>Tests</th><th>CPU max</th><th>RSS max</th></tr></thead><tbody>${r.rows.map((row) => `<tr><td>${esc(row.problem_id)} / ${esc(row.sample_id)}</td><td>${verdict(row.verdict)}</td><td>${row.passed ?? 0}/${row.total ?? "—"}</td><td>${Math.max(0, ...(row.tests || []).map((t) => t.cpu_ms)).toFixed(2)} ms</td><td>${Math.max(0, ...(row.tests || []).map((t) => t.memory_kb))} KiB</td></tr>`).join("")}</tbody></table><details class="section-gap"><summary>Phân tích rating, tags, pass@k và khoảng tin cậy</summary><pre class="result-code">${esc(JSON.stringify(s, null, 2))}</pre></details>`;
  }
  return `${verdict(r.verdict)} <span class="subtext">${esc(r.problem_id || "")} · ${r.passed ?? 0}/${r.total ?? "—"} tests</span>${r.error ? `<pre class="result-code">${esc(r.error)}</pre>` : ""}<div class="lab-hash section-gap">Testset: ${esc(r.testset_version || "")}<br>Image: ${esc(r.environment?.image_id || "")}<br>Source: ${esc(r.source_sha256 || "")}</div>${r.compile?.stderr ? `<h3>Compiler diagnostics</h3><pre class="result-code">${esc(r.compile.stderr)}</pre>` : ""}${r.tests ? `<div class="table-wrap"><table class="lab-table"><thead><tr><th>Test</th><th>Nhóm</th><th>Verdict</th><th>CPU</th><th>Wall</th><th>Memory</th></tr></thead><tbody>${r.tests.map((t) => `<tr><td>${t.index}</td><td>${esc(t.category)}</td><td>${verdict(t.verdict)}</td><td>${t.cpu_ms} ms</td><td>${t.wall_ms} ms</td><td>${t.memory_kb} KiB</td></tr>${t.verdict !== "AC" ? `<tr><td colspan="6"><details open><summary>stdout / stderr / exit ${t.exit_code}</summary><pre class="result-code">${esc(t.stdout)}\n${esc(t.stderr)}</pre></details></td></tr>` : ""}`).join("")}</tbody></table></div>` : ""}`;
}
function bindLabForms() {
  const codeForm = document.querySelector("#submit-code");
  if (codeForm)
    codeForm.onsubmit = async (e) => {
      e.preventDefault();
      await runLabAction(e.submitter, async () => {
        const job = await post(
          "/api/submissions",
          Object.fromEntries(new FormData(codeForm)),
        );
        labState.job = job.id;
        await refreshLabJobs();
        await showLabJob(job.id);
      });
    };
  const evalForm = document.querySelector("#evaluate-code");
  if (evalForm)
    evalForm.onsubmit = async (e) => {
      e.preventDefault();
      await runLabAction(e.submitter, async () => {
        const f = Object.fromEntries(new FormData(evalForm));
        const body = {
          name: f.name,
          jsonl: f.jsonl,
          problem_ids: [
            ...document.querySelector("#eval-ids").selectedOptions,
          ].map((o) => o.value),
          model_metadata: {
            model: f.name,
            temperature: f.temperature === "" ? null : Number(f.temperature),
            seed: f.model_seed || null,
            mode: "offline user-provided code",
          },
        };
        const j = await post("/api/benchmark/runs", body);
        labState.job = j.id;
        await refreshLabJobs();
        await showLabJob(j.id);
      });
    };
  const accountForm = document.querySelector("#account-import");
  if (accountForm)
    accountForm.onsubmit = async (e) => {
      e.preventDefault();
      await runLabAction(e.submitter, async () => {
        const f = Object.fromEntries(new FormData(accountForm));
        f.count = Number(f.count);
        f.offset = Number(f.offset);
        const target = document.querySelector("#account-result");
        target.textContent = "Đang gọi API Codeforces…";
        try {
          const result = await post("/api/account/import", f);
          target.innerHTML = `<div class="lab-note">Đã đọc ${result.scanned} submission, lưu ${result.accepted_cpp_metadata} metadata AC C++ và <strong>${result.source_bodies} source code</strong>.<br>${esc(result.note)}</div>`;
          await refreshCatalog();
        } finally {
          accountForm
            .querySelectorAll("input[type=password]")
            .forEach((i) => (i.value = ""));
        }
      });
    };
  for (const [fileId, textId, max] of [
    ["cpp-file", "cpp-source", 256000],
    ["eval-file", "eval-jsonl", 4000000],
  ]) {
    const input = document.getElementById(fileId);
    if (input)
      input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        if (file.size > max) {
          toast("File vượt giới hạn của pilot");
          return;
        }
        document.getElementById(textId).value = await file.text();
      };
  }
}
async function runLabAction(button, fn) {
  if (button) button.disabled = true;
  try {
    await fn();
  } catch (e) {
    toast(e.message);
  } finally {
    if (button) button.disabled = false;
  }
}
async function refreshLabJobs() {
  labState.data = await json("/api/lab");
  const el = document.querySelector("#lab-jobs");
  if (el) el.innerHTML = labJobs();
}
function scheduleLab() {
  clearTimeout(labState.poll);
  labState.poll = setTimeout(async () => {
    if (state.page !== "benchmark") return;
    try {
      await refreshLabJobs();
      if (labState.job) await showLabJob(labState.job);
    } catch {}
    scheduleLab();
  }, 2500);
}
document.addEventListener("click", async (e) => {
  const el = e.target.closest("button,a");
  if (!el) return;
  try {
    if (el.dataset.labTab) {
      labState.tab = el.dataset.labTab;
      drawLab();
    }
    if (el.dataset.lab === "refresh") await mountLab();
    if (el.dataset.labGenerate) {
      await runLabAction(el, async () => {
        const j = await post("/api/testsets", {
          problem_id: el.dataset.labGenerate,
          seed: 42,
          count: 32,
        });
        labState.job = j.id;
        await refreshLabJobs();
        await showLabJob(j.id);
        toast("Đã xếp lịch sinh và kiểm chứng.");
      });
    }
    if (el.dataset.labValidation) {
      const p = labState.data.packages.find(
        (p) => p.id === el.dataset.labValidation,
      );
      const root = document.querySelector("#lab-result");
      root.innerHTML = `<section class="card pad">${p.validation ? renderLabResult({ problem_id: p.id, testset_version: p.testset_version, validation: p.validation }) : "Chưa có lần kiểm chứng. Nhấn Sinh test."}</section>`;
      root.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (el.dataset.labJob) {
      await showLabJob(el.dataset.labJob);
      document
        .querySelector("#lab-result")
        .scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (el.dataset.lab === "prompts") {
      const ids = [...document.querySelector("#eval-ids").selectedOptions].map(
        (o) => o.value,
      );
      if (!ids.length) throw Error("Chọn ít nhất một bài");
      const response = await fetch(
        "/api/benchmark/prompts?ids=" + encodeURIComponent(ids.join(",")),
      );
      if (!response.ok) throw Error("Không xuất được prompt");
      saveFile("cpbench-prompts.jsonl", await response.text());
    }
    if (el.dataset.reader === "refresh") {
      await runLabAction(el, async () => {
        await post(
          "/api/problems/" + state.detail.id + "/refresh-statement",
          {},
        );
        await openProblem(state.detail.id);
        toast("Đã cập nhật HTML gốc.");
      });
    }
    if (el.dataset.reader === "wide")
      el.closest(".drawer").classList.toggle("reader-wide");
    if (el.dataset.reader === "font")
      el.closest(".detail-content").classList.toggle("large-type");
    if (el.dataset.reader === "print") window.print();
    if (el.dataset.copySample) {
      const [idx, kind] = el.dataset.copySample.split(":");
      await navigator.clipboard.writeText(
        state.detail.statement.examples[Number(idx)][kind],
      );
      toast("Đã sao chép sample.");
    }
  } catch (err) {
    toast(err.message);
  }
});
