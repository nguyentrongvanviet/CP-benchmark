# v0.3: benchmark pilot đã triển khai

Mở **http://127.0.0.1:8765/#benchmark**. Có 6 gói bài mẫu mở rộng được, generator/validator/oracle, Docker C++ judge, nhập code/JSONL, report pass@1/pass@k, API key Codeforces memory-only và trình đọc đề KaTeX offline.

Xem [hướng dẫn benchmark hiện tại](docs/BENCHMARK.md). Trước khi chấm, bật Docker Desktop và chạy `docker build -t cpbench-judge:v1 judge`. Bản này ưu tiên code/JSONL như yêu cầu; model endpoint và submit tự động lên Codeforces chưa bật. Các phần v0.1/v0.2 bên dưới mô tả lịch sử corpus, không mô tả khả năng judge hiện tại.

---

# CPBench — corpus-first LLM research platform

Nền tảng thu thập và phân tích bài toán competitive programming. **v0.2 tập trung vào scrape/import dữ liệu; chưa chạy C++, sinh test hoặc nộp Codeforces.**

## Bắt đầu

Yêu cầu Python 3.11+ (đã kiểm thử bằng 3.14). Từ thư mục chứa README:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m cpbench sync
python -m cpbench serve
```

Mở **http://127.0.0.1:8765**. API tương tác: **http://127.0.0.1:8765/docs**.

**Trạng thái hosting lúc bàn giao:** chưa xuất bản được do lỗi upload/xác thực của dịch vụ Sites. Bản local hoạt động độc lập.

Bản thư mục bàn giao đã có `data/` chứa catalog và statement được nhập. Chạy `serve` sẽ dùng ngay dữ liệu này. ZIP source trên web chỉ chứa mã nguồn; chạy `sync`, sau đó importer để tải lại dữ liệu. Web hosted là **snapshot để tra cứu/xuất dữ liệu**; crawler và SQLite chạy tại local. Không có cloud worker chạy ngầm và không gửi cookie Codeforces lên website.

## Thu thập

```bash
# 2 API calls: toàn bộ problemset + contest metadata
python -m cpbench sync

# HTML statement còn thiếu; 0 = tất cả bài phù hợp
python -m cpbench crawl statements --min-rating 800 --max-rating 1900 --limit 0

# Chỉ lấy metadata AC nhanh, không truy cập trang source
python -m cpbench crawl references --metadata-only --limit 100

# Đối chiếu cả statement imported với trang gốc; giữ lại provenance/editorial cũ
python -m cpbench crawl statements --verify-imported --limit 100

# Public C++ accepted submissions, grouped by contest
python -m cpbench crawl references --min-rating 800 --max-rating 1900 --limit 100

# Bổ sung statement/editorial từ corpus công khai, revision cố định
pip install -r requirements-import.txt
python scripts/import_openr1.py --revision fbe3f6e903ee854eec2e69e9d96d0306cde59baf

