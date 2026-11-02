"use strict";

// This module is loaded only by a source checkout. The runtime package does not
// include it, and packaged BrowserWindows explicitly disable DevTools.
function windowTitle(app) {
  return app.commandLine.hasSwitch("surge-test")
    ? "Surge — Test session"
    : "Surge — Development";
}

function install(app, win, { Menu, dialog }) {
  if (app.isPackaged) return false;
  const contents = win.webContents;
  const open = () => contents.openDevTools({ mode: "right", activate: true });
  const toggle = () =>
    contents.isDevToolsOpened() ? contents.closeDevTools() : open();
  win.setMenu(
    Menu.buildFromTemplate([
      {
        label: "Developer",
        submenu: [
          {
            label: "Toggle interface inspector",
            accelerator: "F12",
            click: toggle,
          },
          {
            label: "How to inspect and edit CSS",
            click: () =>
              dialog.showMessageBox(win, {
                type: "info",
                title: "Learn the Surge interface",
                message:
                  "Inspect a visible element, then follow its styles and source.",
                detail:
                  "Right-click a control and choose Inspect element, or press F12 and use the DevTools element picker (Ctrl+Shift+C).\n\n" +
                  "Elements shows the live HTML and Styles/Computed show its CSS. Edit a value to preview it immediately. These edits reset when the page reloads.\n\n" +
                  "Run pnpm dev for readable JavaScript and CSS source maps. In Sources, follow the mapped src/*.jsx files; set a click-event breakpoint to trace a control. Save lasting edits in the source file and rebuild.\n\n" +
                  "Close the inspector with F12 while Surge has focus. Product releases do not include this inspector. See docs/developer-inspection.md in the source kit.",
                buttons: ["Got it"],
                noLink: true,
              }),
          },
        ],
      },
    ]),
  );
  contents.on("context-menu", (_event, params) => {
    Menu.buildFromTemplate([
      {
        label: "Inspect element",
        click: () => {
          // Capture the element before docking changes the available layout.
          contents.inspectElement(params.x, params.y);
          open();
        },
      },
    ]).popup({ window: win });
  });
  contents.on("before-input-event", (event, input) => {
    if (
      input.type === "keyDown" &&
      !input.alt &&
      input.control &&
      input.shift &&
      input.key.toLowerCase() === "i"
    ) {
      event.preventDefault();
      toggle();
    }
  });
  return true;
}

module.exports = { install, windowTitle };
