import { type PropsWithChildren, type ReactNode } from "react";
import { useI18n } from "../lib/i18n";

export function PageShell({
  title,
  actions,
  children,
}: PropsWithChildren<{ title: string; actions?: ReactNode }>) {
  const { messages } = useI18n();

  return (
    <section className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">{messages.common.eyebrow}</p>
          <h1>{title}</h1>
        </div>
        {actions ? <div className="page-actions">{actions}</div> : null}
      </header>
      <div className="page-content">{children}</div>
    </section>
  );
}

export function Panel({
  title,
  subtitle,
  children,
}: PropsWithChildren<{ title: string; subtitle?: string }>) {
  return (
    <section className="panel">
      <header className="panel-header">
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </header>
      {children}
    </section>
  );
}

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  const { messages } = useI18n();
  return <div className="state-card">{label === "Loading..." ? messages.common.loading : label}</div>;
}

export function EmptyState({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="state-card">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

export function ErrorState({
  title = "Request failed",
  body,
}: {
  title?: string;
  body: string;
}) {
  const { messages } = useI18n();
  return (
    <div className="error-banner" role="alert">
      <strong>{title === "Request failed" ? messages.common.requestFailed : title}</strong>
      <span>{body}</span>
    </div>
  );
}

export function SuccessState({
  title = "Operation accepted",
  body,
}: {
  title?: string;
  body: string;
}) {
  const { messages } = useI18n();
  return (
    <div className="success-banner" role="status">
      <strong>
        {title === "Operation accepted" ? messages.common.operationAccepted : title}
      </strong>
      <span>{body}</span>
    </div>
  );
}

export function KeyValueTable({
  rows,
}: {
  rows: Array<{ label: string; value: ReactNode }>;
}) {
  return (
    <dl className="kv-table">
      {rows.map((row, index) => (
        <div key={`${row.label}-${index}`} className="kv-row">
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Badge({
  tone = "neutral",
  children,
}: PropsWithChildren<{ tone?: "neutral" | "success" | "warning" | "danger" }>) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}
