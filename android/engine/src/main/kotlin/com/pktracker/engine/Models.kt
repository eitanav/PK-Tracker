package com.pktracker.engine

import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.ln

/**
 * Pure pharmacokinetic / pharmacodynamic math — a faithful Kotlin port of the
 * Python `pk_tracker.core.models`. Closed-form analytic models, no state.
 *
 * Time is in hours; one-compartment concentration in mg/L; alcohol BAC in g/dL.
 */
object Models {
    private const val KA_KE_EPS = 1e-6
    val LN2: Double = ln(2.0)
    const val ETHANOL_DENSITY_G_PER_ML = 0.789

    fun keFromHalfLife(halfLifeH: Double): Double {
        require(halfLifeH > 0) { "half_life_h must be positive" }
        return LN2 / halfLifeH
    }

    fun halfLifeFromKe(ke: Double): Double {
        require(ke > 0) { "ke must be positive" }
        return LN2 / ke
    }

    /** Single-dose blood concentration (mg/L) at [t] hours post-ingestion. */
    fun batemanSingle(t: Double, dose: Double, f: Double, v: Double, ka: Double, ke: Double): Double {
        require(v > 0) { "v must be positive" }
        require(ka > 0 && ke > 0) { "ka and ke must be positive" }
        if (t < 0.0) return 0.0
        val c = if (abs(ka - ke) < KA_KE_EPS) {
            (f * dose * ka / v) * t * exp(-ka * t)
        } else {
            val coef = (f * dose * ka) / (v * (ka - ke))
            coef * (exp(-ke * t) - exp(-ka * t))
        }
        return if (c > 0.0) c else 0.0
    }

    /** Time of peak concentration (hours) for a single dose. */
    fun tmaxSingle(ka: Double, ke: Double): Double {
        require(ka > 0 && ke > 0) { "ka and ke must be positive" }
        return if (abs(ka - ke) < KA_KE_EPS) 1.0 / ka else ln(ka / ke) / (ka - ke)
    }

    /** Peak concentration (mg/L) for a single dose. */
    fun cmaxSingle(dose: Double, f: Double, v: Double, ka: Double, ke: Double): Double =
        batemanSingle(tmaxSingle(ka, ke), dose, f, v, ka, ke)

    /** Total concentration from many linear doses (superposition). */
    fun superpose(t: Double, doseEvents: List<Pair<Double, Double>>, f: Double, v: Double, ka: Double, ke: Double): Double {
        var total = 0.0
        for ((ti, amount) in doseEvents) total += batemanSingle(t - ti, amount, f, v, ka, ke)
        return total
    }

    /** Extended-release single dose: two superposed Bateman pulses. */
    fun batemanErSingle(
        t: Double, dose: Double, f: Double, v: Double, ka: Double, ke: Double,
        fracIr: Double = 0.5, lagH: Double = 4.0, ka2: Double? = null,
    ): Double {
        val ka2r = ka2 ?: ka
        val c1 = batemanSingle(t, fracIr * dose, f, v, ka, ke)
        val c2 = batemanSingle(t - lagH, (1.0 - fracIr) * dose, f, v, ka2r, ke)
        return c1 + c2
    }

    /** Superposition of many extended-release doses. */
    fun superposeEr(
        t: Double, doseEvents: List<Pair<Double, Double>>, f: Double, v: Double, ka: Double, ke: Double,
        fracIr: Double = 0.5, lagH: Double = 4.0, ka2: Double? = null,
    ): Double {
        var total = 0.0
        for ((ti, amount) in doseEvents) total += batemanErSingle(t - ti, amount, f, v, ka, ke, fracIr, lagH, ka2)
        return total
    }

    /** Hours for a concentration to decay from [cCurrent] to [cTarget] (elimination only). */
    fun timeToDecayTo(cCurrent: Double, cTarget: Double, ke: Double): Double {
        require(ke > 0) { "ke must be positive" }
        if (cCurrent <= 0 || cTarget >= cCurrent) return 0.0
        if (cTarget <= 0) return Double.POSITIVE_INFINITY
        return (1.0 / ke) * ln(cCurrent / cTarget)
    }

    /** Perceived effect from a concentration (saturating Emax with tolerance-shifted EC50). */
    fun emaxEffect(concentration: Double, emax: Double, ec50: Double, toleranceFactor: Double): Double {
        require(ec50 > 0) { "ec50 must be positive" }
        require(toleranceFactor > 0) { "tolerance_factor must be positive" }
        val denom = ec50 * toleranceFactor + concentration
        return if (denom > 0) emax * concentration / denom else 0.0
    }

    fun gramsEthanol(volumeMl: Double, abvPercent: Double): Double {
        require(volumeMl >= 0 && abvPercent >= 0) { "volume and abv must be non-negative" }
        return volumeMl * (abvPercent / 100.0) * ETHANOL_DENSITY_G_PER_ML
    }

    /**
     * Precomputed piecewise-linear Widmark trajectory. Build once, evaluate at
     * many times cheaply. Zero-order elimination floored at zero.
     */
    class WidmarkTrajectory(
        drinkEvents: List<Pair<Double, Double>>,
        r: Double, massKg: Double, beta: Double = 0.015, rampH: Double = 0.0,
    ) {
        private val eventT: DoubleArray
        private val bacAfter: DoubleArray
        private val beta: Double = beta

        init {
            require(r > 0 && massKg > 0) { "r and mass_kg must be positive" }
            require(beta > 0) { "beta must be positive" }
            var events = drinkEvents.sortedBy { it.first }
            if (rampH > 0) {
                val nSub = 10
                events = events.flatMap { (ti, grams) ->
                    (0 until nSub).map { k -> (ti + rampH * k / nSub) to (grams / nSub) }
                }.sortedBy { it.first }
            }
            eventT = DoubleArray(events.size) { events[it].first }
            val bumps = DoubleArray(events.size) { events[it].second / (r * massKg * 10.0) }
            bacAfter = DoubleArray(events.size)
            var prevT = Double.NaN
            var prevB = 0.0
            for (i in events.indices) {
                val te = eventT[i]
                val b = if (prevT.isNaN()) bumps[i]
                else maxOf(0.0, prevB - beta * (te - prevT)) + bumps[i]
                bacAfter[i] = b
                prevT = te; prevB = b
            }
        }

        fun at(t: Double): Double {
            if (eventT.isEmpty()) return 0.0
            // last index with eventT[idx] <= t
            var idx = -1
            for (i in eventT.indices) {
                if (eventT[i] <= t) idx = i else break
            }
            if (idx < 0) return 0.0
            return maxOf(0.0, bacAfter[idx] - beta * (t - eventT[idx]))
        }
    }

    fun widmarkBac(
        t: Double, drinkEvents: List<Pair<Double, Double>>,
        r: Double, massKg: Double, beta: Double = 0.015, rampH: Double = 0.0,
    ): Double = WidmarkTrajectory(drinkEvents, r, massKg, beta, rampH).at(t)

    fun widmarkTimeToTarget(bacNow: Double, target: Double, beta: Double = 0.015): Double {
        require(beta > 0) { "beta must be positive" }
        if (bacNow <= target) return 0.0
        return (bacNow - target) / beta
    }
}
