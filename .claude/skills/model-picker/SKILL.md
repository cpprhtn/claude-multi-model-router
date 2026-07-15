---
name: model-picker
description: OpenRouter 위임(cn)을 켜고 끄거나, free 고정/역할별 유료 모델 sticky 고정/오토스케일(자동 난이도별 선택)을 대화형으로 조작하는 선택기. "모델 골라줘/바꿔줘", "유료 모델 선택", "어떤 모델 쓸까", "오토스케일 켜/꺼", "오픈라우터 무료모델 써줘", "오픈라우터 그만/꺼줘", "model pick" 같은 발화에서 사용.
---

# model-picker — OpenRouter 위임 on/off·모델 선택기

claude-multi-model-router 스킬의 `cn_run.py`가 참조하는 `cn_models.json`의 `roles`/`models`를 기반으로,
사용자가 **OpenRouter 위임 자체를 켜고 끄거나**, **역할을 고르면 추천 모델로 sticky 고정**하거나,
**오토스케일을 토글**하도록 돕는다. claude-multi-model-router에서 OpenRouter 위임은 기본 꺼짐이라
(sticky도 autoscale도 없으면 단순·기계적 편집은 Sonnet 서브에이전트가, free 텍스트 생성은 Haiku
서브에이전트가 처리 — `route.py`/`cn_run.py` 둘 다 이 스위치 하나를 공유),
이 스킬이 "사용자가 직접 여는 OpenRouter 설정 창구" 역할 전체(켜기/끄기 포함)를 담당한다.

전제: cn_run.py/cn_models.json은 `.claude/skills/claude-multi-model-router/`에 있다.
이 스킬은 그 파일들을 읽기만 하고, 실행은 항상 `cn_run.py`를 통해서만 한다(로스터 직접 수정 금지).

## 절차

1. `.claude/skills/claude-multi-model-router/cn_models.json`을 읽어 `roles`와 `models`를 파악한다.
2. AskUserQuestion으로 아래 선택지를 제시한다(하나의 질문, 단일 선택):
   - **항상 무료만 (등급 없이 free 고정)** → free 고정, cn 위임 활성화
   - **오토스케일 켜기** → 난이도별 자동 전환(진짜 무료~유료), 상한 terra
   - **엑셀/오피스** → `roles.excel` (gemini)
   - **코딩 — 단순/기계적** → `roles.coding_simple` (deepseek-flash)
   - **코딩 — 중간 난이도** → `roles.coding_mid` (glm)
   - **코딩 — 고난도/설계급** → `roles.coding_hard` (terra)
   - **범용 대화/요약** → `roles.general` (flash-lite)
   - **최고 품질(고가, 수동 전용)** → `manual_only` 모델 중 선택(opus/sol) — 별도 확인 질문으로 분리
   - **오토스케일 끄기**
   - **오픈라우터 완전히 끄기 (Claude만 쓰기)**
3. 선택에 따라 실행 (반드시 프로젝트 루트에서, `cn_run.py`와 같은 규칙):
   - 항상 무료만 → `python cn_run.py --set-model free`
   - 역할/모델 선택 → `python cn_run.py --set-model <alias>`
   - 오토스케일 켜기 → `python cn_run.py --autoscale on`
   - 오토스케일 끄기 → `python cn_run.py --autoscale off`
   - 오픈라우터 완전히 끄기 → `python cn_run.py --reset-model` (오토스케일도 켜져 있으면 `--autoscale off`도 함께 — 둘 다 없어야 cn 위임이 기본 상태로 완전히 꺼짐)
4. 실행 후 `python cn_run.py --list-models`로 반영 결과(active 모델 표시 `*`, sticky·오토스케일 상태, cn 위임 활성 여부)를 보여준다.

## 비용 가드

- `manual_only` 모델(opus/sol)이나 sticky 유료 고정, 오토스케일 on은 모두 **크레딧이 실제로 차감될 수 있는 설정**이다.
  이 세션에서 처음 유료 관련 설정을 켜기 직전, 사용자에게 한 줄 확인
  ("유료 모델 X로 고정합니다 / 오토스케일을 켭니다 — OpenRouter 크레딧이 차감될 수 있습니다, 진행할까요?")을 받는다.
- `--set-model`/`--autoscale on` 자체는 호출이 아니라 설정이라 그 순간 크레딧이 나가지는 않는다 — 이후 cn 위임이 실행될 때 차감된다는 점을 안내에 포함.
- `--reset-model`, `--autoscale off`, `--list-models`는 확인 없이 바로 실행 가능(비용 발생 없음).

## 라우터 스킬과의 관계

- claude-multi-model-router: 개발 작업을 티어(플랜/메인/서브에이전트/free/cn)로 **자동** 분류. OpenRouter 위임(route.py+cn_run.py)은 기본 꺼짐(sticky도 autoscale도 없으면 Claude 모델 안에서만 처리).
- model-picker(이 스킬): OpenRouter 위임을 **사용자가 직접** 켜고 끄거나(free 고정 포함), 유료 모델을 고르는 창구. 오토스케일 on/off도 여기서 전환.
- 오토스케일 ladder(trivial/light/mid/reason)·상한 설명은 claude-multi-model-router의 `references/cn.md` 참고.
