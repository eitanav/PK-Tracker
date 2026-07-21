package com.pktracker.android

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.pktracker.android.data.AppDatabase
import com.pktracker.android.data.AppSettings
import com.pktracker.android.data.DoseEntity
import com.pktracker.android.data.SettingsStore
import com.pktracker.android.data.toDose
import com.pktracker.engine.Dose
import com.pktracker.engine.Models
import com.pktracker.engine.Scheduler
import com.pktracker.engine.Substance
import com.pktracker.engine.SubstanceTimeline
import com.pktracker.engine.Substances
import com.pktracker.engine.UserProfile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId

const val H_MS = 3_600_000.0
val DAILY_GUIDELINE_MG = mapOf("caffeine" to 400.0)

// ---- UI state (structured data; the UI localises/formats it) ----------------
enum class ActionKind { REDOSE_NOW, REDOSE_AT, PEAK_AT, SOBER, SOBER_AT, UNDER_LIMIT_AT, CLEARING, NONE }
data class NextAction(val kind: ActionKind, val timeMs: Long?, val colorKey: String)
data class SleepState(
    val feasible: Boolean, val cutoffMs: Long?, val bedtimeMs: Long,
    val mode: String, val targetMg: Int, val hours: Int, val existingMg: Double, val overAlready: Boolean,
)
data class TimingState(
    val feasible: Boolean, val doseTimeMs: Long?, val targetMs: Long, val mg: Int,
    val bodyMg: Double, val withinCutoff: Boolean?,
)
data class AlcoholState(
    val bacNow: Double, val overLimit: Boolean, val underLimitMs: Long?, val zeroMs: Long?, val limit: Double,
)

class CurveData(
    val xHours: DoubleArray, val conc: DoubleArray, val effect: DoubleArray?,
    val simConc: DoubleArray?, val simEffect: DoubleArray?,
    val nowHours: Double, val concTop: Double, val effectTop: Double,
    val concUnit: String, val colorHex: String,
)

data class DashboardState(
    val substance: Substance,
    val nowMs: Long,
    val bodyMg: Double?,
    val effectPct: Double?,
    val concValue: Double,
    val concUnit: String,
    val sinceLastMs: Long?,
    val projectedPeakMs: Long?,
    val dailyMg: Double,
    val dailyGuidelineMg: Double?,
    val overloadThresholdMg: Double?,
    val overloadOver: Boolean,
    val nextAction: NextAction?,
    val sleep: SleepState?,
    val timing: TimingState?,
    val alcohol: AlcoholState?,
    val curve: CurveData,
    val redoseEligible: Boolean,
)

