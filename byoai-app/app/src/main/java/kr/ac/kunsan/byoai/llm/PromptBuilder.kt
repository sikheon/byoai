package kr.ac.kunsan.byoai.llm

import kr.ac.kunsan.byoai.model.SpaceDescriptor
import kr.ac.kunsan.byoai.model.UserModel
import org.json.JSONObject

/** phone_brain.py 의 build_prompt / _extract_targets 를 Kotlin으로 이식. */
object PromptBuilder {

    fun build(desc: SpaceDescriptor, user: UserModel): String {
        val sb = StringBuilder()
        sb.append("너는 BYOAI 스마트홈의 의사결정 AI다. 공간 능력과 사용자 선호를 결합해 ")
        sb.append("각 능력의 목표값을 정하라. 반드시 JSON 하나만 출력.\n\n")
        sb.append("[공간] ${desc.place} / 외부 ${desc.outsideTemp}도 / 재실 ${desc.present}\n[능력]\n")
        desc.capabilities.forEach { c ->
            sb.append("- ${c.kind}: 현재 ${c.current}${c.unit} ")
            c.typicalNow?.let { sb.append("(이 공간 이 시간대 평소 ${it}${c.unit}) ") }
            sb.append("(범위 ${c.min}~${c.max}), 학습모델 ${c.learnedModel}\n")
        }
        sb.append("\n[사용자 휴대 선호]\n")
        sb.append("- 추위민감 오프셋 +${user.climateOffset}도, 조명선호 ${user.lightPref}lux, ")
        sb.append("공기질 상한 ${user.airMax}\n")
        sb.append("- 최근 보정 ${user.corrections.takeLast(3)}\n\n")
        sb.append("[출력] JSON만: {\"targets\":{\"climate\":숫자,\"light\":숫자,")
        sb.append("\"air_quality\":숫자},\"reason\":\"한문장\"}")
        return sb.toString()
    }

    /** 균형 중괄호 스캔으로 "targets" 포함 최상위 객체 추출(프롬프트 에코 회피). */
    fun extractTargets(text: String): Pair<Map<String, Double>, String>? {
        var depth = 0; var start = -1
        val objs = mutableListOf<String>()
        text.forEachIndexed { i, ch ->
            when (ch) {
                '{' -> { if (depth == 0) start = i; depth++ }
                '}' -> if (depth > 0) { depth--; if (depth == 0) objs.add(text.substring(start, i + 1)) }
            }
        }
        for (cand in objs.asReversed()) {
            runCatching {
                val o = JSONObject(cand)
                val t = o.optJSONObject("targets") ?: return@runCatching
                val map = t.keys().asSequence().associateWith { t.getDouble(it) }
                if (map.isNotEmpty()) return map to o.optString("reason")
            }
        }
        return null
    }
}
