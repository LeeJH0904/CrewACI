## 2026-08-06

- Google Gemini provider 지원 추가: `GeminiLLM` 구현 및 provider 라우팅 추가.
- `ACISentinel`이 judge 설정의 provider에 따라 OpenAI/Gemini를 선택하도록 수정.
- Gemini API 사용을 위해 `google-genai` 의존성 추가.

# Debug Log

## 2026-07-23 — `ModuleNotFoundError: No module named 'aciarena.defenses.safety_filter'`

### 수정
`aciarena/aciarena/defenses/__init__.py`
```diff
- from .safety_filter import SafetyFilter
+ from .aci_sentinel import ACISentinel
  from .bert_detector import BertDetector
```

### 검증
수정 후 `safety_filter` 관련 오류 해소됨. import 체인이 정상 진행되어 이후 단계에서 멈춤.



## `C:\Users\Lee\Desktop\ACIArena\aciarena\aciarena\evaluation\datasets`

프로젝트의 새 이름(aciarena)에 맞춰 파일을 리네임:
maspi_code.json → aciarena_code.json
maspi_math.json → aciarena_math.json

## `C:\Users\Lee\Desktop\ACIArena\aciarena\aciarena\utils\factory.py`

오타 수정:
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%]S")
-> timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")