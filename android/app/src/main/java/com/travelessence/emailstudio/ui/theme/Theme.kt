package com.travelessence.emailstudio.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

@Immutable
data class Tones(
    val success: Color,
    val successSoft: Color,
    val danger: Color,
    val dangerSoft: Color,
    val warning: Color,
    val warningSoft: Color,
    val accentSoft: Color,
    val muted: Color,
    val border: Color,
    val gradientStart: Color,
    val gradientEnd: Color,
)

private val LightTones = Tones(
    success = Color(0xFF15803D), successSoft = Color(0xFFE6F6EC),
    danger = Color(0xFFDC2626), dangerSoft = Color(0xFFFDECEC),
    warning = Color(0xFFB45309), warningSoft = Color(0xFFFEF3E2),
    accentSoft = Color(0xFFE2F3F6), muted = Color(0xFF64748B), border = Color(0xFFE2E8F0),
    gradientStart = Color(0xFF0B7A8F), gradientEnd = Color(0xFF14B8C9),
)

private val DarkTones = Tones(
    success = Color(0xFF34C77B), successSoft = Color(0xFF11301F),
    danger = Color(0xFFF05252), dangerSoft = Color(0xFF3A1A20),
    warning = Color(0xFFF5A524), warningSoft = Color(0xFF3A2A12),
    accentSoft = Color(0xFF11303B), muted = Color(0xFF8B9AB1), border = Color(0xFF1F2B40),
    gradientStart = Color(0xFF1597AD), gradientEnd = Color(0xFF3CC7DC),
)

val LocalTones = staticCompositionLocalOf { LightTones }

private val LightColors = lightColorScheme(
    primary = Color(0xFF0B7A8F),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFCFEFF4),
    onPrimaryContainer = Color(0xFF00363F),
    secondary = Color(0xFF4A6268),
    secondaryContainer = Color(0xFFE2F3F6),
    onSecondaryContainer = Color(0xFF0B3A44),
    tertiary = Color(0xFFE0A526),
    background = Color(0xFFF2F5F9),
    onBackground = Color(0xFF0F172A),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF0F172A),
    surfaceVariant = Color(0xFFF1F5F9),
    onSurfaceVariant = Color(0xFF64748B),
    surfaceContainer = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFF7F9FC),
    surfaceContainerHigh = Color(0xFFF1F5F9),
    outline = Color(0xFFCBD5E1),
    outlineVariant = Color(0xFFE2E8F0),
    error = Color(0xFFDC2626),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF3CC7DC),
    onPrimary = Color(0xFF00363F),
    primaryContainer = Color(0xFF0E4D5A),
    onPrimaryContainer = Color(0xFFCFEFF4),
    secondary = Color(0xFFB1CBD1),
    secondaryContainer = Color(0xFF13303A),
    onSecondaryContainer = Color(0xFFCFEFF4),
    tertiary = Color(0xFFF0B840),
    background = Color(0xFF0A101B),
    onBackground = Color(0xFFE6ECF5),
    surface = Color(0xFF111A29),
    onSurface = Color(0xFFE6ECF5),
    surfaceVariant = Color(0xFF162133),
    onSurfaceVariant = Color(0xFF8B9AB1),
    surfaceContainer = Color(0xFF111A29),
    surfaceContainerLow = Color(0xFF0E1522),
    surfaceContainerHigh = Color(0xFF162133),
    outline = Color(0xFF2C3B55),
    outlineVariant = Color(0xFF1F2B40),
    error = Color(0xFFF05252),
)

private val AppTypography = Typography().let { t ->
    t.copy(
        headlineMedium = t.headlineMedium.copy(fontWeight = FontWeight.Bold, fontSize = 26.sp),
        headlineSmall = t.headlineSmall.copy(fontWeight = FontWeight.Bold),
        titleLarge = t.titleLarge.copy(fontWeight = FontWeight.Bold),
        titleMedium = t.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.6.sp),
    )
}

@Composable
fun isDark(themeSetting: String): Boolean = when (themeSetting) {
    "dark" -> true
    "light" -> false
    else -> isSystemInDarkTheme()
}

@Composable
fun TravelEssenceTheme(dark: Boolean, content: @Composable () -> Unit) {
    androidx.compose.runtime.CompositionLocalProvider(LocalTones provides if (dark) DarkTones else LightTones) {
        MaterialTheme(colorScheme = if (dark) DarkColors else LightColors, typography = AppTypography, content = content)
    }
}
