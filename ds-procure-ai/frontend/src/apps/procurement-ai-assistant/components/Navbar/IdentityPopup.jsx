import { useEffect, useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

import "./identity-popup.css";

gsap.registerPlugin(useGSAP);

function formatValue(value) {
  if (value === true || value === false) {
    return String(value);
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function actorRows(actor) {
  if (!actor || typeof actor !== "object") {
    return [];
  }
  const rows = [];
  const seen = new Set();
  for (const key of ["kind", "auth", "id", "user_name", "display_name", "email"]) {
    const value = actor[key];
    if (value == null || value === "") {
      continue;
    }
    rows.push([key, formatValue(value)]);
    seen.add(key);
  }
  const meta = actor.meta && typeof actor.meta === "object" ? actor.meta : {};
  for (const [key, value] of Object.entries(meta)) {
    if (seen.has(key) || value == null || value === "") {
      continue;
    }
    rows.push([key, formatValue(value)]);
  }
  return rows;
}

function sessionRows(identity) {
  if (!identity) {
    return [];
  }
  const rows = [];
  for (const key of ["env", "workspace_host", "profile", "app_name", "resolved_at"]) {
    const value = identity[key];
    if (value == null || value === "") {
      continue;
    }
    rows.push([key, formatValue(value)]);
  }
  return rows;
}

function IdentitySection({ title, rows }) {
  if (!rows.length) {
    return null;
  }
  return (
    <section className="identity-section">
      <h3 className="identity-section-title">{title}</h3>
      <dl className="identity-list">
        {rows.map(([key, value]) => (
          <div className="identity-row" key={`${title}-${key}`}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function IdentityPopup({ identity, onClose }) {
  const popupRef = useRef(null);
  const panelRef = useRef(null);

  useGSAP(
    () => {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const duration = reduce ? 0 : 0.28;
      const yFrom = reduce ? 0 : 12;
      const scaleFrom = reduce ? 1 : 0.96;

      gsap.fromTo(
        panelRef.current,
        { autoAlpha: 0, y: yFrom, scale: scaleFrom },
        { autoAlpha: 1, y: 0, scale: 1, duration, ease: "power3.out" }
      );

      const rows = popupRef.current?.querySelectorAll(".identity-row");
      if (rows?.length) {
        gsap.from(rows, {
          autoAlpha: 0,
          y: reduce ? 0 : 6,
          stagger: reduce ? 0 : 0.02,
          duration: reduce ? 0 : 0.2,
          delay: reduce ? 0 : 0.05,
          ease: "power2.out",
        });
      }
    },
    { scope: popupRef, dependencies: [identity], revertOnUpdate: true }
  );

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="identity-popup" ref={popupRef}>
      <button
        type="button"
        className="identity-backdrop"
        aria-label="Close identity"
        onClick={onClose}
      />
      <div
        className="identity-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="identity-popup-title"
      >
        <header className="identity-header">
          <div>
            <h2 id="identity-popup-title">Session identity</h2>
            <p className="identity-subtitle">
              User and app Databricks identity for this browser session.
            </p>
          </div>
          <button
            type="button"
            className="identity-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <IdentitySection title="Session" rows={sessionRows(identity)} />
        <IdentitySection title="User" rows={actorRows(identity?.user)} />
        <IdentitySection title="App" rows={actorRows(identity?.app)} />
      </div>
    </div>
  );
}

export default IdentityPopup;
