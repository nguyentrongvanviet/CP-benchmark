# CPBench v0.3 — independent pilot benchmark

## Chạy nhanh

```bash
python -m cpbench serve --port 8765
# Bật Docker Desktop, rồi build image một lần:
docker build -t cpbench-judge:v1 judge
```

Mở http://127.0.0.1:8765/#benchmark. Không cần model API key để sử dụng bản này.

1. **Bộ bài & test:** chọn bài, Sinh test. Mặc định seed 42, 32 random cases, cộng boundary/exhaustive và sample. Chỉ bài vượt kiểm chứng mới bật benchmark.
2. **Nộp C++:** nhập code/file .cpp, chờ verdict và xem test đầu tiên thất bại.
3. **Đánh giá model:** chọn tập bài, xuất prompts JSONL; đưa prompt cho model bằng công cụ của bạn; nhập JSONL lời giải rồi chạy benchmark.
4. **Báo cáo JSON:** tải từ từng job. Báo cáo gồm source, source hash, testset version, image digest, compiler version/flags, architecture, CPU/wall time, peak RSS, verdict và metadata thí nghiệm.

Ví dụ JSONL (mỗi object trên một dòng):

```json
{"problem_id":"4A","sample_id":"0","source_code":"#include <iostream>\nint main(){int n;std::cin>>n;std::cout<<(n>2&&n%2==0?\"YES\":\"NO\");}","testset_version":"COPY_FROM_PROMPT_EXPORT"}
```

`source_code` có thể là code thô hoặc đúng một fenced C++ block. `code` là alias. Trùng `(problem_id, sample_id)` bị từ chối. `testset_version` bỏ trống sẽ được đóng băng theo bản hiện tại ở thời điểm tạo run; nên truyền hash từ prompt để tránh lệch phiên bản. Chỉ nhận tối đa 100 samples / run và 4 MB JSONL.

## Phạm vi pilot

| ID | Nội dung | Rủi ro được kiểm tra |
|---|---|---|
| 4A | Watermelon | w=2; exhaustive toàn bộ 1..100 |
| 1A | Theatre Square | chia làm tròn; số nguyên 64-bit; biên 10^9 |
| 158A | Next Round | điểm 0; hòa điểm; k=n |
| 189A | Cut Ribbon | tổng phải đúng; greedy sai; n=4000 |
| 455A | Boredom | quan hệ lân cận; DP; tổng vượt int32; n=100000 |
| 474B | Worms | biên prefix; lower_bound; n,m=100000 |

Các reference `packages/*/reference.cpp` do CPBench viết, không tự nhận là code đã AC Codeforces. `wrong.cpp` là mutation có chủ đích, không tự nhận là WA submission thật. Chỉ có 1 mutation/bài trong pilot; mutation detection không chứng minh test đầy đủ. Những bài công khai, cũ và nhỏ này dùng để kiểm tra pipeline, không dùng để suy rộng năng lực CP của model.

## Gói bài có thể mở rộng

```bash
python scripts/init_package.py 1234A
```

Lệnh đọc bất kỳ ID đã có trong corpus; không có danh sách ID cố định trong engine. Đồng bộ catalog và cào đề mới qua Crawler trước. Lệnh không ghi đè gói đã tồn tại.

Mỗi thư mục `packages/<id>/` chứa:

- `manifest.json`: ID, tên, version, rating/tags, giới hạn, checker, tên generator/reference/mutants, nguồn reference.
- `generator.py`: `generate(seed,count)` trả danh sách `{input,output,category,brute_verified}`; `validate(text)` kiểm tra toàn bộ ràng buộc và raise khi sai. Generator/oracle là **mã ứng dụng được lập trình viên tin cậy rà soát**, chạy trên host. Không có API upload và thực thi Python tùy ý, không chạy generator lấy từ webpage hoặc model.
- `reference.cpp`: lời giải đáng tin cậy, có attribution. Chạy trong Docker.
- `wrong.cpp` hoặc danh sách mutants: chương trình phải compile, thể hiện lỗi hợp lý và bị tests loại. CE không được tính là bắt lỗi thuật toán.

Pipeline yêu cầu: generator deterministic với cùng seed; mọi input qua validator; có sample từ statement; có ít nhất một trường hợp đối chiếu brute; reference AC trên mọi test; mỗi mutant bị WA/TLE/MLE/RTE/OLE. Khi đã lấy được source AC Codeforces của bài, kiểm tra thêm tối đa 5 reference và chỉ bật phiên bản mới nếu tất cả đều local AC. Báo cáo ghi rõ số source có sẵn/đã kiểm tra. Không có source upstream vẫn cho chạy pilot với reference tự viết, và ghi `upstream_checked=0`.

Hợp đồng `brute_verified` là bằng chứng do generator tin cậy trả về; engine không thể tự chứng minh oracle của một extension mới là đúng. Khi viết paper cần review generator, oracle và validator riêng, thêm nhiều reference/mutation độc lập, adversarial tests, và lưu review.

