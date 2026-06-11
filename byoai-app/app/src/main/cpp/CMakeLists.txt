cmake_minimum_required(VERSION 3.22.1)
project(byoai_llm)

# llama.cpp 소스를 여기에 둔다 (git submodule 또는 직접 복사):
#   app/src/main/cpp/llama.cpp/   ← https://github.com/ggml-org/llama.cpp
# 우리가 폰에서 검증한 빌드(b9442)와 동일 계열을 쓰면 됨.
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER   OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP          OFF CACHE BOOL "" FORCE)   # 안드로이드 libomp 이슈 회피

add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/llama.cpp build-llama)

add_library(byoai_llm SHARED llama_jni.cpp)
target_link_libraries(byoai_llm llama ggml android log)
