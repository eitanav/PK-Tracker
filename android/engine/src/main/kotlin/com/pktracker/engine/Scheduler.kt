package com.pktracker.engine

import kotlin.math.abs

/** Derived alerts and solvers. All times are absolute hours. Port of `scheduler.py`. */
object Scheduler {

    val SLEEP_SENSITIVITY_MG = mapOf("sensitive" to 25.0, "average" to 50.0, "resistant" to 100.0)
    private const val MAX_HORIZON_H = 72.0

    data class RedoseInfo(
        val eligible: Boolean, val thresholdFraction: Double, val peakEffect: Double,
        val currentPercent: Double?, val redoseAtHours: Double?, val overdue: Boolean,
    )

    data class SleepCutoff(
        val feasible: Boolean, val cutoffAtHours: Double?, val bedtimeHours: Double,
        val ceiling: Double, val existingAtBedtime: Double, val amount: Double, val reason: String = "",
    )

    data class PerfectTiming(
        val feasible: Boolean, val doseTimeHours: Double?, val targetTimeHours: Double,
        val amount: Double, val tmaxH: Double, val bodyMgAtTarget: Double, val reason: String = "",
    )

    data class OverloadInfo(
        val hasThreshold: Boolean, val bodyAmountMg: Double, val thresholdMg: Double?, val over: Boolean,
    )

    data class AlcoholPrediction(
        val bacNow: Double, val overLimit: Boolean,
        val timeToLimitHours: Double?, val timeToZeroHours: Double?, val legalLimit: Double,
    )

    // ---- root finders --------------------------------------------------------
    private fun bisect(lo: Double, hi: Double, tol: Double = 1e-4, f: (Double) -> Double): Double {
        var a = lo; var b = hi
        var fa = f(a)
        repeat(200) {
            val m = 0.5 * (a + b)
            val fm = f(m)
            if (abs(fm) < tol || (b - a) < tol) return m
            if ((fa > 0) != (fm > 0)) b = m else { a = m; fa = fm }
        }
        return 0.5 * (a + b)
    }

    private fun forwardRoot(startH: Double, horizonH: Double, stepH: Double = 0.1, g: (Double) -> Double): Double? {
        var t0 = startH
        if (g(t0) <= 0) return startH
        val end = startH + horizonH
        var t = t0 + stepH
        while (t <= end) {
            if (g(t) <= 0) return bisect(t0, t) { g(it) }
            t0 = t; t += stepH
        }
        return null
    }

    // ---- redose nudge --------------------------------------------------------
    fun redoseInfo(timeline: SubstanceTimeline, nowH: Double, thresholdFraction: Double? = null): RedoseInfo {
        val sub = timeline.substance
        val frac = thresholdFraction ?: (sub.redoseFraction ?: 0.30)
        if (!sub.redoseEligible || sub.ec50 == null || timeline.doses.isEmpty())
            return RedoseInfo(false, frac, 0.0, null, null, false)
        val peak = timeline.personalPeakEffect(nowH)
        if (peak <= 0) return RedoseInfo(true, frac, 0.0, null, null, false)
        val targetEffect = frac * peak
        val curEffect = timeline.effectAt(nowH)!!
        val curPercent = 100.0 * curEffect / peak
        if (curEffect <= targetEffect) return RedoseInfo(true, frac, peak, curPercent, null, true)
        val crossH = forwardRoot(nowH, MAX_HORIZON_H) { t -> timeline.effectAt(t)!! - targetEffect }
        return RedoseInfo(true, frac, peak, curPercent, crossH, false)
    }

