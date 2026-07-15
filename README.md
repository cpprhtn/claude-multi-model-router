# claude-multi-model-router

Claude Code용 스킬 두 개를 묶은 저장소입니다.

- **claude-multi-model-router** — 개발 작업을 난이도별로 자동 분류해서 Opus(설계) → Sonnet(구현) → 서브에이전트 → 무료/유료 OpenRouter 모델로 라우팅하는 메인 스킬. 매 요청마다 "이 정도 일은 어디로 보낼지"를 사람이 직접 고르지 않아도, Claude가 스스로 판단해서 값싼 티어로 흘려보내도록 만드는 것이 목적입니다.
- **model-picker** — OpenRouter 위임을 대화형으로 켜고 끄는 창구. "항상 무료만" / "오토스케일 켜기" / 역할별 유료 모델(엑셀·오피스, 코딩 난이도별, 범용 대화, 최고 품질) / "오토스케일 끄기" / "완전히 끄기" 중 골라 sticky 고정하거나 상태를 전환합니다.

## 왜 필요한가

Claude Code는 기본적으로 요청 난이도와 상관없이 같은 모델(Sonnet)로 계획도 세우고 코드도 짭니다. opusplan(플랜 모드 = Opus, 실행 = Sonnet)이라는 설정을 켜면 "설계는 Opus, 실행은 Sonnet"으로 나눌 수 있지만, 이건 존재 자체를 모르는 사람이 대부분이고 안다 해도 딱 그 2단계까지만 나눠줄 뿐입니다.

이 스킬은 그 자리에서 한 단계 더 들어갑니다:

- opusplan처럼 큰 설계는 Opus로 보내되,
- "몇 줄 수정"·"이름 변경"·"요약·번역" 같은 더 작은 단위까지 세분화해서 Sonnet 서브에이전트·Haiku·무료 OpenRouter 모델로 자동으로 흘려보냅니다.
- 즉 opusplan이 놓치는 "Opus/Sonnet 이하" 구간까지 티어를 쪼개서, 매번 사람이 "이 정도 일은 어디로 보낼지" 판단하지 않아도 되게 만듭니다.

opusplan을 몰라도 상관없습니다 — 이 스킬을 얹는 순간 그 아이디어(작업 난이도별로 담당 모델을 나눈다)가 opusplan보다 더 촘촘한 티어 구조로 자동 적용됩니다. 판단 기준은 SKILL.md의 티어 판정표에 규칙으로 못박혀 있어서, 세션마다 반복 설명하지 않아도 Claude가 알아서 적용합니다.

## 티어 구조

기본값은 **Claude 모델끼리만 스케일링**합니다 — OpenRouter는 `route.py`(텍스트 생성)든 `cn_run.py`(파일 편집)든 명시적으로 켜기 전까지 절대 자동으로 개입하지 않습니다(둘은 같은 스위치를 공유). 굵직한 설계는 플랜 모드(Opus), 짧은 코드/질의는 메인 세션(Sonnet), 파일 수정과 탐색·요약은 각각 서브에이전트가 처리하는 게 기본이고, OpenRouter를 켜면 같은 4개 작업이 Claude가 이미 판정한 티어(`trivial`~`reason`)에 따라 free~유료 OpenRouter 모델로 자동 위임됩니다.

전체 판정표(OFF/ON 각 열의 정확한 실행처)는 SKILL.md가 원본입니다 — README에 별도 표를 두면 둘이 따로 놀 위험이 있어 여기서는 링크만 둡니다: [`.claude/skills/claude-multi-model-router/SKILL.md`](.claude/skills/claude-multi-model-router/SKILL.md).

OpenRouter를 켜려면 "오픈라우터 무료모델 써줘"(등급 없이 항상 free 고정) 또는 "오토스케일 켜줘"(난이도별 자동 선택, 어려우면 유료로도 감)라고 말하면 됩니다 — 자세한 내용은 아래 "OpenRouter 위임 켜기" 참고.

## 구성 요소

