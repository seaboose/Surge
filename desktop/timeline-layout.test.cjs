// Focused actual-renderer checks for overview/detail navigation and exact cluster selection.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { _electron: electron } = require("playwright");
const esbuild = require("esbuild");
const root = path.resolve(__dirname, "..");
const output =
  process.env.SURGE_UI_TEST_OUTPUT ||
  path.join(root, "verification/survive-layout-20261026");
fs.mkdirSync(output, { recursive: true });
const folder = fs.mkdtempSync(path.join(output, "timeline-layout-"));
const entry = path.join(folder, "entry.cjs");
const index = path.join(folder, "index.html");
const fixture = `import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {MarkerTimeline,SessionSummary,RecordingStrip} from ${JSON.stringify(path.join(__dirname, "src/SurviveFlow.jsx"))};
import ${JSON.stringify(path.join(__dirname, "src/style.css"))};
const events=[{session_id:'fixture-a',seq:0,elapsed_s:0,event:'run_start',detail:'fixed_seed'},
{session_id:'fixture-a',seq:300,elapsed_s:10,event:'threat_hit',detail:'circle_aimed'}];
const constraints=Array.from({length:6},(_,i)=>({session_id:'fixture-a',event_id:(600+i)+':walking',end_seq:600+i,elapsed_s:20+i*.002,status:'Review'}));
const points=Array.from({length:1801},(_,seq)=>({seq,elapsed_s:seq/30})).filter(r=>r.seq<=90||r.seq>=150);
function App(){const[range,setRange]=useState([0,60]),[selected,setSelected]=useState({time:20,seq:null}),[source,setSource]=useState('fixture-a'),[limited,setLimited]=useState(false);
return <div className='survive-workspace'><h1>Timeline verification</h1>
<output aria-label='Fixture selection'>{JSON.stringify(selected)}</output><output aria-label='Fixture range'>{JSON.stringify(range)}</output>
<button onClick={()=>setSource(source==='fixture-a'?'fixture-b':'fixture-a')}>Change fixture recording</button>
<button onClick={()=>setLimited(v=>!v)}>Toggle limited display</button>
<MarkerTimeline events={events} constraints={constraints} points={points} domain={range} duration={60} time={selected.time} recordingId={source}
selectTime={time=>setSelected({time,seq:null})} chooseRecord={r=>setSelected({time:r.elapsed_s,seq:r.seq})}
chooseConstraint={r=>setSelected({time:r.elapsed_s,seq:r.end_seq,constraint:r.event_id})}
onDomainChange={r=>setRange(r||[Math.max(0,selected.time-4),Math.min(60,selected.time+4)])} truncated={limited} />
</div>};createRoot(document.getElementById('root')).render(<App/>);`;
esbuild.buildSync({
  stdin: { contents: fixture, loader: "jsx", resolveDir: __dirname },
  bundle: true,
  outfile: path.join(folder, "app.js"),
  define: { "process.env.NODE_ENV": '"production"' },
});
fs.writeFileSync(
  index,
  '<!doctype html><html><head><meta charset="UTF-8"><link rel="stylesheet" href="app.css"></head><body><div id="root"></div><script src="app.js"></script></body></html>',
);
fs.writeFileSync(
  entry,
  `const {app,BrowserWindow}=require('electron');app.setPath('userData',${JSON.stringify(path.join(folder, "profile"))});app.whenReady().then(()=>{const w=new BrowserWindow({width:1180,height:950,show:false,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false,offscreen:true}});w.loadFile(${JSON.stringify(index)});});app.on('window-all-closed',()=>app.quit());`,
);
const checks = [],
  errors = [];
