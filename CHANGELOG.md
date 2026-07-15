# Changelog

## v2 — 스킬 풋프린트 다이어트 + 안전망 (Fable 리뷰 반영)

### Breaking / 마이그레이션 필요

- **sticky/autoscale 상태 파일 이동**: 스킬 폴더 내부 `cn_active_model.txt`/`cn_autoscale.txt` → 프로젝트 루트 `.claude/.cmr-state.json`(단일 JSON). `route.py`가 첫 실행 시 구 파일을 감지하면 자동으로 새 위치로 옮기고 구 파일을 삭제한다 — 수동 조치 불필요. 프로젝트 루트 `.gitignore`에 `.claude/.cmr-state.json`을 추가해야 커밋되지 않는다(`references/setup.md` §7 참고, 기존 설치는 세팅 재실행 시 자동 반영).
- **`models.json` → `escalate_labels.json` 개명**: sonnet/opus ESCALATE 안내 라벨 전용 파일(배포 파일, 사용자 상태 아님). 실제 모델 로스터는 원래도 `cn_models.json`이었다 — README의 "이건 로스터가 아니다" 해명 문구는 이름 자체가 명확해져 삭제.

### 추가

- `route.py`/`cn_run.py`에 `--tier {trivial|light|mid|reason}` — Claude가 SKILL.md 표에서 이미 판정한 티어를 직접 전달하는 기본 경로. 미지정 시에만 내부 `classify()`가 폴백으로 재분류(이원 분류 충돌 방지).
- `cn_run.py`의 git-clean 안전망: working tree가 dirty하면 위임을 기본 차단(`--allow-dirty`로 강제 가능).
- `route.py`의 free quota 소진(429 반복) 감지 시 `suggestion` 필드로 Sonnet 서브에이전트 폴백 제안.
- `tests/tier_cases.json` + `tests/run_tier_cases.py` + `.github/workflows/tier-classification.yml` — 분류 회귀 테스트 CI(API 키/크레딧 불필요, PR마다 실행).
- lite 프로필: OpenRouter 키 발급 없이 Claude 모델끼리만 스케일링하는 설치 경로(별도 절차 없음 — `references/setup.md` §0 "full vs lite" 참고).

### 변경

- SKILL.md 본문 5.1KB → 2KB 이하로 압축, description 40%+ 축소(트리거 키워드는 전부 보존). 세부 설명은 `references/`로 이동.
- CLAUDE.md 라우팅 앵커 최대 2줄로 축소.
- README의 티어 판정표를 SKILL.md로 단일화(README는 요약 + 링크만 유지) — 두 문서가 서로 다른 말을 하는 드리프트 방지.
- 비용 서술에서 근거 없는 "서브에이전트 손익분기 ≈ 350토큰" 수치를 제거하고 원리(메인 컨텍스트 보호) 중심으로 교정.
- opusplan 전제를 Opus 미보유 요금제(Pro 등)에서도 자연 강등되도록 조건화, API 종량제 사용자를 위한 비용 계산 차이 안내 추가.