# Bản đóng băng độc lập với Codeforces
python -m cpbench freeze frozen
python -m cpbench snapshot dist
```

Dùng **một process ứng dụng trên một thư mục data**. Khóa liên process ngăn CLI crawl và server chạy cùng lúc trên cùng data directory. Giao diện server hỗ trợ pause/resume và quản lý worker. CLI crawl chờ đến trạng thái cuối; trả exit code 1 nếu còn thiếu/lỗi. Giao diện có checkpoint, số lượt xử lý và lỗi của từng bài. Khi restart, tác vụ đang chạy chuyển paused, có thể resume ở UI. Pause có hiệu lực ở ranh giới request và ngắt sớm thời gian backoff; request đang chờ phản hồi có thể cần hết timeout.

Statement job dùng từng URL problemset canonical, kiểm tra robots và checkpoint sau từng bài. Collector dùng ≥2,2 giây/request, cache 24 giờ có kiểm tra hash, retry lỗi mạng/429/5xx tối đa 4 lượt. Lỗi riêng lẻ như 404 không làm dừng lô; mất kết nối sau retry và hạn chế truy cập statement dừng lô với lý do rõ ràng. Không xoay proxy, không vượt CAPTCHA. Khi trang source không cho truy cập, giữ metadata AC, đánh dấu `partial` và tiếp tục các bài khác.

Job reference mặc định quét tối đa 20 trang × 1.000 submissions mỗi contest; không tìm thấy trong phạm vi này không có nghĩa không tồn tại source AC. API nâng `max_pages` đến 1.000 nếu cần. `metadata_only=true` không request trang source. `completed` là số mục **đã xử lý**, gồm thành công/một phần/lỗi; trạng thái `completed_with_errors` cho phép retry chỉ các mục chưa thành công. Xem `/api/jobs/{id}/items` để biết trạng thái và số lượt từng bài. Không xóa dữ liệu đã lấy khi retry.

Importer đọc các cột mô tả bằng HTTP Range từ Parquet: không tải toàn bộ official/generated tests, không chạy generated checkers. Mỗi shard có checkpoint. Phân biệt `codeforces_html` và `open_r1_import`. Revision là SHA cố định; lưu hash file upstream khi được cung cấp, hash bản ghi đã chọn cột và URL.

## Chức năng hiện có

- ID ổn định `contestId + index`, URL problem/contest/submit gốc.
- Lưu toàn bộ object Problem, Contest, ProblemStatistics trả về bởi API; rating, tags, scoring type, thời gian contest, solvedCount và các trường tùy chọn.
- Statement, input/output, note, mẫu, giới hạn time/memory, dấu hiệu interactive, editorial text/link nếu nguồn có cung cấp.
- Reference metadata: submission ID/URL, language, verdict, author public handle, runtime, memory, testset và raw Submission. Chỉ lưu source có thể truy cập; không sinh giả source thiếu.
- SQLite WAL; raw evidence immutable theo SHA-256; timestamps UTC; filter/search/sort; JSONL exports; manifest.
- Giao diện tiếng Việt sáng, responsive; chart lọc rating; selection, drawer chi tiết và tải bản ghi.
- Export `prompts_only=true` dùng allowlist, loại editorial/reference/provenance khỏi prompt.
- Split trên nhóm liên thông của contest + alias + mô tả trùng sau chuẩn hóa khoảng trắng; tính trên toàn corpus trước bộ lọc. Vẫn cần audit trùng ngữ nghĩa/contamination.
- Export đọc một SQLite snapshot; manifest và số liệu xuất từ cùng snapshot. JSONL mang tên SHA-256, manifest được thay thế nguyên tử; file corpus cũ không bị ghi đè. Lấy tên file từ `manifest.json["file"]`.

## API

```bash
curl 'http://127.0.0.1:8765/api/problems?min_rating=1600&max_rating=1900&tag=dp'
curl 'http://127.0.0.1:8765/api/problems/4A'
curl -X POST 'http://127.0.0.1:8765/api/jobs' \
  -H 'Content-Type: application/json' \
  -d '{"kind":"references","min_rating":800,"max_rating":1600,"limit":100,"max_pages":20}'
curl 'http://127.0.0.1:8765/api/export?prompts_only=true' -o prompts.jsonl
```

`GET /api/stats`, `GET /api/jobs`, `GET /api/events`, `GET /api/jobs/{id}/items?offset=0&limit=100`, `POST /api/jobs/{id}/pause`, `POST /api/jobs/{id}/resume`. `POST /api/submissions` trả **501 JUDGE_NOT_CONFIGURED**, không chạy hoặc nộp code. Server bind loopback, không bật wildcard CORS. Không đưa server trực tiếp lên internet khi chưa bổ sung authentication và deployment review.

## Cấu trúc

```text
cpbench/store.py       SQLite schema, raw evidence, truy vấn
cpbench/crawler.py     Codeforces HTTP client và collectors
cpbench/parser.py      HTML statement và source parser
cpbench/jobs.py        Durable queue, checkpoint, pause/resume
cpbench/locking.py     Single collector ownership per data directory
cpbench/export.py      Snapshot, JSONL và deterministic splits
cpbench/api.py         FastAPI và local UI
scripts/import_openr1.py  Import corpus theo revision
scripts/audit.py       Integrity, alias và coverage audit
scripts/package.py     Gói corpus/source cho website
dist/                 UI và web snapshot được sinh
tests/                Kiểm thử hành vi dữ liệu, API, checkpoint
```

## Kiểm thử

```bash
pip install -r requirements-dev.txt
python -m pytest -q
node --check dist/app.js
python scripts/audit.py --data data --output audit.json
```

Test sử dụng fixture cục bộ, không gọi mạng. Thử nghiệm mạng thực tế được ghi trong log thu thập và `docs/VALIDATION.md`. Dependency được pin; `requirements-lock.txt` là toàn bộ environment dùng lúc bàn giao.

## Phạm vi nghiên cứu và attribution

Đọc [METHODOLOGY.md](docs/METHODOLOGY.md), [SCHEMA.md](docs/SCHEMA.md), [PHASE2.md](docs/PHASE2.md), [ATTRIBUTION.md](docs/ATTRIBUTION.md). Kho dữ liệu này **chưa được chứng minh đủ điều kiện paper**: cần đánh giá chất lượng statement, nguồn reference, test adequacy, duplicate/contamination và tái lập môi trường chấm. Không đồng nhất samples hoặc tests từ corpus khác với hidden system tests Codeforces.

## Thay đổi v0.2

Xem [CHANGELOG.md](docs/CHANGELOG.md) để biết các lỗi đã sửa và giới hạn còn lại.