let app, page;
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(10000);
  page.on("pageerror", (e) => errors.push(e.message));
  await page.getByRole("heading", { name: "Timeline", exact: true }).waitFor();
  const selection = async () =>
    JSON.parse(
      await page.getByLabel("Fixture selection", { exact: true }).innerText(),
    );
  const range = async () =>
    JSON.parse(
      await page.getByLabel("Fixture range", { exact: true }).innerText(),
    );
  const cluster = page.getByRole("button", {
    name: /^Timeline cluster · 6 events · Findings/,
  });
  assert.equal(await cluster.count(), 1);
  await cluster.click();
  const list = page.getByLabel("Timeline event list", { exact: true });
  assert.equal(
    await list
      .getByRole("button", { name: /^Timeline Review · record/ })
      .count(),
    6,
  );
  await list
    .getByRole("button", { name: "Timeline Review · record 603", exact: true })
    .click();
  assert.deepEqual(await selection(), {
    time: 20.006,
    seq: 603,
    constraint: "603:walking",
  });
  checks.push("counted cluster preserves all six exact evidence selections");
  const pinned = await selection();
  await page
    .getByRole("button", { name: "Zoom in timeline", exact: true })
    .click();
  assert(Math.abs((await range())[1] - (await range())[0] - 30) < 0.001);
  assert.deepEqual(await selection(), pinned);
  await page
    .getByRole("button", { name: "Zoom out timeline", exact: true })
    .click();
  assert.deepEqual(await range(), [0, 60]);
  checks.push(
    "zoom buttons change the window without changing pinned time or evidence",
  );
  await page.getByText("Filter events", { exact: true }).click();
  await page
    .getByLabel("Timeline filters", { exact: true })
    .getByLabel("Findings", { exact: true })
    .uncheck();
  assert.equal(await cluster.count(), 0);
  assert.equal(await list.count(), 0);
  await page
    .getByLabel("Timeline filters", { exact: true })
    .getByLabel("Missing data", { exact: true })
    .uncheck();
  assert.match(
    await page.getByLabel("Shared event timeline").innerText(),
    /1 missing\/unsupported markers in round/,
  );
  assert.equal(
    await page
      .locator(".survive-timeline-overview .survive-overview-unknown")
      .count(),
    2,
  );
  await page
    .getByLabel("Timeline filters", { exact: true })
    .getByLabel("Missing data", { exact: true })
    .check();
  await page
    .getByLabel("Timeline filters", { exact: true })
    .getByLabel("Findings", { exact: true })
    .check();
  checks.push(
    "filtering preserves global missing-data indicators and closes stale cluster list",
  );
  await page.getByText("Set range", { exact: true }).click();
  await page.getByLabel("Timeline range start", { exact: true }).fill("3");
  await page.getByLabel("Timeline range end", { exact: true }).fill("4");
  await page.getByRole("button", { name: "Apply range", exact: true }).click();
  assert.deepEqual(await range(), [3, 4]);
  assert.equal(
    await page
      .getByRole("button", { name: /^Timeline Unobserved position interval/ })
      .count(),
    1,
  );
  assert.deepEqual(await selection(), pinned);
  checks.push(
    "numeric keyboard range retains a gap whose endpoint lies outside the zoom",
  );
  const overview = page.getByRole("img", {
    name: "Whole-round timeline overview",
    exact: true,
  });
  await overview.scrollIntoViewIfNeeded();
  const box = await overview.boundingBox();
  const px = (t) => box.x + 10 + (t / 60) * (box.width - 20);
  await page.mouse.move(px(10), box.y + 20);
  await page.mouse.down();
  await page.mouse.move(px(20), box.y + 20, { steps: 8 });
  await page.mouse.up();
  const dragged = await range();
  assert(Math.abs(dragged[0] - 10) < 0.01);
  assert(Math.abs(dragged[1] - 20) < 0.01);
  assert.deepEqual(await selection(), pinned);
  await page.mouse.click(px(50), box.y + 20);
  const centered = await range();
  assert(Math.abs(centered[0] - 45) < 0.02);
  assert(Math.abs(centered[1] - 55) < 0.02);
  checks.push(
    "overview dragging selects a range and clicking outside it recenters without moving the replay",
  );
  await page
    .getByRole("button", { name: "Follow selected moment", exact: true })
    .click();
  assert.deepEqual(await range(), [16.006, 24.006]);
  const detailCluster = page.getByRole("button", {
    name: /^Timeline cluster · 6 events · Findings/,
  });
  await detailCluster.focus();
  await detailCluster.press("Enter");
  await page
    .getByLabel("Timeline event list")
    .getByRole("button", { name: "Timeline Review · record 604", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  assert.equal((await selection()).seq, 604);
  checks.push("keyboard cluster activation opens the exact rule endpoint");
  await page
    .getByLabel("Shared event timeline")
    .evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.screenshot({
    path: path.join(folder, "overview-detail.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Change fixture recording", exact: true })
    .click();
  // Recording changes clear selection in an effect after the click render.
  await list.waitFor({ state: "detached" });
  assert.equal(await list.count(), 0);
  checks.push("changing recordings clears stale cluster evidence");
  await page
    .getByRole("button", { name: "Toggle limited display", exact: true })
    .click();
  await page.locator(".survive-timeline-limited").waitFor();
  assert.match(
    await page.getByLabel("Shared event timeline").innerText(),
    /0 missing\/unsupported markers in display/,
  );
  assert.equal(
    await page
      .locator(".survive-timeline-overview .survive-overview-unknown")
      .count(),
    0,
  );
  checks.push(
    "limited projections show an explicit warning and never invent gaps from omitted samples",
  );
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].setSize(660, 780),
  );
  await page.waitForTimeout(100);
  assert.equal(
    await page
      .locator(".survive-workspace")
      .evaluate((el) => el.scrollWidth > el.clientWidth + 1),
    false,
  );
  await page
    .getByLabel("Shared event timeline")
    .evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.screenshot({
    path: path.join(folder, "narrow-timeline.png"),
    fullPage: true,
  });
  checks.push(
    "narrow timeline and range controls fit without horizontal overflow",
  );
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    path.join(folder, "result.json"),
    JSON.stringify(
      {
        scope:
          "Actual hidden Electron renderer using controlled timeline fixtures; no gameplay or human-data claims",
        checks,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ passed: checks.length, evidence: folder }));
})()
  .catch(async (error) => {
    console.error(error);
    process.exitCode = 1;
    fs.writeFileSync(
      path.join(folder, "failure.json"),
      JSON.stringify({ error: String(error), checks, errors }, null, 2),
    );
    if (page)
      await page
        .screenshot({ path: path.join(folder, "failure.png"), fullPage: true })
        .catch(() => {});
  })
  .finally(async () => {
    if (app) await app.close();
  });
