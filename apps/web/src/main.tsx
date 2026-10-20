import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownLeft,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cloud,
  Download,
  Ellipsis,
  FileText,
  Filter,
  Fingerprint,
  FlaskConical,
  Globe2,
  LayoutDashboard,
  Leaf,
  LoaderCircle,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingDown,
  TriangleAlert,
  Upload,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/manrope";
import "./styles.css";
import "./theme.css";
import { api, post, waitJob } from "./client";
import { AISettings, BedrockAdvice } from "./ai";
import type { AdviceRecord } from "./ai";

type Provider = "aws" | "azure" | "gcp";
type Page =
  | "Overview"
  | "Opportunities"
  | "Cloud accounts"
  | "Decision lab"
  | "Review queue"
  | "Reports"
  | "Audit log"
  | "Settings";
type Connection = {
  id: string;
  name: string;
  provider: Provider;
  account_id: string;
  mode: string;
  status: string;
  last_sync: string | null;
  potential: string | null;
  currency: string;
  config: Record<string, string>;
  error?: string;
  warnings?: string[];
  credentials_configured?: boolean;
};
type Analysis = {
  choice: string;
  suggested_route: string;
  outcome: string;
  gaps: string[];
  summary: string;
  evidence_hash: string;
  at: string;
  change_plan: string[];
  rollback_plan: string;
  model_status: string;
  engine: string;
};
type Recommendation = {
  advisory?: AdviceRecord | null;
  id: string;
  title: string;
  provider: Provider;
  connection_id: string;
  service: string;
  category: string;
  savings: string;
  currency: string;
  risk: string;
  status: string;
  environment: string;
  resource_id: string;
  owner: string | null;
  region: string;
  version: number;
  collected_at: string;
  mode: string;
  analysis: Analysis | null;
  evidence: {
    source: string;
    source_id: string;
    cpu_average?: number | null;
    cpu_peak?: number | null;
    memory_peak?: number | null;
    observation_start?: string;
    observation_end_exclusive?: string;
    limitations: string[];
    is_sample: boolean;
  };
  review?: { actor: string; justification: string; at: string };
};
type Overview = {
  spend: string;
  previous_spend: string;
  change_percent: string | null;
  potential: string | null;
  potential_coverage: string;
  potential_basis: string;
  realized: string | null;
  currency: string;
  accounts: number;
  fresh_accounts: number;
  opportunities: number;
  review_count: number;
  start: string;
  end_exclusive: string;
  by_provider: { provider: Provider; amount: string; accounts: number }[];
  trend: { date: string; aws: string; azure: string; gcp: string }[];
  recommendations: Recommendation[];
  currencies: string[];
  mixed_data: boolean;
  stale_accounts: string[];
  cost_basis: string;
};
type User = {
  name: string;
  organization: string;
  email: string;
  role: string;
  deployment: string;
  live_enabled: boolean;
};
type Audit = {
  id: string;
  action: string;
  actor: string;
  target: string;
  at: string;
  detail: string;
};
type Report = {
  id: string;
  name: string;
  at: string;
  rows: number;
  format: string;
};
const providerNames = {
  aws: "Amazon Web Services",
  azure: "Microsoft Azure",
  gcp: "Google Cloud",
};
const shortNames = { aws: "AWS", azure: "Azure", gcp: "Google Cloud" };
const colors = { aws: "#8661df", azure: "#64a5df", gcp: "#e9b15a" };
const currencyFormat = (
  value: string | number | null,
  currency = "USD",
  compact = false,
) =>
  value === null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        ...(compact ? { maximumFractionDigits: 0 } : {}),
      }).format(Number(value));
const dateFormat = (date: string | null, full = false) =>
  date
    ? new Date(date).toLocaleString(
        "en-IN",
        full
          ? {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            }
          : { day: "numeric", month: "short" },
      )
    : "Not collected";
const human = (s: string) => s.toLowerCase().replaceAll("_", " ");

