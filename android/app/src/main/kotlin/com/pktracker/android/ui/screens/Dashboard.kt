@file:OptIn(
    androidx.compose.material3.ExperimentalMaterial3Api::class,
    androidx.compose.foundation.layout.ExperimentalLayoutApi::class,
)

package com.pktracker.android.ui.screens

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowLeft
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pktracker.android.ActionKind
import com.pktracker.android.AppViewModel
import com.pktracker.android.DashboardState
import com.pktracker.android.R
import com.pktracker.android.ui.SectionCard
import com.pktracker.android.ui.TimelineChart
import com.pktracker.android.ui.colorForKey
import com.pktracker.android.ui.fmtClock
import com.pktracker.android.ui.sinceLabel
import com.pktracker.android.ui.substanceName
import com.pktracker.android.ui.theme.Blue
import com.pktracker.android.ui.theme.Danger
import com.pktracker.android.ui.theme.Warn
import kotlinx.coroutines.delay
import kotlin.math.roundToInt

private fun parseColor(hex: String, fallback: Color): Color =
    runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(fallback)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val state by vm.state.collectAsStateWithLifecycle()
    val simOn by vm.simOn.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val s = state

    LazyColumn(
        modifier = modifier.fillMaxSize().padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Spacer(Modifier.height(4.dp)) }

        // substance selector
        item {
            val scroll = rememberScrollState()
            Row(Modifier.horizontalScroll(scroll), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                vm.substances.forEach { sub ->
                    FilterChip(
                        selected = settings.activeSubstanceId == sub.id,
                        onClick = { vm.setActive(sub.id) },
                        label = { Text(substanceName(sub)) },
                    )
                }
            }
        }

        if (s == null) {
            item { Text(stringResource(R.string.no_doses), color = MaterialTheme.colorScheme.onSurfaceVariant) }
        } else {
            item { StatusCard(s) }
            item { ChartCard(s, simOn, vm, settings.simMg, settings.simInMin, settings.graphWindowH) }
            item { LogCard(s, vm) }
            if (s.redoseEligible) {
                item { SleepCard(s) }
                item { TimingCard(s, vm) }
            }
            if (s.alcohol != null) item { AlcoholCard(s) }
            item {
                Text(
                    stringResource(R.string.disclaimer),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
        }
        item { Spacer(Modifier.height(8.dp)) }
    }
}

