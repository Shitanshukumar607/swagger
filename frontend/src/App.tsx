import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import "./App.css";

interface TestCase {
  id: string;
  name: string;
  description: string;
  method: string;
  path: string;
  expected_status: number;
  payload?: Record<string, unknown>;
  headers?: Record<string, string>;
  params?: Record<string, string>;
  category: string;
}

interface RunResult {
  id: string;
  name: string;
  status: "passed" | "failed" | "error";
  expected_status: number;
  actual_status?: number;
  message: string;
}

interface Summary {
  passed: number;
  failed: number;
  errored: number;
  total: number;
}

type Phase = "upload" | "tests" | "results";

const API_BASE = "http://localhost:8000";

// ── SVG Icons ────────────────────────────────────────────────────────────────

function UploadIcon() {
  return (
    <svg
      className="upload-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg
      className="upload-file-icon"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function TerminalIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  );
}

// ── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [baseUrl, setBaseUrl] = useState("http://localhost:3000");
  const [phase, setPhase] = useState<Phase>("upload");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tests, setTests] = useState<TestCase[]>([]);
  const [results, setResults] = useState<RunResult[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── File pick / drag ────────────────────────────────────────────────────

  function handleFile(f: File) {
    setFile(f);
    setError("");
    setPhase("upload");
    setTests([]);
    setResults([]);
    setSummary(null);
  }

  function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.[0]) handleFile(e.target.files[0]);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  // ── Generate tests ──────────────────────────────────────────────────────

  async function generateTests() {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/generate-tests`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Server error ${res.status}`);
      }
      const data = await res.json();
      setTests(data.tests);
      setPhase("tests");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  // ── Run tests ───────────────────────────────────────────────────────────

  async function runTests() {
    if (!tests.length) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/run-tests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tests, base_url: baseUrl }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Server error ${res.status}`);
      }
      const data = await res.json();
      setResults(data.results);
      setSummary(data.summary);
      setPhase("results");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const resultById = results.reduce<Record<string, RunResult>>((acc, r) => {
    acc[r.id] = r;
    return acc;
  }, {});

  return (
    <div className="app">
      <header className="navbar">
        <div className="navbar-brand">
          <TerminalIcon />
          <span className="navbar-title">Swagger Test Generator</span>
          <span className="navbar-badge">v1.0</span>
        </div>
      </header>

      <main className="main animate-fade-in">
        <section className="hero">
          <span className="hero-label">Automated QA</span>
          <h1 className="hero-heading">Validate your API in seconds.</h1>
          <p className="hero-subtext">
            Upload your Swagger specification to automatically generate and execute 
            negative test cases against your API.
          </p>
        </section>

        {/* Upload card */}
        <div className="card animate-fade-in" id="upload-card">
          <div
            className={`upload-zone${dragOver ? " drag-over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            id="upload-zone"
            role="button"
            aria-label="Upload swagger file"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={onFileChange}
              id="file-input"
              style={{ display: "none" }}
            />
            <UploadIcon />
            <p className="upload-primary-text">
              {file ? "Replace Swagger File" : "Drop your spec here or click to browse"}
            </p>
            <p className="upload-hint">Supports OpenAPI .json files</p>

            {file && (
              <div
                className="upload-file-name"
                onClick={(e) => e.stopPropagation()}
              >
                <FileIcon />
                {file.name}
              </div>
            )}
          </div>

          {/* Base URL */}
          <div className="input-section">
            <div className="input-group">
              <label className="input-label" htmlFor="base-url-input">
                API Base URL
              </label>
              <input
                id="base-url-input"
                className="input-field"
                type="url"
                placeholder="http://localhost:3000"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </div>
          </div>

          {error && phase === "upload" && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}

          {/* Generate button */}
          {file && (
            <div className="action-row">
              <button
                id="generate-btn"
                className="btn-primary"
                onClick={generateTests}
                disabled={loading}
              >
                {loading ? <span className="spinner" /> : null}
                {loading ? "Generating…" : "Generate Tests"}
              </button>
            </div>
          )}
        </div>

        {/* Tests card */}
        {phase !== "upload" && (
          <div className="card tests-card animate-fade-in" id="tests-card">
            <div className="tests-header">
              <span className="tests-count">{tests.length} test cases generated</span>
            </div>

            {error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}

            {/* Summary bar after run */}
            {summary && (
              <div className="summary-bar" id="summary-bar">
                <div className="summary-stat">
                  <span className="summary-value">{summary.total}</span>
                  <span className="summary-label">Total</span>
                </div>
                <div className="summary-stat">
                  <span className="summary-value passed-val">{summary.passed}</span>
                  <span className="summary-label">Passed</span>
                </div>
                <div className="summary-stat">
                  <span className="summary-value failed-val">{summary.failed}</span>
                  <span className="summary-label">Failed</span>
                </div>
                <div className="summary-stat">
                  <span className="summary-value error-val">{summary.errored}</span>
                  <span className="summary-label">Errors</span>
                </div>
              </div>
            )}

            {/* Test list */}
            <div className="test-list" id="test-list">
              {tests.map((t) => {
                const result = resultById[t.id];
                const statusClass = result?.status ?? "";
                return (
                  <div
                    key={t.id}
                    className={`test-item ${statusClass}`}
                    id={`test-${t.id}`}
                  >
                    <div className={`test-status-dot ${statusClass}`} />
                    <div className="test-info">
                      <div className="test-name" title={t.name}>
                        {t.name}
                      </div>
                      <div className="test-meta">
                        <span className={`test-method ${t.method}`}>
                          {t.method}
                        </span>
                        <span className="test-path" title={t.path}>
                          {t.path}
                        </span>
                      </div>
                    </div>
                    {result && (
                      <span className={`test-result-text ${result.status}`}>
                        {result.actual_status
                          ? `${result.actual_status} · `
                          : ""}
                        {result.status}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Run button */}
            <div className="action-row">
              <button
                id="run-btn"
                className={phase === "results" ? "btn-secondary" : "btn-green"}
                onClick={runTests}
                disabled={loading}
              >
                {loading ? <span className="spinner" /> : null}
                {loading ? "Running…" : phase === "results" ? "Run Again" : "Execute Tests"}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
