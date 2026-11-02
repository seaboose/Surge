import React, { useState } from "react";
import { useData } from "./context.jsx";
import { Button, InfoBubble, Modal } from "./controls.jsx";

export function CaseNameDialog({
  label,
  close,
  apply,
  working,
  initialName = "",
  collecting = false,
}) {
  const [name, setName] = useState(initialName);
  return (
    <Modal label={label} close={close}>
      <h2>{label}</h2>
      <p>
        Save a new snapshot of the inspected evidence, settings, and results.
        Existing cases stay unchanged.
      </p>
      {collecting && (
        <p>
          Collection is still running. This saves only the snapshot you are
          viewing, not newer observations.
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && !working) apply(name);
        }}
      >
        <label className="control">
          Case name
          <input
            autoFocus
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <div className="actions">
          <Button
            className="primary"
            disabled={working || !name.trim()}
            onClick={() => apply(name)}
          >
            Save to library
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function CaseLibraryDialog({ run, working, close }) {
  const [refresh, setRefresh] = useState(0),
    [editing, setEditing] = useState(null),
    [name, setName] = useState("");
  const [data, error] = useData("library_list", {}, true, refresh);
  const reload = () => setRefresh((n) => n + 1);
  return (
    <Modal label="Case library" close={close}>
      <h2>Case library</h2>
      <p>
        Saved locally on this computer. Each case contains its evidence,
        settings, and results.
      </p>
      <div className="actions">
        <Button
          disabled={working}
          onClick={() => run("library_import", {}, reload)}
        >
          Import case
        </Button>
        <Button disabled={working} onClick={() => run("open", {}, close)}>
          Open case file
        </Button>
      </div>
      <small>
        Import adds a copy. Open leaves the file outside your library.
      </small>
      <InfoBubble label="About case files">
        Import case keeps a verified copy in this computer's library. Open case
        file lets you inspect an external case without adding it. Export case
        creates a portable copy you can reopen or import elsewhere. Original
        files stay unchanged.
      </InfoBubble>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>Loading cases…</p>}
      {data?.unavailable > 0 && (
        <p role="alert">
          {data.unavailable} unavailable entries could not be read. Their files
          were left unchanged.
        </p>
      )}
      {data && !data.entries.length && (
        <p>
          No saved cases yet. Analyze evidence and choose Save case, or import a
          portable case.
        </p>
      )}
      <ul className="case-list">
        {data?.entries.map((entry) => (
          <li key={entry.id}>
            <strong>{entry.name}</strong>
            <small>Saved {new Date(entry.created).toLocaleString()}</small>
            {editing === entry.id ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (name.trim() && !working)
                    run("library_rename", { id: entry.id, name }, () => {
                      setEditing(null);
                      reload();
                    });
                }}
              >
                <label className="control">
                  New case name
                  <input
                    autoFocus
                    maxLength={100}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </label>
                <div className="actions">
                  <Button type="submit" disabled={working || !name.trim()}>
                    Save name
                  </Button>
                  <Button disabled={working} onClick={() => setEditing(null)}>
                    Cancel rename
                  </Button>
                </div>
              </form>
            ) : (
              <div className="actions">
                <Button
                  disabled={working}
                  onClick={() => run("library_open", { id: entry.id }, close)}
                >
                  Open case
                </Button>
                <Button
                  disabled={working}
                  onClick={() => {
                    setEditing(entry.id);
                    setName(entry.name);
                  }}
                >
                  Rename
                </Button>
                <Button
                  disabled={working}
                  onClick={() => run("library_export", { id: entry.id })}
                >
                  Export case
                </Button>
                <Button
                  disabled={working}
                  onClick={() =>
                    run("library_delete", { id: entry.id }, reload)
                  }
                >
                  Delete case
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <small>
        Deleting a saved case preserves original evidence, exported files, and
        your open investigation.
      </small>
    </Modal>
  );
}
