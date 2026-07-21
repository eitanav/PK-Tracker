package com.pktracker.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// ---- palette (mirrors the desktop app) --------------------------------------
val Accent = Color(0xFFD6A04A)      // caffeine amber
val Blue = Color(0xFF4AA3FF)        // effect
val Danger = Color(0xFFE5534B)
val Warn = Color(0xFFD6A04A)
val Good = Color(0xFF5AD6B0)

private val DarkBg = Color(0xFF0F141A)
private val DarkSurface = Color(0xFF1A222C)
private val DarkSurfaceHi = Color(0xFF222C38)
private val DarkText = Color(0xFFE6EDF3)
private val DarkMuted = Color(0xFF8B98A6)
private val DarkBorder = Color(0xFF2A3644)

private val LightBg = Color(0xFFF4F6FA)
private val LightSurface = Color(0xFFFFFFFF)
private val LightSurfaceHi = Color(0xFFEDF1F6)
private val LightText = Color(0xFF16202B)
private val LightMuted = Color(0xFF5B6875)
private val LightBorder = Color(0xFFD6DEE7)

private val DarkColors = darkColorScheme(
    primary = Accent,
    onPrimary = Color(0xFF201607),
    secondary = Blue,
    onSecondary = Color(0xFF06121F),
    background = DarkBg,
    onBackground = DarkText,
    surface = DarkSurface,
    onSurface = DarkText,
    surfaceVariant = DarkSurfaceHi,
    onSurfaceVariant = DarkMuted,
    error = Danger,
    onError = Color(0xFF2A0A08),
    outline = DarkBorder,
    outlineVariant = DarkBorder,
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF9A6E1E),
    onPrimary = Color(0xFFFFFFFF),
    secondary = Color(0xFF1E6FCB),
    onSecondary = Color(0xFFFFFFFF),
    background = LightBg,
    onBackground = LightText,
    surface = LightSurface,
    onSurface = LightText,
    surfaceVariant = LightSurfaceHi,
    onSurfaceVariant = LightMuted,
    error = Color(0xFFC0392B),
    onError = Color(0xFFFFFFFF),
    outline = LightBorder,
    outlineVariant = LightBorder,
)

@Composable
fun PKTrackerTheme(darkTheme: Boolean, content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = Typography(),
        content = content,
    )
}
