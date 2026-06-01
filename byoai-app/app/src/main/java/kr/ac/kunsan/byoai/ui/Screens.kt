@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package kr.ac.kunsan.byoai.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.BlurredEdgeTreatment
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke as DrawStroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import kr.ac.kunsan.byoai.ByoaiViewModel
import kr.ac.kunsan.byoai.model.Capability
import kr.ac.kunsan.byoai.model.DiscoveredSpace
import kr.ac.kunsan.byoai.model.SpaceDescriptor
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

@Composable
fun App(vm: ByoaiViewModel) {
    val descriptor by vm.descriptor.collectAsStateWithLifecycle()
    Background {
        // 화면 전환: 컷 금지 — fade + 미세한 상승 (300ms)
        AnimatedContent(
            targetState = descriptor,
            contentKey = { it == null },
            transitionSpec = {
                (fadeIn(tween(300, 60)) + slideInVertically(tween(300, 60)) { it / 24 })
                    .togetherWith(fadeOut(tween(150)))
            }, label = "nav",
        ) { d ->
            if (d == null) DiscoveryScreen(vm) else SpaceScreen(vm, d)
        }
    }
}

/* ───────────────────────── 공통 ───────────────────────── */

/** 다크 그래파이트 배경 + 슬레이트 블룸 — 죽은 검정 금지. */
@Composable
fun Background(content: @Composable BoxScope.() -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Bg1, Bg0)))
    ) {
        Box(
            Modifier
                .size(340.dp).offset(x = (-90).dp, y = (-120).dp)
                .blur(110.dp, BlurredEdgeTreatment.Unbounded)   // 사각 클립 경계 방지
                .background(Accent.copy(alpha = 0.16f), CircleShape)
        )
        Box(
            Modifier
                .align(Alignment.BottomEnd)
                .size(300.dp).offset(x = 100.dp, y = 130.dp)
                .blur(120.dp, BlurredEdgeTreatment.Unbounded)
                .background(Accent.copy(alpha = 0.10f), CircleShape)
        )
        content()
    }
}

/** 카드 — 불투명 표면(luminance 위계) + 엣지 보더. */
@Composable
fun Card(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(24.dp)
    Column(
        modifier
            .clip(shape)
            .background(Surface1, shape)
            .border(BorderStroke(1.dp, Stroke), shape)
            .then(if (onClick != null) Modifier.clickable { onClick() } else Modifier),
        content = content,
    )
}

/** 능력 라인 아이콘 (sun / thermometer / wind) — 색이 아니라 모양으로 구분. */
@Composable
fun CapIcon(kind: String, tint: Color, size: Int = 18) {
    Canvas(Modifier.size(size.dp)) {
        val w = this.size.width; val c = w / 2f; val sw = w * 0.09f
        when (kind) {
            "light" -> {
                drawCircle(tint, radius = w * 0.18f, style = DrawStroke(sw))
                repeat(8) { i ->
                    val a = Math.toRadians(i * 45.0)
                    val (dx, dy) = cos(a).toFloat() to sin(a).toFloat()
                    drawLine(tint, Offset(c + dx * w * 0.30f, c + dy * w * 0.30f),
                        Offset(c + dx * w * 0.44f, c + dy * w * 0.44f), sw, StrokeCap.Round)
                }
            }
            "climate" -> {
                drawLine(tint, Offset(c, w * 0.12f), Offset(c, w * 0.58f), sw * 1.6f, StrokeCap.Round)
                drawCircle(tint, radius = w * 0.17f, center = Offset(c, w * 0.74f), style = DrawStroke(sw))
            }
            "air_quality" -> {
                drawLine(tint, Offset(w * 0.12f, w * 0.30f), Offset(w * 0.72f, w * 0.30f), sw, StrokeCap.Round)
                drawLine(tint, Offset(w * 0.12f, w * 0.52f), Offset(w * 0.88f, w * 0.52f), sw, StrokeCap.Round)
                drawLine(tint, Offset(w * 0.12f, w * 0.74f), Offset(w * 0.60f, w * 0.74f), sw, StrokeCap.Round)
            }
            else -> drawCircle(tint, radius = w * 0.16f)
        }
    }
}

