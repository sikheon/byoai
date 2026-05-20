# BYOAI 폰 앱 (Kotlin / Android) — 스켈레톤

대뇌(폰) 측 앱. **공간 자동발견(mDNS) → 기기 자동추가(SPACE_DESCRIPTOR) →
폰 Gemma 4 결정(llama.cpp JNI) → 제어 + 수동보정 학습**.
= `byoai-hw/rpi/discover.py` + `phone_brain.py` 를 Kotlin으로 이식한 것.
서버(척수)는 `byoai-hw/rpi/spine.py` 그대로 사용.

## 구조
```
app/src/main/
 ├─ cpp/                    llama.cpp JNI (Gemma 추론)
 │   ├─ CMakeLists.txt      └ llama.cpp/ 를 여기에 두고 빌드
 │   └─ llama_jni.cpp
 └─ java/kr/ac/kunsan/byoai/
     ├─ discovery/SpaceDiscovery.kt   ① mDNS 자동발견 (NsdManager)
     ├─ net/SpineClient.kt            ② TCP 줄단위 JSON (척수 통신)
     ├─ llm/LlamaBridge.kt            ③ JNI 래퍼
     ├─ llm/PromptBuilder.kt          ③ 프롬프트 + targets 추출
     ├─ model/Protocol.kt             데이터클래스 + 휴대용 UserModel
     ├─ data/UserModelStore.kt        휴대용 모델 영속(복리효과)
     ├─ ByoaiViewModel.kt             4화면 상태 + 흐름
     ├─ MainActivity.kt
     └─ ui/Screens.kt                 ①탐색 ②기기카드 ③최적화 ④수동슬라이더
```

## 화면(MVP 4)
1. **공간 탐색** — 같은 WiFi의 `_byoai._tcp` 자동 발견 → 카드 리스트
2. **공간 상세** — `SPACE_DESCRIPTOR`의 능력마다 기기 카드 자동 생성
3. **AI 최적화** — 버튼 → 폰 Gemma 결정(JSON) → 척수로 목표 전송
4. **수동보정** — 슬라이더 조작 → FEEDBACK 학습(휴대용 모델 누적)

## 빌드 준비 (Android Studio에서)
1. `app/src/main/cpp/` 에 **llama.cpp 소스**를 둔다 (폰에서 검증한 b9442 계열):
   ```
   cd app/src/main/cpp && git clone https://github.com/ggml-org/llama.cpp
   ```
   - `llama_jni.cpp`의 API는 그 버전 `llama.h`에 맞춰 조정(샘플: `llama.cpp/examples/llama.android`).
2. **모델 파일**: 검증된 `gemma-4-E4B-it-Q4_K_M.gguf`(≈5GB)를 앱 내부저장소로 복사 후
   경로를 `vm.loadBrain(path)`에 전달. 데모 시엔 `adb push` 후 코드에서 복사.
   - 모델 없으면 자동 heuristic 폴백(앱은 계속 동작).
3. NDK + CMake 설치, ABI = `arm64-v8a`. minSdk 31 (S22 울트라).
4. 같은 WiFi에서 `python spine.py --sim --mdns` 띄우고 앱 실행 → 공간이 자동으로 뜸.

## 주의 (텀프로젝트 범위)
- 버전(AGP/Compose/Kotlin)은 Android Studio가 동기화 제안 → 따라가면 됨.
- JNI `llama_jni.cpp`는 **API 시그니처가 llama.cpp 버전따라 바뀜** → 빌드 에러나면
  해당 버전 `llama.h`/`llama.android` 샘플 기준으로 함수명만 맞추면 됨.
- mDNS는 실기기+실 WiFi에서 검증(에뮬레이터는 멀티캐스트 제약 있음).
