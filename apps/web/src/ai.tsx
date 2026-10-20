import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  CheckCircle2,
  Flag,
  Globe2,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  ThumbsUp,
  TriangleAlert,
} from "lucide-react";
import { api, post, waitJob } from "./client";
import "./ai.css";

type Governance = {
  enabled: boolean;
  data_processing_approved: boolean;
  allow_sample_data: boolean;
  allowed_providers: ("aws" | "azure" | "gcp")[];
  residency_mode: "india_only" | "global_approved";
  daily_request_limit: number;
  daily_token_limit: number;
  max_output_tokens: number;
  runtime_fingerprint: string;
  version: number;
};
type AIState = {
  status: string;
  message: string;
  disclosure: string;
  runtime: {
    enabled: boolean;
    region: string;
    model_id: string;
    global_target: boolean;
    fingerprint: string;
    guardrail_id: string;
    guardrail_version: string;
    issues: string[];
    model_card: string;
  };
  governance: Governance;
  usage: {
    day_utc: string;
    requests: number;
    reserved_tokens: number;
    input_tokens: number;
    output_tokens: number;
    failed_requests: number;
    helpful_feedback: number;
    unsafe_feedback: number;
  };
};
export type AdviceRecord = {
  generation_id: string;
  generated_at: string;
  model_id: string;
  source_region: string;
  destination_regions: string[];
  prompt_version: string;
  guardrail_version: string | null;
  source_version: number;
  evidence_hash: string;
  stale: boolean;
  cache_hit: boolean;
  validation: string;
  latency_ms: number;
  usage: { inputTokens?: number; outputTokens?: number };
  source_guide: string;
  facts: { id: string; field: string; value: unknown }[];
  content: {
    summary: string;
    summary_evidence_ids: string[];
    priority: string;
    observations: { statement: string; evidence_ids: string[] }[];
    actions: {
      id: string;
      title: string;
      guidance: string;
      prerequisite: string;
      evidence_ids: string[];
    }[];
    open_questions: string[];
  };
};
const pretty = (text: string) => text.replaceAll("_", " ");