@Composable
fun PulseDot(color: Color, size: Int = 8, periodMs: Int = 900) {
    val t = rememberInfiniteTransition(label = "pulse")
    val a by t.animateFloat(
        initialValue = 0.35f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(periodMs), RepeatMode.Reverse), label = "a"
    )
    Box(Modifier.size(size.dp).background(color.copy(alpha = a), CircleShape))
}

/* ───────────────────────── ① Spaces ───────────────────────── */

@Composable
fun DiscoveryScreen(vm: ByoaiViewModel) {
    val spaces by vm.spaces.collectAsStateWithLifecycle()
    val connecting by vm.connecting.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()
    var showAi by remember { mutableStateOf(false) }

    DisposableEffect(Unit) {
        vm.startDiscovery()
        onDispose { vm.stopDiscovery() }
    }

    // 빈 상태: 영원한 침묵 금지 — 15초 후 조용한 힌트 한 줄
    var quietHint by remember { mutableStateOf(false) }
    LaunchedEffect(spaces.isEmpty()) {
        quietHint = false
        if (spaces.isEmpty()) { delay(15_000); quietHint = true }
    }

    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = 22.dp)
            .padding(top = 64.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("BYOAI", color = T1, fontSize = 27.sp, fontFamily = Grotesk,
                    fontWeight = FontWeight.Bold, letterSpacing = 3.sp)
                Text("your comfort, in any space", color = T3, fontSize = 12.sp, fontFamily = Inter)
            }
            Spacer(Modifier.weight(1f))
            // My AI — 휴대용 사용자모델 입구
            Box(
                Modifier
                    .size(38.dp).clip(CircleShape)
                    .background(Surface1).border(BorderStroke(1.dp, Stroke), CircleShape)
                    .clickable { showAi = true },
                contentAlignment = Alignment.Center
            ) { Text("✦", color = Accent, fontSize = 16.sp) }
        }
        Spacer(Modifier.height(36.dp))

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Spaces", color = T1, fontSize = 20.sp, fontFamily = Grotesk,
                fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            PulseDot(Accent)
            Spacer(Modifier.width(7.dp))
            Text("Scanning", color = T3, fontSize = 12.sp, fontFamily = Inter)
        }
        if (status.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(status, color = Warn, fontSize = 12.sp, fontFamily = Inter)
        }
        Spacer(Modifier.height(14.dp))

        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(spaces, key = { it.serviceName }) { sp ->
                SpaceCard(sp, busy = connecting == sp.serviceName) { vm.connect(sp) }
            }
        }
        if (spaces.isEmpty() && quietHint) {
            Spacer(Modifier.height(28.dp))
            Text("Join the space's Wi-Fi to find it", color = T3, fontSize = 12.sp,
                fontFamily = Inter, modifier = Modifier.align(Alignment.CenterHorizontally))
        }
    }

    if (showAi) MyAiSheet(vm) { showAi = false }
}

@Composable
fun SpaceCard(sp: DiscoveredSpace, busy: Boolean, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth(), onClick = onClick) {
        Row(
            Modifier.padding(horizontal = 20.dp, vertical = 18.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(sp.place, color = T1, fontSize = 17.sp, fontFamily = Grotesk,
                    fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    sp.caps.split(",").filter { it.isNotBlank() }
                        .forEach { CapIcon(it.trim(), T3, 15) }
                }
            }
            if (busy) CircularProgressIndicator(
                Modifier.size(18.dp), color = Accent, strokeWidth = 2.dp,
                trackColor = Color.Transparent,
            )
            else Text("›", color = Accent, fontSize = 22.sp)
        }
    }
}

/* ───────────────────────── My AI (복리효과 가시화) ───────────────────────── */

@Composable
fun MyAiSheet(vm: ByoaiViewModel, onClose: () -> Unit) {
    val p by vm.profile.collectAsStateWithLifecycle()
    ModalBottomSheet(onDismissRequest = onClose, containerColor = Surface2) {
        Column(Modifier.padding(horizontal = 26.dp).padding(bottom = 44.dp)) {
            Text("My AI", color = T1, fontSize = 21.sp, fontFamily = Grotesk,
                fontWeight = FontWeight.SemiBold)
            Text("travels with you", color = T3, fontSize = 12.sp, fontFamily = Inter)
            Spacer(Modifier.height(22.dp))
            ProfileRow("light", "Light", "${p.lightPct}%")
            ProfileRow("climate", "Warmth", "${if (p.warmth >= 0) "+" else ""}${p.warmth}°")
            ProfileRow("air_quality", "Air limit", "${p.airMax}")
            Spacer(Modifier.height(18.dp))
            HorizontalDivider(color = StrokeLo)
            Spacer(Modifier.height(14.dp))
            Text("${p.corrections} corrections · ${p.spaces} spaces",
                color = T3, fontSize = 12.sp, fontFamily = Inter)
        }
    }
}