fun AppSettings.toProfile(): UserProfile = UserProfile(
    bodyMassKg = bodyMassKg,
    sex = sex,
    tolerance = mapOf("caffeine" to caffeineTolerance),
    halfLifeOverrides = mapOf("caffeine" to caffeineHalfLifeH),
)

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val db = AppDatabase.get(app)
    private val store = SettingsStore(app)
    val substances: List<Substance> = Substances.builtins

    private val nowFlow = MutableStateFlow(System.currentTimeMillis())
    private val simOnFlow = MutableStateFlow(false)

    init {
        viewModelScope.launch {
            while (true) {
                delay(30_000)
                nowFlow.value = System.currentTimeMillis()
            }
        }
    }

    val settings: StateFlow<AppSettings> =
        store.flow.stateIn(viewModelScope, SharingStarted.Eagerly, AppSettings())

    val doses: StateFlow<List<Dose>> =
        db.doseDao().observeAll().map { list -> list.map { it.toDose() } }
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val simOn: StateFlow<Boolean> = simOnFlow

    val state: StateFlow<DashboardState?> =
        combine(doses, settings, nowFlow, simOnFlow) { d, s, now, sim -> compute(d, s, now, sim) }
            .flowOn(Dispatchers.Default)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    // ---- actions ------------------------------------------------------------
    fun setActive(id: String) = viewModelScope.launch { store.update { activeSubstance(id) } }

    fun logDose(sub: Substance, amount: Double, minAgo: Int) = viewModelScope.launch {
        val taken = System.currentTimeMillis() - minAgo * 60_000L
        db.doseDao().insert(DoseEntity(substanceId = sub.id, amount = amount, unit = sub.unit, takenAtEpochMs = taken))
    }

    fun deleteDose(id: Long) = viewModelScope.launch { db.doseDao().deleteById(id) }

    fun undoLast(onDone: (Dose?) -> Unit = {}) = viewModelScope.launch {
        val last = db.doseDao().latest()
        if (last != null) db.doseDao().deleteById(last.id)
        onDone(last?.toDose())
    }

    fun setSim(on: Boolean) { simOnFlow.value = on }

    fun updateSettings(block: SettingsStore.MutablePrefs.() -> Unit) =
        viewModelScope.launch { store.update(block) }

    suspend fun allDosesOnce(): List<Dose> = db.doseDao().allOnce().map { it.toDose() }

    // ---- computation --------------------------------------------------------
    private fun compute(doses: List<Dose>, s: AppSettings, nowMs: Long, simOn: Boolean): DashboardState {
        val sub = Substances.byId(s.activeSubstanceId) ?: Substances.caffeine
        val profile = s.toProfile()
        val tl = SubstanceTimeline(sub, doses, profile)
        val nowH = nowMs / H_MS

        val conc = tl.concentrationAt(nowH)
        val bodyMg = if (sub.isAlcohol || sub.vLPerKg == null) null else tl.bodyAmountAt(nowH)
        val effectPct = tl.effectPercentOfPeak(nowH, nowH)
        val last = tl.lastDose()
        val projectedPeakMs = forwardPeakMs(tl, nowH)
        val overload = Scheduler.overloadInfo(tl, nowH)

        val sleep = if (sub.redoseEligible) computeSleep(tl, sub, profile, s, nowMs, nowH) else null
        val timing = if (sub.redoseEligible) computeTiming(tl, sub, s, nowMs, nowH, sleep) else null
        val alcohol = if (sub.isAlcohol) computeAlcohol(tl, nowH) else null
        val nextAction = computeNextAction(tl, sub, nowH)
        val curve = computeCurve(tl, sub, doses, profile, nowH, nowMs, s, simOn)

        return DashboardState(
            substance = sub, nowMs = nowMs,
            bodyMg = bodyMg, effectPct = effectPct,
            concValue = conc * sub.concScale, concUnit = sub.concUnit,
            sinceLastMs = last?.takenAtEpochMs, projectedPeakMs = projectedPeakMs,
            dailyMg = dailyTotal(doses, sub.id, nowMs), dailyGuidelineMg = DAILY_GUIDELINE_MG[sub.id],
            overloadThresholdMg = if (overload.hasThreshold) overload.thresholdMg else null,
            overloadOver = overload.over,
            nextAction = nextAction, sleep = sleep, timing = timing, alcohol = alcohol,
            curve = curve, redoseEligible = sub.redoseEligible,
        )
    }

    private fun effectiveTargetMg(s: AppSettings): Int =
        if (s.sleepMode == "preset")
            (Scheduler.SLEEP_SENSITIVITY_MG[s.sleepSensitivity] ?: 50.0).toInt()
        else s.sleepMg

    private fun computeSleep(
        tl: SubstanceTimeline, sub: Substance, profile: UserProfile,
        s: AppSettings, nowMs: Long, nowH: Double,
    ): SleepState {
        val bedtimeMs = nextTimeMs(nowMs, s.bedtime)
        val bedtimeH = bedtimeMs / H_MS
        val res = if (s.sleepMode == "hours") {
            Scheduler.sleepCutoffHours(tl, nowH, bedtimeH, s.sleepHours.toDouble())
        } else {
            val v = sub.volumeLiters(profile.bodyMassKg)
            val targetMg = effectiveTargetMg(s).toDouble()
            Scheduler.sleepCutoff(tl, nowH, bedtimeH, absoluteTarget = if (v > 0) targetMg / v else null)
        }
        val v = sub.volumeLiters(profile.bodyMassKg)
        val existingMg = res.existingAtBedtime * v
        return SleepState(
            feasible = res.feasible,
            cutoffMs = res.cutoffAtHours?.let { (it * H_MS).toLong() },
            bedtimeMs = bedtimeMs, mode = s.sleepMode,
            targetMg = effectiveTargetMg(s), hours = s.sleepHours,
            existingMg = existingMg, overAlready = existingMg > effectiveTargetMg(s),
        )
    }

    private fun computeTiming(
        tl: SubstanceTimeline, sub: Substance, s: AppSettings, nowMs: Long, nowH: Double, sleep: SleepState?,
    ): TimingState {
        val targetMs = nextTimeMs(nowMs, s.timingTarget)
        val targetH = targetMs / H_MS
        val res = Scheduler.perfectTiming(tl, nowH, targetH, s.timingMg.toDouble())
        val within = if (res.feasible && res.doseTimeHours != null && sleep?.cutoffMs != null)
            res.doseTimeHours!! <= sleep.cutoffMs / H_MS else null
        return TimingState(
            feasible = res.feasible,
            doseTimeMs = res.doseTimeHours?.let { (it * H_MS).toLong() },
            targetMs = targetMs, mg = s.timingMg, bodyMg = res.bodyMgAtTarget, withinCutoff = within,
        )
    }

    private fun computeAlcohol(tl: SubstanceTimeline, nowH: Double): AlcoholState? {
        val p = Scheduler.alcoholPredictions(tl, nowH) ?: return null
        return AlcoholState(
            bacNow = p.bacNow, overLimit = p.overLimit,
            underLimitMs = p.timeToLimitHours?.let { (it * H_MS).toLong() },
            zeroMs = p.timeToZeroHours?.let { (it * H_MS).toLong() },
            limit = p.legalLimit,
        )
    }

    private fun computeNextAction(tl: SubstanceTimeline, sub: Substance, nowH: Double): NextAction? {
        if (tl.doses.isEmpty()) return null
        if (sub.redoseEligible) {
            val ri = Scheduler.redoseInfo(tl, nowH)
            return when {
                ri.overdue -> NextAction(ActionKind.REDOSE_NOW, null, "warn")
                ri.redoseAtHours != null -> NextAction(ActionKind.REDOSE_AT, (ri.redoseAtHours!! * H_MS).toLong(), "accent")
                else -> null
            }
        }
        if (sub.isAlcohol) {
            val p = Scheduler.alcoholPredictions(tl, nowH) ?: return null
            return when {
                p.bacNow <= 0 -> NextAction(ActionKind.SOBER, null, "good")
                p.overLimit -> NextAction(ActionKind.UNDER_LIMIT_AT, p.timeToLimitHours?.let { (it * H_MS).toLong() }, "warn")
                else -> NextAction(ActionKind.SOBER_AT, p.timeToZeroHours?.let { (it * H_MS).toLong() }, "accent")
            }
        }
        val peak = forwardPeakMs(tl, nowH)
        if (peak != null) return NextAction(ActionKind.PEAK_AT, peak, "accent")
        val thr = sub.sleepThreshold
        if (thr != null && tl.concentrationAt(nowH) > thr) {
            val t = Scheduler.timeBelowLevel(tl, nowH, thr)
            if (t != null) return NextAction(ActionKind.PEAK_AT, (t * H_MS).toLong(), "accent")
        }
        return NextAction(ActionKind.CLEARING, null, "muted")
    }

    private fun computeCurve(
        tl: SubstanceTimeline, sub: Substance, doses: List<Dose>, profile: UserProfile,
        nowH: Double, nowMs: Long, s: AppSettings, simOn: Boolean,
    ): CurveData {
        val startH = nowH - 2.0
        val endH = nowH + 12.0
        val n = 240
        val res = tl.curve(startH, endH, n)
        val concDisp = DoubleArray(n) { res.concentration[it] * sub.concScale }
        val peak = tl.personalPeakEffect(nowH)
        val effect: DoubleArray? = if (res.effect != null && peak > 0)
            DoubleArray(n) { res.effect!![it] / peak * 100.0 } else null

        var simConc: DoubleArray? = null
        var simEffect: DoubleArray? = null
        if (simOn && sub.redoseEligible) {
            val simTaken = nowMs + s.simInMin * 60_000L
            val simDose = Dose(sub.id, s.simMg.toDouble(), sub.unit, simTaken)
            val simTl = SubstanceTimeline(sub, doses + simDose, profile)
            val simRes = simTl.curve(startH, endH, n)
            simConc = DoubleArray(n) { simRes.concentration[it] * sub.concScale }
            val simPeak = maxOf(peak, simTl.personalPeakEffect(endH))
            if (simRes.effect != null && simPeak > 0)
                simEffect = DoubleArray(n) { simRes.effect!![it] / simPeak * 100.0 }
        }

        var concMax = 0.0
        for (v in concDisp) if (v > concMax) concMax = v
        simConc?.let { for (v in it) if (v > concMax) concMax = v }
        val concTop = maxOf(if (concMax > 0) concMax * 1.15 else 1.0, 1e-9)

        var effMax = 0.0
        effect?.let { for (v in it) if (v > effMax) effMax = v }
        simEffect?.let { for (v in it) if (v > effMax) effMax = v }
        val effectTop = maxOf(105.0, effMax * 1.08)

        return CurveData(
            xHours = res.xHours, conc = concDisp, effect = effect,
            simConc = simConc, simEffect = simEffect,
            nowHours = nowH, concTop = concTop, effectTop = effectTop,
            concUnit = sub.concUnit, colorHex = sub.color,
        )
    }
}

