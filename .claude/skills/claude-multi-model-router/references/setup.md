# 설치 / 설정 (1회)

## 0. 사용자가 "세팅해줘"/"설치해줘"라고 하면 — 이 문서를 그대로 실행한다

사용자가 클론/설치 명령만 실행하고 나머지는 Claude에게 맡기는 경우가 기본 시나리오다. 아래 표 순서대로, 이미 있으면 건드리지 않고 없으면 만든다 — **기존 파일 내용을 통째로 덮어쓰지 않는다** (특히 CLAUDE.md·settings.json은 이미 진행 중인 다른 프로젝트의 파일일 수 있다).

| 순서 | 확인 | 없으면 |
|---|---|---|
| 1 | `.claude/skills/claude-multi-model-router/`, `.claude/skills/model-picker/` 존재? | 이미 클론/설치된 상태가 전제 — 없으면 README 설치 명령부터 안내 |
| 2 | `cn --version` 성공하는지 | `npm install -g @continuedev/cli` — **전역 설치이니 먼저 사용자에게 한 줄 확인** 받고 실행 |
| 3 | 프로젝트 루트 `.env`에 `OPENROUTER_API_KEY` 줄이 있는지 | 없으면 `.claude/skills/claude-multi-model-router/.env.example`을 루트 `.env`로 복사(이미 `.env`가 있으면 그 파일 끝에 `OPENROUTER_API_KEY=sk-xxxxxxxxxx` 줄만 추가, 기존 다른 환경변수는 그대로 둠). 실제 키는 사용자가 채팅으로 알려주면 그 값으로 바로 교체하거나, 플레이스홀더로 남겨두고 "openrouter.ai/keys에서 발급해서 이 줄만 채워달라"고 안내 |
| 4 | 루트 `.gitignore`에 `.env` 줄이 있는지 | 없으면 파일 끝에 `.env` 한 줄만 추가(파일 자체가 없으면 새로 생성) — 기존 내용은 보존 |
| 5 | 프로젝트 CLAUDE.md에 "## 라우팅 (필수)" 헤더가 이미 있는지 | 있으면 건드리지 않음(중복 삽입 금지). 없으면 CLAUDE.md 맨 끝에 §2의 앵커 블록만 추가(파일 자체가 없으면 새로 생성) — 이미 진행 중이던 프로젝트의 기존 CLAUDE.md 내용은 절대 지우거나 다시 쓰지 않는다 |
| 6 | `~/.claude/settings.json`에 `model`/`permissions.defaultMode`/`effortLevel`이 §1과 같은지 | Read로 기존 JSON을 먼저 읽고, 없는 키만 채워 넣는 형태로 병합 — 이미 있는 `permissions.allow` 배열이나 다른 커스텀 키(`theme`, `tui` 등)는 절대 지우지 않는다. **이것도 전역 파일이라 고치기 전에 한 줄 확인** |

3~5번(프로젝트 로컬 파일)은 가역적이고 이 프로젝트 스코프라 확인 없이 바로 진행해도 된다. 2번(전역 npm)과 6번(전역 settings.json)은 이 프로젝트 밖에도 영향을 주므로 진행 전 한 줄 확인을 받는다.

### full vs lite

OpenRouter API 키 발급이 부담이거나 회사 정책상 외부 API 호출이 금지된 사용자는 **lite**로 설치한다 — 별도 설치 절차나 플래그가 없다. 위 표에서 **2·3번(cn 설치, OPENROUTER_API_KEY)을 건너뛰면 그 자체로 lite**다. SKILL.md 티어 판정표는 `route.py`/`cn_run.py`가 없으면 항상 OFF 열(Claude 모델끼리만 스케일링)로 처리하도록 이미 짜여 있으므로, 두 스크립트나 `.env`가 없어도 에러 없이 동작한다 — Claude가 호출 전에 파일 존재를 먼저 확인하기 때문이다. 나중에 마음이 바뀌면 2·3번을 그때 채워 넣기만 하면 full로 전환된다(역방향도 마찬가지 — 단순히 안 쓰면 됨).

## 1. ~/.claude/settings.json

```json
{
  "model": "opusplan",
  "permissions": { "defaultMode": "acceptEdits" },
  "effortLevel": "medium"
}
```