저장소 자체가 이미 `.claude/skills/` 레이아웃입니다 — 프로젝트에 그대로 얹으면 됩니다. `README.md`만 저장소 루트에 있고 나머지는 전부 스킬 폴더 안에 있어서, 설치 시 스킬 폴더 단위로만 받으면 이 README는 딸려오지 않습니다(아래 "설치" 참고).

```
(저장소 루트)
  README.md
  .github/workflows/tier-classification.yml — tests/tier_cases.json 회귀 테스트 CI(PR마다, 비용 0).
  tests/
    tier_cases.json          — "프롬프트 → 기대 티어" 회귀 케이스 모음.
    run_tier_cases.py         — 위 케이스를 route.py --tier-only로 검증하는 스크립트.
  .claude/skills/
    claude-multi-model-router/
      SKILL.md              — 티어 판정 로직(진입점, 실행처 판정표의 원본). Claude Code가 세션마다 읽는 스킬 정의.
      route.py               — 규칙 기반 난이도 분류(classify()) + OpenRouter 직접 호출.
                              Claude가 이미 정한 티어를 --tier로 직접 받는 게 기본 경로이고,
                              classify()는 --tier 미지정 시에만 폴백으로 동작합니다. 호출될 때는
                              Claude 토큰을 전혀 쓰지 않습니다. 이 호출 자체가 OpenRouter 위임
                              (opt-in, 기본 꺼짐)에 속해 있어 — 꺼진 기본 상태에서는 이것도 쓰지
                              않고 Haiku가 대신 처리합니다. sticky/autoscale 상태 관리의 원본이기도
                              해서(cn_run.py가 가져다 씀), 켜진 상태에서는 free만 호출하는 게
                              아니라 sticky/autoscale에 따라 유료 모델도 그대로 반영해서 호출합니다.
      cn_run.py               — `cn`(Continue CLI)을 헤드리스로 구동해 실제 파일 편집을
                              free/유료 OpenRouter 모델에 위임하는 래퍼. 위임 자체가 opt-in
                              (기본 꺼짐, 명시적으로 켜야 동작) — 켠 뒤에는 free가 기본이고
                              필요할 때만 온디맨드로 유료 전환(1회성/sticky/오토스케일). working
                              tree가 dirty하면 기본적으로 실행을 막습니다(--allow-dirty로 강제
                              가능). 모델 로스터·상태 관리 로직은 route.py 것을 그대로 가져다
                              씁니다(중복 구현 없음).
      escalate_labels.json     — sonnet/opus ESCALATE 안내 라벨 전용(route.py가 호출하는 실제
                              모델 로스터는 cn_models.json).
      cn_models.json           — route.py·cn_run.py가 공유하는 모델 로스터(free/paid, autoscale, roles).
      base.config.yaml         — `cn` CLI 기본 설정(free 모델).
      .env.example             — 프로젝트 루트 `.env` 만들 때 복사할 템플릿(플레이스홀더 키만 있음).
      references/setup.md      — 1회 설치/설정 가이드.
      references/cn.md         — `cn` 위임 상세 가이드(헤드리스 패턴, 모델 전환, 폴백, 안전망).
    model-picker/
      SKILL.md                — 유료 모델을 역할별로 대화형으로 고르는 보조 스킬(위 라우터의 cn_models.json을 그대로 참조).
```

sticky/autoscale 상태는 스킬 폴더가 아니라 **설치한 프로젝트의** `.claude/.cmr-state.json`에 저장됩니다(이 저장소 자체에는 커밋되지 않음) — 이유와 구버전 마이그레이션은 references/setup.md §7 참고.

## 설치 — 스킬 두 개를 한 번에 불러오기

프로젝트 루트에서 아래 두 줄을 실행하면 됩니다. `npx degit`은 저장소 전체가 아니라 지정한 하위 폴더만 받아오므로, 스킬 폴더 두 개가 각각 정확히 제 위치에 놓이고 이 README나 `.git` 같은 부수적인 것도 전혀 딸려오지 않습니다.

