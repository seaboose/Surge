// Actual React/Electron journey with controlled service replies. Backend persistence,
// source binding and export safety are exercised independently by Python tests.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const out = path.resolve(
  process.env.SURGE_UI_TEST_OUTPUT || path.join(root, "verification/electron"),
);
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, "investigations-ui-"));
const entry = path.join(temp, "entry.cjs");
const recordingId = "2".repeat(32),
  sessionId = "1".repeat(32),
  firstId = "a".repeat(32),
  otherId = "b".repeat(32);
const rows = Array.from({ length: 361 }, (_, seq) => ({
  schema: "survive-v3",
  session_id: sessionId,
  seq,
  elapsed_s: seq / 30,
  event: seq === 0 ? "run_start" : seq === 360 ? "run_end" : "sample",
  x_cm: seq,
  y_cm: 0,
  z_cm: 90,
  movement_mode: "walking",
  related_id: "",
  detail: seq === 360 ? "completed" : "",
  a: 0,
  b: 0,
  c: 0,
  d: 0,
  source_x_cm: 0,
  source_y_cm: 0,
  velocity_x_cm_s: 0,
  velocity_y_cm_s: 0,
  server_tick: seq * 2,
  delta_s: 1 / 60,
  monotonic_s: seq / 30,
  profile_id: "survive-lucian-practice-v1",
  path_radius_cm: 41,
  hit_radius_cm: 65,
  visual_radius_cm: 50,
  threat_x_cm: 0,
  threat_y_cm: 0,
  nearest_clearance_cm: 0,
  clearance_valid: false,
  baseline_threat: "unknown",
}));
const constraint = {
  event_id: "300:walking_displacement",
  elapsed_s: 10,
  constraint: "walking_displacement",
  observed: 20,
  allowed: 16.1667,
  unit: "cm",
  status: "Review",
  start_seq: 299,
  end_seq: 300,
  constraint_ratio: 1.237,
  coverage: "eligible",
};
fs.writeFileSync(
  entry,
  `const {app,ipcMain}=require('electron');
const validate=require(${JSON.stringify(path.join(__dirname, "boundary.cjs"))}).validate;
const rows=${JSON.stringify(rows)}, constraint=${JSON.stringify(constraint)}, rid=${JSON.stringify(recordingId)}, sid=${JSON.stringify(sessionId)}, first=${JSON.stringify(firstId)}, other=${JSON.stringify(otherId)};
global.reportTest={calls:[],forceConflict:false,verifyState:'verified',exports:0};
const sections=()=>({question:'',observations:'',hypothesis:'',conclusion:'',next_steps:''});
const docs={};
function create(id,title,author){const d={investigation_id:id,revision:1,title,author,created_utc:'2026-10-26T00:00:00Z',updated_utc:'2026-10-26T00:00:00Z',status:'draft',change_reason:'Created',sections:sections(),evidence:[],history:[]};d.history=[{revision:1,author,updated_utc:d.updated_utc,status:d.status,change_reason:d.change_reason}];docs[id]=[d];return response(id);}
function response(id,rev){const all=docs[id],d=structuredClone(all[(rev||all.length)-1]);d.history=structuredClone(all.at(-1).history);const state=global.reportTest.verifyState;return {document:d,latest_revision:all.length,verification:{checked_utc:'2026-10-26T00:00:00Z',state:state==='verified'?'verified':'attention',review_valid:state==='verified',items:d.evidence.map(e=>({evidence_id:e.evidence_id,state,message:state==='verified'?'Pinned bytes match':'Source is unavailable or changed'})),counts:{verified:state==='verified'?d.evidence.length:0,missing:state==='missing'?d.evidence.length:0,changed:0,unavailable:0}}};}
function mutate(args,fn){const all=docs[args.investigation_id];if(global.reportTest.forceConflict||args.expected_revision!==all.length)throw Error('Revision conflict: reload latest before saving.');const d=structuredClone(all.at(-1));d.revision++;d.updated_utc='2026-10-26T00:01:00Z';fn(d);d.history.push({revision:d.revision,author:d.author,updated_utc:d.updated_utc,change_reason:d.change_reason,status:d.status});all.push(d);return response(args.investigation_id);}
create(other,'Another investigation','other-analyst');
function capture(){return {capture:{recording_id:rid,state:'complete',finalized:true,session_id:sid,source_id:sid,profile_id:rows[0].profile_id,records:rows.length,bytes:1000,completion:'completed',analysis_state:'complete',health:{}},records:rows.slice(0,256),next_cursor:256,view:{samples:rows.filter(r=>r.event==='sample'),events:rows.filter(r=>r.event!=='sample'),constraints:[constraint],analysis:{state:'complete',counts:{Review:1,Unknown:0,'No finding':1}},metadata:{},summary:{}}};}
const handle=ipcMain.handle.bind(ipcMain);ipcMain.handle=(channel,callback)=>handle(channel,async(event,method,args)=>{if(!method.startsWith('survive_'))return callback(event,method,args);global.reportTest.calls.push({method,args});try{validate(method,args);if(global.reportTest.delayMethod===method)await global.reportTest.operationGate;let value;switch(method){
case 'survive_sources':value={sources:[]};break;
case 'survive_trials':value={trials:[]};break;
case 'survive_sessions':value={sessions:[{recording_id:rid,state:'complete',records:361}]};break;
case 'survive_status':value={capture:null,records:[],view:{}};break;
case 'survive_open':value=capture();break;
case 'survive_record':value={recording_id:rid,seq:args.seq,record:rows[args.seq]};break;
case 'survive_investigations':value={investigations:Object.values(docs).map(d=>({investigation_id:d[0].investigation_id,title:d.at(-1).title,revision:d.length})),unavailable:[]};break;
case 'survive_investigation_create':value=create(first,args.title,args.author);break;
case 'survive_investigation_open':value=response(args.investigation_id,args.revision);break;
case 'survive_investigation_attach':value=mutate(args,d=>{d.author=args.author;d.change_reason=args.change_reason;d.status='draft';d.evidence.push({evidence_id:'E'+(d.evidence.length+1),added_utc:d.updated_utc,added_by:args.author,recording_id:rid,session_id:sid,seq:args.seq,time_s:rows[args.seq].elapsed_s,constraint_id:args.constraint_id,capture:capture().capture,raw_record:rows[args.seq],interval_start_record:rows[299],constraint,fingerprints:{snapshot_sha256:'f'.repeat(64)}})});break;
case 'survive_investigation_save':value=mutate(args,d=>{d.title=args.title;d.author=args.author;d.change_reason=args.change_reason;d.status=args.status;d.sections=args.sections});break;
case 'survive_investigation_resolve':if(global.reportTest.verifyState!=='verified')throw Error('Evidence source is missing; pinned snapshot retained.');value={recording_id:rid,seq:300,constraint_id:constraint.event_id,time_s:10,evidence_id:args.evidence_id,investigation_id:args.investigation_id,revision:args.revision,replay:capture(),raw_record:rows[300],constraint};break;
case 'survive_investigation_export':global.reportTest.exports++;value={saved:true,filename:'investigation.html',bytes:1000};break;
default:throw Error('Unexpected fixture operation '+method);
}return {ok:true,value};}catch(e){return {ok:false,error:e.message};}});
app.setPath('userData',${JSON.stringify(path.join(temp, "profile"))});require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);

let app, page;
const errors = [],
  checks = [];
(async () => {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  app = await electron.launch({
    executablePath: require("electron"),
    args: [entry],
    env,
  });
  page = await app.firstWindow();
  page.setDefaultTimeout(15000);
  page.on("pageerror", (e) => errors.push(e.message));
  await page
    .getByRole("button", { name: "Survive sessions", exact: true })
    .click();
  async function go(stage) {
    await page
      .getByRole("navigation", { name: "Session workflow" })
      .getByRole("button", { name: new RegExp("\\b" + stage + "$") })
      .click();
  }
  const notebook = page.getByLabel("Investigation notebook", { exact: true });
  const readiness = notebook.getByLabel("Report readiness", { exact: true });
  async function chooseSection(label) {
    const tabs = {
      "Investigation question": "Question",
      Observations: "Observations",
      "Hypotheses and alternatives": "Alternatives",
      "Conclusion and limitations": "Conclusion",
      "Next steps": "Next steps",
    };
    if (tabs[label])
      await notebook
        .getByRole("tab", { name: tabs[label], exact: true })
        .click();
    return notebook.getByRole("textbox", { name: label, exact: true });
  }
  async function reportDetails() {
    const details = notebook.locator(".investigation-report-details");
    if (!(await details.evaluate((el) => el.open)))
      await details.locator("summary").click();
  }
  await page
    .getByLabel("Recorded session library")
    .getByRole("button")
    .first()
    .click();
  await page.getByRole("button", { name: "Next review", exact: true }).click();
  const clock = page.getByRole("slider", { name: "Game time", exact: true });
  assert.equal(await clock.inputValue(), "10");
  assert(
    !(await app.evaluate(() => global.reportTest.calls)).some(
      (c) => c.method === "survive_investigations",
    ),
  );
  checks.push("replay remains usable before opening report views");
  await page
    .getByRole("button", {
      name: "Add selection to investigation",
      exact: true,
    })
    .click();
  await notebook
    .getByLabel("New investigation author", { exact: true })
    .fill("reviewer");
  await go("Review");
  await clock.fill("8");
  await go("Explain");
  assert.equal(
    await notebook
      .getByLabel("New investigation author", { exact: true })
      .inputValue(),
    "reviewer",
  );
  await notebook
    .getByRole("button", {
      name: "Create and attach selected evidence",
      exact: true,
    })
    .click();
  const card = notebook.getByLabel("Evidence E1", { exact: true });
  await card.waitFor();
  assert((await card.innerText()).includes("10.000 s · record 300"));
  await card
    .getByText("Source, pinned fingerprints and raw records", { exact: true })
    .click();
  assert((await card.innerText()).includes("299–300"));
  await go("Review");
  assert.equal(await clock.inputValue(), "8");
  await go("Explain");
  checks.push(
    "create and attach pins the requested interval while stage switching preserves replay time and author input",
  );
  assert.equal(await notebook.getByRole("tabpanel").count(), 1);
  assert.equal(await readiness.count(), 0);
  assert.equal(
    await notebook
      .getByRole("button", { name: "Export investigation report", exact: true })
      .count(),
    0,
  );
  await notebook
    .getByRole("button", { name: "Continue to export", exact: true })
    .click();
  assert.equal(
    await readiness.evaluate((el) => getComputedStyle(el).borderTopWidth),
    "1px",
  );
  assert(
    (await readiness.innerText()).includes(
      "Not yet cited in the narrative: E1",
    ),
  );
  assert.equal(
    await notebook
      .getByLabel("Investigation narrative", { exact: true })
      .count(),
    0,
  );
  await notebook
    .getByRole("button", { name: "Edit report", exact: true })
    .click();
  checks.push(
    "Explain and Export show separate focused tools with compact editable section tabs",
  );
  const questionTab = notebook.getByRole("tab", {
    name: "Question",
    exact: true,
  });
  await questionTab.focus();
  await questionTab.press("ArrowRight");
  assert.equal(
    await notebook
      .getByRole("tab", { name: "Observations", exact: true })
      .getAttribute("aria-selected"),
    "true",
  );
  await notebook
    .getByRole("tab", { name: "Observations", exact: true })
    .press("Home");
  assert.equal(await questionTab.getAttribute("aria-selected"), "true");
  checks.push("section tabs support arrow and Home keyboard navigation");

  await (
    await chooseSection("Investigation question")
  ).fill("Does the selected interval exceed its movement allowance?");
  await (
    await chooseSection("Observations")
  ).fill("Unsupported reference [E99]");
  await go("Export");
  assert((await readiness.innerText()).includes("Unknown references: E99"));
  checks.push(
    "readiness distinguishes missing citations from unattached references",
  );
  await go("Explain");
  await notebook
    .getByRole("button", { name: "Cite E1 in observations", exact: true })
    .click();
  await notebook
    .getByRole("textbox", { name: "Observations", exact: true })
    .fill(
      'Measured displacement [E1]. <img src=x onerror="window.injected=true">',
    );
  await (
    await chooseSection("Conclusion and limitations")
  ).fill(
    "Movement exceeded this allowance; automation itself is not established.",
  );
  await notebook
    .getByLabel("Revision reason", { exact: true })
    .fill("Document initial evidence review");
  assert(
    await notebook
      .getByRole("button", { name: "Attach selected evidence", exact: true })
      .isDisabled(),
  );
  for (const stage of ["Play", "Record", "Review", "Export"]) {
    await go(stage);
  }
  assert(
    await notebook
      .getByRole("button", { name: "Export investigation report", exact: true })
      .isDisabled(),
  );
  assert(
    (await readiness.innerText()).includes("Save your edits before exporting"),
  );
  await go("Explain");
  assert(
    (await (await chooseSection("Observations")).inputValue()).includes(
      "Measured displacement",
    ),
  );
  checks.push(
    "unsaved narrative survives all five views while export and attachment remain blocked",
  );
  const attachmentsBeforeDirtyRequest = await app.evaluate(
    () =>
      global.reportTest.calls.filter(
        (c) => c.method === "survive_investigation_attach",
      ).length,
  );
  await go("Review");
  await page
    .getByRole("button", {
      name: "Add selection to investigation",
      exact: true,
    })
    .click();
  assert.equal(
    await app.evaluate(
      () =>
        global.reportTest.calls.filter(
          (c) => c.method === "survive_investigation_attach",
        ).length,
    ),
    attachmentsBeforeDirtyRequest,
  );
  assert(
    (await (await chooseSection("Observations")).inputValue()).includes(
      "Measured displacement",
    ),
  );
  checks.push(
    "one-click handoff retains dirty narrative and does not save implicitly",
  );
  await app.evaluate(() => {
    global.reportTest.verifyState = "changed";
  });
  await go("Export");
  await readiness
    .getByRole("button", { name: "Recheck evidence", exact: true })
    .click();
  await notebook
    .getByRole("status")
    .filter({ hasText: "Evidence sources need attention" })
    .waitFor();
  assert(
    (await readiness.innerText()).includes(
      "Some sources are missing, changed or unavailable",
    ),
  );
  await go("Explain");
  assert(
    (await (await chooseSection("Observations")).inputValue()).includes(
      "Measured displacement",
    ),
  );
  assert((await card.innerText()).includes("20.000 / 16.167"));
  await app.evaluate(() => {
    global.reportTest.verifyState = "verified";
  });
  await go("Export");
  await readiness
    .getByRole("button", { name: "Recheck evidence", exact: true })
    .click();
  await notebook
    .getByRole("status")
    .filter({ hasText: "Evidence sources rechecked" })
    .waitFor();
  checks.push(
    "source rechecks preserve unsaved text and pinned measurements across views",
  );
  await go("Explain");
  const draftBeforePendingOperation = await (
    await chooseSection("Observations")
  ).inputValue();
  await go("Export");
  await app.evaluate(() => {
    global.reportTest.delayMethod = "survive_investigation_open";
    global.reportTest.operationGate = new Promise((resolve) => {
      global.reportTest.releaseOperation = resolve;
    });
  });
  await readiness
    .getByRole("button", { name: "Recheck evidence", exact: true })
    .click();
  await go("Play");
  assert.equal(await notebook.isVisible(), false);
  await page
    .getByRole("button", { name: "Back to Surge", exact: true })
    .click();
  await notebook
    .getByRole("alert")
    .filter({
      hasText: "Wait for the investigation operation to finish before leaving",
    })
    .waitFor();
  assert.equal(await notebook.getAttribute("data-report-view"), "explain");
  assert.equal(
    await notebook
      .getByRole("textbox", { name: "Observations", exact: true })
      .inputValue(),
    draftBeforePendingOperation,
  );
  assert(
    await notebook
      .getByRole("button", { name: "Save revision", exact: true })
      .isDisabled(),
  );
  await app.evaluate(() => {
    global.reportTest.releaseOperation();
    delete global.reportTest.delayMethod;
    delete global.reportTest.operationGate;
    delete global.reportTest.releaseOperation;
  });
  await notebook
    .getByRole("status")
    .filter({ hasText: "Evidence sources rechecked" })
    .waitFor();
  await notebook
    .getByRole("alert")
    .filter({
      hasText: "Wait for the investigation operation to finish before leaving",
    })
    .waitFor({ state: "hidden" });
  assert.equal(
    await notebook
      .getByRole("textbox", { name: "Observations", exact: true })
      .inputValue(),
    draftBeforePendingOperation,
  );
  checks.push(
    "blocked workspace exit during a pending report operation reveals Explain and preserves the draft through completion",
  );
  await go("Explain");
  await notebook
    .getByRole("button", { name: "Read narrative", exact: true })
    .click();
  assert.equal(await notebook.locator(".investigation-prose img").count(), 0);
  assert.equal(await page.evaluate(() => Boolean(window.injected)), false);
  const sourceReadsBefore = await app.evaluate(
    () =>
      global.reportTest.calls.filter((c) =>
        ["survive_open", "survive_record"].includes(c.method),
      ).length,
  );
  await notebook
    .getByRole("button", { name: "Open evidence E1", exact: true })
    .click();
  assert.equal(await clock.inputValue(), "10");
  assert(
    (
      await page.getByLabel("Selected evidence", { exact: true }).innerText()
    ).includes("299–300"),
  );
  assert.equal(
    await app.evaluate(
      () =>
        global.reportTest.calls.filter((c) =>
          ["survive_open", "survive_record"].includes(c.method),
        ).length,
    ),
    sourceReadsBefore,
  );
  await go("Explain");
  await notebook
    .getByRole("button", { name: "Edit narrative", exact: true })
    .click();
  assert(
    (await (await chooseSection("Observations")).inputValue()).includes("<img"),
  );
  checks.push(
    "safe narrative preview and citations restore the exact replay without losing draft text",
  );
  await app.evaluate(() => {
    global.reportTest.forceConflict = true;
  });
  await notebook
    .getByRole("button", { name: "Save revision", exact: true })
    .click();
  await notebook
    .getByRole("alert")
    .filter({ hasText: "Revision conflict" })
    .waitFor();
  assert(
    (
      await notebook
        .getByRole("textbox", { name: "Observations", exact: true })
        .inputValue()
    ).includes("Measured displacement"),
  );
  checks.push("revision conflicts retain unsaved narrative");
  await notebook.getByText("Switch or create report", { exact: true }).click();
  page.once("dialog", (dialog) => dialog.dismiss());
  await notebook
    .getByLabel("Saved investigation", { exact: true })
    .selectOption(otherId);
  assert.equal(
    await notebook
      .getByLabel("Saved investigation", { exact: true })
      .inputValue(),
    firstId,
  );
  page.once("dialog", (dialog) => dialog.dismiss());
  await page
    .getByRole("button", { name: "Back to Surge", exact: true })
    .click();
  await notebook.waitFor();
  checks.push("unsaved guards prevent report switching and workspace exit");
  await app.evaluate(() => {
    global.reportTest.forceConflict = false;
  });
  await notebook
    .getByLabel("Investigation review status", { exact: true })
    .selectOption("reviewed");
  await notebook
    .getByRole("button", { name: "Save revision", exact: true })
    .click();
  await notebook
    .getByText("Saved · revision 3 of 3 · reviewed", { exact: true })
    .waitFor();
  const switchReport = notebook.locator(".investigation-manager");
  if (await switchReport.evaluate((el) => el.open))
    await switchReport.locator(":scope > summary").click();
  await page.screenshot({
    path: path.join(temp, "explain-clean.png"),
    fullPage: true,
  });
  await require("./visual-audit.cjs").auditPage(app, page, "survive-explain");
  await go("Export");
  assert((await readiness.innerText()).includes("Ready for handoff"));
  await page.screenshot({
    path: path.join(temp, "export-ready.png"),
    fullPage: true,
  });
  await require("./visual-audit.cjs").auditPage(app, page, "survive-export");
  await notebook
    .getByRole("button", { name: "Export investigation report", exact: true })
    .click();
  await notebook
    .getByRole("status")
    .filter({ hasText: "Portable investigation report exported" })
    .waitFor();
  assert.equal(await app.evaluate(() => global.reportTest.exports), 1);
  await notebook.getByText("Preview narrative", { exact: true }).click();
  assert.equal(await notebook.locator(".investigation-prose img").count(), 0);
  checks.push(
    "saved reviewed report exports and previews without renderer paths or executable markup",
  );
  await go("Review");
  await clock.fill("9");
  await page
    .getByRole("button", {
      name: "Add selection to investigation",
      exact: true,
    })
    .click();
  const card2 = notebook.getByLabel("Evidence E2", { exact: true });
  await card2.waitFor();
  assert((await card2.innerText()).includes("9.000 s · record 270"));
  assert.equal(
    await notebook
      .getByLabel("Investigation review status", { exact: true })
      .inputValue(),
    "draft",
  );
  await go("Review");
  assert.equal(await clock.inputValue(), "9");
  await go("Export");
  assert(
    (await readiness.innerText()).includes(
      "Not yet cited in the narrative: E2",
    ),
  );
  checks.push(
    "one-click attachment preserves replay position and returns the report to Draft",
  );
  const beforeRepeat = await app.evaluate(
    () =>
      global.reportTest.calls.filter(
        (c) => c.method === "survive_investigation_attach",
      ).length,
  );
  await go("Review");
  await page
    .getByRole("button", {
      name: "Add selection to investigation",
      exact: true,
    })
    .click();
  await notebook
    .getByRole("status")
    .filter({ hasText: "This moment is already attached as E2" })
    .waitFor();
  assert.equal(
    await app.evaluate(
      () =>
        global.reportTest.calls.filter(
          (c) => c.method === "survive_investigation_attach",
        ).length,
    ),
    beforeRepeat,
  );
  checks.push("duplicate attachment creates no extra revision");
  await reportDetails();
  await notebook
    .getByLabel("Investigation revision", { exact: true })
    .selectOption("2");
  await notebook
    .getByText("Historical revision — read only", { exact: false })
    .waitFor();
  assert(
    await notebook.getByLabel("Report title", { exact: true }).isDisabled(),
  );
  assert.equal(
    await notebook
      .getByRole("button", { name: "Save revision", exact: true })
      .count(),
    0,
  );
  assert(
    await notebook
      .getByRole("button", { name: "Attach selected evidence", exact: true })
      .isDisabled(),
  );
  checks.push("historical revisions remain read only");
  await app.evaluate(() => {
    global.reportTest.verifyState = "missing";
  });
  await notebook
    .getByRole("button", { name: "Reload latest and verify", exact: true })
    .click();
  await notebook
    .getByText("Evidence needs attention", { exact: true })
    .waitFor();
  assert(
    await notebook
      .getByRole("button", { name: "Open E1 in replay", exact: true })
      .isDisabled(),
  );
  assert((await card.innerText()).includes("20.000 / 16.167"));
  checks.push("missing evidence warns visibly and preserves original facts");
  await go("Export");
  assert(
    (await readiness.innerText()).includes(
      "Some sources are missing, changed or unavailable",
    ),
  );
  assert(
    await notebook
      .getByText("Evidence needs attention", { exact: true })
      .isVisible(),
  );
  checks.push("source warnings remain visible in the focused export view");
  if (await switchReport.evaluate((el) => el.open))
    await switchReport.locator(":scope > summary").click();
  await page.screenshot({
    path: path.join(temp, "export-view.png"),
    fullPage: true,
  });
  await go("Explain");
  await page.screenshot({
    path: path.join(temp, "explain-view.png"),
    fullPage: true,
  });
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].setSize(760, 650),
  );
  await page.waitForTimeout(120);
  assert.equal(
    await notebook.evaluate((el) => el.scrollWidth > el.clientWidth + 1),
    false,
  );
  await go("Export");
  assert.equal(
    await readiness
      .locator("ul")
      .evaluate(
        (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length,
      ),
    1,
  );
  await page.screenshot({
    path: path.join(temp, "narrow-export.png"),
    fullPage: true,
  });
  const calls = await app.evaluate(() => global.reportTest.calls);
  assert(
    !calls.some(
      (c) =>
        Object.hasOwn(c.args, "path") || Object.hasOwn(c.args, "raw_record"),
    ),
  );
  assert(
    !calls.some((c) =>
      ["survive_start", "survive_stop", "survive_trial_start"].includes(
        c.method,
      ),
    ),
  );
  checks.push(
    "narrow focused layouts preserve safety and cause no gameplay side effects",
  );
  await page
    .getByRole("button", { name: "Back to Surge", exact: true })
    .click();
  await page.getByRole("button", { name: "Try Demo", exact: true }).waitFor();
  assert.deepEqual(errors, []);
  checks.push("return to existing Surge with no renderer errors");
  fs.writeFileSync(
    path.join(temp, "result.json"),
    JSON.stringify(
      {
        scope:
          "Actual Electron renderer with controlled investigation service fixtures; no live game or human dataset",
        checks,
        errors,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ passed: checks.length, evidence: temp }));
})()
  .catch(async (error) => {
    console.error(error);
    console.error(JSON.stringify({ errors, evidence: temp }));
    if (page) {
      await page
        .screenshot({ path: path.join(temp, "failure.png"), fullPage: true })
        .catch(() => {});
      fs.writeFileSync(
        path.join(temp, "failure.txt"),
        await page
          .locator("body")
          .innerText()
          .catch(() => ""),
      );
      // Test-owned page: discard its unsaved fixture form so teardown cannot hang.
      await page
        .evaluate(() => {
          window.onbeforeunload = null;
        })
        .catch(() => {});
    }
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) {
      await app
        .evaluate(({ BrowserWindow }) =>
          BrowserWindow.getAllWindows().forEach((w) => w.destroy()),
        )
        .catch(() => {});
      await app.close();
    }
  });
