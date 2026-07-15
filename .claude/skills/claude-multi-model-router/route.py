#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
route.py — OpenRouter 라우터 (독립 실행, 클로드 토큰 0) + cn_run.py와 공유하는 모델 상태

역할:
  1) 호출자(Claude)가 SKILL.md 티어 판정표에서 이미 정한 난이도를 --tier로 직접 받는 것이
     기본 경로다. --tier 없이 호출되면(사람이 CLI로 치는 경우 등) 규칙 기반 classify()로
     free/sonnet/opus를 폴백 분류한다 — Claude의 판정과 내부 classify()가 서로 다른 결론을
     내려 충돌하는 것을 막기 위해 --tier가 항상 우선한다.
  2) free/delegate 대상 -> OpenRouter 모델 직접 호출 (429/오류 시 짧은 재시도)
     실제로 부를 모델은 cn_run.py와 완전히 같은 상태(sticky/autoscale, cn_models.json)를
     따른다 — "OpenRouter 위임"은 route.py/cn_run.py 공통 스위치이므로, 사용자가
     유료 모델에 sticky 고정했거나 오토스케일을 켰다면 route.py도 그걸 그대로 반영해야
     한다.
  3) --tier 미지정 + classify() 결과가 sonnet/opus -> 호출하지 않고 ESCALATE 마커만 출력
     (클로드가 처리)

사용:
  python route.py "질문 내용"
  python route.py --json "질문 내용"              # 결과를 JSON으로
  python route.py --tier-only "질문"              # 분류만 (호출 없음, 키 불필요)
  python route.py --tier mid "질문"                # Claude가 이미 정한 ladder 티어로 직접 위임
                                                    #   (trivial|light|mid|reason, classify() 건너뜀)
  python route.py --out FILE "질문"                # 응답을 stdout 대신 파일에 저장
                                                    #   (클로드가 내용 재생산 없이 적용/검토)
  echo "질문" | python route.py                    # stdin 입력

모델 선택(= 실제 호출 대상): sticky > --tier(ladder 직접 지정) > autoscale on이면 난이도별
  자동 선택(classify() 폴백) > 없으면 free_slug(기본 openrouter/free). sticky/autoscale on은
  cn_run.py --set-model / --autoscale on으로 설정하며, 상태는 프로젝트 루트
  `.claude/.cmr-state.json`에 저장된다(스킬 폴더 밖 — degit 재설치로 유실되지 않고, git에는
  커밋하지 않도록 .gitignore에 포함). 유료 모델이 선택되면 실제 크레딧이 차감되므로 호출 전
  stderr에 [유료 호출] 마커를 출력한다.

OpenRouter 위임 자체는 opt-in이다: 이 스크립트를 직접 호출하면(사람이 CLI로 치거나
  Claude가 호출하기로 결정한 경우) 항상 실행되고 위 우선순위대로 모델을 호출한다 —
  이 스크립트는 "위임할지 말지" 자체는 판단하지 않는다. 그 판단(free 텍스트 생성을
  OpenRouter로 보낼지, Claude가 Haiku로 직접 처리할지)은 SKILL.md 규칙에 따라 호출하는
  Claude의 몫이며, 기본값은 "sticky도 autoscale도 없으면 이 스크립트를 아예 호출하지
  않음"이다. cn_run.py와 완전히 같은 원칙 — 두 스크립트 모두 스스로 켜짐/꺼짐을
  판단하지 않고, 켜짐/꺼짐 판단은 호출하는 쪽(Claude)의 몫이다.

API 키 (우선순위):
  1) 환경변수 OPENROUTER_API_KEY
  2) 프로젝트 루트 .env (cwd 기준, cn/Continue와 동일한 키 소스)
  3) (레거시) 이 파일과 같은 폴더의 api_key.txt
  키는 https://openrouter.ai/keys 에서 무료 발급.