```bash
npx degit cpprhtn/claude-multi-model-router/.claude/skills/claude-multi-model-router .claude/skills/claude-multi-model-router
npx degit cpprhtn/claude-multi-model-router/.claude/skills/model-picker .claude/skills/model-picker
```

(Node/npm만 있으면 OS 무관하게 동일하게 동작합니다 — `cn` CLI도 어차피 npm 패키지라 Node는 이미 있어야 합니다.) `npx`를 쓰고 싶지 않다면 저장소를 통째로 `git clone`한 뒤 `.claude/skills/` 안의 두 폴더만 프로젝트로 복사해도 결과는 같습니다.

그다음 Claude Code에게 **"이 스킬 세팅해줘"**라고 말하면 됩니다 — `cn` CLI 설치 확인, 프로젝트 루트 `.env`/`.gitignore` 생성(스킬 폴더의 `.env.example`을 템플릿으로 사용, 키는 직접 물어봄), CLAUDE.md 라우팅 앵커 추가, `~/.claude/settings.json` 설정까지 Claude가 직접 확인하고 처리합니다. 이미 진행 중인 프로젝트라 CLAUDE.md·settings.json에 기존 내용이 있어도 덮어쓰지 않고 필요한 부분만 병합합니다(전역 설정 변경 전에는 먼저 확인을 구합니다). 물론 직접 하고 싶다면 아래 순서를 손으로 따라 해도 됩니다:

