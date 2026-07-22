package com.pktracker.android.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.pktracker.android.CurveData
import com.pktracker.android.ui.theme.Accent
import com.pktracker.android.ui.theme.Blue
import com.pktracker.android.ui.theme.Warn
import java.util.Locale

private fun interp(xs: DoubleArray, ys: DoubleArray, x: Double): Double {
    if (xs.isEmpty()) return 0.0
    if (x <= xs.first()) return ys.first()
    if (x >= xs.last()) return ys.last()
    var i = 1
    while (i < xs.size && xs[i] < x) i++
    val x0 = xs[i - 1]; val x1 = xs[i]
    val t = if (x1 == x0) 0.0 else (x - x0) / (x1 - x0)
    return ys[i - 1] + t * (ys[i] - ys[i - 1])
}

private fun fmtLevel(v: Double): String = when {
    v >= 10 -> String.format(Locale.US, "%.0f", v)
    v >= 1 -> String.format(Locale.US, "%.1f", v)
    else -> String.format(Locale.US, "%.2f", v)
}

/**
 * Interactive concentration/effect chart. Shows a [CurveData.windowH]-wide slice
 * of a broader precomputed curve; [centerH] is the hour at the centre of the
 * visible window. Drag the plot (or drive [onPan] from arrow buttons) to move
 * through past and future; tap to read the value at a point.
 */