@Composable
private fun StatusCard(s: DashboardState) {
    val accent = parseColor(s.substance.color, MaterialTheme.colorScheme.primary)
    SectionCard {
        Text(substanceName(s.substance), style = MaterialTheme.typography.titleMedium, color = accent, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        val bigColor = if (s.overloadOver) Warn else accent
        if (s.bodyMg != null) {
            Text(
                "${s.bodyMg.roundToInt()} ${stringResource(R.string.mg)}",
                fontSize = 34.sp, fontWeight = FontWeight.Bold, color = bigColor, fontFamily = FontFamily.Monospace,
            )
            val caption = if (s.overloadThresholdMg != null)
                "${stringResource(R.string.in_body)} · ${stringResource(R.string.jitter_zone, s.overloadThresholdMg.roundToInt())}"
            else stringResource(R.string.in_body)
            Text(caption, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Text(
                String.format(java.util.Locale.US, "%.3f", s.concValue),
                fontSize = 34.sp, fontWeight = FontWeight.Bold, color = bigColor, fontFamily = FontFamily.Monospace,
            )
            Text("${stringResource(R.string.current_level)} · ${s.concUnit}",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(10.dp))
        ReadoutRow(stringResource(R.string.blood_level), String.format(java.util.Locale.US, "%.3f %s", s.concValue, s.concUnit))
        ReadoutRow(stringResource(R.string.since_last), sinceLabel(s.sinceLastMs, s.nowMs))
        ReadoutRow(stringResource(R.string.projected_peak), fmtClock(s.projectedPeakMs))
        s.effectPct?.let { ReadoutRow(stringResource(R.string.effect), stringResource(R.string.of_recent_peak, it.roundToInt())) }
        if (s.dailyMg > 0) {
            val gl = s.dailyGuidelineMg
            val txt = if (gl != null) "${s.dailyMg.roundToInt()} / ${gl.roundToInt()} ${stringResource(R.string.mg)}"
            else "${s.dailyMg.roundToInt()} ${stringResource(R.string.mg)}"
            val col = when {
                gl != null && s.dailyMg >= gl -> Danger
                gl != null && s.dailyMg >= 0.8 * gl -> Warn
                else -> null
            }
            ReadoutRow(stringResource(R.string.today), txt, col)
        }
        s.nextAction?.let { na ->
            Spacer(Modifier.height(8.dp))
            Text(actionText(na.kind, na.timeMs), color = colorForKey(na.colorKey), fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun ReadoutRow(label: String, value: String, valueColor: Color? = null) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium, fontFamily = FontFamily.Monospace,
            color = valueColor ?: MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun actionText(kind: ActionKind, timeMs: Long?): String = when (kind) {
    ActionKind.REDOSE_NOW -> "${stringResource(R.string.redose)} ${stringResource(R.string.redose_now)}"
    ActionKind.REDOSE_AT -> stringResource(R.string.redose_at, fmtClock(timeMs))
    ActionKind.PEAK_AT -> stringResource(R.string.peak_at, fmtClock(timeMs))
    ActionKind.SOBER -> "${stringResource(R.string.sober)}"
    ActionKind.SOBER_AT -> stringResource(R.string.sober_at, fmtClock(timeMs))
    ActionKind.UNDER_LIMIT_AT -> stringResource(R.string.under_limit_at, fmtClock(timeMs))
    ActionKind.CLEARING -> stringResource(R.string.clearing)
    ActionKind.NONE -> ""
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ChartCard(s: DashboardState, simOn: Boolean, vm: AppViewModel, simMg: Int, simInMin: Int, graphWindowH: Int) {
    val curve = s.curve
    val minC = curve.xHours.first() + curve.windowH / 2.0
    val maxC = curve.xHours.last() - curve.windowH / 2.0
    val lo = minOf(minC, maxC)
    val hi = maxOf(minC, maxC)
    var centerH by remember(s.substance.id, graphWindowH) {
        mutableStateOf((curve.nowHours + curve.windowH * 0.15).coerceIn(lo, hi))
    }
    fun setCenter(c: Double) { centerH = c.coerceIn(lo, hi) }

    SectionCard {
        TimelineChart(
            curve = curve,
            centerH = centerH,
            onPan = { setCenter(centerH + it) },
            modifier = Modifier.fillMaxWidth().height(220.dp),
            description = stringResource(R.string.chart_timeline),
        )
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            LegendDot(parseColor(s.substance.color, MaterialTheme.colorScheme.primary), stringResource(R.string.blood_level))
            Spacer(Modifier.width(12.dp))
            if (s.effectPct != null) LegendDot(Blue, stringResource(R.string.effect))
            Spacer(Modifier.weight(1f))
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { setCenter(centerH - curve.windowH * 0.5) }) {
                        Icon(Icons.Filled.KeyboardArrowLeft, contentDescription = stringResource(R.string.graph_pan_back))
                    }
                    IconButton(onClick = { setCenter(curve.nowHours + curve.windowH * 0.15) }) {
                        Icon(Icons.Filled.Refresh, contentDescription = stringResource(R.string.graph_now))
                    }
                    IconButton(onClick = { setCenter(centerH + curve.windowH * 0.5) }) {
                        Icon(Icons.Filled.KeyboardArrowRight, contentDescription = stringResource(R.string.graph_pan_forward))
                    }
                }
            }
        }
        Text(
            "${stringResource(R.string.legend_solid)} · ${stringResource(R.string.legend_dashed)}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (s.redoseEligible) {
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(checked = simOn, onCheckedChange = { vm.setSim(it) })
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.sim_dose))
                Spacer(Modifier.width(12.dp))
                Stepper(simMg, { vm.updateSettings { simMg(it) } }, 10, 10..1000, " ${stringResource(R.string.mg)}")
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.sim_in))
                Spacer(Modifier.width(6.dp))
                Stepper(simInMin, { vm.updateSettings { simInMin(it) } }, 15, 0..1440, " ${stringResource(R.string.minutes_short)}")
            }
        }
    }
}

@Composable
private fun LegendDot(color: Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.width(10.dp).height(10.dp).padding(1.dp)) {
            androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) { drawCircle(color) }
        }
        Spacer(Modifier.width(6.dp))
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LogCard(s: DashboardState, vm: AppViewModel) {
    var minAgo by rememberSaveable { mutableIntStateOf(0) }
    var amount by rememberSaveable { mutableStateOf("") }
    var feedback by remember { mutableStateOf("") }
    LaunchedEffect(feedback) { if (feedback.isNotEmpty()) { delay(3000); feedback = "" } }

    SectionCard(title = stringResource(R.string.log_a_dose)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.minutes_ago) + ":", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.width(8.dp))
            Stepper(minAgo, { minAgo = it }, 15, 0..1440, "")
        }
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            s.substance.presets.forEach { p ->
                OutlinedButton(onClick = {
                    vm.logDose(s.substance, p.amount, minAgo)
                    feedback = "✓ ${p.label}"
                }) {
                    Text("${p.label} · ${p.amount.roundToInt()} ${s.substance.unit}", maxLines = 1)
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = amount,
                onValueChange = { amount = it.filter { c -> c.isDigit() || c == '.' } },
                modifier = Modifier.width(130.dp),
                singleLine = true,
                label = { Text(stringResource(R.string.custom_amount)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )
            Spacer(Modifier.width(10.dp))
            Button(onClick = {
                val v = amount.toDoubleOrNull()
                if (v != null && v > 0) {
                    vm.logDose(s.substance, v, minAgo)
                    feedback = "✓ ${v.roundToInt()} ${s.substance.unit}"
                    amount = ""
                }
            }) { Text(stringResource(R.string.log)) }
        }
        if (feedback.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            Text(feedback, color = MaterialTheme.colorScheme.primary)
        }
    }
}

