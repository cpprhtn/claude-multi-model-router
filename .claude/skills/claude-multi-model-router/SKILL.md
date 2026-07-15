---
name: claude-multi-model-router
description: Route every dev task ("수정/구현/리팩터/디버그해줘", fix/implement/refactor/debug, or any coding request) to the cheapest tier that handles it reliably, conserving Claude Max usage. Also triggers on "토큰 아껴", "사용량". Defines when to use plan mode (Opus), main session (Sonnet), Sonnet/Haiku subagents, free OpenRouter models via route.py, or headless cn CLI delegation (cn_run.py) with on-demand paid-model switching.
---

# claude-multi-model-router — 티어 라우팅

전제: settings.json에 `"model": "opusplan"` → 플랜 모드 = Opus, 실행 = Sonnet.

## 티어 판정

기본값은 **Claude 모델끼리만 스케일링**한다 — OpenRouter는 `route.py`(텍스트 생성)든 `cn_run.py`(파일 편집)든 아래 "OpenRouter 위임 켜기/끄기"에서 명시적으로 켜기 전까지 절대 자동으로 개입하지 않는다. 두 스크립트 모두 같은 스위치를 공유한다 — 한쪽만 켜지는 게 아니다.

| 작업 | 실행처 |
|------|--------|
| 원인분석·설계·계획 (굵직한 요청) | 플랜 모드 (Opus). 절대 다운그레이드 금지 |
| 몇 줄 코드·짧은 답·단순 질의 | 메인 세션 직접 (Sonnet) |
| 여러 파일 수정·긴 출력 (~350토큰 초과) | Sonnet 서브에이전트 — 파일 직접 편집시키고 요약만 회수 |
| 탐색·검색·대량 읽기 후 요점 회수 | Haiku 서브에이전트 |
| free 텍스트 생성 (요약/번역/설명 등, 출력 방대·결과 짧음) — **OpenRouter 꺼짐(기본값)** | Haiku 서브에이전트 |
| free 텍스트 생성 — **OpenRouter 켜짐** | `route.py --out FILE "지시"` → cp/patch로 적용, head/diff로 부분 검토. 내용을 내 출력으로 재생산하지 않는다 |
| 단순·기계적 파일 편집 (이름변경/치환/포맷팅/보일러플레이트) — **OpenRouter 꺼짐(기본값)** | Sonnet 서브에이전트가 직접 처리 — 위 "여러 파일 수정" 행과 동일 |
| 단순·기계적 파일 편집 — **OpenRouter 켜짐** | `cn_run.py -p "자립형 지시"`로 위임(내가 헤드리스로 구동, 핸드오프 아님) → diff로 검증 |

**"OpenRouter 켜짐" 두 행 모두 동작 원리는 같다** — sticky로 특정 모델을 고정하지 않은 한, 단일 free 모델을 고정 호출하는 게 아니라 **내 티어 판정과 똑같은 방식으로 이 요청의 난이도를 다시 분류해서**(`classify()`) OpenRouter 모델 풀 안에서 trivial(진짜 무료)~light~mid~reason 중 하나를 고른다. `route.py`와 `cn_run.py`는 sticky/autoscale 상태를 공유하므로 동일한 판단이 적용된다 — 자세한 표는 아래 참고.

## 비용 규칙 (위임이 항상 싼 게 아니다)

1. **free 위임은 내가 결과를 재생산(output)해야 하면 손해.** 이득인 경우만: Continue가 파일 직접 적용 / `--out`으로 파일 수신 / 결과가 짧음 / 사용자가 직접 소비. 그 외 짧은 생성+적용은 메인 세션이 직접.
2. **서브에이전트 손익분기 ≈ 350토큰.** 작으면 메인 직접, 크면 위임(메인 컨텍스트 보호 → 이후 턴 input도 절약). 필요한 맥락(경로/의도/제약)은 프롬프트에 전부 담을 것 — 컨텍스트 비공유.
3. free 모델은 신뢰도가 낮다. 단순·기계적 작업만. 애매하면 sonnet 이상. free 결과는 반드시 diff 검토.

## OpenRouter 위임 켜기/끄기 (기본 꺼짐 — route.py·cn_run.py 공통 스위치)

**"OpenRouter 위임이 켜짐"** = sticky 모델이 설정돼 있거나(`cn_run.py --list-models`로 확인 가능) autoscale이 on인 상태 — 둘 중 하나라도 있으면 켜진 것. 신규 프로젝트·아무 설정 없는 기본 상태는 항상 꺼짐. 이 상태 하나로 `route.py`(텍스트 생성)와 `cn_run.py`(파일 편집) 둘 다 게이팅된다.

평소 위임 실행(위 표의 "OpenRouter 켜짐" 행)은 `route.py`/`cn_run.py`가 sticky/autoscale을 알아서 반영하므로 이 절 자체를 안 읽어도 된다. 사용자 발화에 **"오픈라우터 무료모델 써줘"/"오토스케일 켜줘"/"이번엔·앞으로 <모델>로"/"오픈라우터 그만"** 같은 온오프·모델 전환 신호가 있을 때만 `references/cn.md`("모델 선택"/"오토스케일" 절)에서 정확한 명령과 phrase별 차이(특히 "무료모델 써줘"≠"오토스케일 켜줘")를 확인해 실행한다. Python이 없는 환경이면 `cn_run.py` 대신 그 문서의 "네이티브 폴백" 절차를 따른다.

## 보조

- `route.py --tier-only "설명"` — 분류 힌트뿐, API 호출 없음(사용량 0, 키 불필요) → OpenRouter 위임 상태와 무관하게 언제나 사용 가능
- cn 위임 상세(모델 선택/오토스케일/헤드리스 패턴/diff 검증/폴백): references/cn.md — 위 표대로 켜는 동작을 할 때만 읽기
- 유료 모델을 역할별로 대화형으로 고르고 싶어하면: model-picker 스킬로 안내
- 설치/설정(opusplan, CLAUDE.md 앵커, VS Code 주의, cn 설치, config/키 관리, OpenRouter 위임 판단 기준 표): references/setup.md — 사용자가 설정을 물을 때만 읽기, 위임 판단 기준만 필요하면 §6으로 바로