@Composable
fun TimelineChart(
    curve: CurveData,
    centerH: Double,
    onPan: (Double) -> Unit,
    modifier: Modifier = Modifier,
    description: String? = null,
) {
    val onSurface = MaterialTheme.colorScheme.onSurface
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val grid = muted.copy(alpha = 0.14f)
    val panel = MaterialTheme.colorScheme.surface
    val levelColor = remember(curve.colorHex) {
        runCatching { Color(android.graphics.Color.parseColor(curve.colorHex)) }.getOrDefault(Accent)
    }
    var touchX by remember { mutableStateOf<Float?>(null) }
    val currentOnPan by rememberUpdatedState(onPan)
    val hasEffect = curve.effect != null

    Canvas(
        modifier = modifier
            .then(if (description != null) Modifier.semantics { contentDescription = description } else Modifier)
            .pointerInput(curve.windowH) {
                val leftAxisPx = 40.dp.toPx()
                val rightAxisPx = 30.dp.toPx()
                detectDragGestures(
                    onDragStart = { touchX = null },
                    onDrag = { change, dragAmount ->
                        val plotW = (size.width - leftAxisPx - rightAxisPx).coerceAtLeast(1f)
                        currentOnPan(-(dragAmount.x / plotW) * curve.windowH)
                        change.consume()
                    },
                )
            }
            .pointerInput(Unit) {
                detectTapGestures(onTap = { touchX = it.x })
            },
    ) {
        if (curve.xHours.size < 2) return@Canvas

        val leftAxis = 40.dp.toPx()
        val rightAxis = 30.dp.toPx()
        val bottomAxis = 22.dp.toPx()
        val topPad = 12.dp.toPx()
        val plotLeft = leftAxis
        val plotRight = size.width - rightAxis
        val plotTop = topPad
        val plotBottom = size.height - bottomAxis
        val plotW = plotRight - plotLeft
        val plotH = plotBottom - plotTop

        // Visible window, clamped to the available data range.
        val dataMin = curve.xHours.first()
        val dataMax = curve.xHours.last()
        val half = curve.windowH / 2.0
        var viewStart = centerH - half
        var viewEnd = centerH + half
        if (viewStart < dataMin) { viewStart = dataMin; viewEnd = minOf(dataMax, viewStart + curve.windowH) }
        if (viewEnd > dataMax) { viewEnd = dataMax; viewStart = maxOf(dataMin, viewEnd - curve.windowH) }
        val span = if (viewEnd == viewStart) 1.0 else viewEnd - viewStart

        fun sx(h: Double): Float = plotLeft + ((h - viewStart) / span * plotW).toFloat()
        val n = curve.xHours.size
        val xs = FloatArray(n) { sx(curve.xHours[it]) }
        fun mapLevel(v: Double): Float = plotBottom - (v / curve.concTop * plotH).toFloat().coerceIn(0f, plotH)
        fun mapEffect(v: Double): Float = plotBottom - (v / curve.effectTop * plotH).toFloat().coerceIn(0f, plotH)

        val dashed = PathEffect.dashPathEffect(floatArrayOf(14f, 12f), 0f)
        var nowIdx = curve.xHours.indexOfFirst { it >= curve.nowHours }
        if (nowIdx < 0) nowIdx = n - 1

        // Horizontal gridlines.
        for (i in 0..4) {
            val y = plotTop + plotH * i / 4
            drawLine(grid, Offset(plotLeft, y), Offset(plotRight, y), 1f)
        }

        fun drawSeries(mapY: (Double) -> Float, values: DoubleArray, color: Color, fill: Boolean, width: Float) {
            val ys = FloatArray(n) { mapY(values[it]) }
            if (fill && nowIdx >= 1) {
                val area = Path().apply {
                    moveTo(xs[0], plotBottom)
                    for (i in 0..nowIdx) lineTo(xs[i], ys[i])
                    lineTo(xs[nowIdx], plotBottom)
                    close()
                }
                drawPath(area, color.copy(alpha = 0.16f))
            }
            if (nowIdx >= 1) {
                val past = Path().apply {
                    moveTo(xs[0], ys[0])
                    for (i in 1..nowIdx) lineTo(xs[i], ys[i])
                }
                drawPath(past, color, style = Stroke(width))
            }
            if (nowIdx < n - 1) {
                val fut = Path().apply {
                    moveTo(xs[nowIdx], ys[nowIdx])
                    for (i in (nowIdx + 1) until n) lineTo(xs[i], ys[i])
                }
                drawPath(fut, color, style = Stroke(width, pathEffect = dashed))
            }
        }

        // Series and the "now" marker are clipped to the plot rectangle so a
        // panned curve never bleeds into the axis gutters.
        clipRect(plotLeft, plotTop, plotRight, plotBottom) {
            drawSeries(::mapLevel, curve.conc, levelColor, fill = true, width = 3.2f)
            curve.effect?.let { drawSeries(::mapEffect, it, Blue, fill = false, width = 2.6f) }
            curve.simConc?.let { drawSeries(::mapLevel, it, Warn, fill = false, width = 2.6f) }
            curve.simEffect?.let { drawSeries(::mapEffect, it, Warn, fill = false, width = 2.0f) }
            if (curve.nowHours in viewStart..viewEnd) {
                val nx = sx(curve.nowHours)
                drawLine(muted, Offset(nx, plotTop), Offset(nx, plotBottom), 1.4f, pathEffect = dashed)
            }
        }

        // Time axis labels across the visible range.
        val axisPaint = android.graphics.Paint().apply {
            color = muted.toArgb(); textSize = 10.dp.toPx(); isAntiAlias = true
            textAlign = android.graphics.Paint.Align.CENTER
        }
        for (i in 0..4) {
            val h = viewStart + span * i / 4
            drawContext.canvas.nativeCanvas.drawText(
                fmtClockHours(h), sx(h).coerceIn(plotLeft, plotRight), size.height - 6.dp.toPx(), axisPaint,
            )
        }

        // Left Y axis: blood level, aligned to the gridlines.
        val leftPaint = android.graphics.Paint().apply {
            color = levelColor.toArgb(); textSize = 9.dp.toPx(); isAntiAlias = true
            textAlign = android.graphics.Paint.Align.RIGHT
        }
        for (i in 0..4) {
            val value = curve.concTop * (1.0 - i / 4.0)
            val y = plotTop + plotH * i / 4 + 3.dp.toPx()
            drawContext.canvas.nativeCanvas.drawText(fmtLevel(value), plotLeft - 4.dp.toPx(), y, leftPaint)
        }
        drawContext.canvas.nativeCanvas.drawText(curve.concUnit, plotLeft - 2.dp.toPx(), plotTop - 2.dp.toPx(), leftPaint)

        // Right Y axis: effect, in % of recent peak.
        if (hasEffect) {
            val rightPaint = android.graphics.Paint().apply {
                color = Blue.toArgb(); textSize = 9.dp.toPx(); isAntiAlias = true
                textAlign = android.graphics.Paint.Align.LEFT
            }
            for (pct in intArrayOf(0, 25, 50, 75, 100)) {
                val y = plotBottom - (pct / curve.effectTop * plotH).toFloat().coerceIn(0f, plotH) + 3.dp.toPx()
                drawContext.canvas.nativeCanvas.drawText("$pct", plotRight + 3.dp.toPx(), y, rightPaint)
            }
            drawContext.canvas.nativeCanvas.drawText("%", plotRight + 3.dp.toPx(), plotTop - 2.dp.toPx(), rightPaint)
        }

        // Tap readout.
        touchX?.let { raw ->
            val clamped = raw.coerceIn(plotLeft, plotRight)
            val h = viewStart + (clamped - plotLeft) / plotW * span
            drawLine(onSurface.copy(alpha = 0.55f), Offset(clamped, plotTop), Offset(clamped, plotBottom), 1.2f)
            val lvl = interp(curve.xHours, curve.conc, h)
            val eff = curve.effect?.let { interp(curve.xHours, it, h) }
            val lines = buildList {
                add(fmtClockHours(h))
                add(String.format(Locale.US, "%.2f %s", lvl, curve.concUnit))
                if (eff != null) add("${eff.toInt()}%")
            }
            val textPaint = android.graphics.Paint().apply {
                color = onSurface.toArgb(); textSize = 11.dp.toPx(); isAntiAlias = true
            }
            val bgPaint = android.graphics.Paint().apply { color = panel.toArgb(); isAntiAlias = true }
            val pad = 6.dp.toPx()
            val lineH = 14.dp.toPx()
            val boxW = 82.dp.toPx()
            val boxH = lineH * lines.size + pad
            val boxX = (clamped + 8.dp.toPx()).coerceAtMost(plotRight - boxW)
            val boxY = plotTop
            drawContext.canvas.nativeCanvas.drawRoundRect(boxX, boxY, boxX + boxW, boxY + boxH, 8f, 8f, bgPaint)
            var ty = boxY + lineH
            for (ln in lines) {
                drawContext.canvas.nativeCanvas.drawText(ln, boxX + pad, ty, textPaint)
                ty += lineH
            }
        }
    }
}