    // ---- sleep cutoff --------------------------------------------------------
    fun sleepCutoff(
        timeline: SubstanceTimeline, nowH: Double, bedtimeH: Double,
        amount: Double? = null, targetFraction: Double? = null, absoluteTarget: Double? = null,
    ): SleepCutoff {
        val sub = timeline.substance
        if (sub.model == MODEL_WIDMARK || sub.ka == null)
            return SleepCutoff(false, null, bedtimeH, 0.0, 0.0, 0.0, "not applicable to this model")
        val amt = amount ?: (timeline.lastDose()?.amount ?: (sub.presets.firstOrNull()?.amount ?: 90.0))
        val ke = timeline.ke()
        val v = sub.volumeLiters(timeline.profile.bodyMassKg)
        val tmax = Models.tmaxSingle(sub.ka, ke)
        val cmax = Models.cmaxSingle(amt, sub.f, v, sub.ka, ke)
        val ceiling = absoluteTarget ?: (targetFraction?.let { it * cmax } ?: (sub.sleepThreshold ?: 0.15 * cmax))
        val existingAtBed = timeline.concentrationAt(bedtimeH)
        val headroom = ceiling - existingAtBed
        if (headroom <= 0)
            return SleepCutoff(false, null, bedtimeH, ceiling, existingAtBed, amt,
                "already over the sleep ceiling at bedtime from logged doses")
        val latestH = bedtimeH - tmax
        if (latestH <= nowH)
            return SleepCutoff(false, null, bedtimeH, ceiling, existingAtBed, amt,
                "bedtime is too soon for another dose to peak and clear")
        fun added(tDose: Double) = Models.batemanSingle(bedtimeH - tDose, amt, sub.f, v, sub.ka, ke)
        val cutoffH: Double = when {
            added(latestH) <= headroom -> latestH
            added(nowH) > headroom -> return SleepCutoff(false, null, bedtimeH, ceiling, existingAtBed, amt,
                "even a dose now would not have cleared by bedtime")
            else -> bisect(nowH, latestH) { added(it) - headroom }
        }
        return SleepCutoff(true, cutoffH, bedtimeH, ceiling, existingAtBed, amt)
    }

    fun sleepCutoffHours(
        timeline: SubstanceTimeline, nowH: Double, bedtimeH: Double, hours: Double, amount: Double? = null,
    ): SleepCutoff {
        val sub = timeline.substance
        val amt = amount ?: (timeline.lastDose()?.amount ?: (sub.presets.firstOrNull()?.amount ?: 90.0))
        val cutoff = bedtimeH - hours
        if (cutoff <= nowH)
            return SleepCutoff(false, null, bedtimeH, 0.0, 0.0, amt, "already inside the pre-bed window")
        return SleepCutoff(true, cutoff, bedtimeH, 0.0, 0.0, amt)
    }

    // ---- perfect timing ------------------------------------------------------
    fun perfectTiming(timeline: SubstanceTimeline, nowH: Double, targetH: Double, amount: Double): PerfectTiming {
        val sub = timeline.substance
        if (sub.ka == null || sub.model == MODEL_WIDMARK)
            return PerfectTiming(false, null, targetH, amount, 0.0, 0.0, "not applicable to this substance")
        val ke = timeline.ke()
        val v = sub.volumeLiters(timeline.profile.bodyMassKg)
        val tmax = Models.tmaxSingle(sub.ka, ke)
        val doseTime = targetH - tmax
        val existing = timeline.concentrationAt(targetH)
        val newPeak = Models.cmaxSingle(amount, sub.f, v, sub.ka, ke)
        val bodyMg = (existing + newPeak) * v
        if (doseTime <= nowH)
            return PerfectTiming(false, null, targetH, amount, tmax, bodyMg, "that peak is too soon — drink now for the closest")
        return PerfectTiming(true, doseTime, targetH, amount, tmax, bodyMg)
    }

    // ---- overload / alcohol --------------------------------------------------
    fun overloadInfo(timeline: SubstanceTimeline, nowH: Double): OverloadInfo {
        val thr = timeline.substance.overloadAmountMg ?: return OverloadInfo(false, 0.0, null, false)
        val body = timeline.bodyAmountAt(nowH)
        return OverloadInfo(true, body, thr, body > thr)
    }

    fun alcoholPredictions(timeline: SubstanceTimeline, nowH: Double): AlcoholPrediction? {
        if (timeline.substance.model != MODEL_WIDMARK) return null
        val bacNow = timeline.concentrationAt(nowH)
        val beta = timeline.profile.beta
        val limit = timeline.profile.legalBacLimit
        if (bacNow <= 0) return AlcoholPrediction(0.0, false, null, null, limit)
        val hToLimit = Models.widmarkTimeToTarget(bacNow, limit, beta)
        val hToZero = Models.widmarkTimeToTarget(bacNow, 0.0, beta)
        return AlcoholPrediction(
            bacNow, bacNow > limit,
            if (bacNow > limit) nowH + hToLimit else nowH,
            nowH + hToZero, limit,
        )
    }

    fun timeBelowLevel(
        timeline: SubstanceTimeline, nowH: Double, level: Double, horizonH: Double = 48.0, stepH: Double = 0.2,
    ): Double? {
        if (timeline.concentrationAt(nowH) <= level) return nowH
        var t = nowH + stepH
        val end = nowH + horizonH
        while (t <= end) {
            if (timeline.concentrationAt(t) <= level) return t
            t += stepH
        }
        return null
    }
}
