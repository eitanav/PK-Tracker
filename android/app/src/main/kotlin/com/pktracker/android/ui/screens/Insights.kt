package com.pktracker.android.ui.screens

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pktracker.android.AppViewModel
import com.pktracker.android.InsightsState
import com.pktracker.android.R
import com.pktracker.android.ui.LocalAccent
import com.pktracker.android.ui.SectionCard
import com.pktracker.android.ui.substanceName
import com.pktracker.engine.Substances
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.roundToInt

private val recentFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("EEE d MMM · HH:mm")
private fun hhmm(min: Int): String = "%02d:%02d".format(min / 60, min % 60)

@Composable
fun InsightsScreen(vm: AppViewModel, modifier: Modifier = Modifier) {
    val ins by vm.insights.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val doses by vm.doses.collectAsStateWithLifecycle()
    val sub = Substances.byId(settings.activeSubstanceId) ?: Substances.caffeine
    val accent = LocalAccent.current

    var grown by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { grown = true }
    val grow by animateFloatAsState(if (grown) 1f else 0f, tween(800), label = "grow")

    LazyColumn(
        modifier = modifier.fillMaxSize().padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Spacer(Modifier.height(4.dp)) }
        item {
            Row(Modifier.fillMaxWidth().padding(horizontal = 2.dp), verticalAlignment = Alignment.Bottom) {
                Text(stringResource(R.string.nav_insights), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(8.dp))
                Text("· ${substanceName(sub)}", style = MaterialTheme.typography.bodyMedium, color = accent)
                Spacer(Modifier.weight(1f))
                Text(stringResource(R.string.insights_window), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        if (!ins.hasData) {
            item {
                SectionCard { Text(stringResource(R.string.insights_empty), color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
        } else {
            item { WhenCard(ins, accent, grow) }
            item { WeeklyCard(ins, accent, grow) }
            item { AveragesCard(ins, sub.unit) }
        }

        item { RecentCard(doses, vm) }
        item { Spacer(Modifier.height(8.dp)) }
    }
}

@Composable
private fun WhenCard(ins: InsightsState, accent: Color, grow: Float) {
    SectionCard(title = stringResource(R.string.insights_when)) {
        val max = (ins.hourCounts.maxOrNull() ?: 0).coerceAtLeast(1)
        val dim = MaterialTheme.colorScheme.surfaceVariant
        Row(Modifier.fillMaxWidth().height(96.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            for (h in 0..23) {
                val frac = ins.hourCounts[h].toFloat() / max
                val hgt = (4f + 88f * frac * grow).dp
                val peak = h in ins.peakHours
                Box(
                    Modifier.weight(1f).height(hgt).clip(RoundedCornerShape(3.dp))
                        .background(if (peak) accent else dim),
                )
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            listOf("00", "06", "12", "18", "23").forEach {
                Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, fontFamily = FontFamily.Monospace)
            }
        }
        if (ins.peakHours.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            val hoursText = ins.peakHours.sorted().joinToString(" · ") { "%02d:00".format(it) }
            Text(stringResource(R.string.insights_peak_hours, hoursText), style = MaterialTheme.typography.bodySmall, color = accent, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun WeeklyCard(ins: InsightsState, accent: Color, grow: Float) {
    SectionCard(title = stringResource(R.string.insights_weekly)) {
        val max = (ins.dowAvgMg.maxOrNull() ?: 0.0).coerceAtLeast(1.0)
        val today = LocalDate.now().dayOfWeek.value - 1
        val labels = listOf("M", "T", "W", "T", "F", "S", "S")
        val dim = MaterialTheme.colorScheme.surfaceVariant
        Row(Modifier.fillMaxWidth().height(80.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (i in 0..6) {
                val frac = (ins.dowAvgMg[i] / max).toFloat()
                val hgt = (6f + 70f * frac * grow).dp
                Box(Modifier.weight(1f).height(hgt).clip(RoundedCornerShape(4.dp)).background(if (i == today) accent else dim))
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (i in 0..6) {
                Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    Text(labels[i], style = MaterialTheme.typography.labelSmall,
                        color = if (i == today) accent else MaterialTheme.colorScheme.onSurfaceVariant, fontFamily = FontFamily.Monospace)
                }
            }
        }
    }
}

@Composable
private fun AveragesCard(ins: InsightsState, unit: String) {
    SectionCard(title = stringResource(R.string.insights_averages)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatBox(Modifier.weight(1f), "%.1f".format(ins.avgPerDay), stringResource(R.string.insights_per_day))
            StatBox(Modifier.weight(1f), "${ins.weekMg.roundToInt()} $unit", stringResource(R.string.insights_per_week))
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatBox(Modifier.weight(1f), ins.firstDoseMinutes?.let { hhmm(it) } ?: "—", stringResource(R.string.insights_first))
            StatBox(Modifier.weight(1f), "${ins.streakDays}", stringResource(R.string.insights_streak))
        }
    }
}

@Composable
private fun StatBox(modifier: Modifier, value: String, label: String) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(MaterialTheme.colorScheme.surfaceVariant).padding(13.dp)) {
        Text(value, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(4.dp))
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun RecentCard(doses: List<com.pktracker.engine.Dose>, vm: AppViewModel) {
    SectionCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.insights_recent), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            OutlinedButton(onClick = { vm.undoLast() }, enabled = doses.isNotEmpty()) {
                Text(stringResource(R.string.undo_last))
            }
        }
        if (doses.isEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.no_doses), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        } else {
            doses.reversed().take(12).forEach { d ->
                val sub = Substances.byId(d.substanceId)
                val name = if (sub != null) substanceName(sub) else d.substanceId
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                        Text(
                            "${d.amount.roundToInt()} ${d.unit} · ${Instant.ofEpochMilli(d.takenAtEpochMs).atZone(ZoneId.systemDefault()).format(recentFmt)}",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    IconButton(onClick = { vm.deleteDose(d.id) }) {
                        Icon(Icons.Filled.Delete, contentDescription = stringResource(R.string.delete))
                    }
                }
            }
        }
    }
}
