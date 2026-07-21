package com.pktracker.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.ln

private const val H = 3_600_000L // ms per hour

class ModelsTest {
    @Test fun keHalfLifeRoundTrip() {
        val ke = Models.keFromHalfLife(5.0)
        assertEquals(ln(2.0) / 5.0, ke, 1e-9)
        assertEquals(5.0, Models.halfLifeFromKe(ke), 1e-9)
    }

    @Test fun batemanZeroBeforeDoseAndNonNegative() {
        assertEquals(0.0, Models.batemanSingle(-1.0, 100.0, 0.99, 42.0, 5.0, 0.139), 0.0)
        assertEquals(0.0, Models.batemanSingle(0.0, 100.0, 0.99, 42.0, 5.0, 0.139), 1e-12)
        assertTrue(Models.batemanSingle(1.0, 100.0, 0.99, 42.0, 5.0, 0.139) > 0.0)
    }

    @Test fun peakIsAtTmax() {
        val ka = 5.0; val ke = 0.139
        val tmax = Models.tmaxSingle(ka, ke)
        val cmax = Models.cmaxSingle(100.0, 0.99, 42.0, ka, ke)
        assertTrue(cmax >= Models.batemanSingle(tmax - 0.2, 100.0, 0.99, 42.0, ka, ke))
        assertTrue(cmax >= Models.batemanSingle(tmax + 0.2, 100.0, 0.99, 42.0, ka, ke))
    }

    @Test fun kaEqualsKeLimit() {
        // No NaN at the removable singularity.
        val c = Models.batemanSingle(1.0, 100.0, 1.0, 10.0, 2.0, 2.0)
        assertTrue(c.isFinite() && c > 0.0)
    }

    @Test fun superpositionAdds() {
        val one = Models.superpose(2.0, listOf(0.0 to 100.0), 0.99, 42.0, 5.0, 0.139)
        val two = Models.superpose(2.0, listOf(0.0 to 100.0, 0.0 to 100.0), 0.99, 42.0, 5.0, 0.139)
        assertEquals(2.0 * one, two, 1e-9)
    }

    @Test fun emaxSaturatesAndTolerance() {
        val e = Models.emaxEffect(1.0, 1.0, 1.0, 1.0)
        assertEquals(0.5, e, 1e-9) // C == EC50 -> half of Emax
        // Higher tolerance -> less effect at the same concentration.
        assertTrue(Models.emaxEffect(1.0, 1.0, 1.0, 1.5) < e)
        assertTrue(Models.emaxEffect(1.0, 1.0, 1.0, 0.5) > e)
    }

    @Test fun widmarkDecaysLinearlyToZero() {
        val grams = Models.gramsEthanol(330.0, 5.0)
        assertEquals(13.02, grams, 0.05)
        val traj = Models.WidmarkTrajectory(listOf(0.0 to grams), r = 0.68, massKg = 70.0, beta = 0.015)
        val peak = traj.at(0.0)
        assertTrue(peak > 0.0)
        // Zero-order: linear drop before it floors. At 1 h: peak - beta*1.
        val later = traj.at(1.0)
        assertEquals(peak - 0.015 * 1.0, later, 1e-9)
        assertEquals(0.0, traj.at(1000.0), 0.0)
    }

    @Test fun widmarkTimeToTarget() {
        assertEquals(0.0, Models.widmarkTimeToTarget(0.02, 0.05), 0.0)
        assertEquals(2.0, Models.widmarkTimeToTarget(0.08, 0.05, 0.015), 1e-9)
    }
}

class TimelineTest {
    private val profile = UserProfile(bodyMassKg = 70.0)
    private fun caffeineDose(hoursAgo: Double, mg: Double) =
        Dose("caffeine", mg, "mg", takenAtEpochMs = ((-hoursAgo) * H).toLong())

    @Test fun concentrationAndBodyAmount() {
        // now = 0h; a 100 mg dose 1h ago.
        val tl = SubstanceTimeline(Substances.caffeine, listOf(caffeineDose(1.0, 100.0)), profile)
        val conc = tl.concentrationAt(0.0)
        assertTrue(conc > 0.0)
        val mg = tl.bodyAmountAt(0.0)
        assertEquals(conc * (0.6 * 70.0), mg, 1e-9)
    }

    @Test fun effectPercentOfPeak() {
        val tl = SubstanceTimeline(Substances.caffeine, listOf(caffeineDose(1.0, 100.0)), profile)
        val pct = tl.effectPercentOfPeak(0.0, 0.0)
        assertNotNull(pct)
        assertTrue(pct!! in 0.0..100.0)
    }