- `opusplan`: 플랜 모드 = Opus, 실행 = Sonnet. 플랜 모드 밖에서는 항상 Sonnet(자잘한 작업의 기본 절약 경로).
- `acceptEdits`: 실행 단계 편집 자동 수락. 늘어나는 승인은 플랜 종료 시 "계획 승인" 1회뿐이며, 그 승인이 Opus→Sonnet 전환 스위치다.
- `effortLevel: medium`: 매 턴 thinking 토큰 절감(가장 큰 레버). 어려운 문제는 그 턴 프롬프트에 `ultrathink`를 넣어 일시적으로 깊게.
- **Opus 접근이 없는 요금제(Pro 등)**: `opusplan`을 설정해도 Opus 미보유 요금제에서는 플랜 모드가 자연히 Sonnet으로 강등된다 — 별도 조치 불요, SKILL.md 티어 판정표의 "설계·원인분석" 행도 그대로 적용하면 된다.
- **API 종량제(Max 구독이 아닌 API 키 직접 과금) 사용자**: 서브에이전트·모델 선택의 경제성 계산이 달라진다. Max 구독은 정액이라 "메인 컨텍스트 보호"가 절약의 핵심이지만(SKILL.md 비용 원칙 #2), 종량제는 Haiku 서브에이전트로 내리는 것 자체가 토큰 단가 차이만큼 실비 절감이 된다 — 더 적극적으로 하위 티어를 선택해도 손해가 아니다.

## 2. CLAUDE.md 라우팅 앵커 (필수, 최대 2줄)

프로젝트 CLAUDE.md(또는 ~/.claude/CLAUDE.md)에 추가 — 이게 없으면 스킬 발동이 키워드 운에 좌우된다. 이미 진행 중인 프로젝트의 CLAUDE.md일 수 있으니 덮어쓰지 말고 끝에 추가할 것(§0 참고). 앵커는 매 턴 상주 비용이므로 아래 2줄을 넘기지 않는다 — 세부 규칙(OpenRouter 기본 꺼짐 등)은 CLAUDE.md가 아니라 SKILL.md 쪽에 이미 있으므로 여기서 반복하지 않는다:

```markdown
## 라우팅 (필수)
모든 개발 작업은 claude-multi-model-router 스킬의 티어 판정을 먼저 적용. 굵직한 요청은 플랜 모드로.
```

## 3. VS Code 확장 주의

- `/model`, `/effort` 슬래시 명령이 막혀 있음 → 반드시 settings.json으로 설정.
- 적용 후 확장의 모델 드롭다운을 건드리지 말 것(설정을 덮어씀).
- 세션 도중 CLAUDE.md·스킬 파일을 수정하면 프롬프트 캐시가 깨져 그 턴 비용이 커진다. 설정 변경은 세션 밖에서.

## 4. `cn` CLI 설치 (파일 편집 위임에 필수)

```bash
npm install -g @continuedev/cli
cn --version
```

- MCP의 openrouter 도구는 Read 전용이라 파일 편집 위임에 쓸 수 없음 — `cn`이 그 역할을 대신한다.
- 모델 전환은 Continue 확장의 `/model`이 아니라 이 스킬의 `cn_run.py --set-model` / `--model`로 한다(헤드리스에는 `/model`이 없음). references/cn.md 참고.
- 이 스킬은 **Claude Code 사용자 전용**으로 배포된다. Continue GUI만 쓰는 별도 그룹은 이 스킬의 대상이 아니다(그런 사용자는 스킬 없이 Continue 확장을 직접 씀).

## 5. config는 스킬 폴더, 키는 프로젝트 루트 `.env` (필수)

`.continue/` 폴더는 쓰지 않는다. cn의 config 파일 자체 위치는 어디든 상관없고(항상 `--config <경로>`로 명시), 시크릿(`${{ secrets.X }}`)만 **cwd 기준 프로젝트 루트 `.env`**에서 찾는다(실측 확인됨: 워크스페이스 루트 `.env`가 `.continue/.env`보다 먼저 조회됨).

```
<프로젝트 루트>/
  .env                                   # OPENROUTER_API_KEY=... (실제 키, 루트 .gitignore로 커밋 금지)
  .gitignore                             # .env
  .claude/skills/claude-multi-model-router/
    .env.example                         # 루트 .env가 없을 때 이걸 복사해서 만든다(플레이스홀더 sk-xxxxxxxxxx)
    base.config.yaml                     # apiKey: ${{ secrets.OPENROUTER_API_KEY }} 만 사용, 평문 키 금지
    _oneoff.config.yaml                  # 유료 1회 위임 시 생성 (스킬 .gitignore로 커밋 금지)
```

- `cn`/`cn_run.py`는 항상 프로젝트 루트(cwd)에서 실행해야 시크릿이 해석된다.
- 키를 교체할 땐 루트 `.env` 한 줄만 갱신하면 됨. base.config.yaml·스킬 파일은 손댈 필요 없음.
- 키가 이미 평문으로 config에 들어가 있었다면, `.env`로 옮긴 뒤 그 자리를 `${{ secrets.OPENROUTER_API_KEY }}`로 바꾸고, 노출됐던 원래 키는 가능하면 [openrouter.ai/keys](https://openrouter.ai/keys)에서 로테이션 권장.
- `.env.example`은 스킬과 함께 커밋되는 템플릿(플레이스홀더 값만 있음, 실키 없음) — 루트 `.env`를 처음 만들 때만 참고하고, 그 뒤로는 루트 `.env`가 진짜 상태다.

## 6. OpenRouter 위임 판단 기준 (canonical — README.md/cn.md는 이 표를 링크)

OpenRouter 위임은 기본 꺼짐이고, `route.py`(텍스트 생성)와 `cn_run.py`(파일 편집) 둘 다 같은 스위치(sticky/autoscale 상태 파일, route.py가 관리하고 cn_run.py가 그대로 가져다 씀)로 게이팅된다 — 한쪽만 켜지는 게 아니다. 아래 기준으로 먼저 분류한다.

| 작업 유형 | 처리 방식 |
|---|---|
| 설계/원인분석/최적화 방안 도출 (판단력 필요) | Claude가 직접 처리 — free 모델은 신뢰도가 낮아 위임 부적합 |
| 범위가 명확한 기계적 코드 수정 (헬퍼 추출, 타입 힌트 추가, 포맷팅 등) | OpenRouter 위임이 켜져 있으면(sticky 또는 autoscale) `cn_run.py`로 위임 → diff로 검증. 꺼져 있으면(기본값) Sonnet 서브에이전트가 직접 처리 |
| 단순 텍스트 생성/요약/설명 (파일 편집 아님) | OpenRouter 위임이 켜져 있으면 `route.py` 위임(cn보다 가벼움). 꺼져 있으면(기본값) Haiku 서브에이전트가 직접 처리 |

두 행 모두 "OpenRouter 켜짐"이면 sticky로 고정한 게 아닌 한 `classify()`로 요청 난이도를 다시 분류해 trivial(진짜 무료)~light~mid~reason 중 적합한 모델을 자동 선택한다 — Claude 자신의 티어 판정과 같은 원리를 OpenRouter 모델 풀 안에서 한 번 더 적용하는 것. `route.py`가 이 상태 판단의 원본이고 `cn_run.py`는 그 함수를 그대로 가져다 쓴다(중복 구현 없음).

## 7. 기타

- sticky/autoscale 상태는 프로젝트 루트 `.claude/.cmr-state.json`에 저장된다(스킬 폴더가 아니라 **프로젝트 루트** — degit 재설치로 유실되지 않도록). 루트 `.gitignore`에 `.claude/.cmr-state.json` 포함 확인(§0/§4와 같은 흐름으로 추가). 구버전(스킬 폴더 내부 `cn_active_model.txt`/`cn_autoscale.txt`)이 있으면 route.py가 첫 실행 시 이 파일로 1회 자동 마이그레이션하고 구파일은 지운다.
- `_oneoff.config.yaml` — 스킬 디렉터리의 `.gitignore`에 포함됨(유료 1회 임시 config, 커밋 금지).
- cn_models.json은 cn 위임용 로스터(free/paid) — `autoscale`/`roles` 블록도 여기 있음.
- 유료 모델을 역할별로 쉽게 고르고 싶으면 `model-picker` 스킬(별도 스킬 폴더)을 쓴다. cn_run.py의 `--autoscale on|off`/`--set-model`을 대화형으로 감싼 것.
