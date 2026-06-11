package kr.ac.kunsan.byoai.llm

/**
 * llama.cpp JNI 래퍼. 폰에서 Gemma 4 E4B(GGUF)를 로드해 결정 추론.
 * 네이티브 구현은 cpp/llama_jni.cpp. 모델 파일은 앱 내부저장소에 복사해 경로 전달.
 */
class LlamaBridge {
    private var handle: Long = 0L

    fun load(modelPath: String, threads: Int = 4): Boolean {
        if (!available) return false          // .so 없으면 heuristic 폴백 (D-4)
        handle = nativeInit(modelPath, threads)
        return handle != 0L
    }

    fun decide(prompt: String, nPredict: Int = 200): String =
        if (handle == 0L) "" else nativeDecide(handle, wrapGemma(prompt), nPredict)

    /** Gemma 챗 템플릿 — llama-cli는 자동 적용하지만 JNI 직접 디코딩은 수동. */
    private fun wrapGemma(p: String) =
        "<start_of_turn>user\n$p<end_of_turn>\n<start_of_turn>model\n"

    fun free() {
        if (handle != 0L) nativeFree(handle)
        handle = 0L
    }

    private external fun nativeInit(modelPath: String, nThreads: Int): Long
    private external fun nativeDecide(handle: Long, prompt: String, nPredict: Int): String
    private external fun nativeFree(handle: Long)

    companion object {
        /** 네이티브 .so 유무 — 없어도 앱은 살아서 heuristic 으로 동작해야 함. */
        val available: Boolean = runCatching { System.loadLibrary("byoai_llm") }.isSuccess
    }
}