@Composable
private fun ProfileRow(kind: String, label: String, value: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        CapIcon(kind, T2)
        Spacer(Modifier.width(14.dp))
        Text(label, color = T2, fontSize = 15.sp, fontFamily = Inter)
        Spacer(Modifier.weight(1f))
        Text(value, color = T1, fontSize = 17.sp, fontFamily = Grotesk,
            fontWeight = FontWeight.SemiBold)
    }
}

/* ───────────────────────── ②③ 공간 상세 ───────────────────────── */

@Composable
fun SpaceScreen(vm: ByoaiViewModel, desc: SpaceDescriptor) {
    val thinking by vm.thinking.collectAsStateWithLifecycle()
    val reason by vm.reason.collectAsStateWithLifecycle()
    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = 22.dp)
            .padding(top = 52.dp)
    ) {
        Text("‹ Spaces", color = T2, fontSize = 14.sp, fontFamily = Inter,
            modifier = Modifier.clickable { vm.disconnect() }.padding(4.dp))
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(desc.place, color = T1, fontSize = 25.sp, fontFamily = Grotesk,
                fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            AiAutoChip(thinking) { vm.optimize() }
        }
        Spacer(Modifier.height(6.dp))
        // 공간 컨텍스트 한 줄 (descriptor 활용)
        Row(verticalAlignment = Alignment.CenterVertically) {
            desc.outsideTemp?.let {
                Text("Outside ${it}°", color = T3, fontSize = 12.sp, fontFamily = Inter)
                Spacer(Modifier.width(12.dp))
            }
            if (desc.present) {
                Box(Modifier.size(5.dp).background(Accent, CircleShape))
                Spacer(Modifier.width(6.dp))
                Text("Occupied", color = T3, fontSize = 12.sp, fontFamily = Inter)
            }
        }
        // 결정 이유 — 투명성 원칙: "왜 바뀌었는지" 한 줄
        AnimatedVisibility(visible = reason != null) {
            Column {
                Spacer(Modifier.height(8.dp))
                Text(reason ?: "", color = T3, fontSize = 12.sp, fontFamily = Inter, maxLines = 2)
            }
        }
        Spacer(Modifier.height(18.dp))

        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(desc.capabilities.filter { it.kind != "occupancy" }, key = { it.kind }) { c ->
                when (c.kind) {
                    "light" -> LightCard(c) { to -> vm.manualOverride(c.kind, c.target, to) }
                    "climate" -> HeatCard(c) { to -> vm.manualOverride(c.kind, c.target, to) }
                    "air_quality" -> AirCard(c) { on -> vm.airToggle(on) }
                }
            }
            item { Spacer(Modifier.height(28.dp)) }
        }
    }
}

/** AI Auto 칩 — 모드 토글이 아니라 "결정" 트리거. 진행은 칩 안에서 보임. */
@Composable
fun AiAutoChip(thinking: Boolean, onClick: () -> Unit) {
    val haptic = LocalHapticFeedback.current
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(CircleShape)
            .background(Surface1)
            .border(BorderStroke(1.dp, Stroke), CircleShape)
            .clickable(enabled = !thinking) {
                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                onClick()
            }
            .padding(horizontal = 14.dp, vertical = 9.dp)
    ) {
        PulseDot(Accent, 7, periodMs = if (thinking) 320 else 900)
        Spacer(Modifier.width(8.dp))
        Text(if (thinking) "Thinking" else "AI Auto", color = T1, fontSize = 13.sp,
            fontFamily = Grotesk, fontWeight = FontWeight.SemiBold)
        if (!thinking) {
            Spacer(Modifier.width(8.dp))
            Text("↻", color = Accent, fontSize = 14.sp)
        }
    }
}

