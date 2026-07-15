#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cn_run.py — cn CLI 위임 래퍼 (free 기본, 유료 모델 온디맨드 전환)

역할:
  1) 기본은 free 모델로 `cn` 헤드리스 실행 (스킬 폴더의 base.config.yaml 사용)
  2) 사용자가 명시적으로 특정 모델을 요청하면 그 1회만 유료 slug로 전환
  3) --set-model / --reset-model 로 유료 모델을 다음 호출부터 지속(sticky) 가능
  4) 유료 경로는 base config를 복제해 `model:` 줄만 교체한 임시 config로 실행
     (헤드리스에서 로컬 config의 named 모델을 선택하는 공식 플래그가 없음 —
      --model은 Continue Hub slug 전용, /model은 대화형 전용)

키 처리: 이 스크립트는 OpenRouter 키를 전혀 다루지 않는다. base.config.yaml의
  apiKey는 `${{ secrets.OPENROUTER_API_KEY }}`이고, cn이 실행 시점에
  워크스페이스 루트 `.env`(cwd 기준, config 파일 자체의 위치와는 무관)에서
  직접 해석한다. 그래서 **반드시 프로젝트 루트(= .env 가 있는 디렉터리)를
  cwd로 두고 실행**해야 시크릿이 해석된다. 복제되는 임시 config에도 같은
  `${{ secrets... }}` 문구만 들어가므로 평문 키가 디스크 어디에도 새로 생기지 않는다.

사용 (프로젝트 루트에서):
  python cn_run.py -p "<자립형 지시>"                 # active 모델(기본 free)로 실행
  python cn_run.py --model <alias|slug> -p "..."      # 이번 1회만 지정 모델
  python cn_run.py --set-model <alias|slug>           # 이후 호출 전부 그 모델로 고정
  python cn_run.py --reset-model                      # sticky 해제(autoscale도 없으면 cn 위임 자체가 비활성화)
  python cn_run.py --list-models                      # 사용 가능 모델 + 현재 active 출력
  python cn_run.py --autoscale on|off|status          # 유료 오토스케일 켜기/끄기/상태
  python cn_run.py --explain -p "..."                 # 오토스케일이 고를 모델만 미리보기(호출 없음)

오토스케일(opt-in, 기본 off): 켜면 sticky 모델이 없을 때 route.py의 classify()로
  난이도를 분류해 cn_models.json의 autoscale ladder(trivial/light/mid/reason)에서
  모델을 자동 선택한다(trivial=진짜 $0 free, 나머지는 유료). 가성비 위주로 구성되어
  있고, 추론이 필요한 경우도 ceiling(기본 terra)을 넘지 않는다 — opus/sol처럼
  manual_only인 고가 모델은 오토스케일이 절대 자동 선택하지 않는다.
  --model/--set-model이 항상 우선한다.

cn 위임 자체는 opt-in이다: 이 스크립트를 직접 호출하면(사람이 CLI로 치거나 Claude가
  호출하기로 결정한 경우) 항상 실행되고 기본은 free다 — 이 스크립트는 "위임할지
  말지" 자체는 판단하지 않는다. 그 판단(단순·기계적 편집을 cn으로 보낼지, Claude가
  직접/서브에이전트로 처리할지)은 SKILL.md 규칙에 따라 호출하는 Claude의 몫이며,
  기본값은 "sticky도 autoscale도 없으면 cn을 아예 호출하지 않음"이다.

주의:
  - 유료 slug 호출은 OpenRouter 크레딧을 실제로 차감한다.
  - 이 세션에서 처음 유료 모델을 호출하기 직전에는 사용자에게 한 줄 확인을 받는다
    (스크립트가 아니라 이 스크립트를 호출하는 Claude의 책임 — references/cn.md 참고).
  - base config는 references/cn.md에 문서화된 단일 모델 템플릿을 전제로
    `model:` 첫 줄만 치환한다. config.yaml을 템플릿과 다르게 크게 손댔다면
    임시 config 결과를 diff로 확인할 것.
  - Python이 없는 환경에서는 이 스크립트 대신 references/cn.md의 "네이티브 폴백"
    절차(Claude가 Read/Write/Bash로 직접 수행)를 따른다.
