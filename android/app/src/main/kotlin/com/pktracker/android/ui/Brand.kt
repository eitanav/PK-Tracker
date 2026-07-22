package com.pktracker.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.pktracker.android.ui.theme.Accent
import com.pktracker.engine.Substance

/** The active substance's accent colour, provided app-wide and animated on change. */
val LocalAccent = compositionLocalOf { Accent }

fun accentColorFor(sub: Substance): Color =
    runCatching { Color(android.graphics.Color.parseColor(sub.color)) }.getOrDefault(Accent)

/**
 * The PK Tracker mark: the pharmacokinetic curve itself — absorption, peak,
 * clearance — inside a rounded badge. Re-tints to [accent].
 */
@Composable
fun PkLogo(size: Dp, accent: Color, modifier: Modifier = Modifier, badge: Boolean = true) {
    val badgeColor = MaterialTheme.colorScheme.surface
    val border = MaterialTheme.colorScheme.outlineVariant
    Canvas(modifier.size(size)) {
        val s = this.size.minDimension
        val k = s / 48f
        fun x(v: Float) = v * k
        if (badge) {
            drawRoundRect(
                color = badgeColor,
                cornerRadius = CornerRadius(x(12f), x(12f)),
                size = Size(s, s),
            )
            drawRoundRect(
                color = border,
                cornerRadius = CornerRadius(x(12f), x(12f)),
                size = Size(s, s),
                style = Stroke(x(1f)),
            )
        }
        val curve = Path().apply {
            moveTo(x(8f), x(35f))
            cubicTo(x(14f), x(35f), x(16f), x(15f), x(23f), x(14f))
            cubicTo(x(31f), x(13f), x(35f), x(26f), x(41f), x(30f))
        }
        val area = Path().apply {
            addPath(curve)
            lineTo(x(41f), x(39f))
            lineTo(x(8f), x(39f))
            close()
        }
        drawPath(area, accent.copy(alpha = 0.20f))
        drawPath(curve, accent, style = Stroke(x(2.6f), cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawCircle(accent, radius = x(3.1f), center = Offset(x(23f), x(14f)))
    }
}
