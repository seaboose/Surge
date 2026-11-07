import React from "react";
import { Button } from "./controls.jsx";
import { Processor } from "./Optical.jsx";
import Instruments from "./Instruments.jsx";

export default function WorkspaceHeader({
  title,
  subtitle,
  onHome,
  homeTitle,
  homeContent,
  working = false,
  settings,
  className = "",
  children,
}) {
  return (
    <header className={`instrument-header ${className}`.trim()}>
      {homeContent || (
        <Button
          className="home-control"
          disabled={working}
          onClick={onHome}
          title={homeTitle}
        >
          <span aria-hidden="true">← </span>Home
        </Button>
      )}
      {title && (
        <div className="instrument-heading">
          <Processor className="workspace-crystal" />
          <div>
            <span className="instrument-brand">SURGE</span>
            <h1 tabIndex={-1}>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </div>
        </div>
      )}
      <Instruments settings={settings}>{children}</Instruments>
    </header>
  );
}