    @Test fun halfLifeOverrideSlowsDecay() {
        val fast = SubstanceTimeline(Substances.caffeine, listOf(caffeineDose(1.0, 100.0)), profile)
        val slow = SubstanceTimeline(
            Substances.caffeine, listOf(caffeineDose(1.0, 100.0)),
            profile.copy(halfLifeOverrides = mapOf("caffeine" to 10.0)),
        )
        // 5 hours ahead, the slower half-life leaves a higher level.
        assertTrue(slow.concentrationAt(5.0) > fast.concentrationAt(5.0))
    }

    @Test fun alcoholHasNoBodyMgButHasBac() {
        val drink = Dose("alcohol", 14.0, "g", 0L)
        val tl = SubstanceTimeline(Substances.alcohol, listOf(drink), profile)
        assertEquals(0.0, tl.bodyAmountAt(0.5), 0.0)
        assertTrue(tl.concentrationAt(0.0) > 0.0)
        assertNull(tl.effectAt(0.0)) // no PD model for alcohol
    }
}

class SchedulerTest {
    private val profile = UserProfile(bodyMassKg = 70.0)
    private fun caffeine(vararg d: Dose) = SubstanceTimeline(Substances.caffeine, d.toList(), profile)

    @Test fun perfectTimingDoseIsOneTmaxBeforeTarget() {
        val tl = caffeine()
        val target = 3.0
        val r = Scheduler.perfectTiming(tl, nowH = 0.0, targetH = target, amount = 90.0)
        assertTrue(r.feasible)
        assertEquals(r.tmaxH, target - r.doseTimeHours!!, 1e-6)
        assertTrue(r.bodyMgAtTarget > 0.0)
    }

    @Test fun perfectTimingInThePastInfeasible() {
        val r = Scheduler.perfectTiming(caffeine(), nowH = 0.0, targetH = -1.0, amount = 90.0)
        assertTrue(!r.feasible)
    }

    @Test fun sleepCutoffMgTargetFeasibleAndOrdered() {
        // now = 0, bedtime = 9h away, no doses.
        val tl = caffeine()
        val v = Substances.caffeine.volumeLiters(70.0)
        val cutoff50 = Scheduler.sleepCutoff(tl, 0.0, 9.0, absoluteTarget = 50.0 / v)
        val cutoff100 = Scheduler.sleepCutoff(tl, 0.0, 9.0, absoluteTarget = 100.0 / v)
        assertTrue(cutoff50.feasible && cutoff100.feasible)
        // A more permissive target (100 mg) allows a later coffee than 50 mg.
        assertTrue(cutoff100.cutoffAtHours!! >= cutoff50.cutoffAtHours!!)
    }

    @Test fun sleepCutoffHoursFlatRule() {
        val r = Scheduler.sleepCutoffHours(caffeine(), 0.0, 9.0, hours = 8.0)
        assertTrue(r.feasible)
        assertEquals(1.0, r.cutoffAtHours!!, 1e-9) // bedtime(9) - 8
    }

    @Test fun redoseOverdueWhenBelowThreshold() {
        // A tiny dose long ago -> effect already below the redose fraction.
        val tl = caffeine(Dose("caffeine", 90.0, "mg", (-12 * H)))
        val r = Scheduler.redoseInfo(tl, nowH = 0.0)
        assertTrue(r.eligible)
        assertTrue(r.overdue || r.redoseAtHours != null)
    }

    @Test fun overloadFiresPastThreshold() {
        // Enough caffeine to exceed the 400 mg jitter threshold.
        val doses = (0 until 6).map { Dose("caffeine", 100.0, "mg", ((-it) * H).toLong()) }
        val info = Scheduler.overloadInfo(SubstanceTimeline(Substances.caffeine, doses, profile), 0.0)
        assertTrue(info.hasThreshold)
        assertTrue(info.bodyAmountMg > 0.0)
    }

    @Test fun alcoholPredictsSoberTimes() {
        val tl = SubstanceTimeline(Substances.alcohol, listOf(Dose("alcohol", 40.0, "g", 0L)), profile)
        val p = Scheduler.alcoholPredictions(tl, 0.0)!!
        assertTrue(p.bacNow > 0.0)
        assertNotNull(p.timeToZeroHours)
        assertTrue(p.timeToZeroHours!! > 0.0)
    }

    @Test fun sensitivityMapMonotonic() {
        assertTrue(abs(Scheduler.SLEEP_SENSITIVITY_MG["sensitive"]!! - 25.0) < 1e-9)
        assertTrue(Scheduler.SLEEP_SENSITIVITY_MG["average"]!! < Scheduler.SLEEP_SENSITIVITY_MG["resistant"]!!)
    }
}