@Composable
private fun CardHeader(c: Capability, label: String, value: String, valueColor: Color = Accent) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CapIcon(c.kind, T2)
        Spacer(Modifier.width(12.dp))
        Text(label, color = T1, fontSize = 16.sp, fontFamily = Inter, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.weight(1f))
        Text(value, color = valueColor, fontSize = 21.sp, fontFamily = Grotesk,
            fontWeight = FontWeight.Bold)
    }
}

private val sliderColors
    @Composable get() = SliderDefaults.colors(
        thumbColor = T1, activeTrackColor = Accent,
        inactiveTrackColor = Color.White.copy(alpha = 0.10f),
    )

/** 드래그 중엔 손을, 평소엔 목표값을 따라가는 슬라이더 상태 (AI 결정 시 부드럽게 이동). */
@Composable
private fun rememberSliderValue(target: Float): Triple<Float, (Float) -> Unit, (() -> Float)> {
    var dragging by remember { mutableStateOf(false) }
    var dragVal by remember { mutableFloatStateOf(target) }
    var optimistic by remember { mutableStateOf<Float?>(null) }
    val anim by animateFloatAsState(target, tween(400), label = "v")
    LaunchedEffect(target) { optimistic = null }   // 서버 목표 반영되면 낙관값 해제
    val shown = if (dragging) dragVal else (optimistic ?: anim)
    return Triple(shown, { v -> dragging = true; dragVal = v },
        { dragging = false; optimistic = dragVal; dragVal })
}

/** Light — 퍼센트 표시·조작 (프로토콜은 lux, UI에서 변환). */
@Composable
fun LightCard(c: Capability, onTarget: (Double) -> Unit) {
    val span = (c.max - c.min).takeIf { it > 0 } ?: 1.0
    val targetPct = (((c.target ?: c.current ?: c.min) - c.min) / span * 100)
        .toFloat().coerceIn(0f, 100f)
    val (shown, onDrag, onRelease) = rememberSliderValue(targetPct)
    val haptic = LocalHapticFeedback.current
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            CardHeader(c, "Light", "${shown.roundToInt()}%")
            Slider(
                value = shown, onValueChange = onDrag,
                onValueChangeFinished = {
                    haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                    onTarget(c.min + onRelease() / 100.0 * span)
                },
                valueRange = 0f..100f, colors = sliderColors,
            )
        }
    }
}

/** Heat — °C 직접 표시. */
@Composable
fun HeatCard(c: Capability, onTarget: (Double) -> Unit) {
    val target = (c.target ?: c.current ?: c.min).toFloat()
    val (shown, onDrag, onRelease) = rememberSliderValue(target)
    val haptic = LocalHapticFeedback.current
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            CardHeader(c, "Heat", "${shown.roundToInt()}°")
            Slider(
                value = shown, onValueChange = onDrag,
                onValueChangeFinished = {
                    haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                    onTarget(onRelease().toDouble())
                },
                valueRange = c.min.toFloat()..c.max.toFloat(), colors = sliderColors,
            )
        }
    }
}

/** Air — 등급(Good/Fair/Bad/Danger) + 청정 on/off 토글. 등급색은 크로스페이드. */
@Composable
fun AirCard(c: Capability, onToggle: (Boolean) -> Unit) {
    val pm = c.current ?: 0.0
    val (grade, gradeColor) = when {
        pm <= 30 -> "Good" to Good
        pm <= 80 -> "Fair" to T2
        pm <= 150 -> "Bad" to Warn
        else -> "Danger" to Danger
    }
    val color by animateColorAsState(gradeColor, tween(500), label = "grade")
    var on by remember(c.target != null) { mutableStateOf(c.target != null) }
    Card(Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(horizontal = 20.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            CapIcon(c.kind, T2)
            Spacer(Modifier.width(12.dp))
            Text("Air", color = T1, fontSize = 16.sp, fontFamily = Inter, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Box(Modifier.size(7.dp).background(color, CircleShape))
            Spacer(Modifier.width(8.dp))
            Text(grade, color = color, fontSize = 15.sp, fontFamily = Grotesk,
                fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.width(14.dp))
            Switch(
                checked = on,
                onCheckedChange = { on = it; onToggle(it) },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = T1, checkedTrackColor = Accent.copy(alpha = 0.55f),
                    uncheckedThumbColor = T3, uncheckedTrackColor = Color.White.copy(alpha = 0.08f),
                    uncheckedBorderColor = Stroke,
                ),
            )
        }
    }
}