function ProviderIcon({
  provider,
  small = false,
}: {
  provider: Provider;
  small?: boolean;
}) {
  return (
    <span
      className={`provider-icon ${provider} ${small ? "small" : ""}`}
      aria-label={shortNames[provider]}
    >
      {provider === "aws" ? (
        <span className="aws-word">
          aws<span>⌣</span>
        </span>
      ) : provider === "azure" ? (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m10 3-7 16h6l4-8 4 8h5L15 3z" fill="currentColor" />
          <path d="m8 18 9-2 4 5H7z" fill="currentColor" opacity=".65" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 16a5 5 0 0 1 1-9l3 3a2 2 0 0 0-3 3z" fill="#4285f4" />
          <path d="M7 7a7 7 0 0 1 12 0l-3 3a3 3 0 0 0-5 0z" fill="#ea4335" />
          <path d="M18 7a5 5 0 0 1 1 9l-3-3a2 2 0 0 0 0-3z" fill="#fbbc04" />
          <path d="M6 13h12v5H6a3 3 0 0 1 0-5" fill="#34a853" />
        </svg>
      )}
    </span>
  );
}
function Status({ value }: { value: string }) {
  const cls = [
    "CONNECTED",
    "SUCCEEDED",
    "APPROVED_PLAN",
    "REVIEWABLE_PLAN",
  ].includes(value)
    ? "green"
    : ["ERROR", "FAILED", "REJECTED", "High"].includes(value)
      ? "red"
      : ["NEW", "DEMO"].includes(value)
        ? "purple"
        : "amber";
  return (
    <span className={`badge ${cls}`}>
      <span className="status-dot" />
      {human(value)}
    </span>
  );
}
function Empty({
  icon: Icon = Cloud,
  title,
  text,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={28} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function Modal({
  title,
  subtitle,
  close,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  close: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const nodes = panel.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input,select,textarea,[tabindex="0"]',
        );
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
        if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    panel.current?.focus();
    document.addEventListener("keydown", handler);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = "";
      before?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`modal ${wide ? "wide" : ""}`}
      >
        <div className="modal-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={close}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null),
    [booting, setBooting] = useState(true);
  const [page, setPage] = useState<Page>("Overview"),
    [provider, setProvider] = useState("all"),
    [days, setDays] = useState(30),
    [currency, setCurrency] = useState("USD"),
    [mode, setMode] = useState("all");
  const [overview, setOverview] = useState<Overview | null>(null),
    [connections, setConnections] = useState<Connection[]>([]),
    [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [events, setEvents] = useState<Audit[]>([]),
    [reports, setReports] = useState<Report[]>([]),
    [totalRecs, setTotalRecs] = useState(0),
    [offset, setOffset] = useState(0);
  const [query, setQuery] = useState(""),
    [risk, setRisk] = useState("all"),
    [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(""),
    [toast, setToast] = useState<{ text: string; error?: boolean } | null>(
      null,
    ),
    [error, setError] = useState("");
  const [connectOpen, setConnectOpen] = useState(false),
    [detail, setDetail] = useState<Recommendation | null>(null),
    [account, setAccount] = useState<Connection | null>(null),
    [help, setHelp] = useState(false);
  const [maxAge, setMaxAge] = useState(48);
  const refreshId = useRef(0);
  const notify = (text: string, error = false) => setToast({ text, error });
  useEffect(() => {
    api<User>("/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setBooting(false));
  }, []);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 6000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  async function refresh() {
    if (!user) return;
    const rid = ++refreshId.current;
    setLoading(true);
    setError("");
    try {
      const [o, c, r, a, rep, policy] = await Promise.all([
        api<Overview>(
          `/overview?days=${days}&provider=${provider}&currency=${currency}&mode=${mode}`,
        ),
        api<{ items: Connection[] }>("/connections"),
        api<{ items: Recommendation[]; total: number }>(
          `/recommendations?provider=${provider}&risk=${risk}&status=${page === "Review queue" ? "NEEDS_REVIEW" : status}&q=${encodeURIComponent(query)}&offset=${offset}&limit=25`,
        ),
        api<{ items: Audit[] }>("/audit"),
        api<{ items: Report[] }>("/reports"),
        api<{ max_evidence_age_hours: number }>("/policy"),
      ]);
      if (rid !== refreshId.current) return;
      setOverview(o);
      setConnections(c.items);
      setRecommendations(r.items);
      setTotalRecs(r.total);
      setEvents(a.items);
      setReports(rep.items);
      setMaxAge(policy.max_evidence_age_hours);
    } catch (e) {
      if (rid === refreshId.current) setError((e as Error).message);
    } finally {
      if (rid === refreshId.current) setLoading(false);
    }
  }
  useEffect(() => {
    const t = setTimeout(() => void refresh(), 180);
    return () => clearTimeout(t);
  }, [user, days, provider, currency, mode, risk, status, query, offset, page]);
  useEffect(() => {
    setOffset(0);
  }, [query, risk, status, provider, page]);
  function navigate(p: Page) {
    setPage(p);
    setQuery("");
    setRisk("all");
    setStatus("all");
    setOffset(0);
  }
  async function synchronize(c?: Connection) {
    setBusy(c?.id || "sync");
    try {
      const selected = c ? [c] : connections.filter((x) => x.mode !== "import");
      if (!selected.length)
        throw new Error(
          "Connect a cloud account or upload billing data to an import connection.",
        );
      for (const connection of selected) {
        const job = await post<{ id: string }>(
          `/connections/${connection.id}/sync`,
          { idempotency_key: crypto.randomUUID() },
        );
        const result = await waitJob(job.id);
        if (result.warnings?.length) notify(result.warnings.join(" "));
      }
      notify("Data refreshed. New evidence is ready for review.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy("");
      await refresh();
      if (c) setAccount(null);
    }
  }
  async function analyze(rec: Recommendation) {
    setBusy("analyze");
    try {
      const job = await post<{ id: string }>(
        `/recommendations/${rec.id}/analyze`,
        { idempotency_key: crypto.randomUUID() },
      );
      await waitJob(job.id);
      const next = await api<Recommendation>("/recommendations/" + rec.id);
      setDetail(next);
      await refresh();
      notify("Evidence assessed with deterministic policy.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy("");
    }
  }
  async function exportReport() {
    setBusy("export");
    try {
      const r = await post<Report>("/reports");
      window.location.assign("/v1/reports/" + r.id + "/download");
      await refresh();
      notify(
        "CSV report created. Includes all workspace providers and currencies in separate rows.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy("");
    }
  }
  if (booting)
    return (
      <div className="boot">
        <LoaderCircle className="spin" /> Opening your workspace…
      </div>
    );
  if (!user)
    return (
      <Auth
        onSuccess={async () => {
          setUser(await api<User>("/me"));
        }}
      />
    );
  const nav: { name: Page; icon: LucideIcon; count?: number }[] = [
    { name: "Overview", icon: LayoutDashboard },
    { name: "Opportunities", icon: Zap, count: overview?.opportunities },
    { name: "Cloud accounts", icon: Cloud },
    { name: "Decision lab", icon: FlaskConical },
    { name: "Review queue", icon: ShieldCheck, count: overview?.review_count },
    { name: "Reports", icon: FileText },
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <span className="brand-mark">
            <Activity size={23} />
          </span>
          <span>
            finops<span className="brand-light">autopilot</span>
            <span className="brand-tag">MULTI-CLOUD INTELLIGENCE</span>
          </span>
        </a>
        <button className="workspace" onClick={() => navigate("Settings")}>
          <span className="workspace-avatar">{user.organization[0]}</span>
          <span>
            <strong>{user.organization}</strong>
            <small>
              {user.deployment === "serverless"
                ? "Cloud workspace"
                : "Local workspace"}
            </small>
          </span>
          <ChevronDown size={15} />
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(({ name, icon: Icon, count }) => (
            <button
              key={name}
              aria-label={name}
              className={`nav-item ${page === name ? "active" : ""}`}
              onClick={() => navigate(name)}
            >
              <Icon size={19} />
              <span>{name}</span>
              {!!count && <span className="nav-count">{count}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-clouds">
          <div className="nav-label">
            YOUR CLOUDS{" "}
            <button
              aria-label="Add cloud account"
              onClick={() => setConnectOpen(true)}
            >
              <Plus size={15} />
            </button>
          </div>
          {(["aws", "azure", "gcp"] as Provider[]).map((p) => (
            <button
              key={p}
              className={
                provider === p ? "cloud-shortcut selected" : "cloud-shortcut"
              }
              onClick={() => {
                setProvider(provider === p ? "all" : p);
                navigate("Overview");
              }}
            >
              <ProviderIcon provider={p} small />
              <span>{shortNames[p]}</span>
              <span className="cloud-count">
                {connections.filter((c) => c.provider === p).length}
              </span>
              <span
                className={`tiny-dot ${connections.some((c) => c.provider === p) ? "on" : ""}`}
              />
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="local-card">
            <span className="local-title">
              <span className="pulse-dot" />{" "}
              {user.deployment === "serverless"
                ? "Cloud workspace"
                : "Running locally"}{" "}
              <span className="version">v0.2</span>
            </span>
            <p>Your cloud data. Your control.</p>
            <span className="local-note">
              <ShieldCheck size={13} /> Read-only by design
            </span>
          </div>
          <button
            className={`nav-item ${page === "Audit log" ? "active" : ""}`}
            aria-label="Audit log"
            onClick={() => navigate("Audit log")}
          >
            <Fingerprint size={18} />
            <span>Audit log</span>
          </button>
          <button
            className={`nav-item ${page === "Settings" ? "active" : ""}`}
            aria-label="Settings"
            onClick={() => navigate("Settings")}
          >
            <Settings2 size={18} />
            <span>Settings</span>
          </button>
          <button
            className="nav-item"
            aria-label="Help and documentation"
            onClick={() => setHelp(true)}
          >
            <CircleHelp size={18} />
            <span>Help & documentation</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="profile">
            <span className="avatar">
              {user.name
                .split(" ")
                .map((s) => s[0])
                .join("")
                .slice(0, 2)}
            </span>
            <span>
              <strong>{user.name}</strong>
              <small>{human(user.role)}</small>
            </span>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                await post("/auth/logout");
                setUser(null);
                setOverview(null);
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <div className="global-search">
              <Search size={16} />
              <input
                aria-label="Search opportunities"
                placeholder="Search opportunities…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  if (page !== "Opportunities") setPage("Opportunities");
                }}
              />
              <kbd>/</kbd>
            </div>
            <span className="top-divider" />
            <button
              className="icon-button notification"
              aria-label="View recent activity"
              onClick={() => navigate("Audit log")}
            >
              <Bell size={19} />
              {events.length > 0 && <span />}
            </button>
            <span className="avatar mini">{user.name[0]}</span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">YOUR CLOUD, IN FOCUS</div>
              <h1>{page === "Overview" ? "Cloud financial overview" : page}</h1>
              <p>
                {
                  {
                    Overview:
                      "A clearer view of your spend. A smarter path to savings.",
                    Opportunities:
                      "Turn cloud waste into evidence-backed opportunities.",
                    "Cloud accounts":
                      "One workspace for every cloud your clients call home.",
                    "Decision lab":
                      "Follow the evidence. Understand every decision.",
                    "Review queue":
                      "Make confident changes with a human in the loop.",
                    Reports: "Your optimization story, ready to share.",
                    "Audit log":
                      "An accountable record of every workspace action.",
                    Settings: "Set the guardrails for your cloud operations.",
                  }[page]
                }
              </p>
            </div>
            <div className="heading-actions">
              {page === "Cloud accounts" ? (
                <button
                  className="primary"
                  onClick={() => setConnectOpen(true)}
                >
                  <Plus size={17} /> Connect account
                </button>
              ) : (
                <>
                  <button
                    className="secondary"
                    disabled={!!busy}
                    onClick={() => void exportReport()}
                  >
                    <Download size={16} /> Export report
                  </button>
                  <button
                    className="primary"
                    onClick={() => setConnectOpen(true)}
                  >
                    <Plus size={17} /> Connect account
                  </button>
                </>
              )}
            </div>
          </div>

          {error && (
            <div className="error-banner" role="alert">
              <TriangleAlert size={17} />
              {error}
              <button onClick={() => void refresh()}>Retry</button>
            </div>
          )}
          {loading && !overview && page !== "Settings" ? (
            <div className="loading-block">
              <LoaderCircle className="spin" /> Loading cloud insights…
            </div>
          ) : (
            <>
              {page === "Overview" && overview && (
                <>
                  <div className="filterbar">
                    <div className="filter-left">
                      <label className="filter-select">
                        <Globe2 size={15} />
                        <select
                          aria-label="Cloud provider"
                          value={provider}
                          onChange={(e) => setProvider(e.target.value)}
                        >
                          <option value="all">All cloud providers</option>
                          <option value="aws">Amazon Web Services</option>
                          <option value="azure">Microsoft Azure</option>
                          <option value="gcp">Google Cloud</option>
                        </select>
                        <ChevronDown size={13} />
                      </label>
                      <label className="filter-select">
                        <Filter size={14} />
                        <select
                          aria-label="Data source mode"
                          value={mode}
                          onChange={(e) => setMode(e.target.value)}
                        >
                          <option value="all">All data sources</option>
                          <option value="live">Live connections</option>
                          <option value="import">Imported data</option>
                        </select>
                        <ChevronDown size={13} />
                      </label>
                      <label className="currency-select">
                        <select
                          aria-label="Reporting currency"
                          value={currency}
                          onChange={(e) => setCurrency(e.target.value)}
                        >
                          {[...new Set([...overview.currencies, currency])].map(
                            (c) => (
                              <option key={c}>{c}</option>
                            ),
                          )}
                        </select>
                      </label>
                    </div>
                    <div className="filter-right">
                      <span className="freshness">
                        <span
                          className={`tiny-dot ${overview.fresh_accounts === overview.accounts && overview.accounts > 0 ? "on" : ""}`}
                        />
                        {overview.accounts
                          ? `${overview.fresh_accounts}/${overview.accounts} sources synced`
                          : "No sources connected"}
                      </span>
                      <button
                        className="icon-button"
                        aria-label="Refresh connected cloud data"
                        disabled={!!busy}
                        onClick={() => void synchronize()}
                      >
                        <RefreshCw size={15} className={busy ? "spin" : ""} />
                      </button>
                      <label className="filter-select date-select">
                        <Clock3 size={14} />
                        <select
                          aria-label="Date range"
                          value={days}
                          onChange={(e) => setDays(Number(e.target.value))}
                        >
                          <option value={7}>Last 7 days</option>
                          <option value={30}>Last 30 days</option>
                          <option value={90}>Last 90 days</option>
                        </select>
                        <ChevronDown size={13} />
                      </label>
                    </div>
                  </div>

                  {overview.stale_accounts.length > 0 && (
                    <div className="inline-notice amber">
                      <Clock3 size={15} /> Data is missing or older than 48
                      hours for {overview.stale_accounts.join(", ")}.
                    </div>
                  )}
                  <div className="kpi-grid">
                    <Kpi
                      label="Total cloud spend"
                      value={currencyFormat(overview.spend, currency)}
                      icon={Wallet}
                      foot={
                        <>
                          <span
                            className={
                              Number(overview.change_percent) <= 0
                                ? "positive"
                                : "negative"
                            }
                          >
                            {Number(overview.change_percent) <= 0 ? (
                              <ArrowDownRight size={13} />
                            ) : (
                              <ArrowUpRight size={13} />
                            )}{" "}
                            {overview.change_percent === null
                              ? "No comparison"
                              : `${Math.abs(Number(overview.change_percent)).toFixed(1)}%`}
                          </span>
                          <span>vs. previous {days} days</span>
                        </>
                      }
                    />
                    <Kpi
                      label="Monthly savings potential"
                      value={currencyFormat(overview.potential, currency)}
                      icon={Sparkles}
                      accent
                      foot={
                        <>
                          <span className="purple-text">
                            {overview.potential_coverage} sources covered
                          </span>
                          <span>· estimated, not realized</span>
                        </>
                      }
                    />
                    <Kpi
                      label="Optimization opportunities"
                      value={String(overview.opportunities).padStart(2, "0")}
                      icon={Target}
                      foot={
                        <>
                          <span className="purple-text">
                            {overview.review_count} awaiting review
                          </span>
                          <span>across your clouds</span>
                        </>
                      }
                    />
                    <Kpi
                      label="Connected cloud accounts"
                      value={String(overview.accounts).padStart(2, "0")}
                      icon={Cloud}
                      foot={
                        <>
                          <div className="tiny-providers">
                            {overview.by_provider
                              .filter((p) => p.accounts)
                              .map((p) => (
                                <ProviderIcon
                                  key={p.provider}
                                  provider={p.provider}
                                  small
                                />
                              ))}
                          </div>
                          <span>
                            {
                              overview.by_provider.filter((p) => p.accounts)
                                .length
                            }{" "}
                            cloud providers
                          </span>
                        </>
                      }
                    />
                  </div>
                  <div className="chart-grid">
                    <section className="card spend-card">
                      <div className="card-heading">
                        <div>
                          <h2>Cloud spend over time</h2>
                          <p>Daily spend across your connected accounts</p>
                        </div>
                        <span className="subtle-tag">{currency} · daily</span>
                      </div>
                      <SpendChart data={overview.trend} currency={currency} />
                      <div className="chart-footer">
                        <div className="legend">
                          {overview.by_provider.map((p) => (
                            <span key={p.provider}>
                              <i style={{ background: colors[p.provider] }} />
                              {shortNames[p.provider]}
                            </span>
                          ))}
                        </div>
                        <span>
                          {dateFormat(overview.start)} –{" "}
                          {dateFormat(
                            new Date(
                              new Date(overview.end_exclusive).getTime() -
                                86400000,
                            ).toISOString(),
                          )}
                        </span>
                      </div>
                    </section>
                    <section className="card cloud-distribution">
                      <div className="card-heading">
                        <div>
                          <h2>Spend by cloud</h2>
                          <p>Your multi-cloud footprint</p>
                        </div>
                        <Cloud size={17} className="muted" />
                      </div>
                      <Donut
                        data={overview.by_provider}
                        total={overview.spend}
                        currency={currency}
                      />
                      <div className="cloud-distribution-list">
                        {overview.by_provider.map((p) => (
                          <button
                            key={p.provider}
                            onClick={() =>
                              setProvider(
                                provider === p.provider ? "all" : p.provider,
                              )
                            }
                          >
                            <span>
                              <i style={{ background: colors[p.provider] }} />
                              {shortNames[p.provider]}
                            </span>
                            <strong>
                              {currencyFormat(p.amount, currency, true)}
                            </strong>
                            <span>
                              {Number(overview.spend)
                                ? (
                                    (Number(p.amount) /
                                      Number(overview.spend)) *
                                    100
                                  ).toFixed(0)
                                : "0"}
                              %
                            </span>
                          </button>
                        ))}
                      </div>
                    </section>
                  </div>
                  <div className="section-title">
                    <div>
                      <h2>Make your next move count</h2>
                      <p>
                        Prioritized opportunities with the biggest potential
                        impact.
                      </p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("Opportunities")}
                    >
                      View all opportunities <ArrowRight size={15} />
                    </button>
                  </div>
                  <RecommendationTable
                    rows={overview.recommendations}
                    open={setDetail}
                    compact
                  />
                  <div className="bottom-grid">
                    <section className="card health-card">
                      <div className="card-heading">
                        <div>
                          <h2>Cloud connection health</h2>
                          <p>Read-only access. Complete visibility.</p>
                        </div>
                        <button
                          className="text-button"
                          onClick={() => navigate("Cloud accounts")}
                        >
                          Manage <ArrowRight size={14} />
                        </button>
                      </div>
                      {connections.length ? (
                        connections.slice(0, 3).map((c) => (
                          <div key={c.id} className="connection-health">
                            <ProviderIcon provider={c.provider} />
                            <div>
                              <strong>{c.name}</strong>
                              <small>{dateFormat(c.last_sync, true)}</small>
                            </div>
                            <Status value={c.status} />
                          </div>
                        ))
                      ) : (
                        <Empty
                          title="Bring your clouds together"
                          text="Connect your first cloud account to start tracking spend."
                          action={
                            <button
                              className="secondary"
                              onClick={() => setConnectOpen(true)}
                            >
                              Connect account
                            </button>
                          }
                        />
                      )}
                    </section>
                    <section className="card activity-card">
                      <div className="card-heading">
                        <div>
                          <h2>Recent activity</h2>
                          <p>A little context behind the numbers</p>
                        </div>
                        <button
                          className="icon-button"
                          aria-label="View all audit events"
                          onClick={() => navigate("Audit log")}
                        >
                          <ArrowUpRight size={17} />
                        </button>
                      </div>
                      {events.slice(0, 3).map((e) => (
                        <div className="activity-row" key={e.id}>
                          <span className="activity-icon">
                            <Check size={15} />
                          </span>
                          <div>
                            <strong>{human(e.action)}</strong>
                            <p>
                              {e.actor} <span>· {dateFormat(e.at, true)}</span>
                            </p>
                          </div>
                        </div>
                      ))}
                      {!events.length && (
                        <p className="muted">
                          Workspace activity will appear here.
                        </p>
                      )}
                    </section>
                    <section className="insight-card">
                      <span className="insight-spark">
                        <Sparkles size={21} />
                      </span>
                      <span className="eyebrow">
                        BUILT FOR CONFIDENT DECISIONS
                      </span>
                      <h2>
                        Savings start with
                        <br />
                        the right questions.
                      </h2>
                      <p>
                        Investigate the evidence, understand the risk, and
                        approve a plan with clarity.
                      </p>
                      <button onClick={() => navigate("Decision lab")}>
                        Explore decision lab <ArrowRight size={16} />
                      </button>
                      <div className="insight-orbit" />
                    </section>
                  </div>
                  <div className="data-note">
                    <ShieldCheck size={14} />
                    <span>
                      Read-only analysis · {overview.potential_basis} ·
                      Individual savings may overlap. {overview.cost_basis}
                    </span>
                  </div>
                </>
              )}
              {(page === "Opportunities" ||
                page === "Review queue" ||
                page === "Decision lab") && (
                <>
                  {page === "Decision lab" && (
                    <div className="lab-intro">
                      <div className="lab-icon">
                        <FlaskConical size={27} />
                      </div>
                      <div>
                        <h2>Every recommendation has a reasoning trail.</h2>
                        <p>
                          The local policy engine checks freshness, ownership,
                          utilization and rollback evidence. Open the Bedrock
                          guidance tab on an opportunity for a client-approved
                          AI draft. Decider routing remains unconfigured.
                        </p>
                      </div>
                      <span className="badge purple">Deterministic mode</span>
                    </div>
                  )}
                  {page === "Review queue" && (
                    <div className="inline-notice">
                      <ShieldCheck size={17} /> Approvals record a reviewed
                      plan. Changes are implemented through your client’s change
                      process.
                    </div>
                  )}
                  <div className="list-toolbar">
                    <div className="search-field">
                      <Search size={16} />
                      <input
                        placeholder="Search resources, services or opportunities"
                        aria-label="Filter recommendations"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </div>
                    <select
                      aria-label="Filter provider"
                      value={provider}
                      onChange={(e) => setProvider(e.target.value)}
                    >
                      <option value="all">All clouds</option>
                      {(["aws", "azure", "gcp"] as Provider[]).map((p) => (
                        <option value={p} key={p}>
                          {shortNames[p]}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Filter risk"
                      value={risk}
                      onChange={(e) => setRisk(e.target.value)}
                    >
                      <option value="all">All risk levels</option>
                      {["Low", "Medium", "High"].map((r) => (
                        <option key={r}>{r}</option>
                      ))}
                    </select>
                    {page !== "Review queue" && (
                      <select
                        aria-label="Filter status"
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                      >
                        <option value="all">All statuses</option>
                        {[
                          "NEW",
                          "NEEDS_REVIEW",
                          "APPROVED_PLAN",
                          "REJECTED",
                          "DEFERRED",
                        ].map((s) => (
                          <option key={s} value={s}>
                            {human(s)}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  <RecommendationTable
                    rows={recommendations}
                    open={setDetail}
                  />
                  <div className="pagination">
                    <span>
                      {totalRecs} opportunities ·{" "}
                      {offset + (recommendations.length ? 1 : 0)}–
                      {offset + recommendations.length} shown
                    </span>
                    <div>
                      <button
                        className="secondary"
                        disabled={offset === 0}
                        onClick={() => setOffset(Math.max(0, offset - 25))}
                      >
                        <ChevronLeft size={14} /> Previous
                      </button>
                      <button
                        className="secondary"
                        disabled={offset + 25 >= totalRecs}
                        onClick={() => setOffset(offset + 25)}
                      >
                        Next <ChevronRight size={14} />
                      </button>
                    </div>
                  </div>
                </>
              )}
              {page === "Cloud accounts" && (
                <>
                  <div className="account-summary">
                    <span>
                      <Cloud size={18} />
                      <strong>{connections.length}</strong> cloud accounts
                    </span>
                    <span>
                      <ShieldCheck size={17} /> Read-only connections
                    </span>
                    <span>
                      <Globe2 size={17} /> AWS · Azure · Google Cloud
                    </span>
                  </div>
                  <div className="account-grid">
                    {connections.map((c) => (
                      <section key={c.id} className="card account-card">
                        <div className="account-top">
                          <ProviderIcon provider={c.provider} />
                          <Status value={c.status} />
                        </div>
                        <h2>{c.name}</h2>
                        <p>{providerNames[c.provider]}</p>
                        <code>{c.account_id}</code>
                        <div className="account-meta">
                          <span>
                            Data source
                            <strong>
                              {c.mode === "import"
                                ? "Customer import"
                                : "Live · read-only"}
                            </strong>
                          </span>
                          <span>
                            Last successful sync
                            <strong>{dateFormat(c.last_sync, true)}</strong>
                          </span>
                        </div>
                        {c.error && <p className="account-error">{c.error}</p>}
                        <div className="account-actions">
                          <button
                            className="secondary"
                            onClick={() => setAccount(c)}
                          >
                            <SlidersHorizontal size={14} /> Connection details
                          </button>
                          <button
                            aria-label={`Sync ${c.name}`}
                            className="icon-button"
                            disabled={!!busy || c.mode === "import"}
                            onClick={() => void synchronize(c)}
                          >
                            <RefreshCw
                              size={16}
                              className={busy === c.id ? "spin" : ""}
                            />
                          </button>
                        </div>
                      </section>
                    ))}
                    <button
                      className="connect-card"
                      onClick={() => setConnectOpen(true)}
                    >
                      <span>
                        <Plus size={25} />
                      </span>
                      <strong>Connect a cloud account</strong>
                      <p>
                        Bring AWS, Azure or Google Cloud
                        <br />
                        into one financial view.
                      </p>
                      <div className="tiny-providers">
                        {(["aws", "azure", "gcp"] as Provider[]).map((p) => (
                          <ProviderIcon key={p} provider={p} small />
                        ))}
                      </div>
                    </button>
                  </div>
                  <div className="inline-notice">
                    <ShieldCheck size={17} /> Credentials stay in your local SDK
                    environment. Onboarding saves scope identifiers; access is
                    verified by a successful collection. Azure and GCP currently
                    collect billing only.
                  </div>
                </>
              )}
              {page === "Reports" && (
                <>
                  <div className="report-hero">
                    <div className="report-illustration">
                      <FileText size={40} />
                    </div>
                    <div>
                      <span className="eyebrow">FROM INSIGHT TO ACTION</span>
                      <h2>Share the full picture.</h2>
                      <p>
                        Export workspace-wide opportunities with source,
                        currency, evidence timestamps and review status. Savings
                        are estimates; reports preserve each currency
                        separately.
                      </p>
                    </div>
                    <button
                      className="primary"
                      disabled={!!busy}
                      onClick={() => void exportReport()}
                    >
                      <Download size={16} /> Create CSV report
                    </button>
                  </div>
                  <section className="card">
                    <div className="card-heading">
                      <h2>Generated reports</h2>
                      <span className="subtle-tag">
                        {reports.length} reports
                      </span>
                    </div>
                    {reports.map((r) => (
                      <div className="report-row" key={r.id}>
                        <span className="document-icon">
                          <FileText size={22} />
                        </span>
                        <div>
                          <strong>{r.name}</strong>
                          <small>
                            {r.format} · {r.rows} opportunities ·{" "}
                            {dateFormat(r.at, true)}
                          </small>
                        </div>
                        <a
                          className="secondary"
                          href={"/v1/reports/" + r.id + "/download"}
                        >
                          <Download size={15} /> Download
                        </a>
                      </div>
                    ))}
                    {!reports.length && (
                      <Empty
                        icon={FileText}
                        title="Your first report is one click away"
                        text="Create a snapshot of your optimization opportunities and share it with your team."
                      />
                    )}
                  </section>
                </>
              )}
              {page === "Audit log" && (
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <h2>Workspace audit trail</h2>
                      <p>
                        Most recent 50 events · persisted locally · tenant
                        scoped
                      </p>
                    </div>
                    <Fingerprint size={20} />
                  </div>
                  <div className="audit-list">
                    {events.map((e) => (
                      <div className="audit-row" key={e.id}>
                        <span className="audit-icon">
                          <Fingerprint size={18} />
                        </span>
                        <div>
                          <strong>{human(e.action)}</strong>
                          <p>{e.detail || e.target}</p>
                          <small>{e.actor}</small>
                        </div>
                        <time>{dateFormat(e.at, true)}</time>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {page === "Settings" && (
                <div className="settings-grid">
                  <section className="card settings-card">
                    <h2>Workspace details</h2>
                    <p>Your client’s isolated financial workspace.</p>
                    <label>
                      Organization
                      <input value={user.organization} readOnly />
                    </label>
                    <label>
                      Signed in as
                      <input value={user.email} readOnly />
                    </label>
                    <div className="settings-line">
                      <span>Role</span>
                      <Status value={user.role} />
                    </div>
                    <div className="settings-line">
                      <span>Persistence</span>
                      <strong>
                        {user.deployment === "serverless"
                          ? "DynamoDB + S3"
                          : "Local SQLite"}
                      </strong>
                    </div>
                    <div className="settings-line">
                      <span>Live collection</span>
                      <strong>
                        {user.live_enabled ? "Enabled" : "Disabled by default"}
                      </strong>
                    </div>
                  </section>
                  <section className="card settings-card">
                    <h2>Evidence & approval policy</h2>
                    <p>
                      Deterministic checks apply before a plan can be approved.
                    </p>
                    <label>
                      Maximum evidence age (hours)
                      <input
                        type="number"
                        min={1}
                        max={168}
                        value={maxAge}
                        onChange={(e) => setMaxAge(Number(e.target.value))}
                      />
                    </label>
                    <div className="check-line">
                      <CheckCircle2 size={17} /> Peak CPU and memory required
                      for compute
                    </div>
                    <div className="check-line">
                      <CheckCircle2 size={17} /> Verified owner and rollback
                      plan
                    </div>
                    <div className="check-line">
                      <CheckCircle2 size={17} /> Production maintenance window
                      required
                    </div>
                    <div className="check-line">
                      <CheckCircle2 size={17} /> Cloud mutations disabled
                    </div>
                    <button
                      className="primary"
                      onClick={async () => {
                        try {
                          await api("/policy", {
                            method: "PUT",
                            body: JSON.stringify({
                              max_evidence_age_hours: maxAge,
                            }),
                          });
                          notify("Workspace policy saved.");
                          await refresh();
                        } catch (e) {
                          notify((e as Error).message, true);
                        }
                      }}
                    >
                      Save policy
                    </button>
                  </section>
                  <AISettings
                    administrator={user.role === "admin"}
                    onSaved={() => void refresh()}
                  />
                  <section className="card settings-card full-width">
                    <h2>Your optimization workflow</h2>
                    <p>
                      Connect your accounts, collect billing, and inspect the
                      evidence behind each opportunity. Review missing telemetry
                      and business approvals before approving a plan. AWS native
                      recommendations are supported; Azure and Google Cloud
                      source recommendations can be imported. Bedrock guidance
                      requires your administrator's processing approval and an
                      enabled platform configuration.
                    </p>
                    <button
                      className="text-button"
                      onClick={() => setHelp(true)}
                    >
                      View setup guidance <ArrowRight size={15} />
                    </button>
                  </section>
                </div>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              finops autopilot <span>·</span> Cloud clarity. Confident
              decisions.
            </span>
            <span>
              <ShieldCheck size={13} /> Read-only by design <span>·</span>
              {user.deployment === "serverless"
                ? "Cloud deployment"
                : "Local development"}
            </span>
          </footer>
        </main>
      </div>
      {connectOpen && (
        <ConnectionWizard
          close={() => { setConnectOpen(false); void refresh(); }}
          created={async (c) => {
            setConnectOpen(false);
            setAccount(c);
            await refresh();
            notify(
              "Cloud scope registered. Complete the setup and collect data to verify access.",
            );
          }}
        />
      )}
      {detail && (
        <RecommendationDetail
          rec={detail}
          onAdviceGenerated={async () => {
            setDetail(
              await api<Recommendation>("/recommendations/" + detail.id),
            );
            await refresh();
          }}
          onOpenAISettings={() => {
            setDetail(null);
            navigate("Settings");
          }}
          close={() => setDetail(null)}
          analyze={() => void analyze(detail)}
          busy={busy}
          reviewed={async (next) => {
            setDetail(next);
            await refresh();
            notify("Review recorded. Cloud resources have not been changed.");
          }}
        />
      )}
      {account && (
        <AccountDetails
          connection={account}
          close={() => setAccount(null)}
          sync={() => void synchronize(account)}
          busy={busy}
          imported={async () => {
            setAccount(null);
            await refresh();
            notify("Client data imported and saved locally.");
          }}
        />
      )}
      {help && (
        <Modal
          title="Your FinOps workspace"
          subtitle="Get started with AWS, Azure and Google Cloud."
          close={() => setHelp(false)}
        >
          <div className="modal-body help-body">
            <div className="inline-notice">
              <BookOpen size={20} /> Full setup guides are in README.md and
              docs/CONNECTORS.md in the project folder.
            </div>
            <h3>1. Explore the workflow</h3>
            <p>
              Connect a real account or import verified billing data to inspect
              spend, assess evidence and review optimization plans.
            </p>
            <h3>2. Onboard a client</h3>
            <p>
              Create a separate workspace from the sign-in page, then register
              each AWS account, Azure subscription or GCP project. Use Import
              mode for CSV data, or Live mode with locally configured
              credentials.
            </p>
            <h3>3. Enable cloud collection</h3>
            <p>
              Install requirements-cloud.txt, configure the SDK credential
              chain, and set FINOPS_ENABLE_LIVE=true before starting the API.
              Provider reads can incur API and query charges.
            </p>
            <h3>4. Assess and review</h3>
            <p>
              The deterministic policy engine flags evidence gaps. Actual model
              inference is not configured. Approval records a plan only.
              Realized savings are unavailable until an attribution workflow is
              implemented.
            </p>
            <a
              className="secondary"
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
            >
              Open local API documentation <ArrowUpRight size={15} />
            </a>
          </div>
        </Modal>
      )}
      {toast && (
        <div className={`toast ${toast.error ? "error" : ""}`} role="status">
          {toast.error ? (
            <TriangleAlert size={19} />
          ) : (
            <CheckCircle2 size={19} />
          )}
          <span>{toast.text}</span>
          <button
            onClick={() => setToast(null)}
            aria-label="Dismiss notification"
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  icon: Icon,
  foot,
  accent = false,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  foot: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <section className={`kpi-card ${accent ? "accent" : ""}`}>
      <div className="kpi-top">
        <span>{label}</span>
        <span className="kpi-icon">
          <Icon size={17} />
        </span>
      </div>
      <strong className="kpi-value">{value}</strong>
      <div className="kpi-foot">{foot}</div>
    </section>
  );
}
function SpendChart({
  data,
  currency,
}: {
  data: Overview["trend"];
  currency: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 800,
    height = 220,
    left = 54,
    top = 15,
    bottom = 30,
    right = 12;
  const max =
    Math.max(
      1,
      ...data.map((d) => Number(d.aws) + Number(d.azure) + Number(d.gcp)),
    ) * 1.12;
  const plotWidth = width - left - right,
    plotHeight = height - top - bottom;
  const point = (i: number, v: number) =>
    `${left + (i / Math.max(1, data.length - 1)) * plotWidth},${top + plotHeight - (v / max) * plotHeight}`;
  const areas = (["aws", "azure", "gcp"] as Provider[]).map((p, pi) => {
    const keys = (["aws", "azure", "gcp"] as Provider[]).slice(0, pi + 1);
    const upper = data.map((d, i) =>
      point(
        i,
        keys.reduce((s, k) => s + Number(d[k]), 0),
      ),
    );
    const lower = [...data]
      .map((d, i) =>
        point(
          i,
          keys.slice(0, -1).reduce((s, k) => s + Number(d[k]), 0),
        ),
      )
      .reverse();
    return (
      <path
        key={p}
        d={"M" + upper.join(" L") + " L" + lower.join(" L") + "Z"}
        fill={colors[p]}
        fillOpacity={pi === 0 ? ".24" : ".2"}
        stroke={colors[p]}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    );
  });
  const totalValue = data.reduce(
    (sum, d) => sum + Number(d.aws) + Number(d.azure) + Number(d.gcp),
    0,
  );
  return (
    <div className="chart-wrap">
      {totalValue === 0 ? (
        <div className="chart-empty">
          <BarChart3 size={28} />
          <span>No spend in this date range</span>
        </div>
      ) : (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Daily stacked spend chart in ${currency}. ${data.length} days. AWS purple, Azure blue, Google Cloud amber.`}
          onMouseLeave={() => setHover(null)}
        >
          {[0, 1, 2, 3, 4].map((i) => (
            <g key={i}>
              <line
                x1={left}
                x2={width - right}
                y1={top + (i * plotHeight) / 4}
                y2={top + (i * plotHeight) / 4}
                stroke="#ecebf0"
                strokeDasharray="3 5"
              />
              <text
                x={left - 12}
                y={top + (i * plotHeight) / 4 + 4}
                textAnchor="end"
                fill="#92929f"
                fontSize="11"
              >
                {currencyFormat(max * (1 - i / 4), currency, true)}
              </text>
            </g>
          ))}
          {areas}
          {[0, 0.2, 0.4, 0.6, 0.8, 1].map((f) => {
            const i = Math.round(f * (data.length - 1));
            return (
              <text
                key={f}
                x={left + f * plotWidth}
                y={height - 6}
                fill="#92929f"
                fontSize="11"
                textAnchor={f === 0 ? "start" : f === 1 ? "end" : "middle"}
              >
                {dateFormat(data[i]?.date || "")}
              </text>
            );
          })}
          {data.map((d, i) => (
            <rect
              key={d.date}
              x={left + ((i - 0.5) / Math.max(1, data.length - 1)) * plotWidth}
              y={top}
              width={plotWidth / Math.max(1, data.length - 1)}
              height={plotHeight}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            >
              <title>
                {d.date}: AWS {currencyFormat(d.aws, currency)}, Azure{" "}
                {currencyFormat(d.azure, currency)}, GCP{" "}
                {currencyFormat(d.gcp, currency)}
              </title>
            </rect>
          ))}
          {hover !== null && (
            <line
              x1={left + (hover / Math.max(1, data.length - 1)) * plotWidth}
              x2={left + (hover / Math.max(1, data.length - 1)) * plotWidth}
              y1={top}
              y2={height - bottom}
              stroke="#7f5acf"
              strokeDasharray="4 3"
            />
          )}
        </svg>
      )}
      {hover !== null && (
        <div className="chart-tooltip">
          <strong>{dateFormat(data[hover].date)}</strong>
          {(["aws", "azure", "gcp"] as Provider[]).map((p) => (
            <span key={p}>
              <i style={{ background: colors[p] }} />
              {shortNames[p]} <b>{currencyFormat(data[hover][p], currency)}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
function Donut({
  data,
  total,
  currency,
}: {
  data: Overview["by_provider"];
  total: string;
  currency: string;
}) {
  let angle = 0;
  const stops = data.map((d) => {
    const start = angle;
    angle += Number(total) ? (Number(d.amount) / Number(total)) * 360 : 0;
    return `${colors[d.provider]} ${start}deg ${angle}deg`;
  });
  return (
    <div className="donut-shell">
      <div
        className="donut"
        role="img"
        aria-label={`Spend distribution: ${data.map((d) => `${shortNames[d.provider]} ${currencyFormat(d.amount, currency)}`).join(", ")}`}
        style={{
          background: Number(total)
            ? `conic-gradient(${stops.join(",")})`
            : "#eeedf2",
        }}
      >
        <div>
          <span>TOTAL SPEND</span>
          <strong>{currencyFormat(total, currency, true)}</strong>
          <small>{currency} · selected period</small>
        </div>
      </div>
    </div>
  );
}
function RecommendationTable({
  rows,
  open,
  compact = false,
}: {
  rows: Recommendation[];
  open: (r: Recommendation) => void;
  compact?: boolean;
}) {
  return (
    <div className="card table-card">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Optimization opportunity</th>
              <th>Cloud / service</th>
              {!compact && <th>Environment</th>}
              <th>Risk level</th>
              <th>Monthly estimate</th>
              <th>Status</th>
              <th>
                <span className="sr-only">View</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} onClick={() => open(r)}>
                <td>
                  <button
                    className="table-title"
                    onClick={(e) => {
                      e.stopPropagation();
                      open(r);
                    }}
                  >
                    {r.title}
                  </button>
                  <small>
                    {r.resource_id.length > 46
                      ? r.resource_id.slice(-46)
                      : r.resource_id}
                  </small>
                </td>
                <td>
                  <div className="service-cell">
                    <ProviderIcon provider={r.provider} small />
                    <span>{r.service}</span>
                  </div>
                </td>
                {!compact && (
                  <td>
                    <span className="environment">{r.environment}</span>
                  </td>
                )}
                <td>
                  <span className={`risk ${r.risk.toLowerCase()}`}>
                    <i />
                    {r.risk}
                  </span>
                </td>
                <td>
                  <strong className="savings">
                    {currencyFormat(r.savings, r.currency)}
                  </strong>
                  <small>{r.currency} / month</small>
                </td>
                <td>
                  <Status value={r.status} />
                </td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={`View ${r.title}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      open(r);
                    }}
                  >
                    <ArrowUpRight size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <Empty
          icon={Target}
          title="No opportunities here yet"
          text="Try another filter, collect cloud recommendations, or add a source estimate through a connection’s import tools."
        />
      )}
    </div>
  );
}

function Auth({ onSuccess }: { onSuccess: () => void }) {
  const [signup, setSignup] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [authMode, setAuthMode] = useState<string | null>(null);
  useEffect(() => {
    api<{ mode: string }>("/auth/config")
      .then((c) => setAuthMode(c.mode))
      .catch(() =>
        setError("Sign-in service is unavailable. Reload to retry."),
      );
  }, []);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    setError("");
    try {
      await post(signup ? "/auth/signup" : "/auth/login", body);
      await onSuccess();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-shell">
      <section className="auth-story">
        <div className="brand">
          <span className="brand-mark">
            <Activity size={24} />
          </span>
          <span>
            finops<span className="brand-light">autopilot</span>
          </span>
        </div>
        <div>
          <span className="eyebrow">ONE WORKSPACE. EVERY CLOUD.</span>
          <h1>
            Cloud clarity.
            <br />
            <span>Confident decisions.</span>
          </h1>
          <p>
            Bring AWS, Azure and Google Cloud into focus. Understand your spend
            and turn evidence into a smarter optimization plan.
          </p>
          <div className="auth-clouds">
            {(["aws", "azure", "gcp"] as Provider[]).map((p) => (
              <span key={p}>
                <ProviderIcon provider={p} />
                {shortNames[p]}
              </span>
            ))}
          </div>
          <div className="auth-proof">
            <ShieldCheck size={18} /> Read-only by design <span>·</span> Built
            for your clients
          </div>
        </div>
        <span className="auth-local">
          <span className="pulse-dot" /> MULTI-CLOUD FINOPS
        </span>
      </section>
      <section className="auth-form-panel">
        <div className="auth-form">
          <span className="eyebrow">YOUR FINOPS WORKSPACE</span>
          <h2>{signup ? "Create your workspace" : "Welcome to Autopilot"}</h2>
          <p>
            {signup
              ? "A separate space for your client’s cloud finances."
              : "Sign in to make your next cloud decision a confident one."}
          </p>
          {authMode === "cognito" ? (
            <a className="primary" href="/v1/auth/start">
              Continue with secure sign-in <ArrowRight size={16} />
            </a>
          ) : authMode === "local" ? (
            <>
              <form onSubmit={(e) => void submit(e)}>
                {signup && (
                  <>
                    <label>
                      Your name
                      <input
                        name="name"
                        required
                        minLength={2}
                        maxLength={80}
                        autoComplete="name"
                        placeholder="Your full name"
                      />
                    </label>
                    <label>
                      Organization
                      <input
                        name="organization"
                        required
                        minLength={2}
                        maxLength={100}
                        placeholder="Your client or company"
                      />
                    </label>
                  </>
                )}
                <label>
                  Email address
                  <input
                    name="email"
                    type="email"
                    required
                    autoComplete="email"
                    placeholder="you@company.com"
                  />
                </label>
                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    minLength={signup ? 12 : 1}
                    maxLength={256}
                    required
                    autoComplete={signup ? "new-password" : "current-password"}
                    placeholder={
                      signup
                        ? "At least 12 characters"
                        : "Your workspace password"
                    }
                  />
                </label>
                {error && (
                  <div className="inline-notice red" role="alert">
                    {error}
                  </div>
                )}
                <button className="primary" disabled={busy}>
                  {busy ? <LoaderCircle className="spin" size={17} /> : null}
                  {signup ? "Create workspace" : "Sign in"}
                  <ArrowRight size={16} />
                </button>
              </form>
              <p className="auth-switch">
                {signup ? "Already have a workspace?" : "New to Autopilot?"}{" "}
                <button
                  onClick={() => {
                    setSignup(!signup);
                    setError("");
                  }}
                >
                  {signup ? "Sign in" : "Create a workspace"}
                </button>
              </p>
            </>
          ) : (
            <p>Connecting to sign-in service…</p>
          )}
          <p className="auth-footnote">
            <ShieldCheck size={13} />{" "}
            {authMode === "cognito"
              ? "Cognito sign-in. Secure, isolated client workspaces."
              : "Runs on your machine. Your data is stored locally."}
          </p>
        </div>
      </section>
    </div>
  );
}

function ConnectionWizard({
  close,
  created,
}: {
  close: () => void;
  created: (c: Connection) => void;
}) {
  const [step, setStep] = useState(1);
  const [provider, setProvider] = useState<Provider>("aws");
  const [mode, setMode] = useState("live");
  const [method, setMethod] = useState("role");
  const [fields, setFields] = useState<Record<string, string>>({
    name: "",
    account_id: "",
    role_arn: "",
    region: "ap-south-1",
    tenant_id: "",
    billing_table: "",
    billing_account_id: "",
    query_project: "",
    access_key_id: "",
    secret_access_key: "",
    session_token: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const registered = useRef<Connection | null>(null);
  const change = (key: string, value: string) =>
    setFields((prev) => ({ ...prev, [key]: value }));
  async function create() {
    setBusy(true);
    setError("");
    try {
      const config =
        mode !== "live"
          ? {}
          : provider === "aws"
            ? {
                auth_method: method,
                region: fields.region,
                ...(method === "role" ? { role_arn: fields.role_arn } : {}),
              }
            : provider === "azure"
              ? { tenant_id: fields.tenant_id }
              : {
                  billing_table: fields.billing_table,
                  billing_account_id: fields.billing_account_id,
                  query_project: fields.query_project || fields.account_id,
                };
      const c =
        registered.current ||
        (await post<Connection>("/connections", {
          provider,
          mode,
          name: fields.name,
          account_id: fields.account_id,
          config,
        }));
      registered.current = c;
      if (provider === "aws" && mode === "live" && method === "access_key") {
        await api(`/connections/${c.id}/credentials`, {
          method: "PUT",
          body: JSON.stringify({
            access_key_id: fields.access_key_id,
            secret_access_key: fields.secret_access_key,
            session_token: fields.session_token,
          }),
        });
        setFields((prev) => ({
          ...prev,
          access_key_id: "",
          secret_access_key: "",
          session_token: "",
        }));
        c.credentials_configured = true;
      }
      created(c);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const accountLabel =
    provider === "aws"
      ? "AWS account ID"
      : provider === "azure"
        ? "Azure subscription ID"
        : "GCP project ID";
  return (
    <Modal
      title="Connect a cloud account"
      subtitle="Read-only access to your real cloud billing."
      close={close}
    >
      <div className="wizard-steps">
        {["Choose cloud", "Account details", "Review setup"].map((label, i) => (
          <span className={step >= i + 1 ? "current" : ""} key={label}>
            <i>{i + 1}</i>
            {label}
          </span>
        ))}
      </div>
      <div className="modal-body">
        {step === 1 && (
          <>
            <h3>Where does your client run?</h3>
            <div className="provider-options">
              {(["aws", "azure", "gcp"] as Provider[]).map((p) => (
                <button
                  key={p}
                  className={`provider-option ${provider === p ? "selected" : ""}`}
                  onClick={() => {
                    setProvider(p);
                    setFields((prev) => ({
                      ...prev,
                      access_key_id: "",
                      secret_access_key: "",
                      session_token: "",
                    }));
                  }}
                >
                  <ProviderIcon provider={p} />
                  <span>
                    <strong>{providerNames[p]}</strong>
                    <small>
                      {p === "aws"
                        ? "Account · role or access keys"
                        : p === "azure"
                          ? "Subscription · Entra identity"
                          : "Project · billing export"}
                    </small>
                  </span>
                  <span className="radio-circle">
                    {provider === p && <span />}
                  </span>
                </button>
              ))}
            </div>
            <h3>Choose a data source</h3>
            <div className="mode-options">
              {[
                {
                  id: "live",
                  title: "Live connection",
                  desc: "Read billing from your cloud account",
                },
                {
                  id: "import",
                  title: "Import client data",
                  desc: "Upload normalized billing CSV files",
                },
              ].map((m) => (
                <label key={m.id}>
                  <input
                    type="radio"
                    name="mode"
                    checked={mode === m.id}
                    onChange={() => setMode(m.id)}
                  />
                  <span>
                    <strong>{m.title}</strong>
                    <small>{m.desc}</small>
                  </span>
                </label>
              ))}
            </div>
          </>
        )}
        {step === 2 && (
          <form
            id="account-form"
            onSubmit={(e) => {
              e.preventDefault();
              setStep(3);
            }}
          >
            <div className="provider-heading">
              <ProviderIcon provider={provider} />
              <h3>{providerNames[provider]}</h3>
              <span className="badge purple">{mode}</span>
            </div>
            <label>
              Connection name
              <input
                autoFocus
                required
                minLength={2}
                maxLength={80}
                value={fields.name}
                onChange={(e) => change("name", e.target.value)}
                placeholder="Your production account"
              />
            </label>
            <label>
              {accountLabel}
              <input
                required
                value={fields.account_id}
                onChange={(e) => change("account_id", e.target.value)}
                placeholder={
                  provider === "aws"
                    ? "12-digit AWS account ID"
                    : "Your cloud scope ID"
                }
              />
            </label>
            {mode === "live" && provider === "aws" && (
              <>
                <label>
                  Authentication method
                  <select
                    value={method}
                    onChange={(e) => {
                      setMethod(e.target.value);
                      setFields((prev) => ({
                        ...prev,
                        access_key_id: "",
                        secret_access_key: "",
                        session_token: "",
                      }));
                    }}
                  >
                    <option value="role">IAM role (recommended)</option>
                    <option value="access_key">
                      Access key and secret key
                    </option>
                  </select>
                </label>
                <label>
                  AWS region
                  <input
                    required
                    value={fields.region}
                    onChange={(e) => change("region", e.target.value)}
                  />
                </label>
                {method === "role" ? (
                  <label>
                    Read-only role ARN
                    <input
                      required
                      value={fields.role_arn}
                      onChange={(e) => change("role_arn", e.target.value)}
                      placeholder="arn:aws:iam::ACCOUNT_ID:role/FinOpsAutopilotReadOnly"
                    />
                    <small>
                      Register first to obtain the external ID for the customer
                      role trust policy.
                    </small>
                  </label>
                ) : (
                  <>
                    <label>
                      Access key ID
                      <input
                        required
                        autoComplete="off"
                        spellCheck={false}
                        value={fields.access_key_id}
                        onChange={(e) =>
                          change("access_key_id", e.target.value)
                        }
                      />
                    </label>
                    <label>
                      Secret access key
                      <input
                        required
                        type="password"
                        autoComplete="new-password"
                        value={fields.secret_access_key}
                        onChange={(e) =>
                          change("secret_access_key", e.target.value)
                        }
                      />
                    </label>
                    <label>
                      Session token (temporary keys only)
                      <textarea
                        autoComplete="off"
                        spellCheck={false}
                        value={fields.session_token}
                        onChange={(e) =>
                          change("session_token", e.target.value)
                        }
                      />
                    </label>
                    <small>
                      Use a dedicated billing reader identity. Keys are
                      write-only, encrypted on the server, and never sent to
                      Bedrock.
                    </small>
                  </>
                )}
              </>
            )}
            {mode === "live" && provider === "azure" && (
              <label>
                Entra directory (tenant) ID
                <input
                  required
                  value={fields.tenant_id}
                  onChange={(e) => change("tenant_id", e.target.value)}
                />
                <small>
                  Configure the runtime's federated Azure identity before
                  collection.
                </small>
              </label>
            )}
            {mode === "live" && provider === "gcp" && (
              <>
                <label>
                  Billing account ID
                  <input
                    required
                    value={fields.billing_account_id}
                    onChange={(e) =>
                      change("billing_account_id", e.target.value)
                    }
                    placeholder="XXXXXX-XXXXXX-XXXXXX"
                  />
                </label>
                <label>
                  Billing export table
                  <input
                    required
                    value={fields.billing_table}
                    onChange={(e) => change("billing_table", e.target.value)}
                    placeholder="project.dataset.table"
                  />
                </label>
                <label>
                  Query project (optional)
                  <input
                    value={fields.query_project}
                    onChange={(e) => change("query_project", e.target.value)}
                  />
                </label>
              </>
            )}
            <div className="inline-notice">
              <ShieldCheck size={17} />
              {mode === "import"
                ? "Upload your billing CSV after registration."
                : "Registration does not verify access. Verify and collect billing after completing the setup."}
            </div>
          </form>
        )}
        {step === 3 && (
          <>
            <div className="setup-summary">
              <ProviderIcon provider={provider} />
              <div>
                <h3>{fields.name}</h3>
                <p>
                  {providerNames[provider]} · {mode}
                  {provider === "aws" && mode === "live"
                    ? ` · ${method === "role" ? "IAM role" : "Access keys"}`
                    : ""}
                </p>
                <code>{fields.account_id}</code>
              </div>
            </div>
            <h3>Ready for your account</h3>
            <p className="setup-copy">
              {mode === "import"
                ? "Upload date,service,amount,currency CSV data. Each import replaces this connection’s previous billing snapshot."
                : provider === "aws"
                  ? method === "role"
                    ? "Use the generated external ID and collector principal in your customer role trust policy. Grant billing read permissions only, then verify the connection."
                    : "Credentials are encrypted using Windows CurrentUser DPAPI locally or AWS Secrets Manager in the cloud. The first collection verifies that their AWS account matches the account ID above."
                  : "Grant the runtime identity read access for the selected scope. Azure and GCP identities require provider setup before live collection."}
            </p>
            {mode === "live" && (
              <div className="inline-notice amber">
                <TriangleAlert size={17} />
                Cloud reads can incur API and query charges. No resource changes
                will be performed.
              </div>
            )}
            {error && (
              <div className="inline-notice red" role="alert">
                {error}
                {registered.current &&
                  " The connection is registered; retry to save its credentials."}
              </div>
            )}
          </>
        )}
      </div>
      <div className="modal-actions">
        <button
          className="secondary"
          disabled={busy || (!!registered.current && step > 1)}
          onClick={step === 1 ? close : () => setStep(step - 1)}
        >
          {step === 1 ? "Cancel" : "Back"}
        </button>
        {step === 1 ? (
          <button className="primary" onClick={() => setStep(2)}>
            Continue <ArrowRight size={15} />
          </button>
        ) : step === 2 ? (
          <button className="primary" type="submit" form="account-form">
            Review setup <ArrowRight size={15} />
          </button>
        ) : (
          <button
            className="primary"
            disabled={busy}
            onClick={() => void create()}
          >
            {busy && <LoaderCircle className="spin" size={16} />}Register
            connection
          </button>
        )}
      </div>
    </Modal>
  );
}

function RecommendationDetail({
  onAdviceGenerated,
  onOpenAISettings,
  rec,
  close,
  analyze,
  busy,
  reviewed,
}: {
  onAdviceGenerated: () => Promise<void>;
  onOpenAISettings: () => void;
  rec: Recommendation;
  close: () => void;
  analyze: () => void;
  busy: string;
  reviewed: (r: Recommendation) => void;
}) {
  const [reason, setReason] = useState(""),
    [decision, setDecision] = useState("DEFERRED"),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [tab, setTab] = useState("Evidence");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setSaving(true);
    setError("");
    try {
      reviewed(
        await post<Recommendation>(`/recommendations/${rec.id}/review`, {
          version: rec.version,
          decision,
          justification: reason,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Modal
      title="Opportunity details"
      subtitle="Evidence first. Confident decisions follow."
      close={close}
      wide
    >
      <div className="detail-summary">
        <div className="detail-title">
          <ProviderIcon provider={rec.provider} />
          <div>
            <h2>{rec.title}</h2>
            <p>
              {rec.service} · {rec.region} · {rec.environment}
            </p>
          </div>
        </div>
        <div className="detail-metrics">
          <div>
            <span>Monthly source estimate</span>
            <strong>
              {currencyFormat(rec.savings, rec.currency)}
              <small> / month</small>
            </strong>
          </div>
          <Status value={rec.status} />
          <span className={`risk ${rec.risk.toLowerCase()}`}>
            <i />
            {rec.risk} risk
          </span>
        </div>
      </div>
      <div className="detail-tabs">
        {["Evidence", "Assessment", "Bedrock guidance", "Review plan"].map(
          (t) => (
            <button
              key={t}
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ),
        )}
      </div>
      <div className="modal-body">
        {tab === "Evidence" && (
          <>
            <div className="evidence-grid">
              <div>
                <span>Resource identifier</span>
                <code>{rec.resource_id}</code>
              </div>
              <div>
                <span>Source</span>
                <strong>{rec.evidence.source}</strong>
              </div>
              <div>
                <span>Workload owner</span>
                <strong>{rec.owner || "Unassigned"}</strong>
              </div>
              <div>
                <span>Collected at</span>
                <strong>{dateFormat(rec.collected_at, true)}</strong>
              </div>
              <div>
                <span>Peak CPU</span>
                <strong>
                  {rec.evidence.cpu_peak == null
                    ? "Unknown"
                    : rec.evidence.cpu_peak + "%"}
                </strong>
              </div>
              <div>
                <span>Peak memory</span>
                <strong
                  className={
                    rec.evidence.memory_peak == null ? "amber-text" : ""
                  }
                >
                  {rec.evidence.memory_peak == null
                    ? "Missing evidence"
                    : rec.evidence.memory_peak + "%"}
                </strong>
              </div>
              <div>
                <span>Source record</span>
                <code>{rec.evidence.source_id}</code>
              </div>
              <div>
                <span>Revision</span>
                <strong>v{rec.version}</strong>
              </div>
            </div>
            <h3>Coverage & assumptions</h3>
            {rec.evidence.limitations.map((s) => (
              <p className="limitation" key={s}>
                <TriangleAlert size={15} />
                {s}
              </p>
            ))}
            <p className="muted small-copy">
              This estimate is potential savings. Other recommendations for the
              same workload may overlap. Realized savings have not been
              verified.
            </p>
            <button
              className="primary"
              disabled={!!busy}
              onClick={() => {
                analyze();
                setTab("Assessment");
              }}
            >
              <FlaskConical size={16} /> Assess evidence
            </button>
          </>
        )}
        {tab === "Assessment" &&
          (rec.analysis ? (
            <>
              <div className="assessment-heading">
                <Status value={rec.analysis.outcome} />
                <span className="subtle-tag">{rec.analysis.engine}</span>
              </div>
              <p className="assessment-copy">{rec.analysis.summary}</p>
              <div className="route-box">
                <span>Next investigation</span>
                <code>{rec.analysis.choice}</code>
                <small>
                  Rule-based routing · model inference not configured ·
                  confidence unavailable
                </small>
              </div>
              <h3>
                {rec.analysis.gaps.length
                  ? "Evidence needed before approval"
                  : "Local evidence checks passed"}
              </h3>
              {rec.analysis.gaps.map((g) => (
                <p className="limitation" key={g}>
                  <TriangleAlert size={15} />
                  {g}
                </p>
              ))}
              {!rec.analysis.gaps.length && (
                <p className="limitation">
                  <CheckCircle2 size={16} /> Continue to review the proposed
                  plan. This assessment does not guarantee workload safety.
                </p>
              )}
              <h3>Proposed investigation & change plan</h3>
              <ol className="plan-steps">
                {rec.analysis.change_plan.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
              <h3>Rollback prerequisite</h3>
              <p className="muted">{rec.analysis.rollback_plan}</p>
              <div className="hash-box">
                Evidence SHA-256 <code>{rec.analysis.evidence_hash}</code>
              </div>
              <button className="secondary" disabled={!!busy} onClick={analyze}>
                <RefreshCw size={15} /> Reassess evidence
              </button>
            </>
          ) : (
            <Empty
              icon={FlaskConical}
              title={
                busy === "analyze"
                  ? "Assessing source evidence…"
                  : "Start with the evidence"
              }
              text="The local policy engine checks source freshness, owner, telemetry and rollback prerequisites."
              action={
                <button className="primary" disabled={!!busy} onClick={analyze}>
                  {busy === "analyze" ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <FlaskConical size={16} />
                  )}{" "}
                  Run evidence assessment
                </button>
              }
            />
          ))}
        {tab === "Bedrock guidance" && (
          <BedrockAdvice
            id={rec.id}
            version={rec.version}
            hasAssessment={!!rec.analysis}
            advice={rec.advisory}
            onRefresh={onAdviceGenerated}
            onSettings={onOpenAISettings}
          />
        )}
        {tab === "Review plan" &&
          (rec.status === "NEEDS_REVIEW" && rec.analysis ? (
            <form onSubmit={(e) => void submit(e)}>
              <div className="inline-notice">
                <ShieldCheck size={17} /> Your decision records a plan only. The
                application does not modify cloud resources.
              </div>
              <label>
                Review decision
                <select
                  value={decision}
                  onChange={(e) => setDecision(e.target.value)}
                >
                  <option value="DEFERRED">Defer — gather more context</option>
                  <option
                    value="APPROVED_PLAN"
                    disabled={rec.analysis.gaps.length > 0}
                  >
                    Approve plan
                    {rec.analysis.gaps.length > 0
                      ? " — blocked by evidence gaps"
                      : ""}
                  </option>
                  <option value="REJECTED">Reject recommendation</option>
                </select>
              </label>
              <label>
                Justification
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  rows={4}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Explain the business context and rationale for this decision…"
                />
              </label>
              {error && (
                <div className="inline-notice red" role="alert">
                  {error}
                </div>
              )}
              <button className="primary" disabled={saving || !!busy}>
                {saving && <LoaderCircle size={16} className="spin" />}
                <ShieldCheck size={16} /> Record decision
              </button>
            </form>
          ) : rec.review ? (
            <div>
              <Status value={rec.status} />
              <h3>Reviewer’s justification</h3>
              <p>{rec.review.justification}</p>
              <small className="muted">
                {rec.review.actor} · {dateFormat(rec.review.at, true)}
              </small>
            </div>
          ) : (
            <Empty
              icon={ShieldCheck}
              title="Assessment comes first"
              text="Assess the evidence before approving, rejecting or deferring this plan."
              action={
                <button
                  className="primary"
                  disabled={!!busy}
                  onClick={() => {
                    analyze();
                    setTab("Assessment");
                  }}
                >
                  Assess evidence <ArrowRight size={15} />
                </button>
              }
            />
          ))}
      </div>
    </Modal>
  );
}

function AccountDetails({
  connection: c,
  close,
  sync,
  busy,
  imported,
}: {
  connection: Connection;
  close: () => void;
  sync: () => void;
  busy: string;
  imported: () => void;
}) {
  const [error, setError] = useState(""),
    [saving, setSaving] = useState(false),
    [json, setJson] = useState(""),
    [showImport, setShowImport] = useState(false);
  async function importCsv(file?: File) {
    if (!file) return;
    setSaving(true);
    setError("");
    try {
      await post(`/connections/${c.id}/import`, { csv: await file.text() });
      imported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const template = {
    title: "",
    source_id: "your-source-recommendation-id",
    resource_id: "your-resource-id",
    service:
      c.provider === "azure"
        ? "Virtual Machines"
        : c.provider === "gcp"
          ? "Compute Engine"
          : "EC2",
    category: "compute",
    savings: "",
    currency: "USD",
    owner: "",
    environment: "Production",
    region: "unknown",
    source: "Customer-provided source export",
    observed_at: new Date().toISOString(),
  };
  return (
    <Modal
      title="Connection details"
      subtitle="Scope configuration and collection status."
      close={close}
    >
      <div className="modal-body">
        <div className="setup-summary">
          <ProviderIcon provider={c.provider} />
          <div>
            <h3>{c.name}</h3>
            <code>{c.account_id}</code>
          </div>
          <Status value={c.status} />
        </div>
        <div className="evidence-grid">
          <div>
            <span>Data source</span>
            <strong>{c.mode}</strong>
          </div>
          <div>
            <span>Last successful sync</span>
            <strong>{dateFormat(c.last_sync, true)}</strong>
          </div>
        </div>
        {c.error && <div className="inline-notice red">{c.error}</div>}
        {c.warnings?.map((w) => (
          <div className="inline-notice amber" key={w}>
            <TriangleAlert size={16} />
            {w}
          </div>
        ))}
        {c.mode === "live" && (
          <>
            <h3>Read-only setup</h3>
            <p className="muted">
              {c.provider === "aws" && c.config.auth_method === "access_key"
                ? "Access keys are stored in the encrypted server vault. Use a dedicated billing reader identity and rotate keys regularly."
                : c.provider === "aws"
                  ? "Configure a customer role trust policy for the local operator’s authorized principal, requiring this external ID. Grant only the read permissions described in docs/CONNECTORS.md."
                  : c.provider === "azure"
                    ? "Grant Cost Management Reader and subscription read access at this subscription. Authenticate the local runtime in the configured Entra directory."
                    : "Use ADC or workload identity federation with BigQuery Job User at the query project and Data Viewer at the export dataset. The standard billing export must already exist."}
            </p>
            {Object.entries(c.config).map(([k, v]) => (
              <div className="config-line" key={k}>
                <span>{human(k)}</span>
                <code>{v}</code>
              </div>
            ))}
            <div className="inline-notice">
              <BookOpen size={17} /> Install requirements-cloud.txt and set
              FINOPS_ENABLE_LIVE=true in your local environment. A successful
              sync verifies billing access, not a full IAM permission audit.
            </div>
          </>
        )}
        {c.provider === "aws" &&
          c.mode === "live" &&
          c.config.auth_method === "access_key" && (
            <AWSKeyForm connection={c} saved={imported} />
          )}
        {c.mode === "import" && (
          <>
            <h3>Upload a billing snapshot</h3>
            <p className="muted">
              CSV columns: <code>date,service,amount,currency</code>. One
              aggregated row per date, service and currency. Each upload
              replaces prior billing rows for this connection.
            </p>
            <label className="upload-zone">
              <Upload size={25} />
              <strong>{saving ? "Importing…" : "Choose a billing CSV"}</strong>
              <small>Up to 10,000 rows · 1.8 MB text</small>
              <input
                type="file"
                accept=".csv,text/csv"
                disabled={saving}
                onChange={(e) => void importCsv(e.target.files?.[0])}
              />
            </label>
          </>
        )}
        {
          <>
            <button
              className="text-button"
              onClick={() => {
                setShowImport(!showImport);
                if (!json) setJson(JSON.stringify(template, null, 2));
              }}
            >
              <Plus size={16} /> Import a source recommendation
            </button>
            {showImport && (
              <>
                <p className="muted small-copy">
                  Replace every example field with verified source data. Imports
                  do not establish telemetry or rollback readiness, and do not
                  contribute to deduplicated savings totals.
                </p>
                <textarea
                  aria-label="Recommendation JSON"
                  rows={13}
                  className="json-input"
                  value={json}
                  onChange={(e) => setJson(e.target.value)}
                />
                <button
                  className="secondary"
                  disabled={saving}
                  onClick={async () => {
                    setError("");
                    setSaving(true);
                    try {
                      await post(
                        `/connections/${c.id}/recommendations`,
                        JSON.parse(json),
                      );
                      imported();
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  Import source estimate
                </button>
              </>
            )}
          </>
        }
        {error && (
          <div className="inline-notice red" role="alert">
            {error}
          </div>
        )}
      </div>
      <div className="modal-actions">
        <button className="secondary" onClick={close}>
          Close
        </button>
        {c.mode !== "import" && (
          <button className="primary" disabled={!!busy} onClick={sync}>
            <RefreshCw size={16} className={busy ? "spin" : ""} />
            Verify & collect billing
          </button>
        )}
      </div>
    </Modal>
  );
}

function AWSKeyForm({
  connection,
  saved,
}: {
  connection: Connection;
  saved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    setBusy(true);
    setError("");
    try {
      await api(`/connections/${connection.id}/credentials`, {
        method: "PUT",
        body: JSON.stringify(values),
      });
      form.reset();
      setOpen(false);
      saved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h3>Access-key credentials</h3>
      <p className="muted">
        {connection.credentials_configured
          ? "Encrypted credentials are configured. Replacing them requires another verification."
          : "Save credentials before the first collection."}
      </p>
      <button className="secondary" onClick={() => setOpen(!open)}>
        {open ? "Cancel credential update" : "Save or rotate access keys"}
      </button>
      {open && (
        <form onSubmit={(e) => void submit(e)}>
          <label>
            Access key ID
            <input
              name="access_key_id"
              required
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <label>
            Secret access key
            <input
              name="secret_access_key"
              required
              type="password"
              autoComplete="new-password"
            />
          </label>
          <label>
            Session token (temporary keys only)
            <textarea
              name="session_token"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          {error && (
            <p role="alert" className="inline-notice red">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            Save encrypted credentials
          </button>
        </form>
      )}
    </section>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
