package com.pktracker.engine

/** A sampled timeline ready for plotting. [xHours] is absolute time in hours. */
class CurveResult(
    val xHours: DoubleArray,
    val concentration: DoubleArray,
    val effect: DoubleArray?,
)

/**
 * On-demand evaluation of one substance's blood level and effect from a dose
 * log. Holds no simulation state — every call recomputes analytically. A port
 * of `pk_tracker.core.engine.SubstanceTimeline`.
 */
class SubstanceTimeline(
    val substance: Substance,
    allDoses: List<Dose>,
    val profile: UserProfile,
) {
    val doses: List<Dose> = allDoses
        .filter { it.substanceId == substance.id }
        .sortedBy { it.takenAtEpochMs }

    val toleranceFactor: Double = profile.toleranceFor(substance.id)

    private val doseEvents: List<Pair<Double, Double>> = doses.map { it.hours to it.amount }

    private val widmark: Models.WidmarkTrajectory? by lazy {
        if (substance.isAlcohol && doseEvents.isNotEmpty())
            Models.WidmarkTrajectory(
                doseEvents, profile.widmarkR(), profile.bodyMassKg,
                profile.beta, profile.alcoholRampMin / 60.0,
            )
        else null
    }

    /** Elimination rate constant, honouring a per-user half-life override. */
    fun ke(): Double {
        val override = profile.halfLifeFor(substance.id)
        return if (override != null) Models.keFromHalfLife(override) else substance.keValue()
    }

    fun concentrationAt(tHours: Double): Double {
        if (doseEvents.isEmpty()) return 0.0
        val s = substance
        return when (s.model) {
            MODEL_WIDMARK -> widmark?.at(tHours) ?: 0.0
            MODEL_ONE_COMPARTMENT_ER -> Models.superposeEr(
                tHours, doseEvents, s.f, s.volumeLiters(profile.bodyMassKg), s.ka!!, ke(),
                s.fracIr ?: 0.5, s.lagH ?: 4.0, s.ka2,
            )
            else -> Models.superpose(tHours, doseEvents, s.f, s.volumeLiters(profile.bodyMassKg), s.ka!!, ke())
        }
    }

    fun effectAt(tHours: Double): Double? {
        val ec50 = substance.ec50 ?: return null
        return Models.emaxEffect(concentrationAt(tHours), substance.emax, ec50, toleranceFactor)
    }

    /** Drug mass currently in the body (mg) = concentration × volume. 0 for alcohol. */
    fun bodyAmountAt(tHours: Double): Double {
        if (substance.isAlcohol || substance.vLPerKg == null) return 0.0
        return concentrationAt(tHours) * substance.volumeLiters(profile.bodyMassKg)
    }

    fun lastDose(): Dose? = doses.lastOrNull()

    fun curve(startH: Double, endH: Double, n: Int = 600): CurveResult {
        val x = DoubleArray(n) { startH + (endH - startH) * it / (n - 1) }
        val conc = DoubleArray(n) { concentrationAt(x[it]) }
        val ec50 = substance.ec50
        val eff = if (ec50 == null) null else DoubleArray(n) {
            Models.emaxEffect(conc[it], substance.emax, ec50, toleranceFactor)
        }
        return CurveResult(x, conc, eff)
    }

    /** Max raw effect across the dose history up to [nowH] (for % display). */
    fun personalPeakEffect(nowH: Double): Double {
        val ec50 = substance.ec50 ?: return 0.0
        if (doses.isEmpty()) return 0.0
        val startH = doses.first().hours
        val endH = maxOf(nowH, doses.last().hours + 0.1)
        var peak = 0.0
        val n = 2000
        for (i in 0 until n) {
            val t = startH + (endH - startH) * i / (n - 1)
            val e = Models.emaxEffect(concentrationAt(t), substance.emax, ec50, toleranceFactor)
            if (e > peak) peak = e
        }
        return peak
    }

    fun effectPercentOfPeak(whenH: Double, nowH: Double): Double? {
        val peak = personalPeakEffect(nowH)
        if (peak <= 0) return null
        val cur = effectAt(whenH) ?: return null
        return 100.0 * cur / peak
    }
}
