"use client";

// "Persona details" recap — a READ-ONLY summary of the current account state.
// It is NOT the onboarding explainer and has NO persona switcher (changing the
// persona requires a Reset). It pulls live data so it reflects reality:
//   • who    — the seeded persona, or the user's own body stats
//   • targets — the saved macros (/goals)
//   • knows   — the lifestyle/preferences feeding the corrector (/profile)
//   • taught  — corrections the user made (/learning/feedback)
//   • learned — the shipped retune rules + version (/preferences)
//   • doing   — avg confidence + meals logged on their meals (/trust)
//   • test set — meals confirmed as held-out ground truth (/preferences)
import { useEffect, useState } from "react";
import { Pencil, Sparkles } from "lucide-react";
import {
  getGoals,
  getPreferences,
  getProfile,
  getTrust,
  listLearningFeedback,
  setProfile as saveProfile,
  type FeedbackItem,
  type Goal,
  type PreferencesResponse,
  type TrustReport,
} from "@/lib/api";
import { Modal } from "@/components/modal";
import type { Setup } from "@/lib/setup";

const ACTIVITY_LABEL: Record<string, string> = {
  sedentary: "Sedentary",
  light: "Lightly active",
  moderate: "Moderately active",
  active: "Active",
  very_active: "Very active",
};
const GOAL_LABEL: Record<string, string> = {
  cut: "Lose weight",
  maintain: "Maintain",
  bulk: "Gain weight",
};
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v * 100)}%`;

export function RecapModal({
  setup,
  onViewDay,
  onClose,
}: {
  setup: Setup;
  onViewDay?: (iso: string) => void;
  onClose: () => void;
}) {
  const [prefs, setPrefs] = useState<PreferencesResponse | null>(null);
  const [profile, setProfile] = useState("");
  const [goals, setGoals] = useState<Goal[]>([]);
  const [trust, setTrust] = useState<TrustReport | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  // Inline editing of the lifestyle/context note (so it can be added/edited here,
  // not just when one already exists).
  const [editingContext, setEditingContext] = useState(false);
  const [draft, setDraft] = useState("");
  const [savingContext, setSavingContext] = useState(false);

  const saveContext = async () => {
    if (savingContext) return;
    setSavingContext(true);
    try {
      const r = await saveProfile(draft);
      setProfile(r.profile_text ?? draft);
      setEditingContext(false);
    } catch {
      /* leave the editor open so the user can retry */
    } finally {
      setSavingContext(false);
    }
  };

  useEffect(() => {
    getPreferences().then(setPrefs).catch(() => {});
    getProfile().then((r) => setProfile(r.profile_text)).catch(() => {});
    getGoals().then((r) => setGoals(r.goals)).catch(() => {});
    getTrust().then(setTrust).catch(() => {});
    listLearningFeedback().then((r) => setFeedback(r.feedback)).catch(() => {});
  }, []);

  const isPersona = setup.kind === "persona";
  const persona = isPersona ? setup.result.persona : null;
  const inputs = setup.inputs;
  const macro = (code: string) => goals.find((g) => g.code === code)?.target;

  const rules = prefs?.block?.provenance ?? [];
  const version = prefs?.block?.version ?? 0;
  const corrections = prefs?.corrections ?? 0;
  const confirmations = prefs?.confirmations ?? 0;

  const MACROS: { code: string; label: string; unit: string; color: string }[] = [
    { code: "208", label: "Calories", unit: "kcal", color: "var(--macro-cal)" },
    { code: "203", label: "Protein", unit: "g", color: "var(--macro-protein)" },
    { code: "205", label: "Carbs", unit: "g", color: "var(--macro-carb)" },
    { code: "204", label: "Fat", unit: "g", color: "var(--macro-fat)" },
  ];

  return (
    <Modal onClose={onClose} labelledBy="recap-title">
      <div className="rc">
        {/* ── Who ─────────────────────────────────────────────────────────── */}
        <span className="su-eyebrow mono">
          {isPersona ? "Loaded a demo" : "Your setup"}
        </span>
        <h2 id="recap-title" className="su-title">
          {isPersona ? persona!.label : "About you"}
        </h2>
        {isPersona ? (
          <p className="su-sub">{persona!.blurb}</p>
        ) : (
          <dl className="su-grid">
            {inputs.sex && (
              <div className="su-row">
                <dt>Gender</dt>
                <dd>{cap(inputs.sex)}</dd>
              </div>
            )}
            {inputs.weight_kg != null && (
              <div className="su-row">
                <dt>Weight</dt>
                <dd>{inputs.weight_kg} kg</dd>
              </div>
            )}
            {inputs.age != null && (
              <div className="su-row">
                <dt>Age</dt>
                <dd>{inputs.age} yr</dd>
              </div>
            )}
            {inputs.height_cm != null && (
              <div className="su-row">
                <dt>Height</dt>
                <dd>{inputs.height_cm} cm</dd>
              </div>
            )}
            {inputs.activity && (
              <div className="su-row">
                <dt>Activity</dt>
                <dd>{ACTIVITY_LABEL[inputs.activity] ?? inputs.activity}</dd>
              </div>
            )}
            {inputs.goal && (
              <div className="su-row">
                <dt>Goal</dt>
                <dd>{GOAL_LABEL[inputs.goal] ?? inputs.goal}</dd>
              </div>
            )}
          </dl>
        )}

        {/* ── Targets ─────────────────────────────────────────────────────── */}
        <section className="rc-section">
          <div className="su-sub mono">Daily targets</div>
          <div className="rc-macros">
            {MACROS.map((m) => (
              <div className="rc-macro" key={m.code}>
                <span className="rc-macro-val" style={{ color: m.color }}>
                  {macro(m.code) != null ? Math.round(macro(m.code)!) : "—"}
                </span>
                <span className="rc-macro-label">
                  {m.label}
                  {macro(m.code) != null ? ` (${m.unit})` : ""}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* ── What it knows about you (editable) ──────────────────────────── */}
        <section className="rc-section">
          <div className="rc-context-head">
            <span className="su-sub mono">What it knows about you</span>
            {!editingContext && (
              <button
                type="button"
                className="lo-context-edit"
                onClick={() => {
                  setDraft(profile);
                  setEditingContext(true);
                }}
              >
                <Pencil size={12} aria-hidden="true" /> {profile ? "Edit" : "Add"}
              </button>
            )}
          </div>
          {editingContext ? (
            <div className="lo-context-edit-box">
              <textarea
                className="lo-context-textarea"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                aria-label="your goals and eating style"
                placeholder="Your goals and eating style, in your words — e.g. “marathon training, mostly plant-based, big appetite after long runs.”"
                autoFocus
              />
              <div className="lo-context-actions">
                <button
                  type="button"
                  className="lo-context-cancel"
                  onClick={() => setEditingContext(false)}
                  disabled={savingContext}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="lo-context-save"
                  onClick={saveContext}
                  disabled={savingContext}
                >
                  {savingContext ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          ) : profile ? (
            <blockquote className="su-lifestyle">{profile}</blockquote>
          ) : (
            <p className="su-empty">
              No note yet — add your goals and eating style so DietTrace tunes to
              you.
            </p>
          )}
        </section>

        {/* ── What you've taught it ───────────────────────────────────────── */}
        <section className="rc-section">
          <div className="su-sub mono">What you’ve taught it · {corrections}</div>
          {feedback.length ? (
            <ul className="rc-list">
              {feedback.slice(0, 4).map((f) => (
                <li className="rc-corr" key={f.id}>
                  <span className="rc-corr-meal">{f.meal_text || "general note"}</span>
                  <span className="rc-corr-text">“{f.feedback_text}”</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="su-empty">No corrections yet.</p>
          )}
        </section>

        {/* ── What it's learned (retunes) ─────────────────────────────────── */}
        <section className="rc-section">
          <div className="su-sub mono">
            What it’s learned{version ? ` · v${version}` : ""}
          </div>
          {rules.length ? (
            <ul className="rc-list">
              {rules.map((r, i) => (
                <li className="rc-rule" key={i}>
                  <Sparkles size={13} className="lm-rule-icon" aria-hidden="true" />
                  <span>{r.rule}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="su-empty">
              Not tuned yet — update in the panel to turn your corrections into
              rules it follows.
            </p>
          )}
        </section>

        {/* ── How it's doing on your meals ────────────────────────────────── */}
        <section className="rc-section">
          <div className="su-sub mono">How it’s doing on your meals</div>
          <div className="rc-stats">
            <div className="rc-stat">
              <span className="rc-stat-val">{pct(trust?.mean_confidence)}</span>
              <span className="rc-stat-label">avg confidence</span>
            </div>
            <div className="rc-stat">
              <span className="rc-stat-val">{trust?.count ?? 0}</span>
              <span className="rc-stat-label">meals logged</span>
            </div>
            <div className="rc-stat">
              <span className="rc-stat-val">{confirmations}</span>
              <span className="rc-stat-label">kept aside in your dataset</span>
            </div>
          </div>
          <p className="rc-foot">
            Your dataset is the meals you’ve confirmed — checked against, never
            learned from, so DietTrace’s grade on you stays honest.
            {isPersona && onViewDay && (
              <button
                type="button"
                className="rc-link"
                onClick={() => {
                  onViewDay(setup.result.dataset_date);
                  onClose();
                }}
              >
                {" "}
                See the confirmed meals →
              </button>
            )}
          </p>
        </section>

        <div className="su-actions">
          <button type="button" className="su-done" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </Modal>
  );
}