// ---- helpers ----------------------------------------------------------------
private fun dailyTotal(doses: List<Dose>, subId: String, nowMs: Long): Double {
    val zone = ZoneId.systemDefault()
    val start = Instant.ofEpochMilli(nowMs).atZone(zone).toLocalDate().atStartOfDay(zone).toInstant().toEpochMilli()
    return doses.filter { it.substanceId == subId && it.takenAtEpochMs >= start }.sumOf { it.amount }
}

fun nextTimeMs(nowMs: Long, hhmm: String): Long {
    val parts = hhmm.split(":")
    val h = parts.getOrNull(0)?.toIntOrNull() ?: 23
    val m = parts.getOrNull(1)?.toIntOrNull() ?: 0
    val zone = ZoneId.systemDefault()
    val nowZ = Instant.ofEpochMilli(nowMs).atZone(zone)
    var cand = nowZ.withHour(h).withMinute(m).withSecond(0).withNano(0)
    if (!cand.isAfter(nowZ)) cand = cand.plusDays(1)
    return cand.toInstant().toEpochMilli()
}

private fun forwardPeakMs(tl: SubstanceTimeline, nowH: Double): Long? {
    val n = 160
    val c0 = tl.concentrationAt(nowH)
    var maxV = Double.NEGATIVE_INFINITY
    var maxT = nowH
    var idx = -1
    for (i in 0 until n) {
        val t = nowH + 16.0 * i / (n - 1)
        val c = tl.concentrationAt(t)
        if (c > maxV) { maxV = c; maxT = t; idx = i }
    }
    return if (idx > 1 && maxV > c0 * 1.02) (maxT * H_MS).toLong() else null
}
