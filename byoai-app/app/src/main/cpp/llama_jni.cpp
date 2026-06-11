// BYOAI llama.cpp JNI 브릿지 — 폰에서 Gemma 4 E4B(GGUF) 결정 추론.
// Kotlin LlamaBridge 의 external 함수에 대응.
// 참고: 공식 llama.android 샘플(llama.cpp/examples/llama.android)을 기반으로 단순화.
// llama.cpp API는 버전마다 바뀌므로 우리가 검증한 b9442 계열 헤더에 맞춰 조정할 것.
#include <jni.h>
#include <android/log.h>
#include <string>
#include <vector>
#include <cstring>
#include "llama.h"

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "byoai-llm", __VA_ARGS__)

struct Ctx {
    llama_model*   model = nullptr;
    llama_context* lctx  = nullptr;
};

extern "C" JNIEXPORT jlong JNICALL
Java_kr_ac_kunsan_byoai_llm_LlamaBridge_nativeInit(
        JNIEnv* env, jobject, jstring jModelPath, jint nThreads) {
    const char* path = env->GetStringUTFChars(jModelPath, nullptr);
    llama_log_set([](ggml_log_level lvl, const char* msg, void*) {
        __android_log_print(lvl >= GGML_LOG_LEVEL_ERROR ? ANDROID_LOG_ERROR : ANDROID_LOG_INFO,
                            "byoai-llm", "%s", msg);
    }, nullptr);
    llama_backend_init();
    llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 0;                       // 8 Gen 1: CPU가 정답(검증됨)
    auto* ctx = new Ctx();
    ctx->model = llama_model_load_from_file(path, mp);
    env->ReleaseStringUTFChars(jModelPath, path);
    if (!ctx->model) { LOG("model load FAIL"); delete ctx; return 0; }
    llama_context_params cp = llama_context_default_params();
    cp.n_ctx     = 2048;
    cp.n_threads = nThreads > 0 ? nThreads : 4; // 4스레드 최적(실측)
    ctx->lctx = llama_init_from_model(ctx->model, cp);
    LOG("model loaded, n_threads=%d", cp.n_threads);
    return reinterpret_cast<jlong>(ctx);
}

// 프롬프트 → 생성 텍스트. greedy 디코딩, nPredict 토큰 한도.
extern "C" JNIEXPORT jstring JNICALL
Java_kr_ac_kunsan_byoai_llm_LlamaBridge_nativeDecide(
        JNIEnv* env, jobject, jlong handle, jstring jPrompt, jint nPredict) {
    auto* ctx = reinterpret_cast<Ctx*>(handle);
    if (!ctx || !ctx->lctx) return env->NewStringUTF("");
    const char* prompt = env->GetStringUTFChars(jPrompt, nullptr);

    const llama_vocab* vocab = llama_model_get_vocab(ctx->model);
    // 1) 토크나이즈
    int n_prompt = -llama_tokenize(vocab, prompt, strlen(prompt), nullptr, 0, true, true);
    std::vector<llama_token> toks(n_prompt);
    llama_tokenize(vocab, prompt, strlen(prompt), toks.data(), toks.size(), true, true);
    env->ReleaseStringUTFChars(jPrompt, prompt);

    // 2) 디코드 + 그리디 샘플링
    auto* smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_greedy());

    llama_batch batch = llama_batch_get_one(toks.data(), toks.size());
    std::string out;
    for (int n = 0; n < nPredict; n++) {
        if (llama_decode(ctx->lctx, batch)) break;
        llama_token id = llama_sampler_sample(smpl, ctx->lctx, -1);
        if (llama_vocab_is_eog(vocab, id)) break;
        char buf[256];
        int k = llama_token_to_piece(vocab, id, buf, sizeof(buf), 0, true);
        if (k > 0) out.append(buf, k);
        batch = llama_batch_get_one(&id, 1);
    }
    llama_sampler_free(smpl);
    return env->NewStringUTF(out.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_kr_ac_kunsan_byoai_llm_LlamaBridge_nativeFree(JNIEnv*, jobject, jlong handle) {
    auto* ctx = reinterpret_cast<Ctx*>(handle);
    if (!ctx) return;
    if (ctx->lctx)  llama_free(ctx->lctx);
    if (ctx->model) llama_model_free(ctx->model);
    delete ctx;
    llama_backend_free();
}
