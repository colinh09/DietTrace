"use client";

// The learning loop, made permanent in the Observability column (no modal). It
// shows — at all times, not hidden behind a click — what the agent has learned,
// the gated re-tune streaming live (the rule it writes, then every meal re-scored
// with the rule vs without, then the ship verdict), the corrections you've taught
// (meal + what you said, persisted), and the held-out dataset it's tested against.
// This is the observability-everywhere rule applied to the loop itself.
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Gauge,
  Pencil,
  RotateCcw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Tooltip } from "@/components/ui/tooltip";
import {
  AgentFeed,
  type AgentEvent,
  type ExperimentRow,
} from "@/components/agent-decision";
import { Modal } from "@/components/modal";
import {
  deleteLearningFeedback,
  getPreferences,
  getProfile,
  learningRetuneStream,
  listLearningFeedback,
  setProfile,
  type FeedbackItem,
  type LearningRetuneEvent,
  type LearningRetuneResult,
  type PreferenceRule,
  type PreferencesResponse,
  type RetuneScores,
} from "@/lib/api";

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v * 100)}%`;

// One row of the live retune table. Listed up front from the manifest (before /
// after null = not scored yet), then filled in as each score streams in.
interface LiveRow {
  set: "fit" | "usda";
  text: string;
  before: number | null;
  after: number | null;
  // For fit rows scored in Phoenix: the truth + the base/tuned kcal estimates, so the
  // results table can show the full per-meal detail pulled from Arize over MCP.
  expected?: number;
  baseKcal?: number | null;
  tunedKcal?: number | null;
}

// One metric's current → proposed as a labeled before/after bar.
function ScoreBar({
  label,
  current,
  proposed,
  hint,
}: {
  label: string;
  current: number;
  proposed: number;
  hint: string;
}) {
  const up = proposed > current;
  const down = proposed < current;
  return (
    <div className="lm-score">
      <div className="lm-score-head">
        <span className="lm-score-label">{label}</span>
        <span className="lm-score-nums mono tnum">
          {pct(current)} <span className="lm-score-arrow">→</span>{" "}
          <b className={up ? "up" : down ? "down" : ""}>{pct(proposed)}</b>
        </span>
      </div>
      <div className="lm-score-track">
        <span className="lm-score-cur" style={{ width: pct(current) }} />
        <span
          className={"lm-score-prop" + (up ? " up" : down ? " down" : "")}
          style={{ width: pct(proposed) }}
        />
      </div>
      <div className="lm-score-hint">{hint}</div>
    </div>
  );
}

// The live retest as it streams: the current phase, the rule the corrector wrote,
// and each meal scored with the rule vs without as it lands.

// The live re-tune as the design's two parallel scoring panels: "Fit to you"
// (your confirmed meals — should improve) and "USDA / everyday" (reference foods —
// must not drop), each streaming base → tuned calorie accuracy per meal as the
// Phoenix experiment scores them.
function RetuneLive({
  phase,
  rules,
  rows,
}: {
  phase: string;
  rules: PreferenceRule[];
  rows: LiveRow[];
}) {
  // No live preview panels: both sets are scored as atomic Phoenix experiments (no
  // trickle), so showing an empty/half-filled grid is pointless. The live view is
  // just the status + the new rule; the per-meal results appear in the collapsible
  // "See your experiment results" under the Updated event once Arize is read back.
  const allDone = rows.length > 0 && rows.every((r) => r.before != null);
  return (
    <div className="rt-live">
      <div className="rt-badge">
        {allDone ? (
          <Check size={13} aria-hidden="true" />
        ) : (
          <span className="lm-spinner" aria-hidden="true" />
        )}
        Updating · {allDone ? "complete" : "live"}
      </div>
      <div className="rt-headline">{phase}</div>
      {rules.length > 0 && (
        <div className="rt-rule">
          <span>
            <b>New rule DietTrace learned — </b>
            {rules[0].rule}
          </span>
        </div>
      )}
    </div>
  );
}

// One scoring panel: Meal · Base · Tuned, streaming a row at a time (a pending row
// shows a spinner on the meal currently being scored, a dash on the rest).
function ScorePanel({
  title,
  tone,
  goal,
  rows,
}: {
  title: string;
  tone: string;
  goal: string;
  rows: LiveRow[];
}) {
  const asPct = (v: number) => `${Math.round(v * 100)}%`;
  return (
    <div className="rt-panel">
      <div className="rt-panel-title">
        <span className="rt-panel-dot" style={{ background: tone }} aria-hidden="true" />
        {title}
      </div>
      <div className="rt-panel-goal">{goal}</div>
      <div className="rt-cols">
        <span className="rt-colhead">Meal</span>
        <span className="rt-colhead">Base</span>
        <span className="rt-colhead">Tuned</span>
        {rows.map((r, i) => {
          const scored = r.before != null && r.after != null;
          const up = scored && (r.after as number) > (r.before as number);
          const down = scored && (r.after as number) < (r.before as number);
          return (
            <Fragment key={i}>
              <span className="rt-name">{r.text}</span>
              <span className="rt-score base">
                {r.before != null ? asPct(r.before) : "—"}
              </span>
              <span
                className={
                  "rt-score " + (!scored ? "pending" : up ? "up" : down ? "down" : "")
                }
              >
                {/* Scores arrive out of order (both sets run as Phoenix
                    experiments) — so an unscored row is always a plain dash, never
                    a spinner that would imply "this one is next". */}
                {r.after != null ? asPct(r.after) : "—"}
              </span>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

function RetuneResult({ result }: { result: LearningRetuneResult }) {
  const [why, setWhy] = useState(false);
  if (!result.ok) {
    const msg =
      result.reason === "not_enough_corrections"
        ? `Give DietTrace at least ${result.need} correction${result.need === 1 ? "" : "s"} first (you have ${result.have}).`
        : result.reason === "no_new_corrections"
          ? "Nothing new to fold in — every correction is already learned. Make a new correction, then update."
          : "DietTrace couldn't propose a change — try again.";
    return <div className="lm-retune-note">{msg}</div>;
  }
  const cur = result.current as RetuneScores;
  const prop = result.proposed as RetuneScores;
  const v = result.verdict!;
  return (
    <div className="lm-result">
      <div className={"lm-verdict " + (result.shipped ? "shipped" : "held")}>
        <span className="lm-verdict-tag mono">
          {result.shipped ? "✓ Kept" : "Skipped"}
        </span>
        <span className="lm-verdict-reason">
          {result.shipped
            ? "It got more accurate on your meals, and stayed accurate on everyday foods — so the change was kept."
            : "It didn't make your meals more accurate (or it would have hurt everyday foods), so nothing changed."}
        </span>
      </div>

      <div className="lm-scores">
        <div className="lm-scores-legend">
          Calorie accuracy, <b>before</b>{" "}
          <span className="lm-score-arrow">→</span> <b>after</b> updating:
        </div>
        <ScoreBar
          label="On your meals"
          current={cur.fit}
          proposed={prop.fit}
          hint={`how close it gets on the ${result.fit_cases} meals you confirmed`}
        />
        <ScoreBar
          label="On everyday foods"
          current={cur.usda}
          proposed={prop.usda}
          hint={`how close it gets on ${result.usda_cases} standard reference foods — this has to stay accurate`}
        />
      </div>

      {result.rules && result.rules.length > 0 && (
        <div className="lm-rules">
          <div className="lm-sub mono">
            {result.shipped ? "What it learned" : "What it proposed"}
          </div>
          {result.rules.map((r, i) => (
            <div className="lm-rule" key={i}>
              <Sparkles size={13} className="lm-rule-icon" aria-hidden="true" />
              <div className="lm-rule-body">
                <div className="lm-rule-text">{r.rule}</div>
                <div className="lm-rule-why">{r.rationale}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        className="lm-why-cta"
        aria-expanded={why}
        onClick={() => setWhy((s) => !s)}
      >
        {why ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        How was this decided?
      </button>
      {why && (
        <ol className="lm-why">
          <li>DietTrace turned your corrections into <b>general rules</b>.</li>
          <li>
            DietTrace re-logged your confirmed meals <b>with</b> the rules and{" "}
            <b>without</b> — checked against your own numbers.
          </li>
          <li>It re-ran the <b>USDA</b> set so personalizing can&apos;t hurt general accuracy.</li>
          <li>
            It applies only if <b>your-meal accuracy improves</b> and USDA holds (within{" "}
            {Math.round(v.eps * 100)}%). All as Phoenix evals.
          </li>
        </ol>
      )}
    </div>
  );
}

// The finished experiment, pulled from Arize over MCP: BOTH sets — Your Dataset and
// USDA — shown as the same two-column Base → Tuned chart, collapsible under the
// "Updated" event.
function ExperimentResults({
  rows,
  experimentUrl,
}: {
  rows: ExperimentRow[];
  experimentUrl?: string;
}) {
  const [open, setOpen] = useState(true);
  const fit = rows.filter((r) => r.set === "fit");
  const usda = rows.filter((r) => r.set === "usda");
  if (!fit.length && !usda.length) return null;
  return (
    <section className="exp-results">
      <button
        type="button"
        className="exp-results-toggle"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        See your experiment results
      </button>
      {open && (
        <div className="exp-results-body">
          <p className="exp-results-sub">
            {fit.length + usda.length} meals scored in Phoenix.
          </p>
          <p className="exp-results-accuracy">
            <b>Accuracy</b>{" "}= how close DietTrace&apos;s calorie estimate was for
            each meal.
          </p>
          <div className="rt-panels">
            <ScorePanel
              title="Your Dataset"
              tone="var(--accent)"
              goal="meals you confirmed"
              rows={fit}
            />
            <ScorePanel
              title="USDA"
              tone="var(--macro-carb)"
              goal="reference foods"
              rows={usda}
            />
          </div>
          {experimentUrl && (
            <a
              className="phoenix-exp-link"
              href={experimentUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              open the experiment in Phoenix ↗
            </a>
          )}
        </div>
      )}
    </section>
  );
}

export function LearningObservability({
  reloadSignal = 0,
  autoRetune = 0,
  agentEvents = [],
  onRetuneComplete,
}: {
  reloadSignal?: number;
  // Bumped by the page when the supervisor's per-meal decision is "retune", so
  // the panel runs the gated eval on its own — the agent drives it, not a click.
  autoRetune?: number;
  // The supervisor's per-meal decisions, newest first (the activity feed).
  agentEvents?: AgentEvent[];
  // When a gated eval finishes, the outcome is handed up to the page so it lives in
  // the single persisted feed (survives reload) rather than panel-local state.
  onRetuneComplete?: (
    event: AgentEvent,
    shipped?: boolean,
    retuneNo?: number | null,
  ) => void;
}) {
  const [prefs, setPrefs] = useState<PreferencesResponse | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [retuning, setRetuning] = useState(false);
  const [result, setResult] = useState<LearningRetuneResult | null>(null);
  const [livePhase, setLivePhase] = useState("");
  const [liveRules, setLiveRules] = useState<PreferenceRule[]>([]);
  const [liveRows, setLiveRows] = useState<LiveRow[]>([]);
  // A live mirror of liveRows so the "done" handler can read the FINAL rows (the
  // state closure would be stale) to attach them to the persisted retune event.
  const liveRowsRef = useRef<LiveRow[]>([]);
  // Link to the Phoenix experiment when the fit set is scored in Arize over MCP.
  const [experimentUrl, setExperimentUrl] = useState("");
  const [showData, setShowData] = useState(false);
  const [showCorr, setShowCorr] = useState(false);
  // The agent-state modal (the deep dive behind the icon).
  const [stateOpen, setStateOpen] = useState(false);
  // The "Retune now" confirm modal — manual override of the auto-retune threshold.
  const [retuneConfirmOpen, setRetuneConfirmOpen] = useState(false);
  // The user's freeform "goals & eating style" — the corrector's standing context.
  const [profileText, setProfileText] = useState("");
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileDraft, setProfileDraft] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  const refresh = useCallback(() => {
    getPreferences().then(setPrefs).catch(() => {});
    listLearningFeedback()
      .then((r) => setFeedback(r.feedback))
      .catch(() => {});
    getProfile()
      .then((r) => setProfileText(r.profile_text))
      .catch(() => {});
  }, []);

  const startEditProfile = () => {
    setProfileDraft(profileText);
    setEditingProfile(true);
  };
  const saveProfile = () => {
    const text = profileDraft.trim();
    setSavingProfile(true);
    setProfile(text)
      .then(() => {
        setProfileText(text);
        setEditingProfile(false);
      })
      .catch(() => {})
      .finally(() => setSavingProfile(false));
  };

  // Refetch on mount and whenever the page signals a correction/confirmation
  // happened — so the loop stays in sync and corrections persist across the day
  // navigation that used to drop them.
  useEffect(() => refresh(), [refresh, reloadSignal]);

  const runRetune = (full = false) => {
    if (retuning) return;
    setRetuning(true);
    setResult(null);
    setLivePhase("Suggesting a change…");
    setLiveRules([]);
    setLiveRows([]);
    liveRowsRef.current = [];
    setExperimentUrl("");
    const onEvent = (e: LearningRetuneEvent) => {
      if (e.type === "phase") setLivePhase(e.label);
      else if (e.type === "rule") setLiveRules(e.rules);
      else if (e.type === "phoenix") setExperimentUrl(e.experiment_url);
      else if (e.type === "manifest") {
        const rows = e.rows.map((r) => ({
          set: r.set,
          text: r.text,
          before: null,
          after: null,
        }));
        liveRowsRef.current = rows;
        setLiveRows(rows);
      } else if (e.type === "score") {
        // Fill the i-th row of this set (1-based). Compute from the REF (synchronous
        // source of truth) so a burst of scores + the "done" event all see the latest
        // rows even before React flushes setLiveRows — the persisted event needs them.
        let seen = 0;
        const next = liveRowsRef.current.map((row) => {
          if (row.set !== e.set) return row;
          seen += 1;
          return seen === e.i
            ? {
                ...row,
                before: e.before,
                after: e.after,
                expected: e.expected,
                baseKcal: e.base_kcal ?? null,
                tunedKcal: e.tuned_kcal ?? null,
              }
            : row;
        });
        liveRowsRef.current = next;
        setLiveRows(next);
      } else if (e.type === "done") {
        setResult(e);
        if (e.ok) {
          const rule = e.rules?.[0]?.rule;
          // Both-set before→after, so the feed renders a full "Accuracy recap"
          // (Your Dataset + USDA), not one raw fit number.
          const recap =
            e.current && e.proposed
              ? {
                  shipped: Boolean(e.shipped),
                  fitBefore: e.current.fit,
                  fitAfter: e.proposed.fit,
                  usdaBefore: e.current.usda,
                  usdaAfter: e.proposed.usda,
                }
              : undefined;
          onRetuneComplete?.(
            {
              id: `retune-${Date.now()}`,
              ts: Date.now(),
              op: "retune",
              reason: e.shipped
                ? (rule ?? "a new rule is now in effect")
                : "no change — it wasn't more accurate",
              // The recap replaces the raw "your-meal accuracy 61% → 86%" line, but
              // keep the blue Phoenix-MCP node like the other feed events.
              phoenix:
                e.scored_via === "phoenix"
                  ? "pulled experiment results from Phoenix"
                  : undefined,
              when: "now",
              recap,
              // Persist the per-meal results ON the event so they survive a reload.
              experiment:
                e.scored_via === "phoenix"
                  ? {
                      rows: liveRowsRef.current,
                      experimentUrl: e.experiment_url,
                    }
                  : undefined,
            },
            // On a SHIP, this retune consumed every pending correction — let the page
            // flip those feedback events to "used in retune N" (the bumped version).
            e.shipped,
            e.version,
          );
        }
      }
    };
    learningRetuneStream(onEvent, full)
      .catch(() => setResult({ ok: false, reason: "corrector_failed" }))
      .finally(() => {
        setRetuning(false);
        refresh();
      });
  };

  // When the supervisor decides "retune" on a logged meal, run the gated eval
  // automatically — the agent triggers it, the panel just shows it happening.
  // Fire ONLY on a genuinely new signal (the counter went up), never on mount:
  // resetting unmounts + remounts this panel, and a stale counter from an earlier
  // retune this session would otherwise auto-run a retune the moment we remount.
  const lastAutoRetune = useRef(autoRetune);
  useEffect(() => {
    const isNew = autoRetune > lastAutoRetune.current;
    lastAutoRetune.current = autoRetune;
    if (isNew && !retuning) runRetune();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRetune]);

  const removeCorrection = (id: number) =>
    deleteLearningFeedback(id).then(refresh).catch(() => {});

  const corrections = prefs?.corrections ?? 0;
  const newCorr = prefs?.new_corrections ?? 0;
  const confirmations = prefs?.confirmations ?? 0;
  const confirmed = prefs?.confirmed ?? [];
  const custom = prefs?.confirmations_custom ?? 0;
  const seeded = prefs?.confirmations_seeded ?? 0;
  // The feed: re-tune events the panel raised + the per-meal decisions from the page.
  const feedEvents = agentEvents;
  const latest = feedEvents[0];
  // The most recent retune that carries persisted experiment results — drives the
  // collapsible "See your experiment results" under the Updated event, restored
  // straight from the persisted feed so it survives a reload.
  const retuneExperiment = feedEvents.find(
    (e) => e.op === "retune" && e.experiment && e.experiment.rows.length > 0,
  )?.experiment;

  return (
    <>
      {/* ── Rail: live status + the autonomous agent-activity trace timeline ── */}
      <div className="dash-head">
        <div className="rail-status">
          <div className="rail-live">
            <span className="rail-live-dot" aria-hidden="true" />
            {retuning ? (
              <span>
                Thinking
                <span className="dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
              </span>
            ) : (
              <span>DietTrace is watching your diet log</span>
            )}
          </div>
        </div>
        <div className="dash-head-actions">
          <Tooltip
            label={
              retuning
                ? "A retune is already running"
                : newCorr === 0
                  ? "Correct a meal first — there's nothing new to fold in"
                  : "Fold your corrections into the agent now"
            }
          >
            <button
              type="button"
              className="dash-retune-btn"
              onClick={() => setRetuneConfirmOpen(true)}
              disabled={newCorr === 0 || retuning}
              aria-label="Retune now"
            >
              <RotateCcw size={13} /> Retune now
            </button>
          </Tooltip>
          <button
            type="button"
            className="dash-state-btn"
            onClick={() => setStateOpen(true)}
            aria-label="Open agent state"
          >
            <Gauge size={14} /> state
          </button>
        </div>
      </div>
      {/* While a re-tune streams, show the live per-meal scoring right in the
          rail — every dataset point re-scored base vs tuned as the eval runs. */}
      {retuning && (
        <>
          <RetuneLive phase={livePhase} rules={liveRules} rows={liveRows} />
          {experimentUrl && (
            <a
              className="phoenix-exp-link"
              href={experimentUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Your meals scored as a Phoenix experiment — view in Phoenix ↗
            </a>
          )}
        </>
      )}
      {/* The experiment's per-meal results ride UNDER the most recent "Updated"
          event in the feed (collapsible), not as a footer at the bottom. */}
      <AgentFeed
        events={feedEvents}
        running={retuning}
        retuneDetail={
          !retuning && retuneExperiment ? (
            <ExperimentResults
              rows={retuneExperiment.rows}
              experimentUrl={retuneExperiment.experimentUrl}
            />
          ) : null
        }
      />
      {feedEvents.length === 0 && !retuning && (
        <p className="agent-feed-empty">
          Log a meal and DietTrace&apos;s decisions show up here.
        </p>
      )}

      {/* ── State modal: the deep dive behind the icon ────────────────────── */}
      {retuneConfirmOpen && (
        <Modal
          onClose={() => setRetuneConfirmOpen(false)}
          labelledBy="retune-confirm-title"
          className="modal-narrow"
        >
          <div className="reset-dialog">
            <div className="reset-dialog-eyebrow retune-dialog-eyebrow mono">
              Retune
            </div>
            <h2 id="retune-confirm-title" className="reset-dialog-title">
              Retune DietTrace now?
            </h2>
            <p className="reset-dialog-body">
              You&apos;ve taught it {corrections} correction
              {corrections === 1 ? "" : "s"}. Retuning turns them into a rule it
              follows — but it only keeps the change if your meals come out more
              accurate. If not, nothing changes.
            </p>
            <div className="reset-dialog-actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setRetuneConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-accent"
                onClick={() => {
                  setRetuneConfirmOpen(false);
                  runRetune();
                }}
              >
                Retune now
              </button>
            </div>
          </div>
        </Modal>
      )}
      {stateOpen && (
        <Modal onClose={() => setStateOpen(false)} labelledBy="agent-state-title">
          <h2 id="agent-state-title" className="agent-state-title">
            Agent state
          </h2>
          <div className="agent-state-grid">
            <div className="agent-state-row">
              <div className="agent-state-stat">
                <span className="agent-state-num">{confirmations}</span>
                <span className="agent-state-cap">
                  meals in your dataset · <b>{custom}</b> from you · {seeded} seeded
                </span>
              </div>
              <div className="agent-state-stat">
                <span className="agent-state-num">{corrections}</span>
                <span className="agent-state-cap">
                  correction{corrections === 1 ? "" : "s"} you&apos;ve made ·{" "}
                  <b>{newCorr}</b> new to learn
                </span>
              </div>
            </div>
            {latest && (
              <div className="agent-state-stat agent-state-decision">
                <span className="agent-state-dec-lab mono">Latest decision</span>
                <span className="agent-state-dec-text">
                  {latest.reason}
                  {latest.detail ? ` (${latest.detail})` : ""}
                </span>
              </div>
            )}
          </div>
          <p className="agent-state-mcp">
            Your dataset is synced to Phoenix over MCP.
          </p>

          <div className="lo">

      {/* ── Your context: the freeform profile the corrector reads when tuning ─ */}
      <section className="dash-card lo-context">
        <div className="lo-context-head">
          <span className="dash-card-head mono">your context</span>
          {!editingProfile && (
            <button
              type="button"
              className="lo-context-edit"
              onClick={startEditProfile}
            >
              <Pencil size={12} aria-hidden="true" />
              {profileText ? "Edit" : "Add"}
            </button>
          )}
        </div>
        <p className="lo-hint">
          Your goals &amp; eating style, in your words. DietTrace reads this
          when it tunes — so what it learns fits who you are.
        </p>
        {editingProfile ? (
          <div className="lo-context-edit-box">
            <textarea
              className="lo-context-textarea"
              value={profileDraft}
              rows={3}
              autoFocus
              aria-label="your goals and eating style"
              placeholder="e.g. Marathon training, mostly plant-based — I like my carbs high on long-run days."
              onChange={(e) => setProfileDraft(e.target.value)}
            />
            <div className="lo-context-actions">
              <button
                type="button"
                className="lo-context-cancel"
                onClick={() => setEditingProfile(false)}
                disabled={savingProfile}
              >
                Cancel
              </button>
              <button
                type="button"
                className="lo-context-save"
                onClick={saveProfile}
                disabled={savingProfile}
              >
                {savingProfile ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        ) : profileText ? (
          <blockquote className="lo-context-text">
            <Sparkles size={13} className="lm-rule-icon" aria-hidden="true" />
            <span>{profileText}</span>
          </blockquote>
        ) : (
          <p className="lo-empty">
            No context yet. Add your goals &amp; eating style so DietTrace tunes
            to you, not a generic average.
          </p>
        )}
      </section>

      {/* ── Corrections you've taught (meal + what you said), persisted ───── */}
      <section className="dash-card lo-corrs">
        <button
          type="button"
          className="lo-dataset-head"
          aria-expanded={showCorr}
          onClick={() => setShowCorr((s) => !s)}
        >
          {showCorr ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span className="dash-card-head mono">
            your corrections · {feedback.length}
          </span>
        </button>
        {showCorr &&
          (feedback.length === 0 ? (
            <p className="lo-empty">
              None yet. Tell DietTrace what it got wrong on any meal — your fixes
              land here.
            </p>
          ) : (
            <>
              {[
                { lab: "Not used in an update yet", rows: feedback.filter((f) => !f.processed) },
                { lab: "Already learned", rows: feedback.filter((f) => f.processed) },
              ]
                .filter((g) => g.rows.length > 0)
                .map((g) => (
                  <div className="lo-corr-group" key={g.lab}>
                    <div className="lo-corr-grouplab mono">
                      {g.lab} · {g.rows.length}
                    </div>
                    <ul className="lo-corr-list">
                      {g.rows.map((f) => (
                        <li
                          className={"lo-corr" + (f.processed ? " done" : "")}
                          key={f.id}
                        >
                          <div className="lo-corr-body">
                            <div className="lo-corr-meal">
                              {f.meal_text || "general note"}
                            </div>
                            <div className="lo-corr-text">“{f.feedback_text}”</div>
                          </div>
                          <div className="lo-corr-actions">
                            <button
                              type="button"
                              className="lo-corr-del"
                              aria-label="delete correction"
                              onClick={() => removeCorrection(f.id)}
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
            </>
          ))}
      </section>

      {/* ── The test set the agent is checked against ─────────────────────── */}
      {confirmations > 0 && (
        <section className="dash-card lo-dataset">
          <button
            type="button"
            className="lo-dataset-head"
            aria-expanded={showData}
            onClick={() => setShowData((s) => !s)}
          >
            {showData ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span className="dash-card-head mono">
              your dataset · {confirmations} meal{confirmations === 1 ? "" : "s"}
            </span>
          </button>
          {showData && (
            <p className="lo-dataset-note">
              Meals you&apos;ve confirmed as right, synced to your Phoenix dataset
              over MCP. Every update is checked against these — but never learns from
              them — so the test stays honest.
            </p>
          )}
          {showData && (
            <ul className="lo-data-list">
              {confirmed.map((c) => (
                <li className="lo-data-row" key={c.id}>
                  <span className="lo-data-text">{c.meal_text}</span>
                  <span className="lo-data-kcal mono tnum">
                    {Math.round(c.calories)} kcal
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
          </div>
        </Modal>
      )}
    </>
  );
}
