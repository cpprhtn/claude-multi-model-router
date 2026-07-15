#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_tier_cases.py — 분류 회귀 테스트 (B-2)

tests/tier_cases.json의 "프롬프트 → 기대 티어" 케이스를 `route.py --tier-only --json`으로
실제 호출해 검증한다(서브프로세스 — 인자 파싱까지 포함해 실제 사용 경로 그대로 테스트).
--tier-only는 분류만 하고 API를 호출하지 않으므로 키·크레딧 불필요, PR마다 돌려도 비용 0.

사용:
  python tests/run_tier_cases.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
ROUTE_PY = os.path.join(REPO_ROOT, ".claude", "skills", "claude-multi-model-router", "route.py")


def run_tier_only(prompt):
    result = subprocess.run(
        [sys.executable, ROUTE_PY, "--tier-only", "--json", prompt],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"route.py --tier-only 실패(exit={result.returncode}): {result.stderr}")
    payload = json.loads(result.stdout)
    return payload["tier"], payload["reason"]


def main():
    cases_path = os.path.join(HERE, "tier_cases.json")
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    failures = []
    for idx, case in enumerate(cases):
        prompt = case["prompt"]
        expected = case["expected"]
        tier, reason = run_tier_only(prompt)
        ok = tier == expected
        label = prompt if len(prompt) < 60 else f"{prompt[:57]}..."
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] #{idx} expected={expected} got={tier}  {label!r}")
        if not ok:
            failures.append((idx, case, tier, reason))

    print(f"\n{len(cases) - len(failures)}/{len(cases)} passed")

    if failures:
        print("\n실패 상세:", file=sys.stderr)
        for idx, case, tier, reason in failures:
            print(f"  #{idx} note={case.get('note', '')!r}", file=sys.stderr)
            print(f"    prompt={case['prompt']!r}", file=sys.stderr)
            print(f"    expected={case['expected']} got={tier} ({reason})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
