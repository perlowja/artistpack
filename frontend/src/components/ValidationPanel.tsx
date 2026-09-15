"use client";

import { useEffect, useState } from "react";
import { api, APIError } from "@/lib/api-client";
import type { PublishValidationOut } from "@/lib/api-types";
import { ApiErrorBanner } from "@/components/ApiErrorBanner";

/**
 * Renders a `PublishValidationOut` as a live checklist of the four
 * publish-gate checks from `docs/api-design.md` §"the gate":
 *
 *   1. Structural — manifest passes `schema/pack.schema.json`.
 *   2. C2PA provenance — every artwork has a verified C2PA record.
 *   3. License — `rights.license` is a recognized SPDX id or
 *      `artistpack-display-license-1.0`.
 *   4. Attribution — every artwork has non-empty
 *      `attribution.display_name`.
 *
 * Pass/fail for each is derived by *matching* the error paths coming
 * back from the backend, so the dashboard stays in sync with whatever
 * the gate enforces server-side without duplicating the rule list
 * client-side.
 */

export interface PublishCheck {
  id: "structural" | "c2pa" | "license" | "attribution";
  label: string;
  description: string;
  /** True when there are no errors matching this check. */
  ok: boolean;
  /** Errors attributed to this check, if any. */
  errors: { path: string; message: string }[];
}

export interface ValidationPanelProps {
  token: string;
  packPublicId: string;
  /** Optional server-rendered initial validation so the panel is populated
   *  immediately on first paint. */
  initial?: PublishValidationOut | null;
  /** Fires when checks are done loading (or refreshed) with the
   *  derived per-check summary. */
  onChange?: (checks: PublishCheck[]) => void;
}

export function classifyErrors(
  errors: PublishValidationOut["errors"],
): PublishCheck[] {
  const checks: PublishCheck[] = [
    {
      id: "structural",
      label: "Manifest schema",
      description:
        "Generated manifest must validate against schema/pack.schema.json.",
      ok: !errors.some((e) => e.path.startsWith("manifest.")),
      errors: errors.filter((e) => e.path.startsWith("manifest.")),
    },
    {
      id: "c2pa",
      label: "C2PA provenance",
      description:
        "Every artwork must have a verified C2PA Content Credentials record.",
      ok: !errors.some(
        (e) =>
          e.path.includes("provenance.c2pa") ||
          e.path.includes("provenance.verification_status"),
      ),
      errors: errors.filter(
        (e) =>
          e.path.includes("provenance.c2pa") ||
          e.path.includes("provenance.verification_status"),
      ),
    },
    {
      id: "license",
      label: "License is recognized",
      description:
        "rights.license must be a recognized SPDX id or artistpack-display-license-1.0.",
      ok: !errors.some(
        (e) => e.path === "rights.license" || e.path === "artworks[].license",
      ),
      errors: errors.filter(
        (e) => e.path === "rights.license" || e.path === "artworks[].license",
      ),
    },
    {
      id: "attribution",
      label: "Attribution on every artwork",
      description:
        "Every artwork must have a non-empty attribution.display_name.",
      ok: !errors.some((e) => e.path.includes("attribution.display_name")),
      errors: errors.filter((e) => e.path.includes("attribution.display_name")),
    },
  ];
  return checks;
}

export function ValidationPanel(props: ValidationPanelProps) {
  const [validation, setValidation] = useState<PublishValidationOut | null>(
    props.initial ?? null,
  );
  const [error, setError] = useState<APIError | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const result = await api.validation(props.token, props.packPublicId);
      setValidation(result);
      if (props.onChange) {
        props.onChange(classifyErrors(result.errors));
      }
    } catch (err) {
      if (err instanceof APIError) setError(err);
      else
        setError(
          new APIError({
            status: 0,
            code: "unknown",
            message: err instanceof Error ? err.message : "Failed.",
          }),
        );
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (props.initial) {
      // Fire onChange once on mount with initial data.
      if (props.onChange) {
        props.onChange(classifyErrors(props.initial.errors));
      }
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.packPublicId]);

  const checks = validation ? classifyErrors(validation.errors) : [];
  const allOk = checks.length > 0 && checks.every((c) => c.ok);
  const blockingErrors = validation ? validation.errors.length : 0;

  return (
    <section className="card stack" data-testid="validation-panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Publish gate</h2>
        <div className="btn-row">
          <button
            type="button"
            className="btn-secondary"
            onClick={refresh}
            disabled={refreshing}
            data-testid="refresh-validation"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        The publish action runs the same gate server-side. Until every
        check below is green, publishing will be rejected with a 422 and
        the exact <code>details.errors[]</code> shown below.
      </p>

      {error ? <ApiErrorBanner error={error} /> : null}

      {validation ? (
        <>
          <ul className="checklist" data-testid="validation-checks">
            {checks.map((check) => (
              <li
                key={check.id}
                data-testid={`check-${check.id}`}
                data-ok={check.ok ? "true" : "false"}
              >
                <span
                  className={`check-icon ${check.ok ? "ok" : "fail"}`}
                  aria-hidden
                >
                  {check.ok ? "✓" : "✗"}
                </span>
                <span>
                  <strong>{check.label}</strong>
                  <span className="muted"> &mdash; {check.description}</span>
                  {check.errors.length > 0 ? (
                    <ul
                      style={{
                        margin: "0.4rem 0 0",
                        paddingLeft: "1rem",
                        fontSize: "0.85rem",
                      }}
                    >
                      {check.errors.map((e, idx) => (
                        <li key={idx} className="check-meta">
                          <code>{e.path}</code>: {e.message}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>

          <div
            className={allOk ? "info-banner" : "warning-banner"}
            data-testid="validation-summary"
            data-all-ok={allOk ? "true" : "false"}
          >
            {allOk
              ? `All checks pass (${checks.length}/${checks.length}). The publish action will succeed.`
              : `${blockingErrors} blocking error${blockingErrors === 1 ? "" : "s"} remaining.`}
          </div>
        </>
      ) : !error ? (
        <p className="loading">Loading validation…</p>
      ) : null}
    </section>
  );
}