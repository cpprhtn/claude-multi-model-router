---
name: claude-multi-model-router
description: Route dev tasks ("수정/구현/리팩터/디버그해줘", fix/implement/refactor/debug, any coding request, "토큰 아껴", "사용량") to the cheapest reliable tier — conserves Claude usage.
---

# claude-multi-model-router — 티어 라우팅

전제: `opusplan` → 플랜=Opus, 실행=Sonnet. Opus 미보유 요금제는 플랜도 자동 Sonnet 강등 — 종량제 비용差: setup.md §6.

## 티어 판정

기본은 Claude 모델끼리만 스케일링, OpenRouter는 sticky/autoscale 켜기 전까지 미개입(공통 스위치). lite 설치(스크립트 없음)면 ON 열 무시, 항상 OFF — 호출 전 파일 존재 확인.

| 작업 | OFF(기본) | ON — `--tier <ladder>`로 명시 위임 |
|---|---|---|
| 설계·원인분석 | 플랜 모드 | `reason`(`terra`,상한). 최상급은 `--set-model`로만 |
| 짧은 코드·질의 | 메인 세션(Sonnet) | `route.py --tier mid ...` |
| 파일 수정(다수/기계적) | Sonnet 서브에이전트 | `cn_run.py --tier <t> -p "..."` |
| 탐색·요약·번역 | Haiku 서브에이전트 | `route.py --tier <t> --out FILE "..."` |

ladder: `trivial`(진짜 무료)<`light`<`mid`(`glm`)<`reason`(`terra`,ceiling). 표에서 판정한 티어를 `--tier`로 직접 넘긴다 — 내부 `classify()`는 `--tier` 미지정 시만 폴백(이원 분류 방지). 상세: references/cn.md.

## 비용 원칙

1. free 위임은 결과를 내가 재생산하면 손해 — 파일 직접 적용/짧은 결과만 이득.
2. 서브에이전트 절약은 단가差가 아니라 메인 컨텍스트 보호(이후 턴 input 절감)에서 나옴.
3. free 모델은 신뢰도 낮음 — 단순·기계적만, 결과는 항상 diff 검토.

## OpenRouter 켜기/끄기 + 안전망

전환 신호("무료모델 써줘"/"오토스케일 켜줘"/"X로"/"그만") 보일 때만 references/cn.md 읽기. 파일 편집 위임은 working tree clean일 때만(`cn_run.py` 자체 검사, dirty면 `--allow-dirty` 필요).

## 보조

- `route.py --tier-only "설명"` — 분류 힌트만(무료, 호출 없음)
- 유료 모델 역할별 선택: model-picker 스킬
- 설치: references/setup.md · sticky 고지/quota 폴백/프롬프트 인젝션 주의: references/cn.md
