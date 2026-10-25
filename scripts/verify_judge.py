"""Real Docker integration checks. Output is evidence, not a model benchmark score."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpbench import judge
from cpbench.store import now

base = {
    "id": "harness",
    "time_limit_ms": 250,
    "memory_limit_mb": 32,
    "checker": "integer_tokens_v1",
}
cases = [{"input": "1\n", "output": "1\n", "category": "harness"}]
programs = {
    "AC": '#include <iostream>\nint main(){std::cout<<"0001";}',
    "WA": "#include <iostream>\nint main(){std::cout<<2;}",
    "CE": "this is not cpp",
    "RTE": "#include <cstdlib>\nint main(){abort();}",
    "TLE": 'int main(){for(;;){asm volatile("":::"memory");}}',
    "OLE": '#include <cstdio>\nint main(){for(;;)puts("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx");}',
    "MLE": "#include <cstdlib>\n#include <unistd.h>\nint main(){for(int j=0;j<48;j++){volatile char*p=(char*)malloc(1024*1024);for(int i=0;i<1024*1024;i+=4096)p[i]=1;usleep(1000);}sleep(1);}",
    "SECURITY_VIOLATION": "#include <unistd.h>\nint main(){fork();}",
}
results = []
for expected, source in programs.items():
    limits = dict(base, time_limit_ms=1500 if expected in ("MLE", "OLE") else 250)
    result = judge.evaluate(source, cases, limits)
    print(expected, "=>", result["verdict"], flush=True)
    results.append(
        {
            "expected": expected,
            "actual": result["verdict"],
            "passed": result["verdict"] == expected,
            "details": result,
        }
    )
# Candidate cannot read supervisor memory, hidden payload, or root-only input pathname.
security = '#include <fstream>\n#include <iostream>\nint main(){std::ifstream a("/proc/1/mem"),b("/work/.stdin"),c("/payload/request.json");std::cout<<(!a&&!b&&!c);}'
r = judge.evaluate(security, cases, base)
results.append(
    {
        "expected": "AC",
        "actual": r["verdict"],
        "passed": r["verdict"] == "AC",
        "name": "hidden_data_access_denied",
        "details": r,
    }
)
output = {
    "at": now(),
    "passed": all(r["passed"] for r in results),
    "checks": results,
    "environment": judge.environment(),
}
Path("docs/judge-validation.json").write_text(json.dumps(output, indent=2))
print("ALL PASSED:", output["passed"])
raise SystemExit(0 if output["passed"] else 1)