1. `cn` CLI 설치: `npm install -g @continuedev/cli`
2. 프로젝트 루트 `.env`에 `OPENROUTER_API_KEY=...` 추가 — 키는 [openrouter.ai/keys](https://openrouter.ai/keys)에서 무료 발급. 루트 `.gitignore`에 `.env`가 포함돼 있는지 확인.
3. (권장) CLAUDE.md에 라우팅 앵커 추가 — 스킬이 키워드 운에 의존하지 않고 항상 먼저 적용되도록.
4. (선택) `~/.claude/settings.json`에 `opusplan` / `acceptEdits` / `effortLevel` 설정.

OpenRouter 키 발급이 부담이거나 외부 API 호출이 막힌 환경이면 **1·2번을 건너뛰면 그대로 lite 설치**가 됩니다 — 별도 절차 없이 Claude 모델(Opus/Sonnet/서브에이전트)끼리만 스케일링하고 OpenRouter 관련 파일이 없어도 에러 없이 동작합니다.

전체 1회 설치 절차와 각 항목의 이유는 [`references/setup.md`](.claude/skills/claude-multi-model-router/references/setup.md) 참고. model-picker는 별도 설치 단계가 없고, claude-multi-model-router가 설치돼 있으면 그 위에서 바로 동작합니다.

## 사용법

설치 후에는 평소처럼 Claude에게 요청하면 됩니다 — 별도 명령 없이 SKILL.md의 티어 판정이 자동 적용됩니다.

수동으로 확인·조작하고 싶을 때(항상 프로젝트 루트에서 실행 — `cn_run.py`가 루트 `.env`에서 키를 찾기 때문. 아래 `python`은 Windows는 그대로, macOS·일부 Linux 배포판은 `python3`로 실행해야 할 수 있습니다):

```bash
CMR=.claude/skills/claude-multi-model-router
python $CMR/route.py --tier-only "이 코드 리팩터링 해줘"   # 분류 결과만 확인 (호출 없음, 키 불필요)
python $CMR/cn_run.py --list-models                        # 사용 가능 모델 + 현재 active/sticky/오토스케일 상태 확인
python $CMR/cn_run.py --set-model glm                       # 이후 cn 위임을 이 유료 모델로 고정
python $CMR/cn_run.py --reset-model                          # sticky 해제 (autoscale도 꺼져 있으면 cn 위임 자체가 비활성화)
python $CMR/cn_run.py --autoscale on                        # OpenRouter 위임 켜기 + 난이도별 자동 선택(진짜 무료 포함)
python $CMR/cn_run.py --explain -p "이 함수 이름 바꿔줘"    # 실제 호출 없이(크레딧 0) 지금 설정대로면 어떤 모델이 골라질지만 미리보기
```

`--tier-only`는 분류 힌트만 보는 용도(호출 없음)이고, 실제 위임 시에는 Claude가 이미 판정한 티어를 `--tier trivial|light|mid|reason`으로 직접 넘기는 게 기본 경로입니다(예: `cn_run.py --tier mid -p "..."`) — 둘을 혼동하지 않도록 구분해서 씁니다. `--explain`은 크레딧을 전혀 쓰지 않으므로, 오토스케일이나 sticky를 처음 만져볼 때 실제로 유료 모델을 부르기 전에 먼저 이걸로 확인해보는 걸 권장합니다.

## OpenRouter 위임 켜기

기본 상태(설치 직후)에서는 OpenRouter를 전혀 쓰지 않습니다 — free 텍스트 생성은 Haiku 서브에이전트가, 단순·기계적 파일 편집은 Sonnet 서브에이전트가 처리합니다. Claude에게 아래처럼 말하면 그때부터 (route.py·cn_run.py 둘 다) 켜집니다:

- **"오픈라우터 무료모델 써줘"** (= "항상 무료만 써, 등급 매기지 마") — `cn_run.py --set-model free`로 free에 고정합니다. 등급 판단 없이 항상 무료만 씁니다.
- **"오토스케일 켜줘"** — `cn_run.py --autoscale on`. 위와는 다른 스위치입니다 — 작업 난이도에 따라 진짜 무료(trivial)부터 저가 유료(light) · 중간(mid) · 고성능(reason)까지 자동으로 등급을 매겨 고르므로, 어려운 작업이면 유료 모델도 씁니다. 상한(ceiling)을 넘는 고가 모델(Opus/Sol급)은 자동 선택 대상이 아닙니다.
- **"이번엔/앞으로 <모델>로"** — 특정 유료 모델을 1회 또는 계속 쓰고 싶을 때. `model-picker` 스킬로 역할별 추천을 대화형으로 고르거나, `cn_run.py --model` / `--set-model`을 직접 씁니다.
- **"오픈라우터 그만 / 다시 Claude만"** — `cn_run.py --reset-model`(+ 오토스케일도 켜져 있었다면 `--autoscale off`)로 기본 상태(cn 위임 완전 비활성)로 되돌립니다.

`openrouter/free`는 OpenRouter 공식 free 라우터로, 그 순간 살아있는 무료 모델 중에서 자동으로 골라 호출합니다. 특정 free 모델(`qwen/qwen3-coder:free` 등)을 직접 고정하면 그 모델이 일시적으로 무응답 상태일 때 위임이 통째로 멈추는 문제가 있어(실측 확인), 개별 모델을 하드코딩한 폴백 체인 대신 자동 라우터를 씁니다.

유료 모델은 같은 OpenRouter API 키로 호출되며 실제 크레딧이 차감됩니다(진짜 무료 trivial 등급 제외). 세션에서 처음 유료 모델을 쓸 때는 Claude가 한 줄로 확인을 구하고 진행합니다.

## 따라 해보기

설치가 끝났다면 아래 순서 그대로 쳐보면서 감을 잡을 수 있습니다. 전부 같은 프로젝트 안에서 이어서 시도 가능합니다.

**1. 기본 상태 그대로 (OpenRouter 안 씀)**

```
나: 이 프로젝트에 있는 함수 이름들 좀 일관되게 정리해줘
```
→ 아무것도 켜지 않았으므로 OpenRouter는 전혀 호출되지 않습니다. Sonnet 서브에이전트가 직접 파일을 고칩니다.

**2. 무료로 전환한 뒤 파일 편집 위임**

```
나: 오픈라우터 무료모델 써줘
```
→ 이후 위임은 등급 없이 `openrouter/free`로 고정됩니다. 크레딧 소모 없음.

```
나: calc.py 파일의 add, subtract 함수에 타입 힌트 추가해줘
```
→ `cn_run.py`가 free 모델로 실제 파일을 편집하고, 지시한 범위만 정확히 수정됐는지 diff로 보여줍니다.

**3. 오토스케일로 난이도별 자동 전환**

```
나: 오토스케일 켜줘
```
→ 이후 요청 난이도에 따라 자동으로 등급이 바뀝니다.

```
나: 이 파일 요약해줘
```
→ trivial 단계 — 진짜 무료 모델로 처리(크레딧 0).

```
나: 이 모듈 동시성 구조를 재설계해줘
```
→ reason 단계 — 상한선 안의 고성능 유료 모델로 자동 승격. 이 세션 첫 유료 호출이라면 진행 여부를 먼저 확인합니다.

**4. 다시 끄기**

```
나: 오픈라우터 그만
```
→ sticky·오토스케일이 모두 해제되고 기본 상태(Claude 모델 안에서만 처리)로 돌아갑니다.

지금 상태(sticky 고정 여부·오토스케일 on/off)가 궁금하면 `python .claude/skills/claude-multi-model-router/cn_run.py --list-models`로 직접 확인하거나 Claude에게 "모델 상태 보여줘"라고 물어보면 됩니다.

## 문제 해결

| 증상 | 원인/해결 |
|---|---|
| `cn: command not found` | `npm install -g @continuedev/cli`가 안 됐거나 npm 전역 bin이 PATH에 없음. `cn --version`으로 먼저 확인 |
| `OPENROUTER_API_KEY 없음` 오류 | 프로젝트 루트(= `.env`가 있어야 하는 위치)에서 실행 중인지 확인. cwd가 다르면 키를 못 찾습니다 |
| VS Code Claude Code 확장에서 `/model`, `/effort`가 안 먹힘 | 확장에서는 이 슬래시 명령이 막혀 있습니다 — `~/.claude/settings.json`(또는 프로젝트의 `.claude/settings.local.json`)에 직접 설정해야 합니다 |
| 설정을 바꿨는데 확장의 모델 드롭다운이 다시 덮어씀 | settings.json 적용 후에는 확장 UI의 모델 드롭다운을 건드리지 마세요 — 드롭다운 조작이 settings.json 설정을 덮어씁니다 |
| 세션 중간에 CLAUDE.md/스킬 파일을 고쳤더니 그 턴이 갑자기 비쌈 | 프롬프트 캐시가 깨진 것입니다 — 스킬·CLAUDE.md 수정은 세션 밖(새 세션 시작 전)에서 하세요 |
| 위임을 켰는데 결과가 이상함 | free 모델은 신뢰도가 낮습니다 — 항상 diff로 검토하고, 반복되면 `--set-model`로 더 나은 모델에 고정하거나 오토스케일을 꺼보세요 |

더 자세한 설치·설정 이유는 [`references/setup.md`](.claude/skills/claude-multi-model-router/references/setup.md)에 있습니다.

## 검증된 사용 패턴 (`cn` 헤드리스)

```bash
cn --config .claude/skills/claude-multi-model-router/base.config.yaml --auto -p "<자립형 지시문>" --format json
```

(프로젝트 루트에서 실행 — cn이 워크스페이스 루트 `.env`에서 키를 찾기 때문)

- 지시문은 자립형으로 작성 (대상 파일, 변경 범위, 건드리면 안 되는 것을 명시).
- 실제 프로젝트 파일에 처음 적용하기 전에는 스크래치 복사본으로 먼저 테스트하고 diff를 확인하는 것을 권장합니다.
- 위임 후에는 항상 diff로 의도치 않은 변경이 없는지 검토합니다.

## 실제 검증 결과 (calc.py 대상)

1. **구조 리팩터링**: 중복 종료 처리/포맷팅 로직을 `is_quit()`, `print_result()` 헬퍼로 추출 — 동작 손상 없이 정확히 수행.
2. **좁은 범위 지시**: "이 함수에만 타입 힌트 추가, 나머지는 건드리지 마" → 지시한 한 줄만 정확히 수정, 나머지 전혀 손대지 않음.

두 테스트 모두 지시 범위를 벗어나지 않았고 diff 검토로 확인 완료.
