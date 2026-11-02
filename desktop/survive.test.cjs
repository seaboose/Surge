// Focused renderer journey. Controlled IPC fixtures exercise the actual React UI;
// recorder parsing, persistence and detector parity have separate Python checks.
const { _electron: electron } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const out = path.resolve(
  process.env.SURGE_UI_TEST_OUTPUT || path.join(root, "verification/electron"),
);
fs.mkdirSync(out, { recursive: true });
const temp = fs.mkdtempSync(path.join(out, "survive-ui-"));
const entry = path.join(temp, "entry.cjs");
const sourceId = "11111111111111111111111111111111";
const recordingId = "22222222222222222222222222222222";
const profileId = "survive-lucian-practice-v1";
const rows = Array.from({ length: 360 }, (_, seq) => ({
  schema: "survive-v3",
  session_id: sourceId,
  seq,
  elapsed_s: seq / 30,
  event: seq === 0 ? "run_start" : seq === 10 ? "command_grant" : "sample",
  x_cm: seq < 300 ? seq : seq + 19,
  y_cm: 0,
  z_cm: 90,
  movement_mode: "walking",
  related_id: "",
  detail: seq === 0 ? "fixed_seed" : seq === 10 ? "move" : "",
  a: 250,
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
  profile_id: profileId,
  path_radius_cm: 41,
  hit_radius_cm: 65,
  visual_radius_cm: 50,
  threat_x_cm: 0,
  threat_y_cm: 0,
  nearest_clearance_cm: 0,
  clearance_valid: false,
  baseline_threat: "unknown",
}));
const constraints = [
  {
    session_id: sourceId,
    event_id: "300:walking_displacement",
    elapsed_s: 10,
    constraint: "walking_displacement",
    observed: 20,
    allowed: 16.1667,
    unit: "cm",
    constraint_ratio: 1.2371,
    coverage: "eligible",
    run_completion: "completed",
    start_seq: 299,
    end_seq: 300,
    profile_id: profileId,
    policy_sha256: "a".repeat(64),
    status: "Review",
  },
];
const sampleKeys = [
  "seq",
  "elapsed_s",
  "x_cm",
  "y_cm",
  "z_cm",
  "movement_mode",
  "server_tick",
  "delta_s",
  "monotonic_s",
];
const studyTrials = [
  {
    trial_id: "7".repeat(32),
    participant: "player",
    mode: "human",
    seed: 1337,
    adjudication: {
      expected_mechanical_violation: "no",
      note: "Reviewed legal trial A",
    },
  },
  {
    trial_id: "8".repeat(32),
    participant: "player",
    mode: "human",
    seed: 1338,
    adjudication: { expected_mechanical_violation: "unknown", note: "" },
  },
  {
    trial_id: "9".repeat(32),
    participant: "player",
    mode: "speed_probe",
    seed: 1339,
    adjudication: {
      expected_mechanical_violation: "yes",
      note: "Confirmed violation trial C",
    },
  },
];
fs.writeFileSync(
  entry,
  `const {app,ipcMain}=require('electron');
const rows=${JSON.stringify(rows)},constraints=${JSON.stringify(constraints)},sampleKeys=${JSON.stringify(sampleKeys)};
const id=${JSON.stringify(recordingId)},source=${JSON.stringify(sourceId)},profile=${JSON.stringify(profileId)};
const trials=${JSON.stringify(studyTrials)};
let state='idle',count=0;
global.surviveGame=false;global.surviveFixture={finish:()=>{state='complete';count=rows.length;},running:(v)=>{global.surviveGame=v;}};
global.surviveCalls=[];
function value(after=0, saved=false){const all=saved?rows:rows.slice(0,count);const final=saved||state==='complete';return {trial:{process_state:global.surviveGame?'running':'exited'},capture:{recording_id:id,state:saved?'complete':state,source_id:source,session_id:source,profile_id:profile,records:all.length,bytes:all.length*640,source_elapsed_s:all.at(-1)?.elapsed_s||0,elapsed_s:all.at(-1)?.elapsed_s||0,completion:saved?'completed':null,provenance:'selected_source_backfill_from_byte_zero',health:{sequence_gaps:0,parse_errors:0,stale_s:0,pending_bytes:0,error:null},analysis_state:final?'complete':state==='stopped'?'unavailable':'pending'},records:all.slice(after,after+256),next_cursor:Math.min(all.length,after+256),view:{samples:all.filter(r=>r.event==='sample').map(r=>Object.fromEntries(sampleKeys.map(k=>[k,r[k]]))),events:all.filter(r=>r.event!=='sample'),constraints:final?constraints:[],analysis:{state:final?'complete':'pending'},metadata:{source_sha256:'b'.repeat(64),display_truncated:false},summary:{}}};}
const handle=ipcMain.handle.bind(ipcMain);
ipcMain.handle=(channel,callback)=>handle(channel,(event,method,args)=>{if(!method.startsWith('survive_'))return callback(event,method,args);global.surviveCalls.push({method,args});let result;
switch(method){
case 'survive_sources':result={sources:[{source_id:source,filename:source+'.jsonl',bytes:230400,modified_utc:'2026-10-26T00:00:00Z'}]};break;
case 'survive_sessions':result={sessions:[{recording_id:id,session_id:source,state:'complete',records:360,verified:false}]};break;
case 'survive_trials':result={trials};break;
case 'survive_adjudicate':{const trial=trials.find(t=>t.trial_id===args.trial_id);trial.adjudication={expected_mechanical_violation:args.expected_mechanical_violation,note:args.note};result={message:'Study annotation saved.'};break;}
case 'survive_status':if(global.surviveStatusFailure)return {ok:false,error:'Simulated temporary status failure'};if(state==='idle')result={capture:null,records:[],view:{}};else{if(state==='recording')count=Math.min(count+6,rows.length);result=value(args.after||0);}break;
case 'survive_start':state='recording';count=12;result=value();break;
case 'survive_trial_start':state='recording';count=12;result={...value(),trial:{trial_id:'3'.repeat(32),mode:args.mode,physical_input_verified:false}};break;
case 'survive_stop':state='stopped';result=value();break;
case 'survive_open':result=value(0,true);break;
case 'survive_record':result={recording_id:id,seq:args.seq,record:rows[args.seq]};break;
case 'survive_report':result={groups:[{condition:'human',participant:'player',phase:'development',profile_id:profile,sessions:1,complete_sessions:1,review_sessions:1,records:1,unknown_records:0,unverified_sessions:0}],pending_recordings:['4'.repeat(32),'5'.repeat(32)],rejected_recordings:[{recording_id:'6'.repeat(32),error:'Controlled verification failure'}],confusion:{true_positive:0,false_positive:0,true_negative:0,false_negative:0,excluded_trials:1,false_positive_rate:null},limits:['Controlled UI fixture; not a human study.']};break;
default:return {ok:false,error:'Unsupported fixture request'};
}return {ok:true,value:result};});
app.setPath('userData',${JSON.stringify(path.join(temp, "profile"))});
require(${JSON.stringify(path.join(__dirname, "main.cjs"))});`,
);