"""

import sys
import os
import re
import shutil
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))

if HERE not in sys.path:
    sys.path.insert(0, HERE)
# route.py가 sticky/autoscale 상태 관리와 로스터 로딩의 원본이다(순환참조를 피하려고
# 이 방향으로만 import — route.py는 cn_run.py를 몰라도 된다). route.py를 직접 호출해도
# (사람이 CLI로, 혹은 Claude가 free 텍스트 생성에) 여기서 설정한 sticky/autoscale을
# 그대로 반영해서 같은 모델을 쓴다 — 두 스크립트가 상태를 공유하는 이유.
from route import (  # noqa: E402 — route.py의 __main__ 블록은 실행 안 됨
    classify, FREE_KW, load_roster, read_sticky, write_sticky, clear_sticky,
    read_autoscale, write_autoscale, resolve, autoscale_pick,
)


def default_base_config():
    return os.path.join(HERE, "base.config.yaml")


def oneoff_config_path():
    return os.path.join(HERE, "_oneoff.config.yaml")


def active_model(roster, override=None, autoscale_prompt=None):
    """route.active_model()과 동일한 우선순위에 override(--model 1회성 지정)만 추가."""
    if override:
        return resolve(override, roster)
    sticky = read_sticky()
    if sticky:
        return resolve(sticky, roster)
    if autoscale_prompt is not None and read_autoscale():
        alias, tier, reason = autoscale_pick(autoscale_prompt, roster)
        slug, entry_tier, note = resolve(alias, roster)
        return slug, entry_tier, f"{note} [오토스케일: {tier}→{alias}, 사유: {reason}]"
    free_slug = roster["free_slug"]
    return resolve(free_slug, roster)


def build_paid_config(base_config_path, slug):
    if not os.path.exists(base_config_path):
        print(f"[오류] base config 없음: {base_config_path}", file=sys.stderr)
        sys.exit(1)
    with open(base_config_path, "r", encoding="utf-8") as f:
        text = f.read()
    new_text, n = re.subn(r"(\n\s*model:\s*)\S+", r"\g<1>" + slug, text, count=1)
    if n == 0:
        print("[오류] base config에서 'model:' 줄을 찾지 못함 — 템플릿과 다른 구조인지 확인",
              file=sys.stderr)
        sys.exit(1)
    out_path = oneoff_config_path()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return out_path


def cmd_list_models(roster):
    sticky = read_sticky()
    current = sticky if sticky else roster["free_slug"]
    autoscale_on = read_autoscale()
    print("alias        tier   slug                                   note")
    for alias, entry in roster["models"].items():
        mark = " *" if entry["slug"] == current else ""
        manual = " (manual only)" if entry.get("manual_only") else ""
        print(f"{alias:<12} {entry['tier']:<6} {entry['slug']:<38} {entry.get('note',''):<20}{mark}{manual}")
    print(f"\ncn_run.py가 호출되면 사용할 모델: {current}{' (sticky)' if sticky else ' (free, sticky 없음)'}")
    ladder = roster.get("autoscale", {})
    scale_line = f"오토스케일: {'on' if autoscale_on else 'off'}"
    if autoscale_on:
        scale_line += (f"  (trivial={ladder.get('trivial')} / light={ladder.get('light')} / "
                        f"mid={ladder.get('mid')} / reason={ladder.get('reason')}, 상한={ladder.get('ceiling')})")
    print(scale_line)
    if not sticky and not autoscale_on:
        print("cn 위임 자체는 비활성(기본값) — sticky 또는 autoscale이 없으면 단순·기계적 편집도 "
              "Claude가 Sonnet 서브에이전트로 직접 처리하고 cn_run.py를 호출하지 않는다.")


def cmd_autoscale(action, roster):
    ladder = roster.get("autoscale", {})
    if action == "status":
        on = read_autoscale()
        print(f"오토스케일: {'on' if on else 'off'}")
        if on:
            print(f"  trivial={ladder.get('trivial')} light={ladder.get('light')} mid={ladder.get('mid')} "
                  f"reason={ladder.get('reason')} ceiling={ladder.get('ceiling')}")
        return
    if action == "on":
        write_autoscale(True)
        print(f"[설정 완료] 오토스케일 on — cn 위임이 활성화됩니다. sticky 모델이 없으면 프롬프트 "
              f"난이도에 따라 trivial={ladder.get('trivial')}(진짜 무료) / light={ladder.get('light')} / "
              f"mid={ladder.get('mid')} / reason={ladder.get('reason')} 중 하나로 자동 전환합니다"
              f"(상한={ladder.get('ceiling')}, manual_only 모델은 자동 선택 대상 아님). trivial 이외에는 "
              f"OpenRouter 크레딧이 차감될 수 있습니다. 끄려면: python cn_run.py --autoscale off")
        return
    if action == "off":
        write_autoscale(False)
        print("[설정 완료] 오토스케일 off. sticky 모델이 설정돼 있으면 그게 여전히 우선(cn 위임 유지), "
              "없으면 cn 위임 자체가 비활성 상태(기본값)로 돌아갑니다.")
        return


def cmd_explain(prompt, roster, override):
    slug, tier, note = active_model(roster, override, autoscale_prompt=prompt)
    sticky = read_sticky()
    print(f"[설명] override={override!r} sticky={sticky!r} 오토스케일={'on' if read_autoscale() else 'off'}")
    print(f"→ 선택된 모델: {slug} (tier={tier}) {note}")
    print("(--explain은 실제 cn 호출을 하지 않습니다 — 크레딧 소비 없음)")


def cmd_set_model(alias_or_slug, roster):
    """alias 'free'를 포함해 항상 sticky를 기록한다 — 'free로 고정'도 명시적 결정이므로
    (cn 위임 자체가 opt-in인 기본 상태에서) 이 호출 자체가 cn 위임을 활성화하는 신호다."""
    slug, tier, note = resolve(alias_or_slug, roster)
    write_sticky(slug)
    if tier == "free":
        print(f"[설정 완료] cn 위임을 활성화하고 '{slug}'(무료, 등급 없이 항상 고정)로 설정했습니다. "
              f"완전히 끄려면: python cn_run.py --reset-model (autoscale도 켜져 있다면 --autoscale off도)")
        return
    print(f"[설정 완료] 이후 모든 cn 위임을 '{slug}'(유료)로 고정합니다. "
          f"무료로 되돌리려면: python cn_run.py --set-model free / 완전히 끄려면 --reset-model")


def cmd_reset_model():
    clear_sticky()
    print("[설정 완료] sticky 모델 고정을 해제했습니다. autoscale이 꺼져 있다면 cn 위임 자체가 "
          "비활성 상태(기본값 — 단순 편집도 Claude가 직접/서브에이전트로 처리)로 돌아갑니다. "
          "autoscale이 켜져 있다면 난이도별 자동 선택으로 돌아갑니다.")


def cmd_run(prompt, roster, override, base_config_arg, extra_format):
    slug, tier, note = active_model(roster, override, autoscale_prompt=prompt)

    base_config = base_config_arg or default_base_config()
    if not os.path.exists(base_config):
        print(f"[오류] base config 없음: {base_config} (--base-config로 잘못된 경로를 지정했는지 확인)",
              file=sys.stderr)
        sys.exit(1)

    if tier == "paid":
        config_path = build_paid_config(base_config, slug)
        print(f"[유료 호출] model={slug} note={note!r} config={config_path} "
              f"— OpenRouter 크레딧이 차감됩니다.", file=sys.stderr)
    else:
        config_path = base_config
        print(f"[무료 호출] model={slug}", file=sys.stderr)

    cn_path = shutil.which("cn")
    if not cn_path:
        print("[오류] 'cn' 실행 파일을 PATH에서 찾지 못함. "
              "npm install -g @continuedev/cli 로 설치했는지, PATH에 잡히는지 확인.",
              file=sys.stderr)
        sys.exit(1)

    cmd = [cn_path, "--config", config_path, "--auto", "-p", prompt]
    if extra_format:
        cmd += ["--format", extra_format]

    if os.name == "nt":
        # Windows npm 글로벌 설치는 cn.cmd(배치 스텁)라 CreateProcess가 직접
        # 실행 못 함 — cmd.exe를 shell=True로 경유. 인자는 list2cmdline으로
        # 안전하게 이스케이프한 뒤 단일 문자열로 넘겨야 프롬프트 내 공백/따옴표가
        # 깨지지 않는다(리스트+shell=True는 Windows에서 뒤 인자가 shell 자체로 감).
        result = subprocess.run(subprocess.list2cmdline(cmd), shell=True)
    else:
        result = subprocess.run(cmd)
    sys.exit(result.returncode)


def main():
    args = sys.argv[1:]
    roster = load_roster()

    override = None
    prompt = None
    base_config_arg = None
    extra_format = "json"
    explain_mode = False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-p", "--print"):
            i += 1
            prompt = args[i] if i < len(args) else ""
        elif a == "--model":
            i += 1
            override = args[i] if i < len(args) else None
        elif a == "--set-model":
            i += 1
            target = args[i] if i < len(args) else None
            if not target:
                print("사용법: python cn_run.py --set-model <alias|slug>", file=sys.stderr)
                sys.exit(2)
            cmd_set_model(target, roster)
            return
        elif a == "--reset-model":
            cmd_reset_model()
            return
        elif a == "--list-models":
            cmd_list_models(roster)
            return
        elif a == "--autoscale":
            i += 1
            action = args[i] if i < len(args) else None
            if action not in ("on", "off", "status"):
                print("사용법: python cn_run.py --autoscale on|off|status", file=sys.stderr)
                sys.exit(2)
            cmd_autoscale(action, roster)
            return
        elif a == "--explain":
            explain_mode = True
        elif a == "--base-config":
            i += 1
            base_config_arg = args[i] if i < len(args) else None
        elif a == "--format":
            i += 1
            extra_format = args[i] if i < len(args) else "json"
        else:
            print(f"[오류] 알 수 없는 옵션: {a}", file=sys.stderr)
            sys.exit(2)
        i += 1

    if prompt is None:
        print("사용법: python cn_run.py -p \"<지시>\" [--model <alias|slug>] "
              "| --set-model <alias|slug> | --reset-model | --list-models "
              "| --autoscale on|off|status | --explain -p \"...\"",
              file=sys.stderr)
        sys.exit(2)

    if explain_mode:
        cmd_explain(prompt, roster, override)
        return

    cmd_run(prompt, roster, override, base_config_arg, extra_format)


if __name__ == "__main__":
    main()
