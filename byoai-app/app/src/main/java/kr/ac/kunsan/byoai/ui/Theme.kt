package kr.ac.kunsan.byoai.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import kr.ac.kunsan.byoai.R

/* ───────────── 디자인 시스템 v2 (DESIGN.md 정본) ─────────────
 * 단일 슬레이트블루 액센트 · luminance 위계(다크에서 표면은 밝기로 뜸) ·
 * Space Grotesk(타이틀·수치) + Inter(본문). 금지: 네온 무지개, 골드, 순백 텍스트. */

val Bg0 = Color(0xFF0A0B0E)      // 최심부 배경
val Bg1 = Color(0xFF111318)      // 배경 그라데이션 상단
val Surface1 = Color(0xFF16191F) // 카드 — 배경보다 한 단 밝게 (Material 다크 elevation)
val Surface2 = Color(0xFF1C2028) // 시트·강조 표면 — 두 단 밝게

val T1 = Color(0xFFEEF1F6)       // 고강조 텍스트 (순백 금지)
val T2 = Color(0xFF9DA3B0)       // 보조
val T3 = Color(0xFF6A7180)       // 약한 라벨

val Accent = Color(0xFF86A4C8)   // 슬레이트블루 — 유일한 액센트
val Good   = Color(0xFF79B89A)
val Warn   = Color(0xFFC2A878)
val Danger = Color(0xFFC88686)

val Stroke   = Color(0x1FFFFFFF) // 12% 백색 보더 (엣지 하이라이트)
val StrokeLo = Color(0x14FFFFFF) // 8% — 비강조 구분선

/* variable TTF: Font(weight=...)가 API26+에서 wght 축을 자동 적용 (minSdk 31) */
val Grotesk = FontFamily(
    Font(R.font.space_grotesk, weight = FontWeight.Medium),
    Font(R.font.space_grotesk, weight = FontWeight.SemiBold),
    Font(R.font.space_grotesk, weight = FontWeight.Bold),
)
val Inter = FontFamily(
    Font(R.font.inter, weight = FontWeight.Normal),
    Font(R.font.inter, weight = FontWeight.Medium),
    Font(R.font.inter, weight = FontWeight.SemiBold),
)

private val Scheme = darkColorScheme(
    primary = Accent, onPrimary = Bg0,
    background = Bg0, onBackground = T1,
    surface = Surface1, onSurface = T1,
    surfaceVariant = Surface2, outline = Stroke,
)

@Composable
fun ByoaiTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, content = content)
}