export function AISettings({
  administrator,
  onSaved,
}: {
  administrator: boolean;
  onSaved: () => void;
}) {
  const [state, setState] = useState<AIState | null>(null),
    [form, setForm] = useState<Governance | null>(null);
  const [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [saved, setSaved] = useState(false);
  useEffect(() => {
    api<AIState>("/ai/status")
      .then((s) => {
        setState(s);
        setForm({
          ...s.governance,
          data_processing_approved:
            s.governance.runtime_fingerprint === s.runtime.fingerprint &&
            s.governance.data_processing_approved,
        });
      })
      .catch((e) => setError(e.message));
  }, []);
  function change<K extends keyof Governance>(key: K, value: Governance[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setSaved(false);
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!state || !form) return;
    setSaving(true);
    setError("");
    setSaved(false);
    const body: Governance = {
      enabled: form.enabled,
      data_processing_approved: form.data_processing_approved,
      allow_sample_data: form.allow_sample_data,
      allowed_providers: form.allowed_providers,
      residency_mode: form.residency_mode,
      daily_request_limit: form.daily_request_limit,
      daily_token_limit: form.daily_token_limit,
      max_output_tokens: form.max_output_tokens,
      runtime_fingerprint: state.runtime.fingerprint,
      version: form.version,
    };
    try {
      const next = await api<AIState>("/ai/governance", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setState(next);
      setForm(next.governance);
      setSaved(true);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <section
      className="card settings-card full-width ai-settings"
      aria-label="Bedrock AI governance"
    >
      <div className="ai-card-title">
        <div className="ai-symbol">
          <Sparkles size={24} />
        </div>
        <div>
          <h2>Amazon Bedrock · client governance</h2>
          <p>
            Claude Opus 5.5 through Mumbai. Customer approval controls every
            evidence transfer.
          </p>
        </div>
        <span className="badge purple">India deployment</span>
      </div>
      {error && (
        <div className="inline-notice red" role="alert">
          {error}
        </div>
      )}
      {!state || !form ? (
        <p className="muted">Loading AI processing controls…</p>
      ) : (
        <>
          <div className="ai-runtime">
            <div>
              <span>Model / inference profile</span>
              <code>{state.runtime.model_id}</code>
            </div>
            <div>
              <span>Request source region</span>
              <strong>{state.runtime.region}</strong>
            </div>
            <div>
              <span>Current status</span>
              <strong>{pretty(state.status)}</strong>
            </div>
            <div>
              <span>Guardrail version</span>
              <strong>
                {state.runtime.guardrail_version || "Not configured"}
              </strong>
            </div>
          </div>
          <div className="inline-notice amber">
            <TriangleAlert size={17} />
            <span>{state.message}</span>
          </div>
          {state.runtime.issues.length > 0 && (
            <ul className="ai-config-issues">
              {state.runtime.issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          )}
          <div className="ai-disclosure">
            <Globe2 size={20} />
            <div>
              <strong>
                International processing requires a client decision
              </strong>
              <p>
                Opus 5.5 currently uses global inference from Mumbai. Prompts
                and responses may be processed outside India. A Mumbai endpoint
                is not an India-only residency guarantee. Your customer’s
                contracts, sector requirements and approved model terms must
                allow this processing.
              </p>
              <a
                href={state.runtime.model_card}
                target="_blank"
                rel="noreferrer"
              >
                Review the AWS model card <ArrowUpRight size={13} />
              </a>
            </div>
          </div>
          <form onSubmit={(e) => void save(e)}>
            <fieldset
              disabled={!administrator || saving}
              className="ai-form-controls"
            >
              <label className="ai-checkbox">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => change("enabled", e.target.checked)}
                />
                <span>
                  <strong>
                    Enable Bedrock guidance for this client workspace
                  </strong>
                  <small>
                    Saving these controls does not send data or invoke a model.
                    Analysts must explicitly request each draft.
                  </small>
                </span>
              </label>
              <label>
                Client processing policy
                <select
                  value={form.residency_mode}
                  onChange={(e) => {
                    change(
                      "residency_mode",
                      e.target.value as Governance["residency_mode"],
                    );
                    setForm((f) =>
                      f
                        ? {
                            ...f,
                            residency_mode: e.target
                              .value as Governance["residency_mode"],
                            data_processing_approved: false,
                          }
                        : f,
                    );
                  }}
                >
                  <option value="india_only">
                    India-only processing · blocks global Opus 5.5
                  </option>
                  <option value="global_approved">
                    Client-approved global AWS processing
                  </option>
                </select>
              </label>
              <div className="ai-provider-controls">
                <span>Approved cloud evidence sources</span>
                <div>
                  {(["aws", "azure", "gcp"] as const).map((p) => (
                    <label key={p} className="ai-checkbox">
                      <input
                        type="checkbox"
                        checked={form.allowed_providers.includes(p)}
                        onChange={(e) =>
                          change(
                            "allowed_providers",
                            e.target.checked
                              ? [...form.allowed_providers, p]
                              : form.allowed_providers.filter((x) => x !== p),
                          )
                        }
                      />
                      {p === "aws" ? "AWS" : p === "azure" ? "Azure" : "GCP"}
                    </label>
                  ))}
                </div>
              </div>
              <label className="ai-checkbox">
                <input
                  type="checkbox"
                  checked={form.allow_sample_data}
                  onChange={(e) =>
                    change("allow_sample_data", e.target.checked)
                  }
                />
                <span>
                  Also permit explicitly requested synthetic sample-data
                  inference
                </span>
              </label>
              <div className="ai-limits">
                <label>
                  Daily AI request limit
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={form.daily_request_limit}
                    onChange={(e) =>
                      change("daily_request_limit", Number(e.target.value))
                    }
                  />
                </label>
                <label>
                  Daily token reservation limit
                  <input
                    type="number"
                    min={4096}
                    max={1000000}
                    value={form.daily_token_limit}
                    onChange={(e) =>
                      change("daily_token_limit", Number(e.target.value))
                    }
                  />
                </label>
                <label>
                  Maximum output tokens per call
                  <input
                    type="number"
                    min={1024}
                    max={8192}
                    value={form.max_output_tokens}
                    onChange={(e) =>
                      change("max_output_tokens", Number(e.target.value))
                    }
                  />
                </label>
              </div>
              <p className="ai-limit-note">
                Opus 5.5 does not support CountTokens. Admission uses a
                conservative byte-based token reservation; actual model token
                usage is recorded separately. This is not a rupee-spend
                guarantee. Failed requests retain their reservation for the day.
              </p>
              <label className="ai-checkbox ai-approval">
                <input
                  type="checkbox"
                  checked={form.data_processing_approved}
                  onChange={(e) =>
                    change("data_processing_approved", e.target.checked)
                  }
                />
                <span>
                  <strong>
                    I am authorized by this client to approve the stated AWS
                    processing scope.
                  </strong>
                  <small>
                    I reviewed the model, processing regions, provider/model
                    terms and customer requirements. When global processing is
                    selected, this approval explicitly includes processing
                    outside India. The app checkbox does not replace the
                    customer’s legal and security approval.
                  </small>
                </span>
              </label>
              <div className="ai-minimization">
                <ShieldCheck size={18} />
                <p>{state.disclosure}</p>
              </div>
              <button className="primary" disabled={saving}>
                {saving ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <ShieldCheck size={16} />
                )}{" "}
                Save client AI policy
              </button>
            </fieldset>
          </form>
          {saved && (
            <div className="inline-notice" role="status">
              <CheckCircle2 size={17} /> Client AI policy saved. No model was
              invoked.
            </div>
          )}
          {!administrator && (
            <p className="muted">
              Only this workspace’s administrator can approve or change AI
              processing.
            </p>
          )}
          <div className="ai-usage-strip">
            <span>
              <strong>{state.usage.requests}</strong> requests today
            </span>
            <span>
              <strong>{state.usage.input_tokens.toLocaleString()}</strong> input
              tokens
            </span>
            <span>
              <strong>{state.usage.output_tokens.toLocaleString()}</strong>{" "}
              output tokens
            </span>
            <span>
              <strong>{state.usage.helpful_feedback}</strong> helpful ratings
            </span>
            <span>
              <strong>{state.usage.unsafe_feedback}</strong> safety flags
            </span>
          </div>
          <p className="ai-limit-note">
            Daily limits reset at midnight UTC. Ratings measure user feedback,
            not factual accuracy or compliance.
          </p>
        </>
      )}
    </section>
  );
}

export function BedrockAdvice({
  id,
  version,
  hasAssessment,
  advice,
  onRefresh,
  onSettings,
}: {
  id: string;
  version: number;
  hasAssessment: boolean;
  advice?: AdviceRecord | null;
  onRefresh: () => Promise<void>;
  onSettings: () => void;
}) {
  const [state, setState] = useState<AIState | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [feedback, setFeedback] = useState("");
  const [objective, setObjective] = useState("balance_performance");
  useEffect(() => {
    api<AIState>("/ai/status")
      .then(setState)
      .catch((e) => setError(e.message));
  }, []);
  const allowed = state?.status === "READY_UNVERIFIED";
  async function generate() {
    setBusy(true);
    setError("");
    setFeedback("");
    try {
      const job = await post<{ id: string }>(`/recommendations/${id}/advise`, {
        version,
        objective,
        idempotency_key: crypto.randomUUID(),
      });
      await waitJob(job.id);
      await onRefresh();
      setState(await api<AIState>("/ai/status"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function rate(verdict: string) {
    if (!advice) return;
    try {
      await post(`/recommendations/${id}/advice/feedback`, {
        generation_id: advice.generation_id,
        verdict,
      });
      setFeedback("Feedback recorded for this model draft.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const refs = (ids: string[]) => (
    <span className="ai-citations">
      {ids.map((ref) => (
        <a
          key={ref}
          href={`#fact-${ref}`}
          title={advice?.facts.find((f) => f.id === ref)?.field}
          onClick={() => {
            const details = document
              .getElementById(`fact-${ref}`)
              ?.closest("details");
            if (details) details.open = true;
          }}
        >
          {ref}
        </a>
      ))}
    </span>
  );
  return (
    <div className="ai-advice">
      <div className="ai-card-title">
        <div className="ai-symbol">
          <Sparkles size={22} />
        </div>
        <div>
          <h3>Bedrock improvement guidance</h3>
          <p>Source-based explanations and a proposed investigation plan.</p>
        </div>
      </div>
      <div className="inline-notice">
        <ShieldCheck size={17} /> AI cannot change source savings, evidence
        gaps, approval status or cloud resources. Every accepted response is
        still a draft for human review.
      </div>
      {state && (
        <div className="ai-target">
          <code>{state.runtime.model_id}</code>
          <span>
            {state.runtime.region}
            {state.runtime.global_target ? " · global inference" : ""}
          </span>
        </div>
      )}
      {!allowed && state && (
        <div className="inline-notice amber">
          <TriangleAlert size={17} />
          <div>
            <p>{state.message}</p>
            <button className="text-button" onClick={onSettings}>
              Open client AI settings <ArrowUpRight size={14} />
            </button>
          </div>
        </div>
      )}
      {!hasAssessment && (
        <p className="ai-prerequisite">
          Run an evidence assessment first, then request a Bedrock draft.
        </p>
      )}
      <div className="ai-generate-controls">
        <label>
          Guidance objective
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
          >
            <option value="balance_performance">
              Balance savings and performance
            </option>
            <option value="reduce_waste">Investigate avoidable waste</option>
            <option value="understand_risk">
              Understand evidence gaps and risk
            </option>
          </select>
        </label>
        <button
          className="primary"
          disabled={!allowed || !hasAssessment || busy}
          onClick={() => void generate()}
        >
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Sparkles size={16} />
          )}{" "}
          {busy ? "Requesting Bedrock draft…" : "Generate Bedrock guidance"}
        </button>
      </div>
      {allowed && (
        <p className="ai-limit-note">
          This request sends minimized evidence to the approved AWS route and
          may incur Bedrock charges. A first call or model response can take
          longer; leaving the dialog does not cancel the local job.
        </p>
      )}
      {error && (
        <div className="inline-notice red" role="alert">
          {error}
        </div>
      )}
      {advice && (
        <>
          {advice.stale && (
            <div className="inline-notice amber">
              <TriangleAlert size={17} /> This draft is stale because the
              evidence, policy, source revision or client approval changed.
              Generate a new draft before using it.
            </div>
          )}
          <div className="ai-result-header">
            <span className="badge purple">AI-generated draft</span>
            <span>
              {pretty(advice.content.priority)}
              {advice.cache_hit ? " · reused current draft" : ""}
            </span>
          </div>
          <p className="ai-summary">
            {advice.content.summary} {refs(advice.content.summary_evidence_ids)}
          </p>
          <h3>What the evidence suggests</h3>
          {advice.content.observations.map((o, index) => (
            <p className="ai-observation" key={index}>
              {o.statement} {refs(o.evidence_ids)}
            </p>
          ))}
          <h3>Recommended next steps</h3>
          <div className="ai-actions">
            {advice.content.actions.map((a, index) => (
              <article key={a.id}>
                <span className="ai-step-number">{index + 1}</span>
                <div>
                  <h4>{a.title}</h4>
                  <p>{a.guidance}</p>
                  <small>{a.prerequisite}</small>
                  {refs(a.evidence_ids)}
                </div>
              </article>
            ))}
          </div>
          <h3>Questions for the workload owner</h3>
          <ul className="ai-questions">
            {advice.content.open_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
          <details className="ai-facts">
            <summary>Inspect the minimized source facts</summary>
            <dl>
              {advice.facts.map((f) => (
                <div id={`fact-${f.id}`} key={f.id}>
                  <dt>
                    <strong>{f.id}</strong> {pretty(f.field)}
                  </dt>
                  <dd>
                    {f.value === null
                      ? "Unknown"
                      : typeof f.value === "object"
                        ? JSON.stringify(f.value)
                        : String(f.value)}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
          <div className="ai-trace">
            <span>
              Generated{" "}
              <strong>
                {new Date(advice.generated_at).toLocaleString("en-IN")}
              </strong>
            </span>
            <span>
              Source region <strong>{advice.source_region}</strong>
            </span>
            <span>
              Possible processing destinations{" "}
              <strong>{advice.destination_regions.join(", ")}</strong>
            </span>
            <span>
              Prompt / guardrail{" "}
              <strong>
                {advice.prompt_version} /{" "}
                {advice.guardrail_version || "Not configured"}
              </strong>
            </span>
            <span>
              Tokens in / out{" "}
              <strong>
                {advice.usage.inputTokens ?? "Unknown"} /{" "}
                {advice.usage.outputTokens ?? "Unknown"}
              </strong>
            </span>
            <span>
              Request latency{" "}
              <strong>{(advice.latency_ms / 1000).toFixed(1)} s</strong>
            </span>
          </div>
          <p className="ai-limit-note">
            {advice.validation} Fact references are application references; they
            are not a guarantee that every model interpretation is correct.
            Internal model reasoning is not displayed or stored.
          </p>
          <a
            href={advice.source_guide}
            className="text-button"
            target="_blank"
            rel="noreferrer"
          >
            Provider optimization reference <ArrowUpRight size={14} />
          </a>
          <div className="ai-feedback">
            <span>Review this draft</span>
            <button className="secondary" onClick={() => void rate("helpful")}>
              <ThumbsUp size={14} /> Helpful
            </button>
            <button
              className="secondary"
              onClick={() => void rate("inaccurate")}
            >
              <Flag size={14} /> Inaccurate
            </button>
            <button className="secondary" onClick={() => void rate("unsafe")}>
              <TriangleAlert size={14} /> Unsafe
            </button>
          </div>
          {feedback && (
            <p className="ai-feedback-message" role="status">
              {feedback}
            </p>
          )}
        </>
      )}
    </div>
  );
}