Checker hiện hỗ trợ `integer_tokens_v1` (parse integer), `yesno_casefold_v1`, `exact_tokens_v1` (bỏ khác biệt whitespace). Bài có nhiều đáp án, output thực sai số, interactive, output-only cần checker/interactor riêng: chưa hỗ trợ, không gắn benchmark-ready tự động.

Giới hạn hiện tại: 512 tests và 8 MiB/testset, random count 1..128, 50 bài/run. Không sinh cho toàn corpus. Frozen testsets nằm ở `data/testsets/<sha256>.json`; không sửa file đã đóng băng. Sinh lại tạo phiên bản kiểm chứng mới, `tests_sha256` cho biết input/output có giống nhau hay không. Bản cũ vẫn dùng được qua API với version cụ thể. Image cũ cũng phải được giữ để tái lập.

## Compiler và cách ly

Docker Linux, GNU g++ 12 (phiên bản chính xác trong report), `-std=c++20 -O2 -pipe -DONLINE_JUDGE`. Image base pin digest; image build thực tế cũng pin theo content ID cho từng testset. Apt dependency có thể đổi khi build lại, nên giữ image đã dùng (`docker save`) nếu cần tái lập xuyên máy.

Một container/submission; compile đúng một lần, chạy process mới cho mỗi test, dừng ở lỗi đầu. Một worker tuần tự; không tái sử dụng binary giữa submission để tránh cache không rõ nguồn.

- Container không network, root filesystem read-only, không mount host directory/Docker socket, no-new-privileges, 1 CPU, cgroup 1 GiB, pids 64, tmpfs /work 128 MiB và /tmp 64 MiB.
- Supervisor có các capability tối thiểu để hạ UID và dọn process; compiler/candidate là UID/GID 65534. Payload chỉ ở bộ nhớ supervisor, không nằm trên filesystem candidate đọc được.
- Candidate seccomp chặn fork/clone/thread/socket/ptrace và các syscall quản trị. Đây là profile CP **đơn tiến trình, đơn thread**; code cần thread không tương thích.
- Per-process RLIMIT_CPU, RLIMIT_AS (2x RSS budget), RLIMIT_NPROC, RLIMIT_FSIZE, no core dump; giám sát output 1 MiB/stream và RSS. Wall timeout là `2 * CPU budget + 0.5 s` để bắt sleep/hang.
- Không có fallback chạy code trực tiếp trên macOS. Docker/image không sẵn sàng => INFRA_ERROR.

Đây là sandbox local nghiên cứu, không phải dịch vụ public multi-tenant đã được audit bảo mật. Không expose API ra mạng. Timing Linux ARM64/Docker Desktop khác Codeforces; không tuyên bố “y hệt Codeforces”. RSS có độ trễ sampling; peak RSS của wait4 được kiểm tra thêm sau exit. Nếu allocation bị RLIMIT_AS từ chối trước khi RSS vượt budget, chương trình có thể nhận RTE thay vì MLE. Compiler quá tài nguyên được ghi trong diagnostics của CE.

Verdicts triển khai: AC, WA, CE, RTE, TLE, MLE, OLE, SECURITY_VIOLATION, INFRA_ERROR. Với profile batch này không có điểm từng phần, interactive idleness hay presentation-error riêng. Lỗi checker/generator hoặc restart hạ tầng được ghi INFRA_ERROR; job đang chạy khi restart thành `interrupted`, không giả là đã chấm xong.

## Phương pháp đánh giá

- `pass_at_1`: trung bình tỷ lệ AC per-problem trên các bài có kết quả chấm hợp lệ; nếu mỗi bài có 1 sample thì chính là tỷ lệ bài AC.
- `pass_at_k`: ước lượng `1 - C(n-c,k)/C(n,k)`; chỉ những bài có đủ k samples hợp lệ được tính; báo số bài đủ điều kiện.
- `coverage`: số bài có ít nhất một kết quả hợp lệ / số bài đã chọn. Báo bài thiếu và số lỗi hạ tầng riêng, không âm thầm đổi lỗi infra thành WA hoặc kết luận đã đánh giá toàn tập.
- Wilson 95% chỉ khi mỗi bài được tính có đúng 1 attempt. Không phải CI của benchmark đại diện nếu tập bài được chọn có thiên lệch.
- Phân nhóm rating và tags; lưu model name/temperature/seed do người dùng khai báo. JSONL offline không chứng minh code thật sự do model được khai báo sinh ra.
- Prompt export dùng allowlist statement/input/output/note/samples, không chứa editorial/reference/hidden tests. Lưu prompt hash và manifest. Với code nhập offline, hash này mô tả prompt đề xuất, không chứng minh model thực sự đã nhận nó.
- Tách test-content hash, package hash, source hash, image ID. Muốn paper cần frozen dataset manifest, duplicate/alias audit, time cutoff, contamination discussion, số mẫu và token/time budget nhất quán. Pilot không tạo một kết luận khoa học thay cho nghiên cứu.

## Codeforces account và nguồn AC

Trong tab Codeforces account, handle mặc định `Viet_love_KA`. Chỉ metadata public khi không nhập key. Để lấy source chính tài khoản, tạo key tại https://codeforces.com/settings/api rồi nhập key + secret vào form localhost. Request ký SHA512 theo tài liệu chính thức; không lưu khóa hoặc URL có chữ ký. Secret được xóa khỏi form sau request, không localStorage/cookie. Data có source vẫn lưu provenance, submission ID, link, verdict và SHA256. Không tự nộp code hoặc sửa tài khoản.

