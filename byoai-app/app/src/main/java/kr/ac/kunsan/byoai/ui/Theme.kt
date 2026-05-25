package kr.ac.kunsan.byoai.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ===== BYOAI v1 neon theme =====
// First-pass look: saturated violet/cyan neon on near-black, heavy glow.
// (Replaced later by the calmer slate system — see redesign.)

val NeonViolet = Color(0xFF7C3AED)
val NeonCyan = Color(0xFF22D3EE)
val NeonMagenta = Color(0xFFEC4899)
val NeonLime = Color(0xFFA3E635)
val NearBlack = Color(0xFF0A0A0F)
val PanelBlack = Color(0xFF14141C)
val PanelBlack2 = Color(0xFF1C1C28)
val NeonText = Color(0xFFEDEDFF)
val NeonTextDim = Color(0xFF9A9AB8)
val NeonOk = Color(0xFF34D399)
val NeonWarn = Color(0xFFFBBF24)
val NeonBad = Color(0xFFF87171)

private val NeonDark = darkColorScheme(
    primary = NeonViolet,
    onPrimary = Color.White,
    secondary = NeonCyan,
    onSecondary = NearBlack,
    tertiary = NeonMagenta,
    background = NearBlack,
    onBackground = NeonText,
    surface = PanelBlack,
    onSurface = NeonText,
    surfaceVariant = PanelBlack2,
    onSurfaceVariant = NeonTextDim,
    error = NeonBad,
)

private val NeonLight = lightColorScheme(
    primary = NeonViolet,
    secondary = NeonCyan,
    tertiary = NeonMagenta,
)

private val NeonType = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Black,
        fontSize = 30.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 20.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
    ),
)

@Composable
fun ByoaiTheme(content: @Composable () -> Unit) {
    val scheme = if (isSystemInDarkTheme()) NeonDark else NeonLight
    MaterialTheme(
        colorScheme = scheme,
        typography = NeonType,
        content = content,
    )
}