@Composable
private fun SleepCard(s: DashboardState) {
    val sleep = s.sleep ?: return
    SectionCard(title = stringResource(R.string.sleep_cutoff)) {
        val name = substanceName(s.substance)
        if (sleep.feasible && sleep.cutoffMs != null) {
            Text(stringResource(R.string.latest_caffeine, name, fmtClock(sleep.cutoffMs)),
                color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            val detail = if (sleep.mode == "hours")
                stringResource(R.string.sleep_flat, sleep.hours, fmtClock(sleep.bedtimeMs))
            else stringResource(R.string.sleep_keeps_below, name, sleep.targetMg, fmtClock(sleep.bedtimeMs))
            Text(detail, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Text(stringResource(R.string.no_more_before_bed, name),
                color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            if (sleep.mode != "hours" && sleep.overAlready) {
                Text(stringResource(R.string.sleep_already_over, sleep.existingMg.roundToInt(), fmtClock(sleep.bedtimeMs), sleep.targetMg),
                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Spacer(Modifier.height(4.dp))
        val config = if (sleep.mode == "hours")
            stringResource(R.string.sleep_config_hours, fmtClock(sleep.bedtimeMs), sleep.hours)
        else stringResource(R.string.sleep_config_mg, fmtClock(sleep.bedtimeMs), sleep.targetMg)
        Text(config, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun TimingCard(s: DashboardState, vm: AppViewModel) {
    val t = s.timing ?: return
    val settings by vm.settings.collectAsStateWithLifecycle()
    SectionCard(title = stringResource(R.string.perfect_timing)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.be_sharp_at) + " ", color = MaterialTheme.colorScheme.onSurfaceVariant)
            TimeButton(settings.timingTarget) { vm.updateSettings { timingTarget(it) } }
            Spacer(Modifier.width(10.dp))
            Stepper(settings.timingMg, { vm.updateSettings { timingMg(it) } }, 10, 10..400, " ${stringResource(R.string.mg)}")
        }
        Spacer(Modifier.height(6.dp))
        if (t.feasible && t.doseTimeMs != null) {
            Text(stringResource(R.string.timing_drink, t.mg, fmtClock(t.doseTimeMs)),
                color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(2.dp))
            val note = stringResource(R.string.timing_peaks, fmtClock(t.targetMs), t.bodyMg.roundToInt()) +
                when (t.withinCutoff) {
                    true -> "  " + stringResource(R.string.timing_within)
                    false -> "  " + stringResource(R.string.timing_after, fmtClock(s.sleep?.cutoffMs))
                    null -> ""
                }
            Text(note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Text(stringResource(R.string.timing_drink_now, t.mg),
                color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun AlcoholCard(s: DashboardState) {
    val a = s.alcohol ?: return
    SectionCard(title = stringResource(R.string.bac)) {
        if (a.bacNow <= 0) {
            Text(stringResource(R.string.alcohol_sober), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Text(stringResource(R.string.alcohol_bac, String.format(java.util.Locale.US, "%.3f", a.bacNow)),
                fontWeight = FontWeight.SemiBold)
            if (a.overLimit) Text(stringResource(R.string.alcohol_below_limit,
                String.format(java.util.Locale.US, "%.2f", a.limit), fmtClock(a.underLimitMs)),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(stringResource(R.string.alcohol_zero, fmtClock(a.zeroMs)), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(stringResource(R.string.alcohol_warn), style = MaterialTheme.typography.bodySmall, color = Warn)
        }
    }
}

@Composable
fun Stepper(value: Int, onChange: (Int) -> Unit, step: Int, range: IntRange, suffix: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedButton(
            onClick = { onChange((value - step).coerceIn(range.first, range.last)) },
            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
            modifier = Modifier.width(38.dp).height(38.dp),
        ) { Text("−") }
        Text("$value$suffix", modifier = Modifier.padding(horizontal = 8.dp), fontFamily = FontFamily.Monospace)
        OutlinedButton(
            onClick = { onChange((value + step).coerceIn(range.first, range.last)) },
            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
            modifier = Modifier.width(38.dp).height(38.dp),
        ) { Text("+") }
    }
}

@Composable
fun TimeButton(current: String, onPicked: (String) -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    OutlinedButton(onClick = {
        val parts = current.split(":")
        val h = parts.getOrNull(0)?.toIntOrNull() ?: 23
        val m = parts.getOrNull(1)?.toIntOrNull() ?: 0
        android.app.TimePickerDialog(context, { _, hh, mm ->
            onPicked(String.format(java.util.Locale.US, "%02d:%02d", hh, mm))
        }, h, m, true).show()
    }) { Text(current) }
}