let app, page;
const errors = [];
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
  page.on("pageerror", (error) => errors.push(error.message));
  await page
    .getByRole("button", { name: "Survive sessions", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Survive sessions", exact: true })
    .waitFor();
  await require("./visual-audit.cjs").auditPage(app, page, "survive-play");
  await page
    .getByRole("button", { name: "Play and record trial", exact: true })
    .click();
  await page
    .getByRole("status")
    .filter({ hasText: "Trial launched" })
    .waitFor();
  await require("./visual-audit.cjs").auditPage(app, page, "survive-record");
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await page
    .getByRole("navigation", { name: "Session workflow" })
    .getByRole("button", { name: "1 Play", exact: true })
    .click();
  await page
    .getByText("Record an existing or next game session", { exact: true })
    .click();
  await page.getByLabel("Source", { exact: true }).selectOption(sourceId);
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Inspect live recording", exact: true })
    .click();
  await page.getByRole("button", { name: "Pause view", exact: true }).waitFor();
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "Pause view", exact: true }).click();
  const frozenTime = await page
    .getByRole("slider", { name: "Game time", exact: true })
    .inputValue();
  const health = page.getByLabel("Recording status", { exact: true });
  const oldHealth = await health.innerText();
  await page.waitForTimeout(1100);
  assert.equal(
    await page
      .getByRole("slider", { name: "Game time", exact: true })
      .inputValue(),
    frozenTime,
  );
  assert.notEqual(await health.innerText(), oldHealth);
  await page.getByRole("button", { name: "Resume view", exact: true }).click();
  assert.notEqual(
    await page
      .getByRole("slider", { name: "Game time", exact: true })
      .inputValue(),
    frozenTime,
  );
  const clock = page.getByRole("slider", { name: "Game time", exact: true });
  await clock.fill("0.2");
  const pinnedTime = await clock.inputValue();
  await page.waitForTimeout(650);
  assert.equal(await clock.inputValue(), pinnedTime);
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await page
    .getByText("Unknown — incomplete evidence", { exact: true })
    .waitFor();
  assert.equal(await clock.inputValue(), pinnedTime);
  await page.getByLabel("Recorded session library").locator("summary").click();
  await page
    .getByLabel("Recorded session library")
    .getByRole("button")
    .first()
    .click();
  await page.getByRole("button", { name: "Next review", exact: true }).click();
  const inspector = page.getByLabel("Selected evidence", { exact: true });
  assert.equal(
    await inspector.locator(".survive-assessment").innerText(),
    "Review",
  );
  assert((await inspector.innerText()).includes("299–300"));
  assert.equal(
    Number(
      await page
        .getByRole("slider", { name: "Game time", exact: true })
        .inputValue(),
    ),
    10,
  );
  await inspector.getByText("Raw source record", { exact: true }).click();
  await page.waitForFunction(() =>
    [...document.querySelectorAll(".survive-inspector pre")].some((p) =>
      p.textContent.includes('"seq": 300'),
    ),
  );
  const calls = await app.evaluate(() => global.surviveCalls);
  assert(
    calls.some(
      (c) =>
        c.method === "survive_trial_start" &&
        c.args.mode === "human" &&
        c.args.participant === "player",
    ),
  );
  assert(
    calls.some((c) => c.method === "survive_record" && c.args.seq === 300),
  );
  assert(!calls.some((c) => Object.hasOwn(c.args, "path")));
  // Focused views preserve exact selected evidence and independent layout state.
  const nav = page.getByRole("navigation", { name: "Session workflow" });
  const separator = page.getByRole("separator", {
    name: "Resize replay and evidence",
  });
  await separator.focus();
  await separator.press("End");
  assert.equal(await separator.getAttribute("aria-valuenow"), "65");
  await separator.press("Home");
  assert.equal(await separator.getAttribute("aria-valuenow"), "35");
  await page
    .getByRole("button", { name: "Reset review layout", exact: true })
    .click();
  assert.equal(await separator.getAttribute("aria-valuenow"), "55");
  await page.getByText("Set range", { exact: true }).click();
  await page
    .getByRole("spinbutton", { name: "Timeline range start", exact: true })
    .fill("8");
  await page
    .getByRole("spinbutton", { name: "Timeline range end", exact: true })
    .fill("11");
  await page.getByRole("button", { name: "Apply range", exact: true }).click();
  assert.equal(Number(await clock.inputValue()), 10);
  await nav.getByRole("button", { name: "1 Play", exact: true }).click();
  assert.equal(
    await page.getByLabel("Review workspace", { exact: true }).isVisible(),
    false,
  );
  assert.equal(
    await page
      .getByLabel("Trial and recording controls", { exact: true })
      .isVisible(),
    true,
  );
  await nav.getByRole("button", { name: "3 Review", exact: true }).click();
  assert.equal(Number(await clock.inputValue()), 10);
  assert.equal(
    Number(
      await page
        .getByRole("spinbutton", { name: "Timeline range start", exact: true })
        .inputValue(),
    ),
    8,
  );
  assert.equal(
    await inspector.locator(".survive-assessment").innerText(),
    "Review",
  );
  assert.equal(
    await page
      .getByLabel("Trial and recording controls", { exact: true })
      .isVisible(),
    false,
  );
  await page
    .getByText("Compare sessions and study labels", { exact: true })
    .click();
  await page
    .getByRole("button", { name: "Refresh comparison", exact: true })
    .click();
  await page
    .getByLabel("Study comparison")
    .getByText("human", { exact: true })
    .waitFor();
  await page
    .getByText(
      "2 recordings await verification; 1 recordings failed verification.",
      { exact: false },
    )
    .waitFor();
  await page
    .getByLabel("Adjudicated mechanical outcomes")
    .getByText("Unavailable — no eligible negative annotations", {
      exact: false,
    })
    .waitFor();
  const outcomes = page.getByLabel("Adjudicated mechanical outcomes");
  assert.equal(
    await outcomes
      .getByRole("columnheader", { name: "No Review observed", exact: true })
      .count(),
    1,
  );
  assert.equal(
    await outcomes
      .getByRole("columnheader", { name: "No finding", exact: true })
      .count(),
    0,
  );
  await outcomes
    .getByText("No Review can still include Unknown intervals.", {
      exact: false,
    })
    .waitFor();
  await outcomes
    .getByText("0 false positives / 0 eligible negative sessions", {
      exact: false,
    })
    .waitFor();
  await outcomes
    .getByText("This pooled rate is not a held-out accuracy estimate.", {
      exact: false,
    })
    .waitFor();
  await page
    .getByText("Study labels and held-out freeze", { exact: true })
    .click();
  const trialChoice = page.getByLabel("Study trial", { exact: true });
  const expectedChoice = page.getByLabel("Expected mechanical violation", {
    exact: true,
  });
  const reason = page.getByLabel("Study label reason", { exact: true });
  const saveLabel = page.getByRole("button", {
    name: "Save study label",
    exact: true,
  });
  await trialChoice.selectOption(studyTrials[0].trial_id);
  assert.equal(await expectedChoice.inputValue(), "no");
  assert.equal(await reason.inputValue(), "Reviewed legal trial A");
  await expectedChoice.selectOption("yes");
  await reason.fill("Unsaved draft belonging only to trial A");
  await trialChoice.selectOption(studyTrials[1].trial_id);
  assert.equal(await expectedChoice.inputValue(), "unknown");
  assert.equal(await reason.inputValue(), "");
  assert.equal(await saveLabel.isDisabled(), true);
  await expectedChoice.selectOption("no");
  await reason.fill("Reviewed legal trial B");
  await saveLabel.click();
  await page
    .getByRole("status")
    .filter({ hasText: "Study annotation saved." })
    .waitFor();
  await trialChoice.selectOption(studyTrials[2].trial_id);
  assert.equal(await expectedChoice.inputValue(), "yes");
  assert.equal(await reason.inputValue(), "Confirmed violation trial C");
  await trialChoice.selectOption(studyTrials[0].trial_id);
  assert.equal(await expectedChoice.inputValue(), "no");
  assert.equal(await reason.inputValue(), "Reviewed legal trial A");
  await trialChoice.selectOption(studyTrials[1].trial_id);
  assert.equal(await expectedChoice.inputValue(), "no");
  assert.equal(await reason.inputValue(), "Reviewed legal trial B");
  const annotations = await app.evaluate(() =>
    global.surviveCalls.filter((c) => c.method === "survive_adjudicate"),
  );
  assert.deepEqual(
    annotations.map((c) => c.args),
    [
      {
        trial_id: studyTrials[1].trial_id,
        expected_mechanical_violation: "no",
        note: "Reviewed legal trial B",
      },
    ],
  );
  await inspector.getByText("Raw source record", { exact: true }).click();
  await page
    .locator(".survive-review-grid")
    .screenshot({ path: path.join(temp, "survive-replay-inspector.png") });
  await page
    .getByLabel("Shared event timeline")
    .evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.screenshot({
    path: path.join(temp, "survive-investigation.png"),
    fullPage: true,
  });
  await require("./visual-audit.cjs").auditPage(app, page, "survive-review");
  await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0].setSize(760, 650),
  );
  await page.waitForTimeout(150);
  const overflow = await page
    .locator(".survive-workspace")
    .evaluate((el) => el.scrollWidth > el.clientWidth + 1);
  assert.equal(overflow, false);
  // Completing a background recording must not replace a paused inspection.
  await page
    .getByRole("navigation", { name: "Session workflow" })
    .getByRole("button", { name: "1 Play", exact: true })
    .click();
  await app.evaluate(() => global.surviveFixture.running(true));
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Inspect live recording", exact: true })
    .click();
  await page.getByRole("button", { name: "Pause view", exact: true }).click();
  await app.evaluate(() => {
    global.surviveStatusFailure = true;
  });
  await page
    .getByRole("alert")
    .filter({
      hasText:
        "Recording status unavailable: Simulated temporary status failure",
    })
    .waitFor();
  await page
    .getByLabel("Recording status", { exact: true })
    .getByText("Recorder status unavailable", { exact: true })
    .waitFor();
  await app.evaluate(() => {
    global.surviveStatusFailure = false;
  });
  await page
    .getByRole("alert")
    .filter({ hasText: "Recording status unavailable:" })
    .waitFor({ state: "hidden" });
  const completionPinnedTime = await clock.inputValue();
  await app.evaluate(() => global.surviveFixture.finish());
  await page
    .getByLabel("Post-game handoff")
    .getByText("Your recording is ready", { exact: true })
    .waitFor();
  assert.equal(await clock.inputValue(), completionPinnedTime);
  assert.equal(
    await page
      .locator('[aria-label="Trial and recording controls"] button')
      .filter({ hasText: "Play and record trial" })
      .isDisabled(),
    true,
  );
  await page
    .getByRole("button", { name: "Review this session", exact: true })
    .click();
  await page.locator(".survive-summary-disclosure > summary").click();
  await page
    .getByLabel("Session summary", { exact: true })
    .getByText("Analysis complete", { exact: false })
    .waitFor();
  assert.equal(Number(await clock.inputValue()), 0);
  await app.evaluate(() => global.surviveFixture.running(false));
  await page.waitForFunction(() =>
    [...document.querySelectorAll("button")].some(
      (b) => b.textContent.trim() === "Play and record trial" && !b.disabled,
    ),
  );
  await page.getByRole("button", { name: "Next review", exact: true }).click();
  const marker = page.getByRole("button", {
    name: "Timeline Review · record 300",
    exact: true,
  });
  await marker.focus();
  await marker.press("Enter");
  assert.equal(Number(await clock.inputValue()), 10);
  assert((await inspector.innerText()).includes("299–300"));
  await page.getByText("Filter events", { exact: true }).click();
  await page
    .getByLabel("Timeline filters")
    .getByLabel("Findings", { exact: true })
    .uncheck();
  assert.equal(await marker.count(), 0);
  await page
    .getByLabel("Timeline filters")
    .getByLabel("Findings", { exact: true })
    .check();
  assert.equal(await marker.count(), 1);
  assert.equal(Number(await clock.inputValue()), 10);
  const openCalls = await app.evaluate(() =>
    global.surviveCalls.filter((c) => c.method === "survive_open"),
  );
  assert.equal(openCalls.at(-1).args.recording_id, recordingId);
  await page
    .getByRole("button", { name: "Back to Surge", exact: true })
    .click();
  await page.getByRole("button", { name: "Try Demo", exact: true }).waitFor();
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    path.join(temp, "result.json"),
    JSON.stringify(
      {
        scope:
          "Actual renderer with controlled IPC fixture; recorder and detector verified separately.",
        checks: [
          "entry preserves legacy home",
          "start and polling",
          "human trial request keeps external study label",
          "pause display while capture grows",
          "resume latest",
          "selected time stays pinned while recorder advances",
          "partial stop stays unknown and preserves selected time",
          "saved session beyond first256 raw rows",
          "constraint/time/inspector linking",
          "exact raw record lookup",
          "no renderer paths",
          "comparison groups",
          "pending and rejected coverage; no false-positive rate without labels",
          "negative prediction says no Review observed and preserves Unknown interpretation",
          "switching trials loads its saved annotation and clears the previous unsaved draft",
          "annotation save targets only the selected trial",
          "narrow layout",
          "return to existing Surge",
          "no runtime errors",
          "temporary recorder status failure becomes visible and clears after recovery",
          "resizable review keyboard bounds and reset preserve selected evidence",
          "timeline zoom changes the view without changing the selected moment",
          "focused views preserve time range, exact selection and stage isolation",
          "completion handoff preserves paused selection",
          "recording completion does not enable launcher while game runs",
          "review handoff opens the completed recording at its beginning",
          "post-recording status polling unlocks launcher after game exit",
          "timeline keyboard selection restores exact constraint and time",
          "timeline filters preserve current selection",
        ],
        errors,
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ passed: 29, evidence: temp }));
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
        (await page
          .locator("body")
          .innerText()
          .catch(() => "")) +
          "\n" +
          errors.join("\n"),
      );
    }
    process.exitCode = 1;
  })
  .finally(async () => {
    if (app) await app.close();
  });
