"use client";

// The learning loop, made permanent in the Observability column (no modal). It
// shows — at all times, not hidden behind a click — what the agent has learned,
// the gated re-tune streaming live (the rule it writes, then every meal re-scored
// with the rule vs without, then the ship verdict), the corrections you've taught
// (meal + what you said, persisted), and the held-out dataset it's tested against.
// This is the observability-everywhere rule applied to the loop itself.
import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Gauge,
  Pencil,
  Sparkles,
  Trash2,
} from "lucide-react";
import { AgentFeed, type AgentEvent } from "@/components/agent-decision";
import { Modal } from "@/components/modal";
import {
  deleteLearningFeedback,
  editLearningFeedback,
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
// One score cell — the running row spins, not-yet-scored rows show a dash.
function Cell({ value, active }: { value: number | null; active: boolean }) {
  if (value != null) return <span className="lm-cell-val tnum">{pct(value)}</span>;
  if (active) return <span className="lm-cell-spin" aria-label="scoring" />;
  return <span className="lm-cell-dash" aria-hidden="true">—</span>;
}

function RetuneLive({
  phase,
  rules,
  rows,
}: {
  phase: string;
  rules: PreferenceRule[];
  rows: LiveRow[];
}) {
  // The row currently being scored = the first one without a result yet.
  const activeIdx = rows.findIndex((r) => r.before == null);
  return (
    <div className="lm-live">
      <div className="lm-live-phase">
        <span className="lm-spinner" aria-hidden="true" />
        {phase}
      </div>
      {rules.length > 0 && (
        <div className="lm-live-rule">
          <Sparkles size={13} className="lm-rule-icon" aria-hidden="true" />
          <span>{rules[0].rule}</span>
        </div>
      )}
      {rows.length > 0 && (
        <div className="lm-live-table">
          <div className="lm-live-caption">
            Base agent <span className="lm-score-arrow">→</span> agent tuned to you
            · calorie accuracy per meal (100% = exact)
          </div>
          <div className="lm-live-thead">
            <span aria-hidden="true" />
            <span aria-hidden="true" />
            <span className="lm-live-th">Base</span>
            <span className="lm-live-th">Tuned</span>
          </div>
          <ul className="lm-live-rows">
            {rows.map((r, i) => {
              const up = r.after != null && r.before != null && r.after > r.before;
              const down = r.after != null && r.before != null && r.after < r.before;
              return (
                <li
                  className={"lm-live-row" + (i === activeIdx ? " active" : "")}
                  key={i}
                >
                  <span className={"lm-live-set mono lm-set-" + r.set}>
                    {r.set === "fit" ? "you" : "usda"}
                  </span>
                  <span className="lm-live-text">{r.text}</span>
                  <span className="lm-live-cell">
                    <Cell value={r.before} active={i === activeIdx} />
                  </span>
                  <span className={"lm-live-cell" + (up ? " up" : down ? " down" : "")}>
                    <Cell value={r.after} active={i === activeIdx} />
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
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
          ? "Nothing new to fold in — every correction is already learned. Make a new correction, then re-tune."
          : "The corrector couldn't propose a change — try again.";
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
          <span className="lm-score-arrow">→</span> <b>after</b> re-tuning:
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
          hint={`how close it gets on ${result.usda_cases} standard reference foods — this can't drop`}
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
          <li>The corrector turned your corrections into <b>general rules</b>.</li>
          <li>
            The agent re-logged your confirmed meals <b>with</b> the rules and{" "}
            <b>without</b> — scored against your own numbers.
          </li>
          <li>It re-ran the <b>USDA</b> set so personalizing can&apos;t hurt general accuracy.</li>
          <li>
            It ships only if <b>fit improves</b> and USDA holds (within{" "}
            {Math.round(v.eps * 100)}%). All as Arize evals.
          </li>
        </ol>
      )}
    </div>
  );
}

export function LearningObservability({
  reloadSignal = 0,
  autoRetune = 0,
  agentEvents = [],
}: {
  reloadSignal?: number;
  // Bumped by the page when the supervisor's per-meal decision is "retune", so
  // the panel runs the gated eval on its own — the agent drives it, not a click.
  autoRetune?: number;
  // The supervisor's per-meal decisions, newest first (the activity feed).
  agentEvents?: AgentEvent[];
}) {
  const [prefs, setPrefs] = useState<PreferencesResponse | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [retuning, setRetuning] = useState(false);
  const [result, setResult] = useState<LearningRetuneResult | null>(null);
  const [livePhase, setLivePhase] = useState("");
  const [liveRules, setLiveRules] = useState<PreferenceRule[]>([]);
  const [liveRows, setLiveRows] = useState<LiveRow[]>([]);
  // Link to the Phoenix experiment when the fit set is scored in Arize over MCP.
  const [experimentUrl, setExperimentUrl] = useState("");
  const [showData, setShowData] = useState(false);
  const [explain, setExplain] = useState(false);
  // The agent-state modal (the deep dive behind the icon), + re-tune events the
  // panel adds to the feed when a gated eval finishes.
  const [stateOpen, setStateOpen] = useState(false);
  const [retuneEvents, setRetuneEvents] = useState<AgentEvent[]>([]);
  // Quick = sample of standard foods (fast, good for demos); full = the whole set.
  const [mode, setMode] = useState<"quick" | "full">("quick");
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
    setLivePhase("Starting the eval…");
    setLiveRules([]);
    setLiveRows([]);
    setExperimentUrl("");
    const onEvent = (e: LearningRetuneEvent) => {
      if (e.type === "phase") setLivePhase(e.label);
      else if (e.type === "rule") setLiveRules(e.rules);
      else if (e.type === "phoenix") setExperimentUrl(e.experiment_url);
      else if (e.type === "manifest") {
        setLiveRows(
          e.rows.map((r) => ({ set: r.set, text: r.text, before: null, after: null })),
        );
      } else if (e.type === "score") {
        // Fill the i-th row of this set (1-based) with its scores.
        setLiveRows((rows) => {
          let seen = 0;
          return rows.map((row) => {
            if (row.set !== e.set) return row;
            seen += 1;
            return seen === e.i ? { ...row, before: e.before, after: e.after } : row;
          });
        });
      } else if (e.type === "done") {
        setResult(e);
        if (e.ok) {
          const fit =
            e.current && e.proposed
              ? `fit ${pct(e.current.fit)} → ${pct(e.proposed.fit)}`
              : undefined;
          const rule = e.rules?.[0]?.rule;
          setRetuneEvents((curr) => [
            {
              id: `retune-${curr.length}`,
              op: "retune",
              reason: e.shipped
                ? rule
                  ? `shipped: ${rule}`
                  : "shipped a new rule"
                : "no change — the gate held the line",
              detail: fit,
              when: "now",
            },
            ...curr,
          ]);
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
  useEffect(() => {
    if (autoRetune > 0 && !retuning) runRetune();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRetune]);

  const removeCorrection = (id: number) =>
    deleteLearningFeedback(id).then(refresh).catch(() => {});
  const toggleEmphasis = (f: FeedbackItem) =>
    editLearningFeedback(f.id, { weight: f.weight > 1 ? 1 : 2 })
      .then(refresh)
      .catch(() => {});

  const corrections = prefs?.corrections ?? 0;
  const newCorr = prefs?.new_corrections ?? 0;
  const confirmations = prefs?.confirmations ?? 0;
  const confirmed = prefs?.confirmed ?? [];
  // The threshold is the backend's ground truth (min_corrections) so the UI can
  // never drift from it. A retune only folds in NEW (fresh) corrections.
  const minCorr = prefs?.min_corrections ?? 1;
  const ready = newCorr >= minCorr;
  const block = prefs?.block ?? null;
  const custom = prefs?.confirmations_custom ?? 0;
  const seeded = prefs?.confirmations_seeded ?? 0;
  // The feed: re-tune events the panel raised + the per-meal decisions from the page.
  const feedEvents = [...retuneEvents, ...agentEvents];
  const latest = feedEvents[0];

  return (
    <>
      {/* ── Rail: the autonomous agent-activity feed ──────────────────────── */}
      <div className="dash-head">
        <span className="dash-title mono">agent activity</span>
        <button
          type="button"
          className="dash-state-btn"
          onClick={() => setStateOpen(true)}
          aria-label="Open agent state"
        >
          <Gauge size={14} /> state
        </button>
      </div>
      {/* While a re-tune streams, show the live per-meal scoring right in the
          rail — every dataset point re-scored base vs tuned as the eval runs. */}
      {retuning && (
        <section className="dash-card agent-retune-live">
          <div className="dash-card-head mono">re-tuning · live</div>
          <RetuneLive phase={livePhase} rules={liveRules} rows={liveRows} />
          {experimentUrl && (
            <a
              className="phoenix-exp-link"
              href={experimentUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Your meals scored as a Phoenix experiment — view in Arize ↗
            </a>
          )}
        </section>
      )}
      <AgentFeed events={feedEvents} />
      {feedEvents.length === 0 && !retuning && (
        <p className="agent-feed-empty">
          Log a meal and the supervisor&apos;s decisions show up here.
        </p>
      )}

      {/* ── State modal: the deep dive behind the icon ────────────────────── */}
      {stateOpen && (
        <Modal onClose={() => setStateOpen(false)} labelledBy="agent-state-title">
          <h2 id="agent-state-title" className="agent-state-title">
            Agent state
          </h2>
          <div className="agent-state-grid">
            <div className="agent-state-stat">
              <span className="agent-state-num">{confirmations}</span>
              <span className="agent-state-cap">
                held-out points · <b>{custom}</b> from you · {seeded} seeded
              </span>
            </div>
            <div className="agent-state-stat">
              <span className="agent-state-num">{newCorr}</span>
              <span className="agent-state-cap">
                of {corrections} correction{corrections === 1 ? "" : "s"} not yet
                incorporated
              </span>
            </div>
          </div>
          {latest && (
            <p className="agent-state-latest">
              <span className="mono">latest decision:</span> {latest.reason}
              {latest.detail ? ` (${latest.detail})` : ""}
            </p>
          )}
          <p className="agent-state-mcp">
            Held-out points are synced to your Phoenix dataset over MCP.
          </p>

          <div className="lo">
      {/* ── Re-tune: the gated eval, streaming live, always visible ───────── */}
      <section className="dash-card lo-retune">
        <div className="dash-card-head mono">self-tuning · agent-driven</div>
        <p className="lo-counts">
          The supervisor re-tunes on its own once there&apos;s enough signal: it learns
          from your <b>{corrections}</b> correction{corrections === 1 ? "" : "s"}, then
          tests itself on <b>{confirmations}</b> of your meal{confirmations === 1 ? "" : "s"} before keeping any change.
        </p>
        <p className={"lo-fresh" + (ready ? " ready" : "")} aria-live="polite">
          <span className="lo-fresh-dot" aria-hidden="true" />
          {ready
            ? `${newCorr} fresh correction${newCorr === 1 ? "" : "s"} — ready to re-tune`
            : `${newCorr} of ${minCorr} fresh correction${minCorr === 1 ? "" : "s"} — ${
                newCorr === 0 ? "correct a meal" : "one more"
              } to re-tune`}
        </p>
        <div className="lo-retune-action">
          <button
            type="button"
            className="lo-retune-btn"
            onClick={() => runRetune(mode === "full")}
            disabled={retuning || !ready}
            title={
              ready
                ? ""
                : corrections === 0
                  ? "Correct a meal first"
                  : "All corrections are already learned — make a new one to re-tune"
            }
          >
            {retuning ? "re-tuning…" : "Re-tune"}
          </button>
          <span className="lo-mode-seg" role="group" aria-label="Re-tune depth">
            <button
              type="button"
              className={"lo-mode-opt" + (mode === "quick" ? " on" : "")}
              aria-pressed={mode === "quick"}
              disabled={retuning}
              onClick={() => setMode("quick")}
            >
              Quick
            </button>
            <button
              type="button"
              className={"lo-mode-opt" + (mode === "full" ? " on" : "")}
              aria-pressed={mode === "full"}
              disabled={retuning}
              onClick={() => setMode("full")}
            >
              Full
            </button>
          </span>
        </div>
        <p className="lo-mode-hint">
          {mode === "quick"
            ? "Quick: a sample of standard foods — fast, good for demos."
            : "Full: the entire standard set — slower, best accuracy."}
        </p>

        <button
          type="button"
          className="lo-explain-cta"
          aria-expanded={explain}
          onClick={() => setExplain((s) => !s)}
        >
          {explain ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          What is this doing?
        </button>
        {explain && (
          <div className="lo-explain">
            <p>
              Re-tuning takes the corrections you gave on your logged meals and
              folds them into the food-logging agent, so it estimates portions
              <i> your</i> way.
            </p>
            <p>
              To make sure it adapts to you <b>without overfitting</b> — without
              getting worse at logging ordinary foods — it re-scores two sets and
              ships the change only if both hold up:
            </p>
            <ul>
              <li>
                <b>Fit to you</b> — the meals you confirmed, kept <i>out</i> of
                learning so the test stays honest (your held-out ground truth).
              </li>
              <li>
                <b>USDA accuracy</b> — a curated set of standard reference foods,
                so general accuracy can&apos;t regress.
              </li>
            </ul>
            <p>
              Each row below is one meal&apos;s <b>calorie accuracy</b> — the agent{" "}
              <b>before → after</b> tuning (100% = matches the known calories).{" "}
              <span className="lm-tag mono lm-set-fit">you</span> = a meal you
              confirmed · <span className="lm-tag mono lm-set-usda">usda</span> = a
              standard reference food. It&apos;s kept only if your meals improve and
              everyday foods hold.
            </p>
            <p>
              <b>Quick</b> checks a sample of standard foods (fast — good for
              demos); <b>Full</b> checks the whole set (slower — best accuracy,
              the strongest guard against overfitting).
            </p>
          </div>
        )}

        {/* The live streaming view lives in the rail (always visible); here the
            modal just shows the ship verdict once the re-tune is done. */}
        {retuning && (
          <p className="lo-mode-hint">Re-tuning live — watch it in the rail →</p>
        )}
        {result && !retuning && <RetuneResult result={result} />}

        {/* The current learned profile, when nothing is mid-flight. */}
        {!retuning && !result && block && block.provenance.length > 0 && (
          <div className="lm-rules lo-learned">
            <div className="lm-sub mono">what it&apos;s learned</div>
            {block.provenance.map((r, i) => (
              <div className="lm-rule" key={i}>
                <Sparkles size={13} className="lm-rule-icon" aria-hidden="true" />
                <div className="lm-rule-body">
                  <div className="lm-rule-text">{r.rule}</div>
                </div>
              </div>
            ))}
          </div>
        )}
        {!retuning && !result && !block && (
          <p className="lo-empty">
            {ready
              ? "Re-tune to turn your corrections into a rule the agent follows — it's only kept if your meals get more accurate."
              : "Tell the agent what it got wrong on a meal, then re-tune to watch it learn."}
          </p>
        )}
      </section>

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
          Your goals &amp; eating style, in your words. The corrector reads this
          when it tunes the agent — so what it learns fits who you are.
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
            No context yet. Add your goals &amp; eating style so the agent tunes
            to you, not a generic average.
          </p>
        )}
      </section>

      {/* ── Corrections you've taught (meal + what you said), persisted ───── */}
      <section className="dash-card lo-corrs">
        <div className="dash-card-head mono">your corrections</div>
        {feedback.length === 0 ? (
          <p className="lo-empty">
            None yet. Tell the agent what it got wrong on any meal — your fixes
            land here.
          </p>
        ) : (
          <>
            <p className="lo-hint">
              What you told the agent it got wrong. Star one to mark it important.
              Re-tune only learns from <b>new</b> ones — those it&apos;s already
              learned show <span className="lo-done-inline">✓ learned</span>.
            </p>
            <ul className="lo-corr-list">
              {feedback.map((f) => (
                <li className={"lo-corr" + (f.processed ? " done" : "")} key={f.id}>
                  <div className="lo-corr-body">
                    <div className="lo-corr-meal">
                      {f.meal_text || "general note"}
                      {f.processed && (
                        <span className="lo-corr-done mono" title="Already learned — a re-tune won't re-learn it">
                          ✓ learned
                        </span>
                      )}
                      {!f.processed && (
                        <span className="lo-corr-new mono">new</span>
                      )}
                    </div>
                    <div className="lo-corr-text">“{f.feedback_text}”</div>
                  </div>
                  <div className="lo-corr-actions">
                    <button
                      type="button"
                      className={"lo-corr-emph" + (f.weight > 1 ? " on" : "")}
                      aria-pressed={f.weight > 1}
                      aria-label={f.weight > 1 ? "important (click to undo)" : "mark as important"}
                      title={
                        f.weight > 1
                          ? "Marked important — the agent weights this more. Click to undo."
                          : "Mark important — the agent weights this correction more"
                      }
                      onClick={() => toggleEmphasis(f)}
                    >
                      {f.weight > 1 ? "★" : "☆"}
                    </button>
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
          </>
        )}
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
              your test set · {confirmations} meal{confirmations === 1 ? "" : "s"}
            </span>
          </button>
          <p className="lo-dataset-note">
            Meals you&apos;ve confirmed as right, synced to your Phoenix dataset over
            MCP. Every re-tune is tested on these — but never learns from them — so
            the test stays honest.
          </p>
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