"""

import sys
import os
import json
import re
import time
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
API_URL = "https://openrouter.ai/api/v1/chat/completions"
ROSTER_FILE = os.path.join(HERE, "cn_models.json")
LADDER_TIERS = ("trivial", "light", "mid", "reason")

# 상태 파일(sticky/autoscale)은 스킬 폴더 밖, 프로젝트 루트(cwd — .env와 같은 기준)에 둔다.
# 스킬 폴더 안에 두면 degit 재설치 시 유실되고, 실수로 git에 개인 상태가 커밋될 위험이 있다.
STATE_DIR = os.path.join(os.getcwd(), ".claude")
STATE_FILE = os.path.join(STATE_DIR, ".cmr-state.json")
# v1 레거시 위치(스킬 폴더 내부) — 있으면 1회 자동 마이그레이션 후 제거.
_LEGACY_ACTIVE_MODEL_FILE = os.path.join(HERE, "cn_active_model.txt")
_LEGACY_AUTOSCALE_FILE = os.path.join(HERE, "cn_autoscale.txt")

# ─────────────────────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────────────────────
def load_models():
    # ESCALATE 안내 라벨 전용(호출 대상 로스터가 아님 — 그건 cn_models.json).
    with open(os.path.join(HERE, "escalate_labels.json"), "r", encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────────────────────────────────────────────
# cn_run.py와 공유하는 모델 상태(sticky/autoscale) — cn_models.json 로스터 기준.
# cn_run.py가 이 함수들을 그대로 import해서 쓴다(중복 구현 금지, 순환참조 방지를 위해
# 상태 관리는 여기 route.py에 두고 cn_run.py가 가져다 쓰는 방향으로 통일).
# ─────────────────────────────────────────────────────────────
def load_roster():
    with open(ROSTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _migrate_legacy_state():
    """v1(스킬 폴더 내부 txt 2개) -> v2(프로젝트 루트 JSON 1개) 1회 마이그레이션."""
    if not (os.path.exists(_LEGACY_ACTIVE_MODEL_FILE) or os.path.exists(_LEGACY_AUTOSCALE_FILE)):
        return None
    state = {}
    if os.path.exists(_LEGACY_ACTIVE_MODEL_FILE):
        with open(_LEGACY_ACTIVE_MODEL_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                state["sticky"] = v
    if os.path.exists(_LEGACY_AUTOSCALE_FILE):
        with open(_LEGACY_AUTOSCALE_FILE, "r", encoding="utf-8") as f:
            state["autoscale"] = f.read().strip() == "on"
    _write_state(state)
    for p in (_LEGACY_ACTIVE_MODEL_FILE, _LEGACY_AUTOSCALE_FILE):
        try:
            os.remove(p)
        except OSError:
            pass
    return state

def _load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    migrated = _migrate_legacy_state()
    return migrated if migrated is not None else {}

def _write_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

def read_sticky():
    return _load_state().get("sticky") or None

def write_sticky(slug):
    state = _load_state()
    state["sticky"] = slug
    _write_state(state)

def clear_sticky():
    state = _load_state()
    if "sticky" in state:
        del state["sticky"]
        _write_state(state)

def read_autoscale():
    return bool(_load_state().get("autoscale", False))

def write_autoscale(on):
    state = _load_state()
    state["autoscale"] = bool(on)
    _write_state(state)

def resolve(alias_or_slug, roster):
    """반환: (slug, tier, note) — 로스터 alias면 매핑, 아니면 원문을 유료 slug로 취급."""
    models = roster["models"]
    if alias_or_slug in models:
        entry = models[alias_or_slug]
        return entry["slug"], entry["tier"], entry.get("note", "")
    for entry in models.values():
        if entry["slug"] == alias_or_slug:
            return entry["slug"], entry["tier"], entry.get("note", "")
    return alias_or_slug, "paid", "(로스터 외 직접 지정 slug)"

def load_api_key():
    # 1) 환경변수
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    # 2) 프로젝트 루트 .env (cwd 기준 — cn/Continue와 동일한 키 소스)
    envfile = os.path.join(os.getcwd(), ".env")
    if os.path.exists(envfile):
        with open(envfile, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip()
    # 3) (레거시) 스킬 폴더의 api_key.txt
    keyfile = os.path.join(HERE, "api_key.txt")
    if os.path.exists(keyfile):
        with open(keyfile, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

# ─────────────────────────────────────────────────────────────
# 난이도 분류 (LLM 호출 없음 → 토큰 0, 즉시)
# ─────────────────────────────────────────────────────────────
# 고난도(opus) 신호: 깊은 추론/설계/증명/보안/동시성/복잡한 최적화
OPUS_KW = [
    "설계", "아키텍처", "architecture", "design a", "증명", "prove", "proof",
    "race condition", "동시성", "concurrency", "deadlock", "교착",
    "보안 취약", "취약점", "vulnerabilit", "exploit", "threat model",
    "분산 시스템", "distributed system", "합의 알고리즘", "consensus",
    "시간 복잡도", "복잡도 분석", "optimize the algorithm", "최적화 알고리즘",
    "trade-off", "트레이드오프", "왜 이렇게", "근본 원인", "root cause",
    "전체 리팩터", "대규모 리팩터", "마이그레이션 전략", "migration strategy",
]
# 중난도(sonnet) 신호: 코드 작성/수정/디버그/테스트/구조화된 작업
SONNET_KW = [
    "리팩터", "refactor", "디버그", "debug", "버그", "bug", "고쳐", "fix",
    "구현", "implement", "함수 작성", "클래스 작성", "테스트 작성", "write test",
    "코드 리뷰", "code review", "리팩토링", "예외 처리", "에러 처리",
    "API 설계", "스키마", "schema", "타입", "제네릭", "정규식 만들", "알고리즘 짜",
]
# 저난도(free) 신호: 단순 질의/번역/요약/설명/포맷
FREE_KW = [
    "번역", "translate", "요약", "summar", "무엇", "뭐야", "뭔가요", "설명해",
    "explain", "정의", "definition", "예시", "example", "list", "나열",
    "맞춤법", "다듬어", "문장", "이메일 써", "제목 지어", "요점", "tl;dr",
]

def classify(text):
    """반환: (tier, reason) — tier ∈ {'free','sonnet','opus'}"""
    t = text.lower()
    has_code = bool(re.search(r"```|def |class |function |import |#include|;\s*$", text, re.M))
    length = len(text)

    opus_hit = [k for k in OPUS_KW if k.lower() in t]
    sonnet_hit = [k for k in SONNET_KW if k.lower() in t]
    free_hit = [k for k in FREE_KW if k.lower() in t]

    # 1) 고난도 키워드가 있으면 opus
    if opus_hit:
        return "opus", f"고난도 신호: {', '.join(opus_hit[:3])}"
    # 2) 매우 긴 입력: 고난도 키워드가 없으면 "그냥 긴 붙여넣기"일 가능성이 높다.
    #    심층 추론 신호가 없는 대량 텍스트는 free의 long_context 체인으로 (사용량 절약).
    if length > 4000:
        return "free", f"긴 입력({length}자) + 고난도 신호 없음 → free long_context"
    # 3) 코드 편집/작성 계열은 sonnet (짧아도 코드 의도면 free로 떨어뜨리지 않음)
    code_hint = [k for k in ["함수", "메서드", "클래스", "변수", "코드", "code", "중복 코드",
                             "모듈", "파일", "리턴", "return", "루프", "반복문", "조건문",
                             "파이썬", "python", "자바", "java", "sql", "타입", "인터페이스"]
                 if k.lower() in t]
    if sonnet_hit or has_code or code_hint:
        sig = sonnet_hit or code_hint
        why = "코드 작성/수정 신호" + (f": {', '.join(sig[:3])}" if sig else " (코드 블록 감지)")
        return "sonnet", why
    # 4) 단순 질의 계열은 free
    if free_hit:
        return "free", f"단순 질의 신호: {', '.join(free_hit[:3])}"
    # 5) 기본값: 짧으면 free, 애매하게 길면 sonnet
    if length <= 300:
        return "free", "짧은 일반 질의 → 무료 모델로 충분"
    return "sonnet", "분류 애매 + 중간 길이 → 안전하게 Sonnet"

def autoscale_pick(prompt_text, roster):
    """반환: (alias, classify_tier, classify_reason) — classify() 결과를 autoscale
    ladder(trivial/light/mid/reason)에 매핑. classify()가 'free'를 반환한 경우, FREE_KW
    (명시적 단순 질의 키워드)가 매치된 가장 확실한 케이스만 진짜 $0(trivial)로 보내고
    나머지 free 판정은 light(저가 유료)로 — fallback(길이 기반) 판정까지 진짜 무료로
    보내면 오분류 시 품질 리스크가 커진다. cn_run.py도 이 함수를 그대로 재사용한다."""
    tier, reason = classify(prompt_text)
    ladder = roster["autoscale"]
    if tier == "opus":
        alias = ladder["reason"]
    elif tier == "sonnet":
        alias = ladder["mid"]
    else:  # free
        t = prompt_text.lower()
        is_trivial = any(k.lower() in t for k in FREE_KW)
        alias = ladder["trivial"] if is_trivial else ladder["light"]
    return alias, tier, reason

def active_model(prompt_text=None, forced_ladder_tier=None):
    """cn_run.py의 sticky/autoscale 상태를 그대로 따라 실제로 호출할 모델을 정한다:
    sticky > forced_ladder_tier(Claude가 SKILL.md 표에서 이미 정한 --tier, classify() 건너뜀)
    > (autoscale on이면) 난이도별 자동 선택(classify() 폴백) > free_slug. cn_run.py의
    --set-model/--autoscale on/off와 상태 파일을 공유하므로, 사용자가 유료 모델에
    고정했거나 오토스케일을 켰다면 route.py도 그 결과를 그대로 반영한다.
    반환: (slug, tier, note)"""
    roster = load_roster()
    sticky = read_sticky()
    if sticky:
        return resolve(sticky, roster)
    if forced_ladder_tier:
        ladder = roster["autoscale"]
        alias = ladder[forced_ladder_tier]
        slug, entry_tier, note = resolve(alias, roster)
        return slug, entry_tier, f"{note} [명시 지정: {forced_ladder_tier}→{alias}]"
    if prompt_text is not None and read_autoscale():
        alias, tier, reason = autoscale_pick(prompt_text, roster)
        slug, entry_tier, note = resolve(alias, roster)
        return slug, entry_tier, f"{note} [오토스케일 폴백: {tier}→{alias}, 사유: {reason}]"
    return resolve(roster["free_slug"], roster)

# ─────────────────────────────────────────────────────────────
# free 티어 카테고리 선택 (coding / long_context / general) — 결과 라벨링용,
# 모델 선택 자체는 이제 active_model()이 담당한다.
# ─────────────────────────────────────────────────────────────
def pick_free_category(text):
    t = text.lower()
    if re.search(r"```|def |class |function |import |#include", text) or \
       any(k in t for k in ["코드", "code", "함수", "버그", "파이썬", "python", "자바", "sql"]):
        return "coding"
    if len(text) > 2000:
        return "long_context"
    return "general"

# ─────────────────────────────────────────────────────────────
# OpenRouter 호출 (429 폴백 + 짧은 재시도)
# ─────────────────────────────────────────────────────────────
def call_model(model, message, api_key, system=None, timeout=90):
    body = {"model": model, "messages": []}
    if system:
        body["messages"].append({"role": "system", "content": system})
    body["messages"].append({"role": "user", "content": message})
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost/claude-multi-model-router",
            "X-Title": "claude-multi-model-router skill",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    choice = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    return choice, usage

def run_delegated(text, api_key, system=None, forced_ladder_tier=None):
    """sticky/autoscale/--tier 상태에 따라 실제로 부를 모델을 정하고(active_model()) 호출한다.
    free_slug가 선택되면 비용 없음, sticky/autoscale/--tier가 유료 모델을 골랐으면 실제
    크레딧이 차감된다 — 호출 전 stderr에 [유료 호출]/[무료 호출] 마커를 남긴다."""
    category = pick_free_category(text)  # 결과 라벨링용(모델 선택과 무관)
    slug, tier, note = active_model(prompt_text=text, forced_ladder_tier=forced_ladder_tier)
    if tier == "paid":
        print(f"[유료 호출] model={slug} note={note!r} — OpenRouter 크레딧이 차감됩니다.",
              file=sys.stderr)
    else:
        print(f"[무료 호출] model={slug}", file=sys.stderr)
    errors = []
    # 1회 재시도(429는 잠깐 대기 후) — sticky/autoscale로 특정된 단일 모델이라
    # 다른 모델로 폴백하지 않는다(품질 기대와 다른 모델로 조용히 바뀌는 것을 방지).
    for attempt in range(2):
        try:
            answer, usage = call_model(slug, text, api_key, system=system)
            return {
                "tier": tier, "category": category, "model_used": slug, "note": note,
                "answer": answer, "usage": usage, "fallbacks_tried": errors,
            }
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            if e.code == 429:
                wait = 6
                m = re.search(r'"retry_after_seconds"\s*:\s*([\d.]+)', raw)
                if m:
                    wait = min(float(m.group(1)) + 1, 20)
                if attempt == 0:
                    time.sleep(wait)
                    continue
                errors.append({"model": slug, "code": 429})
                break
            else:
                errors.append({"model": slug, "code": e.code, "detail": raw[:200]})
                break
        except Exception as e:
            errors.append({"model": slug, "error": str(e)[:200]})
            break
    # free 티어가 429로 소진되면(quota exhaustion) 호출자가 재시도 없이 Sonnet 서브에이전트로
    # 바로 넘어갈 수 있게 신호를 준다 — SKILL.md/cn.md의 "free quota 소진 폴백" 규칙.
    suggestion = None
    if tier == "free" and any(e.get("code") == 429 for e in errors):
        suggestion = "free quota 소진으로 보임(429 반복) — Sonnet 서브에이전트로 직접 처리 권장"
    return {
        "tier": tier, "category": category, "model_used": None, "note": note,
        "answer": None, "error": f"모델 호출 실패: {slug}",
        "fallbacks_tried": errors, "suggestion": suggestion,
    }

# ─────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    as_json = False
    forced_ladder_tier = None  # Claude가 SKILL.md 표에서 이미 정한 --tier (classify() 건너뜀)
    tier_only = False
    out_file = None
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--json":
            as_json = True
        elif args[i] == "--tier-only":
            tier_only = True
        elif args[i] == "--tier" and i + 1 < len(args):
            forced_ladder_tier = args[i + 1]; i += 1
        elif args[i] == "--out" and i + 1 < len(args):
            out_file = args[i + 1]; i += 1
        else:
            rest.append(args[i])
        i += 1

    if forced_ladder_tier and forced_ladder_tier not in LADDER_TIERS:
        print(f"[오류] --tier 값은 {'/'.join(LADDER_TIERS)} 중 하나(--tier-only는 별개 플래그): "
              f"'{forced_ladder_tier}'", file=sys.stderr)
        sys.exit(2)

    text = " ".join(rest).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print("사용법: python route.py \"질문\"", file=sys.stderr)
        sys.exit(2)

    models = load_models()

    # --tier-only: classify() 분류 힌트만 보고 종료 (호출 없음, API 키 불필요, 사용량 0).
    # --tier(ladder)와는 별개 경로 — 이건 항상 classify()로 재분류해서 보여준다.
    if tier_only:
        tier, reason = classify(text)
        if as_json:
            print(json.dumps({"tier": tier, "reason": reason}, ensure_ascii=False, indent=2))
        else:
            print(f"tier={tier}  ({reason})")
        return

    # --tier가 명시되면 Claude가 이미 위임하기로 결정한 것 — classify()/ESCALATE 재분류 없이
    # 바로 지정된 ladder 티어로 위임한다(이원 분류 방지, B-1).
    if forced_ladder_tier:
        reason = "Claude가 SKILL.md 티어 판정표에서 이미 분류(명시 지정)"
        tier = "free"  # ESCALATE 분기를 타지 않고 바로 아래 위임 경로로 진행
    else:
        tier, reason = classify(text)
        # sonnet/opus 티어는 호출하지 않고 클로드에게 넘김 (폴백 경로에서만 발생)
        if tier in ("sonnet", "opus"):
            result = {
                "tier": tier, "action": "ESCALATE",
                "target_model": models[tier], "reason": reason,
                "message": text,
                "note": "이 작업은 클로드가 처리해야 합니다. 무료 모델 호출 안 함.",
            }
            if as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"[ESCALATE → {tier.upper()}] 사유: {reason}")
                print(f"→ 클로드({models[tier]})가 처리해야 합니다. (무료 모델 미호출)")
            return

    # free 티어 분류 결과 → 실제 호출(위임 실행). 부를 모델 자체는 sticky/autoscale에 따라
    # free일 수도 paid일 수도 있다(run_delegated 참고).
    api_key = load_api_key()
    if not api_key:
        msg = ("OPENROUTER_API_KEY 없음. 환경변수 설정 또는 프로젝트 루트의 "
               ".env 에 OPENROUTER_API_KEY=... 추가 필요 (https://openrouter.ai/keys)")
        if as_json:
            print(json.dumps({"tier": "free", "error": msg}, ensure_ascii=False, indent=2))
        else:
            print(f"[오류] {msg}", file=sys.stderr)
        sys.exit(1)

    result = run_delegated(text, api_key, forced_ladder_tier=forced_ladder_tier)
    result["classify_reason"] = reason
    cost_tier = result.get("tier")  # "free" 또는 "paid" — 실제로 호출된 모델의 과금 여부
    label = "FREE" if cost_tier == "free" else "PAID"

    # --out: 응답 본문을 파일에 저장하고 stdout에는 메타 정보만.
    # 클로드가 내용을 자기 출력으로 재생산하지 않고 cp/patch로 적용, head/diff로 검토 가능.
    if out_file and result.get("answer"):
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(result["answer"])
        u = result.get("usage", {})
        meta = {
            "tier": cost_tier, "model_used": result["model_used"],
            "saved_to": out_file, "bytes": len(result["answer"].encode("utf-8")),
            "usage": u, "classify_reason": reason,
        }
        if as_json:
            print(json.dumps(meta, ensure_ascii=False, indent=2))
        else:
            print(f"[{label} → {result['model_used']}] 저장: {out_file} "
                  f"({meta['bytes']} bytes, in {u.get('prompt_tokens','?')} / out {u.get('completion_tokens','?')} tok)")
        return

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("answer"):
            u = result.get("usage", {})
            print(f"[{label} → {result['model_used']}] (in {u.get('prompt_tokens','?')} / out {u.get('completion_tokens','?')} tok)")
            print(result["answer"])
        else:
            print(f"[실패] {result.get('error')}", file=sys.stderr)
            if result.get("suggestion"):
                print(f"[제안] {result['suggestion']}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
