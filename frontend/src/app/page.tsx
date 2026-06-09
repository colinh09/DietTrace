"use client";

// The DietTrace day view: a centered single-column page that owns the selected
// day, renders the ✦ DietTrace header, the day-macros band (calories + P/C/F vs
// targets), the inline log input, and the day's logged meals as compact rows
// read from /history. Expanding a row reveals that
// meal's agent's-work trace, kept from its /log response.
import { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "@/components/header";
import { DatePicker } from "@/components/date-picker";
import { DayMacros } from "@/components/day-macros";
import { LogInput } from "@/components/log-input";
import { LiveMeal, type LiveEntry } from "@/components/live-meal";
import { MealList, type MealDetail } from "@/components/meal-list";
import { SafetyNotice } from "@/components/safety-notice";
import type { AgentEvent } from "@/components/agent-decision";
import { Dashboard } from "@/components/dashboard";
import { OverviewModal } from "@/components/observability-modal";
import { MacroModal } from "@/components/macro-modal";
import { Onboarding } from "@/components/onboarding";
import {
  deleteMeal,
  getAnalysis,
  getGoals,
  getHistory,
  getPreferences,
  getProfile,
  logMealStream,
  userId,
  type GoalProgress,
  type Meal,
  type Safety,
  type SeededDecision,
} from "@/lib/api";
import { clearOnboarded, isOnboardedFlag, markOnboarded } from "@/lib/onboarding";
import { clearSetup } from "@/lib/setup";
import { fromISODate, isSameDay, shiftDate, toISODate } from "@/lib/date";
import { foldRetuneIntoFeed } from "@/lib/feed";
import { useAuth } from "@/lib/auth";
import { chooseAnon, hasChosenAnon } from "@/lib/auth-gate";
import { SignIn } from "@/components/sign-in";

export default function Home() {
  const [date, setDate] = useState(() => new Date());
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [meals, setMeals] = useState<Meal[]>([]);
  // The agent's-work detail per meal id, captured from each /log response so an
  // expanded row can show the trace + per-item table the backend just produced.
  const [details, setDetails] = useState<Record<number, MealDetail>>({});
  // The in-progress meal while its /log/stream is running, or null when idle.
  const [live, setLive] = useState<LiveEntry | null>(null);
  // The supervisor's per-meal decisions, newest first (the agent-observability feed).
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  // Bumped when a decision is "retune", so the observability panel runs the gated
  // eval on its own — the agent drives the re-tune, not a button click.
  const [retuneSignal, setRetuneSignal] = useState(0);
  // Bumped whenever a correction/confirmation/seed happens, so the always-visible
  // learning panel in the Observability column refetches and stays in sync (the
  // corrections persist across day navigation instead of disappearing).
  const [reloadSignal, setReloadSignal] = useState(0);
  const bumpLearning = useCallback(() => setReloadSignal((n) => n + 1), []);
  // Learning-loop counts for the day-summary glance zone — refreshed whenever the
  // learning state changes (a correction, confirmation, seed, or shipped re-tune).
  const [learnStats, setLearnStats] = useState<{
    corrections: number;
    confirmations: number;
    version: number;
  } | null>(null);
  useEffect(() => {
    let alive = true;
    getPreferences()
      .then((p) => {
        if (alive)
          setLearnStats({
            corrections: p.corrections,
            confirmations: p.confirmations,
            version: p.block?.version ?? 0,
          });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [reloadSignal]);
  // The safety guardrail result from the most recent log, or null when clear —
  // surfaces a calm supportive notice above the meals.
  const [safety, setSafety] = useState<Safety | null>(null);
  // Whether the combined Accuracy+Trust "Overview" page is open.
  const [overviewOpen, setOverviewOpen] = useState(false);
  // Whether the macro editor ("Set your targets") modal is open.
  const [macroOpen, setMacroOpen] = useState(false);
  // Whether the "recalculate from your details" flow (the reused onboarding chat)
  // is open, overlaying the app.
  const [recalcOpen, setRecalcOpen] = useState(false);
  // First-run gate: null while we decide, false → show onboarding, true → the app.
  // A returning browser (flag set) skips straight through; otherwise a user who
  // already has a saved profile or logged meals (a seeded judge, a returning
  // signed-in user) is treated as onboarded so they never re-see the welcome.
  const [onboarded, setOnboarded] = useState<boolean | null>(null);
  // The Firebase sign-in gate. Inert unless Firebase is configured: `user` is
  // null when signed out / anonymous, `authLoading` holds the first paint, and
  // `anonChosen` records "continue without an account" so a reload skips the gate.
  const { user, loading: authLoading, configured: authConfigured } = useAuth();
  // Lazy + SSR-safe: `hasChosenAnon` guards `window`, so this is false on the
  // server and reads localStorage on the client without a hydration mismatch
  // (the gate paints "busy" while auth resolves, regardless of this value).
  const [anonChosen, setAnonChosen] = useState(hasChosenAnon);
  const continueAnon = useCallback(() => {
    chooseAnon();
    setAnonChosen(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Decide off-render (async) so we never setState synchronously in the effect:
    // the localStorage flag is the fast path; otherwise a saved profile or any
    // logged meal also counts as onboarded (seeded judge / returning user).
    const decide = async (): Promise<boolean> => {
      if (isOnboardedFlag()) return true;
      const [profile, history] = await Promise.allSettled([
        getProfile(),
        getHistory(toISODate(new Date())),
      ]);
      const hasProfile =
        profile.status === "fulfilled" &&
        profile.value.profile_text.trim() !== "";
      const hasMeals =
        history.status === "fulfilled" && history.value.meals.length > 0;
      if (hasProfile || hasMeals) {
        markOnboarded();
        return true;
      }
      return false;
    };
    decide().then((v) => {
      if (!cancelled) setOnboarded(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the daily targets first so the band isn't empty; fail-soft.
  useEffect(() => {
    getGoals()
      .then((res) =>
        setGoals((current) =>
          current.length
            ? current
            : res.goals.map((g) => ({ ...g, consumed: 0, remaining: g.target })),
        ),
      )
      .catch(() => {});
  }, []);

  // The meal list AND the day-macros band are both sourced for the selected day,
  // and re-fetch on date navigation and after a meal is logged or removed — so
  // navigating days updates both the meals and the consumed/remaining totals.
  const loadHistory = useCallback(() => {
    getHistory(toISODate(date))
      .then((res) => {
        setMeals(res.meals);
        // Rebuild the per-meal breakdown from the persisted fields so the table +
        // trace survive a reload / navigation; don't clobber richer session detail.
        setDetails((current) => {
          const next = { ...current };
          for (const m of res.meals) {
            if (!m.per_item) continue;
            // Refresh from the persisted fields every load so a corrected meal's
            // table + confidence update in place. Keep a richer in-session trace
            // when history's reconstructed one is empty (older logs).
            const prev = next[m.id];
            next[m.id] = {
              trace: m.trace && m.trace.length ? m.trace : (prev?.trace ?? []),
              perItem: m.per_item,
              confidence: m.confidence,
              reasons: m.reasons,
              axes: m.axes,
              needsReview: m.needs_review,
              reviewReason: m.review_reason ?? null,
            };
          }
          return next;
        });
      })
      .catch(() => {});
  }, [date]);

  const loadAnalysis = useCallback(() => {
    getAnalysis(toISODate(date))
      .then((res) => setGoals(res.goals))
      .catch(() => {});
  }, [date]);

  useEffect(() => {
    loadHistory();
    loadAnalysis();
  }, [loadHistory, loadAnalysis]);

  // Remove a logged meal: drop it optimistically, then reconcile both reads.
  const handleDelete = useCallback(
    (meal: Meal) => {
      setMeals((current) => current.filter((m) => m.id !== meal.id));
      deleteMeal(meal.id)
        .then(() => {
          loadHistory();
          loadAnalysis();
        })
        .catch(() => {});
    },
    [loadHistory, loadAnalysis],
  );

  // Stream a new meal: show the working entry immediately, append each agent
  // step as it streams in, then settle it into the list when the result lands.
  const handleSubmit = useCallback(
    (text: string) => {
      const day = toISODate(date);
      setLive({ text, steps: [] });
      setSafety(null);
      logMealStream(text, day, (event) => {
        if (event.type === "step") {
          setLive((current) => {
            if (!current) return current;
            // A step emits "running" then "done" — replace the running placeholder
            // rather than appending a duplicate (e.g. "Read your meal" twice).
            const last = current.steps[current.steps.length - 1];
            const steps =
              last && last.step === event.step && last.status === "running"
                ? [...current.steps.slice(0, -1), event]
                : [...current.steps, event];
            return { ...current, steps };
          });
          return;
        }
        // A safety-flagged input is not a meal: show the supportive notice and
        // log nothing (no row, no totals).
        if (event.safety?.flagged) {
          setSafety(event.safety);
          setLive(null);
          return;
        }
        const id = event.id ?? 0;
        const meal: Meal = {
          id,
          created_at: new Date().toISOString(),
          date: day,
          text,
          totals: event.totals ?? [],
        };
        setMeals((current) => [meal, ...current.filter((m) => m.id !== id)]);
        setDetails((current) => ({
          ...current,
          [id]: {
            trace: event.trace ?? [],
            perItem: event.per_item ?? [],
            confidence: event.confidence,
            reasons: event.reasons,
            axes: event.axes,
            needsReview: event.needs_review,
            reviewReason: event.review_reason,
          },
        }));
        setSafety(event.safety ?? null);
        if (event.supervisor) {
          // Only an auto-retune acts on a logged meal. Dataset adds + feedback are
          // USER-driven (the "Looks right → confirm" review and the correction box),
          // so we never surface a supervisor-decided add_dataset_point / bank_feedback
          // here — logging a meal must not silently add it to the dataset.
          if (event.supervisor.op === "retune") {
            setRetuneSignal((n) => n + 1);
          }
        }
        setLive(null);
        loadHistory();
        loadAnalysis();
      }).catch(() => setLive(null));
    },
    [date, loadHistory, loadAnalysis],
  );

  const handleCorrected = useCallback(() => {
    bumpLearning();
    loadHistory();
    loadAnalysis();
  }, [bumpLearning, loadHistory, loadAnalysis]);

  // Push a supervisor action into the activity feed live — every correction the
  // user gives and every meal they confirm shows up the moment it happens. A
  // "retune" decision (feedback is the primary trigger) instead runs the gated
  // eval, exactly like a /log decision — its outcome lands in the feed via the panel.
  const pushAgentEvent = useCallback(
    (e: {
      op: AgentEvent["op"];
      reason: string;
      mealText?: string;
      phoenix?: string | null;
    }) => {
      if (e.op === "retune") {
        setRetuneSignal((n) => n + 1);
        return;
      }
      const ts = Date.now();
      setAgentEvents((cur) =>
        [{ ...e, id: `act-${ts}-${cur.length}`, ts, when: "now" }, ...cur].slice(
          0,
          30,
        ),
      );
    },
    [],
  );

  // A finished re-tune's outcome drops into the same persisted feed (so it survives
  // a reload too, not just the live per-meal events).
  const handleRetuneComplete = useCallback(
    (event: AgentEvent, shipped?: boolean, retuneNo?: number | null) => {
      setAgentEvents((cur) => foldRetuneIntoFeed(cur, event, shipped, retuneNo));
      // Refresh the glance stats so "updates" reflects the new version right away
      // (corrections already refresh on /log; a shipped retune bumps the version).
      bumpLearning();
    },
    [bumpLearning],
  );

  // After a reset wipes the user server-side, re-trigger onboarding so a clean
  // slate always starts from the welcome flow. Shared by both Reset entry points
  // (the account menu and the quiet control on the date row).
  const handleAfterReset = useCallback(() => {
    clearOnboarded();
    clearSetup();
    // Clear the feed + zero the retune trigger so the remount can't replay a stale
    // signal. Remove the PERSISTED feed directly (not just the in-memory state) —
    // otherwise a reset that doesn't re-seed leaves the prior session's traces in
    // localStorage, and they reappear on the next mount. Re-seeding repopulates it.
    try {
      window.localStorage.removeItem(`diettrace_activity_${userId()}`);
    } catch {
      /* storage unavailable — the in-memory clear below still applies */
    }
    setAgentEvents([]);
    setRetuneSignal(0);
    setOnboarded(false);
  }, []);

  // Persist the activity feed per-user in localStorage so a reload keeps it (until a
  // real account replaces the anonymous id with Firebase auth, same key path). Skip
  // the first write so the empty initial state can't clobber a restored feed.
  const restoredFeed = useRef(false);
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(`diettrace_activity_${userId()}`);
      if (saved) setAgentEvents(JSON.parse(saved) as AgentEvent[]);
    } catch {
      /* corrupt/absent storage — start with an empty feed */
    }
  }, []);
  useEffect(() => {
    if (!restoredFeed.current) {
      restoredFeed.current = true;
      return;
    }
    try {
      window.localStorage.setItem(
        `diettrace_activity_${userId()}`,
        JSON.stringify(agentEvents),
      );
    } catch {
      /* storage full/unavailable — feed just won't persist this session */
    }
  }, [agentEvents]);

  // Onboarding finished (or was skipped): enter the app and refresh the day so
  // the just-saved targets show in the band.
  const handleOnboarded = useCallback(
    (seededDecisions?: SeededDecision[]) => {
      setOnboarded(true);
      // Backfill the feed with the seeded persona's prior decisions (previous day).
      if (seededDecisions?.length) {
        setAgentEvents(
          seededDecisions.map((d, i) => ({
            id: `seed-${i}`,
            op: d.op,
            reason: d.reason,
            mealText: d.meal_text,
            when: "yesterday",
          })),
        );
      }
      loadHistory();
      loadAnalysis();
      bumpLearning();
    },
    [loadHistory, loadAnalysis, bumpLearning],
  );

  // Sign-in gate — the app's entry point when Firebase is wired. Hold the paint
  // while auth resolves, then show the dedicated sign-in screen to an
  // unauthenticated user who hasn't opted into the anonymous path. When Firebase
  // is unconfigured this gate is inert and the app runs fully anonymous.
  if (authConfigured && authLoading)
    return <div className="ob-page" aria-busy="true" />;
  if (authConfigured && !user && !anonChosen)
    return <SignIn onContinueAnon={continueAnon} />;

  // Hold the paint until the gate decides (avoids flashing the app then the
  // welcome). A returning user resolves synchronously from the localStorage flag.
  if (onboarded === null) return <div className="ob-page" aria-busy="true" />;
  if (onboarded === false) return <Onboarding onDone={handleOnboarded} />;

  const heading = isSameDay(date, new Date()) ? "Today" : "Logged";

  return (
    <div className="page">
      <main className="wrap wrap-wide">
        <Header
          date={date}
          onOpenOverview={() => setOverviewOpen(true)}
          onOpenMacros={() => setMacroOpen(true)}
          onSeeded={() => {
            loadHistory();
            loadAnalysis();
            bumpLearning();
          }}
          onViewDay={(iso) => setDate(fromISODate(iso))}
          onReset={handleAfterReset}
          onAuthChange={() => {
            loadHistory();
            loadAnalysis();
            bumpLearning();
          }}
        />
        <div className="layout">
          <div className="col-log">
            {/* The day card — date navigator + calorie/macro rings, one panel. */}
            <section className="day-card">
              <DatePicker
                date={date}
                onShift={(days) => setDate((d) => shiftDate(d, days))}
                onPickDate={setDate}
                onReset={handleAfterReset}
              />
              <DayMacros goals={goals} stats={learnStats} />
            </section>

            {/* The log card — input + the day's meals, a separate panel below. */}
            <section className="log-card">
              <h2 className="log-card-head">Food Log</h2>
              <LogInput onSubmit={handleSubmit} busy={live !== null} />
              <SafetyNotice safety={safety ?? undefined} />
              {live && <LiveMeal entry={live} />}
              <MealList
                meals={meals}
                heading={heading}
                detailsById={details}
                onEdit={handleDelete}
                onCorrected={handleCorrected}
                onAgentEvent={pushAgentEvent}
              />
            </section>
          </div>
          <Dashboard
            reloadSignal={reloadSignal}
            agentEvents={agentEvents}
            autoRetune={retuneSignal}
            onRetuneComplete={handleRetuneComplete}
          />
        </div>
      </main>
      {overviewOpen && <OverviewModal onClose={() => setOverviewOpen(false)} />}
      {macroOpen && (
        <MacroModal
          goals={goals}
          onClose={() => setMacroOpen(false)}
          onRecalc={() => {
            // Re-run the onboarding chat to recompute everything from scratch.
            setMacroOpen(false);
            setRecalcOpen(true);
          }}
          onSaved={() => {
            // Saved targets become the user's per-user goals; refresh the band.
            loadAnalysis();
          }}
        />
      )}

      {recalcOpen && (
        <div className="ob-overlay">
          <Onboarding
            startMode="chat"
            onCancel={() => setRecalcOpen(false)}
            onDone={() => {
              // The chat recomputed + saved new targets — refresh the band.
              setRecalcOpen(false);
              loadAnalysis();
            }}
          />
        </div>
      )}
    </div>
  );
}
