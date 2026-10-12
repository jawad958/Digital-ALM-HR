"use client";

/**
 * Renders any Alpago form from its server-side definition.
 *
 * The definition carries sections → fields, each with a type. Nothing here
 * knows which form it is drawing, so adding a form to FORM_REGISTRY on the
 * backend makes it appear here with no frontend change.
 */

import { useMemo, useState } from "react";

export function FormRenderer({ definition, value, onChange, disabled = false }) {
  function set(key, v) {
    onChange({ ...value, [key]: v });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
      {definition.sections.map((section) => (
        <section key={section.title}>
          <div
            className="upper"
            style={{
              paddingBottom: 8,
              marginBottom: 14,
              borderBottom: "1px solid var(--color-stroke)",
              color: "var(--color-brand)",
            }}
          >
            {section.title}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 15 }}>
            {section.fields.map((field) => (
              <Field
                key={field.key}
                field={field}
                value={value[field.key]}
                onChange={(v) => set(field.key, v)}
                disabled={disabled}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Label({ field }) {
  return (
    <label className="field-label" htmlFor={field.key}>
      {field.label}
      {field.required && <span style={{ color: "var(--color-bad)" }}> *</span>}
    </label>
  );
}

function Help({ field }) {
  if (!field.help) return null;
  return (
    <div style={{ fontSize: 11, color: "var(--color-muted)", marginTop: 5 }}>{field.help}</div>
  );
}

function Field({ field, value, onChange, disabled }) {
  const common = { id: field.key, disabled, placeholder: field.placeholder || "" };

  switch (field.type) {
    case "textarea":
      return (
        <div>
          <Label field={field} />
          <textarea {...common} rows={4} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
          <Help field={field} />
        </div>
      );

    case "date":
      return (
        <div>
          <Label field={field} />
          <input {...common} type="date" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
          <Help field={field} />
        </div>
      );

    case "number":
      return (
        <div>
          <Label field={field} />
          <input
            {...common} type="number" value={value ?? ""}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          />
          <Help field={field} />
        </div>
      );

    case "currency":
      return (
        <div>
          <Label field={field} />
          <div style={{ position: "relative" }}>
            <span style={{
              position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)",
              fontSize: 12, color: "var(--color-muted)", pointerEvents: "none",
            }}>
              AED
            </span>
            <input
              {...common} type="number" min="0" style={{ paddingLeft: 44 }}
              value={value ?? ""}
              onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
            />
          </div>
          <Help field={field} />
        </div>
      );

    case "select":
      return (
        <div>
          <Label field={field} />
          <select {...common} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
            <option value="">— select —</option>
            {field.options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <Help field={field} />
        </div>
      );

    case "multiselect": {
      const selected = Array.isArray(value) ? value : [];
      return (
        <div>
          <Label field={field} />
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 4 }}>
            {field.options.map((o) => (
              <label key={o.value} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13 }}>
                <input
                  type="checkbox" style={{ width: "auto" }} disabled={disabled}
                  checked={selected.includes(o.value)}
                  onChange={(e) =>
                    onChange(e.target.checked
                      ? [...selected, o.value]
                      : selected.filter((v) => v !== o.value))
                  }
                />
                <span>{o.label}</span>
              </label>
            ))}
          </div>
          <Help field={field} />
        </div>
      );
    }

    case "checkbox":
      return (
        <label
          style={{
            display: "flex", alignItems: "flex-start", gap: 10,
            padding: "11px 13px", borderRadius: 9, fontSize: 13, lineHeight: 1.6,
            border: `1px solid ${value ? "var(--color-brand)" : "var(--color-stroke)"}`,
            background: value ? "var(--color-brand-soft)" : "transparent",
            cursor: disabled ? "default" : "pointer",
          }}
        >
          <input
            type="checkbox" style={{ width: "auto", marginTop: 3, flexShrink: 0 }}
            disabled={disabled} checked={value === true}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>
            {field.label}
            {field.required && <span style={{ color: "var(--color-bad)" }}> *</span>}
          </span>
        </label>
      );

    case "rating_grid":
      return <RatingGrid field={field} value={value} onChange={onChange} disabled={disabled} />;

    case "yesno_grid":
      return <YesNoGrid field={field} value={value} onChange={onChange} disabled={disabled} />;

    case "table":
      return <TableField field={field} value={value} onChange={onChange} disabled={disabled} />;

    default:
      return (
        <div>
          <Label field={field} />
          <input {...common} type="text" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
          <Help field={field} />
        </div>
      );
  }
}

function RatingGrid({ field, value, onChange, disabled }) {
  const scores = value || {};
  const average = useMemo(() => {
    const nums = Object.values(scores).filter((n) => typeof n === "number");
    return nums.length ? (nums.reduce((a, b) => a + b, 0) / nums.length).toFixed(1) : null;
  }, [scores]);

  return (
    <div>
      <Label field={field} />
      <div className="panel" style={{ marginTop: 6 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: "40%" }}>Criterion</th>
              {field.scale.map((s) => (
                <th key={s.value} style={{ textAlign: "center" }}>{s.value}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {field.rows.map((row) => (
              <tr key={row}>
                <td style={{ color: "var(--color-ink)" }}>{row}</td>
                {field.scale.map((s) => (
                  <td key={s.value} style={{ textAlign: "center" }}>
                    <input
                      type="radio" style={{ width: "auto" }} disabled={disabled}
                      name={`${field.key}:${row}`}
                      checked={scores[row] === s.value}
                      onChange={() => onChange({ ...scores, [row]: s.value })}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 7, fontSize: 11, color: "var(--color-muted)" }}>
        <span>{field.scale.map((s) => s.label).join("  ·  ")}</span>
        {average && <span style={{ color: "var(--color-brand)", fontWeight: 600 }}>Average {average}</span>}
      </div>
    </div>
  );
}

function YesNoGrid({ field, value, onChange, disabled }) {
  const answers = value || {};
  return (
    <div>
      <Label field={field} />
      <div className="panel" style={{ marginTop: 6 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: "70%" }}>Question</th>
              <th style={{ textAlign: "center" }}>Yes</th>
              <th style={{ textAlign: "center" }}>No</th>
            </tr>
          </thead>
          <tbody>
            {field.rows.map((row) => (
              <tr key={row}>
                <td style={{ color: "var(--color-ink)" }}>{row}</td>
                {[true, false].map((v) => (
                  <td key={String(v)} style={{ textAlign: "center" }}>
                    <input
                      type="radio" style={{ width: "auto" }} disabled={disabled}
                      name={`${field.key}:${row}`}
                      checked={answers[row] === v}
                      onChange={() => onChange({ ...answers, [row]: v })}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TableField({ field, value, onChange, disabled }) {
  const rows = Array.isArray(value) && value.length
    ? value
    : [Object.fromEntries(field.columns.map((c) => [c.key, ""]))];

  function setCell(i, key, v) {
    const next = rows.map((r, idx) => (idx === i ? { ...r, [key]: v } : r));
    onChange(next);
  }
  function addRow() {
    onChange([...rows, Object.fromEntries(field.columns.map((c) => [c.key, ""]))]);
  }
  function removeRow(i) {
    onChange(rows.filter((_, idx) => idx !== i));
  }

  const total = field.total_column
    ? rows.reduce((sum, r) => sum + (Number(r[field.total_column]) || 0), 0)
    : null;

  return (
    <div>
      <Label field={field} />
      <div className="panel" style={{ marginTop: 6 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 36 }}>#</th>
              {field.columns.map((c) => <th key={c.key}>{c.label}</th>)}
              {!disabled && <th style={{ width: 40 }}></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="num" style={{ color: "var(--color-muted)" }}>{i + 1}</td>
                {field.columns.map((c) => (
                  <td key={c.key}>
                    <input
                      type={c.type === "number" ? "number" : "text"}
                      disabled={disabled}
                      value={row[c.key] ?? ""}
                      onChange={(e) =>
                        setCell(i, c.key, c.type === "number"
                          ? (e.target.value === "" ? "" : Number(e.target.value))
                          : e.target.value)
                      }
                      style={{ padding: "6px 9px", fontSize: 12 }}
                    />
                  </td>
                ))}
                {!disabled && (
                  <td style={{ textAlign: "center" }}>
                    <button
                      type="button" className="btn btn-sm btn-ghost"
                      onClick={() => removeRow(i)} aria-label="Remove row"
                      disabled={rows.length === 1}
                    >
                      ×
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {total !== null && (
              <tr>
                <td></td>
                <td style={{ fontWeight: 600, color: "var(--color-ink)" }}>TOTAL</td>
                <td className="num" style={{ fontWeight: 600, color: "var(--color-brand)" }}>
                  AED {total.toLocaleString()}
                </td>
                {!disabled && <td></td>}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!disabled && (
        <button type="button" className="btn btn-sm" style={{ marginTop: 8 }} onClick={addRow}>
          + Add row
        </button>
      )}
    </div>
  );
}

/** Read-only rendering of a submitted form's data. */
export function FormReadout({ definition, data }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {definition.sections.map((section) => (
        <section key={section.title}>
          <div
            className="upper"
            style={{
              paddingBottom: 8, marginBottom: 12,
              borderBottom: "1px solid var(--color-stroke)",
              color: "var(--color-brand)",
            }}
          >
            {section.title}
          </div>
          <dl className="kv">
            {section.fields.map((f) => (
              <div key={f.key} style={{ display: "contents" }}>
                <dt>{f.label.length > 60 ? f.label.slice(0, 57) + "…" : f.label}</dt>
                <dd><ReadValue field={f} value={data[f.key]} /></dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

function ReadValue({ field, value }) {
  if (value === null || value === undefined || value === "") {
    return <span style={{ color: "var(--color-muted)" }}>—</span>;
  }

  if (field.type === "checkbox") return value ? "Yes" : "No";

  if (field.type === "select") {
    return field.options?.find((o) => o.value === value)?.label ?? String(value);
  }

  if (field.type === "multiselect" && Array.isArray(value)) {
    const labels = value.map((v) => field.options?.find((o) => o.value === v)?.label ?? v);
    return labels.join(", ") || "—";
  }

  if (field.type === "currency") return `AED ${Number(value).toLocaleString()}`;

  if (field.type === "rating_grid" && typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) return "—";
    const avg = (entries.reduce((a, [, v]) => a + Number(v), 0) / entries.length).toFixed(1);
    return (
      <div>
        <div style={{ fontWeight: 600, color: "var(--color-brand)", marginBottom: 5 }}>
          Average {avg} / 5
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.8 }}>
          {entries.map(([k, v]) => (
            <div key={k}>{k}: <strong>{v}</strong></div>
          ))}
        </div>
      </div>
    );
  }

  if (field.type === "yesno_grid" && typeof value === "object") {
    return (
      <div style={{ fontSize: 12, lineHeight: 1.8 }}>
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>{k} <strong>{v ? "Yes" : "No"}</strong></div>
        ))}
      </div>
    );
  }

  if (field.type === "table" && Array.isArray(value)) {
    const total = field.total_column
      ? value.reduce((s, r) => s + (Number(r[field.total_column]) || 0), 0)
      : null;
    return (
      <div style={{ fontSize: 12, lineHeight: 1.8 }}>
        {value.map((r, i) => (
          <div key={i}>
            {field.columns.map((c) => r[c.key]).filter(Boolean).join(" — ")}
          </div>
        ))}
        {total !== null && (
          <div style={{ fontWeight: 600, color: "var(--color-brand)", marginTop: 4 }}>
            Total AED {total.toLocaleString()}
          </div>
        )}
      </div>
    );
  }

  if (field.type === "textarea") {
    return <span style={{ whiteSpace: "pre-wrap" }}>{String(value)}</span>;
  }

  return String(value);
}
