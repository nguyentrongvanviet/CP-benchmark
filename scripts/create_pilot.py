"""Creates reviewed small pilot packages; does not fetch or generate mass corpus tests."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLUTIONS = {
    "4A": (
        "Watermelon",
        800,
        ["math", "brute force"],
        'int w;cin>>w;cout<<(w>2&&w%2==0?"YES":"NO");',
        'int w;cin>>w;cout<<(w%2==0?"YES":"NO");',
    ),
    "1A": (
        "Theatre Square",
        1000,
        ["math"],
        "long long n,m,a;cin>>n>>m>>a;cout<<((n+a-1)/a)*((m+a-1)/a);",
        "int n,m,a;cin>>n>>m>>a;cout<<((n+a-1)/a)*((m+a-1)/a);",
    ),
    "158A": (
        "Next Round",
        800,
        ["implementation"],
        "int n,k;cin>>n>>k;vector<int>a(n);for(int&x:a)cin>>x;int ans=0;for(int x:a)ans+=x>0&&x>=a[k-1];cout<<ans;",
        "int n,k;cin>>n>>k;vector<int>a(n);for(int&x:a)cin>>x;int ans=0;for(int x:a)ans+=x>=a[k-1];cout<<ans;",
    ),
    "189A": (
        "Cut Ribbon",
        1300,
        ["dp", "brute force"],
        "int n,a,b,c;cin>>n>>a>>b>>c;int ans=0;for(int i=0;i*a<=n;i++)for(int j=0;i*a+j*b<=n;j++){int r=n-i*a-j*b;if(r%c==0)ans=max(ans,i+j+r/c);}cout<<ans;",
        "int n,a,b,c;cin>>n>>a>>b>>c;cout<<n/min({a,b,c});",
    ),
    "455A": (
        "Boredom",
        1500,
        ["dp"],
        "int n;cin>>n;vector<long long>cnt(100001),dp(100001);while(n--){int x;cin>>x;cnt[x]++;}dp[1]=cnt[1];for(int i=2;i<=100000;i++)dp[i]=max(dp[i-1],dp[i-2]+i*cnt[i]);cout<<dp[100000];",
        "int n;cin>>n;int s=0,x;while(n--){cin>>x;s+=x;}cout<<s;",
    ),
    "474B": (
        "Worms",
        1200,
        ["binary search", "implementation"],
        'int n;cin>>n;vector<int>a(n);for(int i=0;i<n;i++){cin>>a[i];if(i)a[i]+=a[i-1];}int m;cin>>m;while(m--){int q;cin>>q;cout<<lower_bound(a.begin(),a.end(),q)-a.begin()+1<<"\\n";}',
        'int n;cin>>n;vector<int>a(n);for(int i=0;i<n;i++){cin>>a[i];if(i)a[i]+=a[i-1];}int m;cin>>m;while(m--){int q;cin>>q;cout<<upper_bound(a.begin(),a.end(),q)-a.begin()+1<<"\\n";}',
    ),
}
for pid, (name, rating, tags, correct, wrong) in SOLUTIONS.items():
    p = ROOT / "packages" / pid
    p.mkdir(exist_ok=True, parents=True)
    manifest = dict(
        schema_version=1,
        id=pid,
        name=name,
        rating=rating,
        tags=tags,
        version="1.0.0",
        generator="generator.py",
        checker="yesno_casefold_v1" if pid == "4A" else "integer_tokens_v1",
        time_limit_ms=3000 if pid == "158A" else 1000,
        memory_limit_mb=64 if pid == "4A" else 256,
        reference="reference.cpp",
        mutants=["wrong.cpp"],
        reference_origin="cpbench_authored_not_codeforces_verified",
        scope="pilot",
        limitations="Small public pilot; not representative of full CP ability. No official hidden tests.",
        url=f"https://codeforces.com/problemset/problem/{pid[:-1]}/{pid[-1]}",
    )
    (p / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (p / "generator.py").write_text(
        f'from cpbench.generators import generate as _generate, validate as _validate\n\ndef generate(seed, count):\n    return _generate("{pid}", seed, count)\n\ndef validate(text):\n    return _validate("{pid}", text)\n'
    )
    for file, body in [("reference.cpp", correct), ("wrong.cpp", wrong)]:
        (p / file).write_text(
            "#include <bits/stdc++.h>\nusing namespace std;\nint main(){ios::sync_with_stdio(false);cin.tie(nullptr);"
            + body
            + "return 0;}\n"
        )
print("Created", len(SOLUTIONS), "pilot packages")