Có thể đọc tiếp trang lịch sử bằng offset, tối đa 500 submission/request; không tải tất cả lịch sử mặc định. Tất cả requests dùng chung pacing lock với collector (ít nhất 2,2 giây giữa các request). Nếu Codeforces từ chối quyền, báo lỗi rõ ràng; không vượt challenge hoặc robots của crawler.

Codeforces submission qua trình duyệt tự động chưa bật. Có thể dùng link submit gốc và code export để đối chiếu thủ công. Local AC không đồng nghĩa Codeforces AC. Không gửi mật khẩu/cookie vào chat.

## API

- `GET /api/lab`: environment, packages, lịch sử jobs.
- `POST /api/testsets`: `{problem_id,seed,count}` -> 202 + job ID.
- `POST /api/submissions`: `{problem_id,source_code,language:"cpp20",testset_version?,idempotency_key?}` -> 202. problem_id có thể là link `/problemset/problem/4/A` hoặc `/contest/4/problem/A`.
- `GET /api/lab/jobs/{id}` / `GET /api/submissions/{id}`.
- `GET /api/benchmark/prompts?ids=4A,1A` -> JSONL.
- `POST /api/benchmark/runs`: `{name,problem_ids,jsonl,model_metadata}`.
- `GET /api/benchmark/runs/{id}/export` -> đầy đủ request + report.
- `POST /api/account/import`: `{handle,api_key?,api_secret?,offset,count}`.

Queue tối đa 50 jobs. Idempotency key gắn với request cụ thể; dùng lại key cho code khác bị từ chối. Run/testset/submit API dùng cùng dữ liệu với UI. OpenAPI tại `/docs`.

## Đọc đề

Rich HTML khi raw Codeforces HTML đã có; fallback Markdown có cấu trúc cho Open R1. DOMPurify lọc HTML; KaTeX render math với trust=false; thư viện/font đóng gói offline. Mở rộng khung, đổi cỡ chữ, copy sample và in/PDF. Ảnh Codeforces có thể cần mạng. Văn bản bị mất công thức ngay từ dữ liệu upstream không thể được khôi phục một cách đáng tin cậy bằng renderer; cần cào lại HTML gốc.

## Kiểm chứng

```bash
python -m pytest -q
python scripts/verify_judge.py
```

`docs/judge-validation.json` lưu kết quả thật của Docker cho AC/WA/CE/RTE/TLE/OLE/MLE/SECURITY_VIOLATION và kiểm tra cấm đọc dữ liệu supervisor. Nó là kiểm tra phần mềm, không phải score model.

## Kết quả kiểm chứng ngày 15/10/2026

Đã nhập 7 source C++ có verdict OK từ Codeforces qua trình duyệt đã đăng nhập, gồm một source của `Viet_love_KA` cho 2249C và sáu source public của bộ pilot. Không đọc hoặc lưu cookie đăng nhập. Tác giả được giữ theo metadata submission, không suy ra từ tài khoản đang đăng nhập. API metadata và nội dung source có provenance riêng. Trang Codeforces chèn NBSP vào một số dòng trống khi hiển thị; importer chỉ bỏ NBSP trên dòng hoàn toàn trắng, giữ nguyên các dòng code, và lưu cả raw capture cùng quy tắc chuẩn hóa.

Sáu bài 4A, 1A, 158A, 189A, 455A, 474B có tổng 298 tests, khoảng 3,3 MiB cho sáu frozen testsets hiện hành. Mỗi bài đã qua reference tự viết, brute checks, một mutation bị loại và một source AC Codeforces chạy local AC. Source 2249C được lưu làm dữ liệu; chưa có generator cho bài đó.

`docs/pilot-validation.json` lưu kết quả từng bài; `docs/judge-validation.json` lưu kiểm tra verdict và cách ly; `docs/pipeline-selftest-report.json` lưu run JSONL 12 samples (6 reference + 6 mutants): 6 AC, 6 WA, coverage 6/6, pass@1 50%, pass@2 100%, không lỗi hạ tầng. Đây là **kiểm tra pipeline, không phải điểm model**. Luồng nộp C++ trực tiếp trên giao diện cũng đã kiểm tra với 4A, AC 101/101.

51 unit/integration tests Python đã pass; Docker kiểm tra AC/WA/CE/RTE/TLE/MLE/OLE/SECURITY_VIOLATION và candidate không đọc được payload/supervisor. Các kiểm tra này không thay thế security audit.

Đóng gói nhỏ bằng `python scripts/package_pilot.py`: chỉ sáu bài, source, frozen tests và raw evidence liên quan; không gom toàn bộ corpus. Bản bundle không chứa Docker image. Nếu chuyển máy, build image và sinh phiên bản test mới, hoặc chuyển đúng image cũ bằng công cụ Docker để giữ khả năng tái lập. Các archive corpus cũ là snapshot lịch sử, không phản ánh kết quả judge mới.
