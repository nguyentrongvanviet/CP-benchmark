"""Reviewed pilot generators: independent Python oracles, constraints and brute checks.
These are trusted application code, never loaded from scraped statements.
"""

import bisect
import itertools
import random
from collections import Counter


def validate(pid, text):
    x = list(map(int, text.split()))
    if pid == "4A":
        assert len(x) == 1 and 1 <= x[0] <= 100
    elif pid == "1A":
        assert len(x) == 3 and all(1 <= v <= 10**9 for v in x)
    elif pid == "158A":
        n, k, *a = x
        assert 1 <= k <= n <= 50 and len(a) == n
        assert all(0 <= v <= 100 for v in a) and a == sorted(a, reverse=True)
    elif pid == "189A":
        assert len(x) == 4 and all(1 <= v <= 4000 for v in x)
        n, a, b, c = x
        assert any(
            (n - i * a - j * b) >= 0 and (n - i * a - j * b) % c == 0
            for i in range(n // a + 1)
            for j in range((n - i * a) // b + 1)
        )
    elif pid == "455A":
        n, *a = x
        assert 1 <= n <= 100000 and len(a) == n and all(1 <= v <= 100000 for v in a)
    elif pid == "474B":
        n = x[0]
        assert 1 <= n <= 100000 and len(x) > n + 1
        a, m, q = x[1 : n + 1], x[n + 1], x[n + 2 :]
        total = sum(a)
        assert all(1 <= v <= 1000 for v in a) and total <= 1000000
        assert 1 <= m <= 100000 and len(q) == m and all(1 <= v <= total for v in q)
    else:
        raise ValueError("Unknown built-in generator")


def oracle(pid, text):
    x = list(map(int, text.split()))
    if pid == "4A":
        return "YES\n" if x[0] > 2 and x[0] % 2 == 0 else "NO\n"
    if pid == "1A":
        n, m, a = x
        return f"{(-(-n // a)) * (-(-m // a))}\n"
    if pid == "158A":
        n, k, *a = x
        return f"{sum(v > 0 and v >= a[k - 1] for v in a)}\n"
    if pid == "189A":
        n, *cuts = x
        dp = [-10000] * (n + 1)
        dp[0] = 0
        for length in range(1, n + 1):
            dp[length] = max(
                (dp[length - c] + 1 for c in cuts if c <= length), default=-10000
            )
        return f"{dp[n]}\n"
    if pid == "455A":
        counts = Counter(x[1:])
        prev2 = prev1 = 0
        for v in range(1, max(counts) + 1):
            prev2, prev1 = prev1, max(prev1, prev2 + v * counts[v])
        return f"{prev1}\n"
    if pid == "474B":
        n = x[0]
        a = x[1 : n + 1]
        q = x[n + 2 :]
        prefix = list(itertools.accumulate(a))
        return "".join(f"{bisect.bisect_left(prefix, v) + 1}\n" for v in q)


def brute(pid, text):
    """Algorithmically separate small-case oracles; None means case too large."""
    x = list(map(int, text.split()))
    if pid == "4A":
        return (
            "YES\n"
            if any(i % 2 == 0 and (x[0] - i) % 2 == 0 for i in range(1, x[0]))
            else "NO\n"
        )
    if pid == "1A":
        n, m, a = x
        if max(n, m) > 50:
            return None
        return f"{len(range(0, n, a)) * len(range(0, m, a))}\n"
    if pid == "158A":
        n, k, *scores = x
        threshold = sorted(scores, reverse=True)[k - 1]
        qualified = [i for i in range(n) if scores[i] and not scores[i] < threshold]
        return f"{len(qualified)}\n"
    if pid == "189A":
        n, a, b, c = x
        if n > 100:
            return None
        return f"{max(i + j + (n - i * a - j * b) // c for i in range(n // a + 1) for j in range((n - i * a) // b + 1) if (n - i * a - j * b) % c == 0)}\n"
    if pid == "455A":
        counts = Counter(x[1:])
        keys = sorted(counts)
        if len(keys) > 12:
            return None
        best = 0
        for mask in range(1 << len(keys)):
            chosen = [k for i, k in enumerate(keys) if mask >> i & 1]
            if any(b - a == 1 for a, b in zip(chosen, chosen[1:])):
                continue
            best = max(best, sum(k * counts[k] for k in chosen))
        return f"{best}\n"
    if pid == "474B":
        n = x[0]
        a = x[1 : n + 1]
        qs = x[n + 2 :]
        if sum(a) > 1000:
            return None
        expanded = [i + 1 for i, v in enumerate(a) for _ in range(v)]
        return "".join(f"{expanded[q - 1]}\n" for q in qs)


def generate(pid, seed, count):
    rng = random.Random(seed)
    cases = []

    def add(text, category):
        validate(pid, text)
        expected = oracle(pid, text)
        check = brute(pid, text)
        if check is not None and check.split() != expected.split():
            raise ValueError("Independent oracle disagreement")
        cases.append(
            dict(
                input=text,
                output=expected,
                category=category,
                brute_verified=check is not None,
            )
        )

    if pid == "4A":
        for n in range(1, 101):
            add(f"{n}\n", "exhaustive")
    elif pid == "1A":
        for vals in [
            (1, 1, 1),
            (1, 1, 10**9),
            (10**9, 10**9, 1),
            (10**9, 10**9, 999999999),
            (6, 6, 4),
            (10, 10, 5),
        ]:
            add(" ".join(map(str, vals)) + "\n", "boundary")
        for _ in range(count):
            add(
                " ".join(str(rng.randint(1, 50)) for _ in range(3)) + "\n",
                "small_random",
            )
    elif pid == "158A":

        def fmt(scores, k):
            return (
                f"{len(scores)} {k}\n"
                + " ".join(map(str, sorted(scores, reverse=True)))
                + "\n"
            )

        for scores, k in [
            ([0], 1),
            ([1], 1),
            ([0] * 50, 50),
            ([100] * 50, 1),
            ([10, 9, 8, 7, 7, 7, 5, 5], 5),
            ([5, 0, 0], 2),
        ]:
            add(fmt(scores, k), "boundary")
        for _ in range(count):
            n = rng.randint(1, 50)
            add(
                fmt([rng.randint(0, 10) for _ in range(n)], rng.randint(1, n)),
                "small_random",
            )
    elif pid == "189A":
        for vals in [
            (5, 5, 3, 2),
            (7, 5, 5, 2),
            (4000, 1, 1, 1),
            (4000, 3999, 1, 4000),
            (4000, 2, 3, 7),
            (1, 1, 2, 3),
        ]:
            add(" ".join(map(str, vals)) + "\n", "boundary")
        for _ in range(count):
            cuts = [rng.randint(1, 10) for _ in range(3)]
            n = sum(c * rng.randint(0, 3) for c in cuts) or cuts[0]
            add(" ".join(map(str, [n, *cuts])) + "\n", "small_random")
    elif pid == "455A":

        def fmt(a):
            return f"{len(a)}\n" + " ".join(map(str, a)) + "\n"

        for a in [
            [1],
            [1, 2, 3],
            [2, 2, 3, 3, 3, 4],
            [100000] * 100000,
            [1] * 100000,
            list(range(1, 100001)),
        ]:
            add(fmt(a), "boundary")
        for _ in range(count):
            add(
                fmt([rng.randint(1, 12) for _ in range(rng.randint(1, 30))]),
                "small_random",
            )
    elif pid == "474B":

        def fmt(a, q):
            return (
                f"{len(a)}\n"
                + " ".join(map(str, a))
                + f"\n{len(q)}\n"
                + " ".join(map(str, q))
                + "\n"
            )

        for a, q in [
            ([1], [1]),
            ([2, 7, 3, 4, 9], [1, 2, 3, 9, 10, 25]),
            ([10] * 100000, [1, 10, 11, 999999, 1000000]),
            ([1] * 100000, list(range(1, 100001))),
        ]:
            add(fmt(a, q), "boundary")
        for _ in range(count):
            a = [rng.randint(1, 10) for _ in range(rng.randint(1, 30))]
            add(fmt(a, [rng.randint(1, sum(a)) for _ in range(30)]), "small_random")
    return cases
