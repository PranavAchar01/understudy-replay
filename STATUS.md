# Understudy build status

Keep this current. A future session resumes from here.

## Budget (Runway)
- Cap: 350 credits total. Start balance 460 (2026-09-23), so the floor is balance 110.
- Spent: 247 (balance 213 at 15:18). Ledger: data/runway-ledger.jsonl (17 calls + 1 reconciliation line for 25
  credits the interrupted session spent without logging, most likely a v02 video whose task id was lost).
- Left under the cap: 103. Kept as a reserve for a live run on demo day (a new clip costs 27: turbo frame 2 +
  gen4_turbo 5 s 25).
- v00 = the first v01 video from an older prompt (two red blocks). Kept as a real rejection example.

## Milestones
- [x] Recovered partial build, first commit
- [x] Pose extractor comparison (docs/POSE-COMPARE.md): MediaPipe chosen
- [x] Track + events + metric retarget (object-anchored)
- [x] Sim replay + 22 gates-worth of tests (tests/test_pipeline.py, 22 pass)
- [x] 7 Runway clips + v00 in data/runs/put-the-red-block-in-the-bowl/clips
- [x] run1 (older code): whole path works end to end, dataset v3.0 loads back, policy 29/50 (superseded)
- [x] run2 final (8426c9f): 4/8 clips accepted, 44 episodes (4 + re-anchored copies, each re-gated), policy 46/50 in MuJoCo on unseen cube positions (sim only)
- [ ] scripts/build_site.py, then browser check + screenshot of site/index.html
- [x] media/understudy-demo.mp4 (86 s, 1080p) + 720p preview; contact sheet checked by Jarvis 09-23
- [ ] README with measured numbers

## Current verdicts (scripts/evaluate_clips.py)
v01 v03 v06 v07 accepted; v00 two red blocks (Claude); v02 v04 v05 the video duplicates the block after release.

## Notes
- Claude CLI at /usr/local/bin/claude works headless (`-p ... --allowedTools Read --model sonnet`, ~12 s) for
  the scene audit. The shell alias `claude` is a shim; call the absolute path.
- RTMW-x weights are now cached in ~/.cache/rtmlib.
- Pose cache key includes the extractor VERSION (data/cache/pose/<sha>_mediapipe_v2.json).
- Dataset writing is the slow stage (~20 s per episode: render + AV1 encode).

## Film v2 (Player Two style, started 2026-09-23 16:10)
Goal: recut the demo 1:1 in the style of player-two/media/player-two-brains-80s.mp4, silent, 80-90 s, plus an SO-101
simulation section. Output media/understudy-demo-v2.mp4 + -720p. No Runway credits.
- Renderer reused, copied (player-two untouched): film/app = player-two-site (index.html, site.css, site.js, film
  driver) with Understudy's robot, tier, run and 44 episode tiles; film/deck/broll.html = player-two-brain-deck
  broll.html (+ outro terminal shot); film/tools/film-site.mts + film-deck.mts; scripts/film2_edit_app.py =
  edit-film.py; scripts/film2_join.py = join-film.py (audio removed).
- scripts/film2_assets.py rebuilds the 44 dataset episodes exactly (asserts against understudy_episodes.json),
  renders one Player Two layout tile per episode, the manifest, and the deck plates (media/work2, film/*/media,
  both gitignored).
- scripts/film2.sh runs everything (needs `cd film && python3 -m http.server 4650 --bind 127.0.0.1`).
- Order: title, pitch, app demo (~30 s), Runway grid, MediaPipe+OpenCV, Claude audit reject, SO-101 model, IK,
  pass/fail replay, LeRobot dataset, policy 46/50 (first time the policy appears), end card.
- [x] DONE 17:13: media/understudy-demo-v2.mp4 (1920x1080, 30 fps, 87.2 s, no audio stream) + -720p.mp4.
  Sections: 0:00 title, 0:04.5 pitch, 0:09 app demo (compose, run, 44 tiles, 4 rejections, viewer), 0:38.6 Runway,
  0:43.5 MediaPipe+OpenCV, 0:48.3 Claude audit, 0:52.7 SO-101 model, 0:59.3 IK, 1:04.8 physics pass/fail,
  1:10.3 LeRobot, 1:15.2 policy 46/50, 1:21.8 end card.
- Checked against the reference frame by frame at matching times (title, run, library, viewer, B-roll, end).
- Known deviations: tiles show the MuJoCo table scene instead of Player Two's grey backdrop; the dataset terminal
  shot's [gates] and [dataset] lines summarise run.json (only [run] and [episodes] are verbatim log lines).

## Film v3 (one robot from all the clips, started 2026-09-23 19:10)
Goal: his new structure. Silent, 80-90 s, same Player Two look (broll.html styles), media/understudy-demo-v3.mp4
+ -720p. No app interface; the robot appears once (the hero sim), apart from the Runway robot-clip evidence.
- Order: title (blurred Runway clips, no robot) -> prompt typed + 8 Runway clips in a grid -> "Why not just generate
  videos of the robot?" + the Runway SO-101 clip as evidence -> all 8 files fly into Understudy -> inside 1/2: track
  (MediaPipe + OpenCV overlay), gates (4 rejections with the verbatim run2.log reasons) -> inside 2/2: v01 joint
  angles from the dataset parquet, top-down map of the 44 episode cube positions -> training (the 5 logged loss
  points only, no curve drawn; verbatim [train] lines) -> the model (layer shapes read from MLPChunk, 164,984
  params, state-based, 30.1 s on the Apple M4 CPU) -> hero: 3 successful eval rollouts, full frame -> end card.
- Files: film/deck/v3.html (the page), scripts/film3_assets.py (plates + media/v3/facts3.json),
  scripts/v3_robot_clip.py (the one Runway call), film/tools/stills.mts (frame checks), scripts/film3.sh (render).
- Robot-clip experiment (data/runs/robot-clip/r00.*, seed 31): gen4_image_turbo (refs: a MuJoCo render of the SO-101
  as @arm + v01's first frame as @scene) then gen4_turbo 5 s. Spent 27 (balance 213 -> 186), ledger lines 18-19.
  Verdict FAIL, seen frame by frame: the first frame already has no base, no shoulder and no mount, just a yellow
  wrist + gripper floating in mid-air; the video lowers it onto the block, carries the block to the bowl, dips in,
  then carries the block back up and out of frame instead of releasing it. No kinematic chain, so no joint angles.
- Hero rollouts: eval seeds 10001 (1x), 10003 and 10009 (2x), rebuilt with the exact unrounded eval start positions;
  the script asserts each rollout succeeds with the same frame count the evaluation logged. Closer free camera.
- Runway budget after v3: balance 186; the 30-credit v3 cap is used up to 27. Rest is the demo-day reserve.
- [x] DONE 19:46: media/understudy-demo-v3.mp4 (1920x1080, 30 fps, 82.5 s, no audio stream) + -720p.mp4, rendered
  with scripts/film3.sh (one deck recording, fade out at the end). Sections: 0:00 title, 0:04.2 prompt + Runway grid,
  0:16.3 why-not + robot clip, 0:23.3 files into Understudy, 0:28.3 track + gates, 0:38.4 joint angles + 44 episodes,
  0:47.4 training, 0:55.4 the model, 1:02.9 hero sim (first robot besides the evidence clip), 1:16.0 end card.
- Checked frame by frame (1 fps sheets + stills per shot): overlay on the hand/block, no robot before 1:02.9 except
  the evidence clip, no em-dashes, terminal = verbatim [train] lines from data/run2.log only.
- Not verbatim / judgement calls: the caption "Video models have seen far more hands than hobby robot arms" is a
  reasoned claim, not measured; the training progress bar is an animation (30.1 s shown in 5 s, labelled so); the
  stage names and "4 clips -> 44 episodes" card are UI text, with the [episodes] log line shown verbatim beside it.

## Film v4 (his v3 notes: frame rate, Player Two look, story order; started 2026-09-23 22:55)
Goal: v3's content in the Player Two / v2 frame, a true 30 fps, one story a judge follows in one pass. Silent, 80-90 s,
media/understudy-demo-v4.mp4 + -720p. No Runway credits.
- Frame rate, measured (scripts/fps_probe.py: frames that differ from the previous one, per second):
  v3 = 6.6 unique fps overall (title 6, grid 7, track+gates 7, joints 2, training 2.5, model 3.6, hero 9, end 14).
  Reference player-two-brains-80s.mp4 = 18 overall (app screencast 10-16, B-roll 24-30). Causes: film-deck.mts films
  the deck with a real-time puppeteer screencast (Chrome only emits a frame when it has time, ~7/s under load), and
  the Runway clips are 24 fps copied to 30 by repeating every fourth frame. The MuJoCo hero was already 30 real fps.
- Fix at the source: film/deck/v4.html is a pure function of time (window.seek(t) lays out every element and seeks
  every visible video to its exact frame); film/tools/render-v4.mts steps it 1/30 s at a time and screenshots, so
  there is no wall clock. scripts/film4_assets.py turns every 24 fps Runway clip into real 30 fps frames
  (ffmpeg minterpolate, motion compensated; checked frame by frame on the fastest carry of v01, no tearing on the
  hand) and redraws the tracking overlay on the 30 fps frames with the measured points linearly interpolated
  between the two 24 fps measurements on either side.
- Order (his recommended one, kept): title -> hook -> sentence -> 8 Runway clips -> drop into Understudy -> 1 Track ->
  2 Gate -> 3 Retarget (joint angles) -> aside "why not generate the robot?" -> 4 Write (44 episodes) -> training ->
  what was trained -> hero -> end. The chips carry the pipeline step (Understudy 1/4 .. 4/4) so the middle reads as
  one pipeline. The aside sits right after the joint angles because that is where "why a hand?" comes up.
- Two capture bugs found and fixed on the way: python's http.server serves no Range requests, so Chrome could not
  seek a streamed 1080p video past its buffer (the hero froze 3 frames in 4); v4.html now loads every video as a
  blob. Shot starts are snapped to whole frames so no frame is sampled twice at a cut.
- Gates beat: all 8 in a full-frame grid, each rejected clip shown around the moment its gate fired with the
  verbatim run2.log reason, the 4 bounce out, the 4 accepted close ranks into a 2x2 (continuity into Retarget).
- [x] DONE 23:55: media/understudy-demo-v4.mp4 (1920x1080, 30 fps, 85.9 s, no audio stream) + -720p.mp4, rendered
  with scripts/film4.sh. Beats: 0:00 title, 0:04.5 hook, 0:09.4 sentence, 0:13.0 8 Runway clips, 0:19.2 drop,
  0:23.8 Track, 0:28.8 Gate, 0:36.8 Retarget/joint angles, 0:42.2 why-not-the-robot aside, 0:48.1 44 episodes,
  0:55.1 training, 1:01.9 what was trained, 1:07.7 hero (first working robot), 1:20.5 end card.
- Unique fps (fps_probe.py) v4 per beat: 29.3, 30, 29.7, 30, 30, 29.9, 30, 26.3, 26.9, 29.6, 29.3, 29.8, 29.5,
  24.7 (the last is the fade to black); 29.0 overall vs v3 6.6 and the reference 18.1. Lowest seconds: 41-43 s
  (14-20), the blurred question card over the robot clip's first frame.
- Checked: 1 fps sheet (media/work4/check/v4-final-1fps.jpg), side by side with the reference
  (media/work4/check/sbs.jpg: title, composer, B-roll chip + caption pill, end card), overlays on the hand/block,
  no robot before 1:07.7 except the failed Runway robot clip, no em-dashes on screen.
- Judgement calls: 24 fps Runway footage is motion-interpolated to 30 (synthesised in-between frames, not new
  Runway output); the tracking overlay between measured frames is interpolated; the composer is a UI mock in the
  Player Two app style (the real entry point is bin/understudy run "..."), as in v2/v3.

## Film v5 / live site (his v4 notes: a real website, a real live demo; started 2026-09-24 00:00)
Goal: Understudy as a working local web app that runs the real pipeline, and v5 of the demo = a recording of a user
really using it on the new prompt "put a red block into a bowl" (real Runway spend), with B-roll pop-ups of real
news sources. Silent, 80-90 s, media/understudy-demo-v5.mp4 + -720p.
- Budget rule changed by him: spend down to a Runway balance of 25, no lower (runway.FLOOR_BALANCE, replaces the
  350 cap). Balance 186 at start => 5 new clips (30 + 4 x 27 = 138 -> 48 left). A 6th would end at 21.
- Run it: `bin/understudy serve` -> http://127.0.0.1:8765 (key from the Keychain into the server env only).
  Runs land in data/web-runs/<slug>/ (gitignored); every stage's events are also logged in <run>/jobs/*.jsonl.
- Code: src/understudy/stages.py (footage / training_data / train_and_eval, each emits live events; pipeline.run
  now calls the same stages), webjob.py (a stage as a child process, `@@EV {json}` lines), web.py (FastAPI: /api/
  budget, plan, footage, data, train, jobs/<id>/events SSE; one stage at a time; data+train run under
  nice 19 + taskpolicy -b), site/ (index.html, app.css, app.js; the old static page moved to site/report/).
- Flow on the page: type the task -> plan check (plan.py, live) -> Generate Footage (Runway, parallel after the base
  frame, live task status) -> Generate Training Data (track, audit, 21 gates, retarget, re-anchor, LeRobot v3.0)
  -> drag accepted clips onto the drop zone (pointer drag; shift-click to select several; OS file drops of the same
  clip files also work) -> training loss live, model card, 50 MuJoCo eval rollouts live -> Watch the rollout
  (hero camera, 1920x1080, same seed/start/outcome as the eval asserted).
- Recording: film/tools/record-live.mts drives the real site (?film hands the page clock to the recorder; real
  mouse/keyboard events, real drag). UI beats: 1 frame per 1/30 s of page time. Server waits: frames paced on the
  wall clock; timeline.json keeps each frame's wall time so the edit compresses waits with an honest speed label.
- B-roll sources (verified on the page by a research subagent, screenshots in film/v5/sources/, sources.json):
  IEEE Spectrum "Will Scaling Solve Robotics?" (28 May 2024); Google DeepMind "Scaling up learning across many
  different robot types" (3 Oct 2023); Business Insider "Inside the glass-walled Tesla lab where workers train the
  Optimus robot to act like a human" (2 Nov 2025); Figure "Introducing Index: ..." (25 Aug 2026); TechCrunch "Nvidia
  wants to be the Android of generalist robotics" (5 Jan 2026); Apple ML Research "EgoDex: ..." (Jul 2025).
- [x] backend + site built, tested on the cached old prompt (0 credits; test server ran with floor 186 so any real
  call would have been refused)
- Live takes (all on "put a red block into a bowl", run dir data/web-runs/put-a-red-block-into-a-bowl/):
  - First try (00:47): all 5 clips came back from the cache: the Runway prompts are built from (colour, block,
    container), so the new sentence made the same requests as the old one. Fixed: seeds now come from the
    sentence (generate.seed_for; the first run's sentence keeps seed 11). Nothing spent.
  - Take 1 (00:48, media/work5/take1): real Runway, v01 base gen4_image + 4 restyles + 3 videos = 88 credits
    (186 -> 98). A budget bug (in-flight credits counted twice: Runway already takes them at submission) stopped
    the v04/v05 videos early. Fixed: balance check + submit under one lock, no reservation.
  - Take 2 (00:52, media/work5/live): v04 + v05 videos live (50 credits, 98 -> 48); v01-v03 and both first frames
    from the take-1 cache, labelled "from cache" on the page. Balance now 48 (floor 25): no further clip possible.
  - Take 2 data stage, real: ALL 5 REJECTED. v01 hand + wrist visible on 82% of frames; v02 a second red object
    41% of the block; v03 + v05 Claude counts 2 red blocks; v04 Claude counts 2 bowls. No bar was lowered.
  - So the site gained a real feature: footage that passed the gates in earlier runs on this machine is listed
    in the train step ("Passed the gates earlier", /api/library) and can be dragged onto the trainer too;
    training reads each run's LeRobot dataset (stages.train_and_eval with "<slug>/<clip>" refs). The old sentence
    was re-run through the site with 7 clips (all cached, 0 credits) to fill that library honestly.
  - Reopen a saved run: /?run=<slug> redraws a run from its saved stage events (/api/runs/<slug>/events), labelled
    "Saved run, reopened" in the top bar. Take 3 records from the reopened take-2 run: inspect the rejections,
    drag the earlier footage onto the trainer, train, rollout. The film cuts from take 2 to take 3 with a label.
- Take 3 (01:17, media/work5/take3): /?run=put-a-red-block-into-a-bowl reopened; inspect v01 (hand seen on 82%)
  and v03 (Claude counts 2 red blocks); shift-select the 4 earlier clips (put the red block in the bowl: v01 v03
  v06 v07), drag onto the trainer; 44 episodes, 4,000 steps in 29.4 s on the Apple M4 CPU, 46/50 unseen positions
  (Wilson 0.81-0.97), sim only; hero = seed 10000 at 1920x1080, same start and outcome as the eval.
- [x] DONE 01:40: media/understudy-demo-v5.mp4 (1920x1080, 30 fps, 84.4 s, no audio stream) + -720p.mp4, rendered
  with scripts/film5.sh (edit: --take live:compose:inspect-accepted --take take3:reopened:).
  Beats: 0:00 title, 0:03.6 live site + typing, 0:10.6 Generate Footage, 0:11.9-0:20.9 Runway (sped up 4.7x, 0:42
  real; pop-up 1 the data problem: Business Insider, IEEE Spectrum, Figure), 0:23.5 Generate Training Data,
  0:24.6-0:36.6 data stage (20.2x, 4:03 real; pop-up 2 why hands: Apple EgoDex + quote, the failed Runway SO-101
  clip), 0:36.6 all 5 rejected, 0:38.1 cut to the reopened run (chip "Same run, reopened in the site" + dip),
  0:39.6 inspect v01 (tracking), 0:45.8 inspect v03 (Claude audit), 0:51.2 select, 0:54.0 drag, 0:55.7 drop,
  0:56.7-1:06.7 training + eval (8.9x, 1:29 real; pop-up 3 the model card from this run), 1:09.0 Watch the
  rollout (hero, first working robot), 1:20.3 end card.
- Unique fps (fps_probe.py): 18.9 overall; 17-27 through the live parts; title 2.5 (a still card), typing 10
  (a key every 3 frames), hero+end 12.7 (the rollout stops once the cube rests, then the fade). Every frame is a
  real 1/30 s step of the page clock; low numbers are frames where nothing on screen moved.
- Credits: 138 on this sentence (take 1: 88, take 2: 50), balance 186 -> 48. Floor 25 kept. Ledger lines 20-29.
- Cleaned: take-1 frames encoded to media/work5/take1.mp4, rehearsal frames deleted (disk pressure). Earlier
  test outputs were moved to the Trash (his to empty). Kept: media/work5/live + take3 frames (needed to re-render).

## Film v6 (his v5 notes: prompt fix from real research, a paper pop-up, no all-rejected dead end, v4-like motion; started 2026-09-24 01:41)
Rule for this version: ZERO Runway credits (balance 48 stays for Wednesday's re-record). Verified: the take's footage
job has 7 CACHED video events and no SUCCEEDED ones (film6_assets.py asserts credits_this_take == 0); the server ran
with UNDERSTUDY_FLOOR_BALANCE=100000 so any real call would have been refused.
- Research (read on arXiv HTML v2 + CVF page + repo): PhyT2V, "PhyT2V: LLM-Guided Iterative Self-Refinement for
  Physics-Grounded Text-to-Video Generation", Qiyao Xue, Xiangyu Yin, Boyuan Yang, Wei Gao (Univ. of Pittsburgh),
  CVPR 2025 pp. 18826-18836, https://arxiv.org/abs/2412.00596, code github.com/pittisl/PhyT2V. Method: each round,
  Step 1 an LLM lists the objects and physical rules the prompt implies; Step 2 a captioner (Tarsier) describes the
  video and the LLM finds prompt/video mismatches; Step 3 the LLM rewrites the prompt with the rules and the fixes
  (step-back reasoning), and the rewrite is the next round's prompt. Their number (abstract, verbatim): "improves
  existing T2V models' adherence to real-world physical rules by 2.3x"; Sec 4.1: largest on CogVideoX-2B, PC up to
  2.2x, SA up to 2.3x, other models 1.3-1.9x; models CogVideoX-5B/2B, OpenSora 1.2, VideoCrafter; VideoPhy +
  PhyGenBench prompts. Not Runway. Their Appendix D: hands stay hard even after several rounds (relevant to us).
  Also used: Runway's Gen-4 prompting guide says negative phrasing is not supported and may give the opposite, so
  the v2 prompts are all positive ("the only red object", not "nothing else red").
- Implemented (src/understudy/plan.py, prompt version 2): Step 1 scene_spec() = inventory with exact counts (one
  red cube, one bowl, one right hand; "exactly three things") + six physical rules (rigid, one block in every
  frame, moves only while pinched, falls into the bowl on release, bowl stays put, hand + wrist in frame); Step 2
  mismatches() reads our gate / Claude-audit rejection reasons as the mismatch (duplicate_block, extra_container,
  second_red_object, hand_out_of_frame); Step 3 refine_fixes() + variants(fixes=...) put each corrective rule first
  in the prompt that caused it (first-frame vs motion) and drop the base sentence it supersedes; every prompt stays
  under Runway's 1000-character limit for any combination of fixes. No LLM or captioner in the loop (our gates are
  the critic); that is our adaptation, not PhyT2V itself. The first run's sentence keeps its v1 prompts byte for byte
  (tests/data/prompts_v1.json) so its cache still hits; a refined take always uses v2.
  Site: GET /api/runs/<slug>/refine (text only, plus the next take's credit estimate); POST /api/footage
  {"refine": true} makes the next take use the fixes (not run: it would spend); the inspector shows "Prompt fix for
  the next take" on a rejected clip. tests/test_plan.py (8 tests) on the real v5 rejection reasons.
  EFFECT UNMEASURED: no clip has been generated with v2 prompts. Measure on Wednesday: same sentence, v2 vs the v5
  rejection rate (5/5).
- Recording (media/work6/live, film/tools/record-live.mts): the real site on "put the red block in the bowl", the
  first run's sentence, 7 clips (UNDERSTUDY_CLIPS=7) all replayed from the Runway cache; the tiles and the step-2
  panel now keep "from cache" and "7 of 7 clips from the cache ... 0 credits" on screen (site fix). The data stage ran
  for real (15:33 wall, niced): 4 of 7 accepted (v01 v03 v06 v07), 3 rejected (v02 v04 v05, the video duplicated
  the block); 44 episodes; training 36.2 s on the M4 CPU, 46/50 unseen positions (sim only). One take, no cut to an
  older run. (He mentioned 8 cached clips: v00 is from an older prompt and is not part of this sentence's run.)
- Edit: scripts/film6.sh (film6_assets.py, film5_edit.py --work work6, film/deck/v6.html, render-v4.mts). Pop-ups:
  the v5 news sources during the data stage, then PhyT2V (arXiv abstract screenshot, their Figure 1 apple row, the
  abstract quote attributed to them with "not on Runway", caption "Our effect is measured on demo day"), then the
  model card. Motion: a slow drift push on the recorded plate (scale 1.011-1.027, 3-5 px), bg push on title/end.
- [x] DONE 03:35: media/understudy-demo-v6.mp4 (1920x1080, 30 fps, 81.6 s, no audio stream) + -720p.mp4, rendered with
  scripts/film6.sh. Beats: 0:00 title, 0:03.6 live site + typing, 0:09.7 Generate Footage, 0:11.0 7 clips from the
  cache (0 credits), 0:15.3 Generate Training Data, 0:16.4-0:32.4 data stage (58x, 15:33 real; pop-ups: the data
  problem, why hands), 0:32.4 4 of 7 pass, 0:33.9 inspect accepted v01, 0:39.6 inspect rejected v02 + prompt fix,
  0:44.5-0:48.9 PhyT2V pop-up, 0:48.3 select, 0:51.2 drag, 0:52.9 drop, 0:53.9-1:03.9 training + eval (9x, 1:31 real;
  model card), 1:06.2 Watch the rollout (hero), 1:17.0 end card.
- Unique fps (fps_probe.py): 28.9 overall (v4 29.0, v5 18.9). Per beat: 30, 29.6, 27.0, 30.1, 30, 28.2, 30, 30,
  29.7, 30, 24.5 (hero: the robot rests at the end, push only), 29.8. The motion that fills still moments is a slow
  camera drift/push on the recorded frames and a drift on pop-ups; no data or UI state is faked.
- Checked: media/work6/check/v6-final-1fps.jpg (1 fps sheet), beat stills media/work6/check/beat-*.jpg, no
  em-dashes in v6.html, balance still 48 after the take (GET /api/budget).
- Credits: 0. Balance 48 kept for Wednesday.

## Film v7 (his v6 notes: stack beat, a real robot foundation model, second physics engine, training in the terminal; started 2026-09-24 03:29)
Rule: ZERO Runway credits (balance 48 stays for Wednesday). Heavy work niced + taskpolicy -b, one heavy job at a time
(research render running); stop heavy work by 13:30 PT, nothing 14:30-15:45 PT.
- Foundation model: SmolVLA, `lerobot/smolvla_base` (450M params, 100M trainable: action expert + state proj, vision
  frozen; VLM backbone HuggingFaceTB/SmolVLM2-500M-Video-Instruct). Recipe verified in the installed lerobot 0.6.1
  source (modeling_smolvla.py docstring: `lerobot-train --policy.path=lerobot/smolvla_base ...`; configuration defaults)
  and the HF model card. Our dataset's camera `observation.images.front` maps to smolvla_base's `camera1` with the
  stock `--rename_map` (camera2/3 are simply absent; empty_cameras=0). No dataset rewrite needed.
  scripts/train_smolvla.sh = the exact command, recorded verbatim by scripts/termrec.py -> data/term/smolvla.jsonl.
  Run 1 (RUN=understudy): 650 steps, batch 8, MPS, stock defaults otherwise. 2343.6 s = 39 min 4 s wall on the M4
  (nice 19 + taskpolicy -b, research render running). Logged loss 0.519 (step 25) -> 0.113 (step 650).
  Eval: 17/50 (Wilson 0.22-0.48) vs MLP 46/50. (Its hero re-run was not bit-exact on MPS: 265 vs 268 frames, both
  successes; so the eval now stores every episode's qpos and the hero film re-draws the evaluated episode itself.)
  Run 2 (RUN=understudy-1h, the one in the film): 1000 steps, batch 8: 2967.7 s = 49 min 28 s wall; logged loss
  0.516 (step 25) -> 0.105 (step 1000; 0.083 at 975). Trained on the dataset the recorded site take produced.
  Checkpoints data/smolvla/<run>/checkpoints/last (gitignored, ~1.2 GB each with optimizer state).
  Measured before: AMP (fp16 autocast on MPS) gave no speed-up, so fp32. Download note: snapshot_download of the
  SmolVLM2 repo pulls 5.5 GB of onnx; removed via the HF cache API and re-fetched without onnx.
- Eval: src/understudy/vla.py, same MuJoCo harness, same 50 seeds and exact start positions as the MLP (asserted
  against train.json), same success rule; SmolVLA sees the sim front camera (320x240) + joints + sentence, not the
  cube position. Torch seed per episode so the hero film replays the evaluated episode (asserted).
- Second engine: src/understudy/crosscheck.py, PyBullet 3.2.7 (no macOS arm64 wheel: scripts/build_pybullet.sh
  patches zlib's fdopen define and builds data/wheels/*.whl, pinned in pyproject). Scene converted from the compiled
  MuJoCo model; replays each dataset episode's recorded 30 fps actions open loop in both engines (same servo law);
  Bullet solver settings (300 iterations, contact ERP 0.95, slop 0, 2 substeps) fixed after a 5-8 episode probe,
  before the full run. RESULT (data/term/crosscheck.jsonl): open-loop replay of the 30 fps actions: MuJoCo 43/44 in
  the bowl, PyBullet 30/44, both 29/44, engines agree on 29/44, median final-cube gap 3.3 cm (678 s). Disagreements
  are mostly v06 copies (8 of 11) and v01 (5): in Bullet the cube slips in the grasp / catches the bowl rim while
  carried. Reported as "29 of 44 in both, 15 flagged"; not tuned further after seeing the result.
- Site take (media/work7/live, 2289 frames, 992 s wall): same 4/7 accepted, 44 episodes, 14,985 frames; its
  dataset is byte-identical to the one both SmolVLA runs trained on (parquet arrays equal, video file identical,
  compared against the 04:12 download of the earlier dataset). The Download click saved the real 56.8 MB zip.
- MLP in the terminal (data/term/mlp.jsonl, 74.7 s): 4000 steps in 26.5 s on the M4 CPU, 46/50 (same as v6).
- Site: ends at the dataset. Step 3 = "Your training data is ready": counts from meta/info.json, the zip
  (GET /api/runs/<slug>/dataset.zip, 56.8 MB, loads back with LeRobotDataset), Download button (real fetch + save),
  and the terminal commands. Drag/drop trainer, /api/train, /api/library removed. `bin/understudy train <run>` = the
  MLP baseline in a terminal (same stages.train_and_eval).
- Film: film/deck/v7.html, scripts/film7_assets.py (facts + verbatim terminal logs -> media/work7), scripts/film7.sh.
- SmolVLA run 2 eval (the film's): 16/50 (Wilson 0.21-0.46) vs MLP 46/50 on the same 50 positions; run 1 (39 min)
  was 17/50, so the extra 10 min did not help (within noise). Hero = seed 10001, the evaluated episode re-drawn from
  its stored qpos (264 frames, end position asserted equal).
- [x] DONE 07:45: media/understudy-demo-v7.mp4 (1920x1080, 30 fps, 112.6 s, no audio) + -720p, scripts/film7.sh.
  Beats: 0:00 title (stack chips), 0:03.6 live site + typing, 0:10.0 Generate Footage (7 from cache, 0 credits),
  0:16.7-0:30.7 data stage (62x, 14:35 real; pop-ups: robot data, why hands), 0:30.7 4 of 7 pass, 0:32.2 inspect
  accepted, 0:37.9 inspect rejected + prompt fix, 0:42.2 PhyT2V pop-up, 0:47.8 Download dataset (real 56.8 MB zip),
  0:52.0 two engines (MuJoCo | PyBullet film of episode 0; "both 29 of 44", verbatim [crosscheck] line), 1:01.0
  foundation models (HF SmolVLA blog, two verbatim quotes), 1:07.5 terminal: lerobot-train verbatim (49:28 real
  shown in ~8.5 s, 349x, real clock + logged loss curve), 1:18.5 terminal: bin/understudy train (1:15 real, 21x),
  1:24.0 results (SmolVLA 16/50 vs MLP 46/50, per-seed dots), 1:31.5 SmolVLA hero rollout, 1:41.5 stack (11 tools
  with roles), 1:48.0 end card.
- Unique fps (fps_probe.py): 29.9 overall; every beat 29.4-30.0 (a slow push on every post-site segment).
- Checked: media/work7/check/v7-final-1fps.jpg, beat-*.jpg; no em-dashes in v7.html / site; credits 0 (assets
  script asserts the take spent 0; balance 48).
- Terminal text: verbatim from data/term/*.jsonl (ANSI colour codes stripped; long lines clipped at the window edge;
  the macOS objc duplicate-class warnings kept). The command is shown typed out over ~1.5 s (the real command).

## v8 prep (Runway Hackathon Wed 2026-09-30; started 2026-09-24 08:42; plan in docs/V8-PLAN.md)
Rule: ZERO Runway credits (balance 48). Heavy jobs niced + taskpolicy -b, one at a time (research render live from 09:31).
- BEFORE number (the missing baseline): `lerobot/smolvla_base`, no fine-tuning, same harness/seeds/success rule:
  **0/50 (Wilson 0.00-0.07)**, 2723 s. Processors = the fine-tuned checkpoint's (rename + our mean/std = lerobot-train
  step 0), so the only difference to AFTER (16/50) is the 1000 steps (49 min 28 s). Fisher two-sided p = 7e-6.
  Arm moves, pushes the cube > 1 cm in 8/50, lifts 0/50. scripts/eval_smolvla_base.sh -> data/smolvla/base-zeroshot/.
  vla.py gained --weights (evaluate other weights with ckpt's processors) and --proc (other processors) + --out.
- Out-of-the-box variant (base weights + its own SO-100 pretraining stats): scripts/eval_smolvla_base_ootb.sh ->
  data/smolvla/base-ootb/. **Also 0/50** (0.00-0.07), lifted 0, pushed 8/50; 6701 s (starved by the render, as intended).
- Runway (docs read 2026-09-24): `gen4_aleph` is gone from /v1/video_to_video; it is `aleph2`, 28 credits/s, 56-credit
  minimum, input 2-30 s <= 30 fps. Balance 48 cannot pay one Aleph call. act_two needs a visible human face (no
  robot/G1). Recommendation: Option 2 (MuJoCo drives the arm, Aleph restyles, pose-IoU gate), Option 3 fallback.
- Scraper probe (scripts/scraped_probe.py, data/scraped/ gitignored): Pexels 5944803 + Commons CC BY 4.0 grasp-lift
  trial, both REJECTED by the unchanged gates: length, hand visible 59%/73%, red-only tracker/audit; motion gates (IK,
  vel/acc/jerk) pass on the Pexels clip. Needs trim + pinch-seeded object tracking + task-generic audit.
- Privacy sentence (docs/V8-PLAN.md D).
- Research pass (2026-09-24 evening, 0 credits): docs/RESEARCH-PIPELINE.md (diagnosis, ranked interventions, credit
  plan for the ~1,000 and the 50K, day-of plan, true stage sentences) + docs/research/LIT-NOTES.md (primary sources).
  Failure sort of the 16/50 model (scripts/eval_failures.py): 18 grasp misses (14 pushed, 4 untouched), 10 lifted
  but ended at the bowl rim, 6 lifted and dropped away. Dataset carries clear the 2.5 cm wall by only 0.3-1.1 cm.
  Our fine-tune = 0.53 epoch; docs recipe 20k steps x batch 64 (160x more samples). Eval ran 50-action chunks open
  loop; SmolVLA's own LIBERO ablation: 50 steps worst (51.8%), 10 steps 82.8%.
- Probes running (scripts/probe_chain.sh, log data/probes/chain.log): P1 replan every 10 actions on the same
  checkpoint (data/smolvla/probe-replan10), then P2 aug25 dataset (~70 episodes) + 1000 steps front, P3 + wrist camera, P4 best of
  P2/P3 at 3000 steps. Code: vla.py --n-action-steps/--cameras, dataset.write(cameras=), scripts/augment_dataset.py,
  scripts/lerobot_train_lean.py (no optimizer state; disk ~2 GB above floor).
- APPROVED (Pranav, 2026-09-24 chat): the ~1,000-credit test plan in docs/RESEARCH-PIPELINE.md section 7 (10 v2-prompt
  clips 270, second phrasing 6 clips 162, 2 aleph2 5 s probes 280, ~290 reserve; stop clips if v2 acceptance < 2/10),
  to run once Runway grants the credits. Balance 48 at approval. 50K day-of plan NOT yet approved.
- P1 RESULT: replan every 10 actions, same 1000-step checkpoint: 11/50 (0.13-0.35) vs 16/50, Fisher p = 0.37, no gain;
  dropped. Chain then STOPPED itself at 22:07: free disk 20-21 GB (floor 20); P2-P4 need ~3 GB (dataset ~0.3 GB + 0.87 GB
  per lean checkpoint). Resumed 2026-09-25 after he had the uv cache cleared (6.2 GB freed, 27.9 GB free).
- 2026-09-25 03:15 HELD for render memory pressure (Jarvis, swap 9.4/10 GB): chain parent (pid 66397) stopped; the running P2 training (pid 3805, aug25 front, 1000 steps) left to finish (step 252 at 03:15, ~16-18 s/step under swap, so ~06:45). No eval/training/augmentation until Jarvis clears it after 08:00. Resume: scripts/probe_chain.sh (skips aug + finished training, evaluates P2, then P3, P4).
- 04:20 P2 training (aug25 front, 1000 steps) finished: 2 h 4 min wall under swap; lean checkpoint; eval held until Jarvis clears (after 08:00).
- 2026-09-26 01:50 hold LIFTED (Jarvis: Pranav wants research running overnight). probe_chain.sh rewritten for the shared ~/helloworld/.heavy-lock rule (waits if swap > 10 GB or disk < 15 GiB); new order: P2 eval -> P4 aug25 front 3000 steps -> P3 wrist (disk 16 GiB fits ~1 more checkpoint). Chain pid 47728 (data/probes/chain.pid).
- P2 RESULT (02:32 09-26): aug25 (74 eps, 70/100 re-anchored copies passed) + 1000 steps front: 22/50 (0.31-0.58) vs 16/50;
  Fisher 0.30, paired McNemar 0.07 (7 vs 1 discordant). Rim/drop failures down (16 -> 9), grasp misses unchanged (19).
  Chain now WAITING: free disk 13 GiB < 15 (shared rule); P4 (3000 steps) needs ~0.9 GB more.
- 2026-09-26 disk (Jarvis asked to free ~3.5 GB): moved the superseded 650-step SmolVLA run (data/smolvla/understudy, 1.2 GB,
  17/50) to the macOS Trash; its eval.json + train_config kept in data/smolvla/understudy-650-record/. Regenerate: STEPS=650
  RUN=understudy scripts/train_smolvla.sh (39 min). Space frees only when Pranav empties the Trash (hard rule: no permanent
  deletes, even when asked). NOT moved: media/work5-7 (mostly the recorded site takes live/ + take3/ frames, kept to re-render).
- P4 training (aug25 front, 3000 steps = 2.4 epochs of 25,190 frames) DONE 07:23 09-26: 4 h 36 min wall at 5.5 s/step; loss 0.661 (step 25) -> ~0.06 at 3000 (P2's 1000-step run ended ~0.095). Eval WAITING (shared rule: disk 13 GiB < 15, swap 11 GB > 10); it starts on its own.
- P4 RESULT (12:14 09-26): aug25 front, 3000 steps: **33/50 (0.52-0.78)**. Paired vs film model 16/50: 17 only-P4, 0 only-film
  (McNemar p < 1e-4); vs P2 22/50: 13 vs 2 (p = 0.007). Failures: 10 grasp, 7 rim. Checkpoint data/probes/smolvla-aug-3000
  (lean). First result above 30. Next: P3 wrist (needs 15 GiB), hero rollout of P4 for the film, quiet window 19:30-23:30.
- 13:08 09-26: P4 hero rendered: data/probes/smolvla-aug-3000/checkpoints/last/hero.mp4 (seed 10000, 263 frames, end position asserted equal to the eval). P3 (aug25 front+wrist, 1000 steps) training started 13:08, disk guard armed.
- 15:59 09-26: P3 wrist training STOPPED (stalled at 31 s/step, 132/1000, swap 10.7 GB; would have run into the 19:30-23:30 quiet window promised to servo-metrology). Chain stopped, heavy-lock released (Jarvis needed it). No P3 result.
- 03:11 09-27: understudy/.venv was REMOVED by a disk cleanup at 01:39 (jarvis/log 09-27: 'removed .venv for understudy + scout'). Chain stopped before it failed. scripts/rebuild_venv.sh (pid data/probes/venv.pid, log data/probes/venv.log) runs uv sync --frozen behind the heavy-lock, then restarts the chain (P4 eval-noise check). Jarvis asked not to remove it again.
- 04:25 09-27: .venv rebuilt 03:44 (uv sync --frozen, 1.2 GB, imports OK). P4 eval-noise check: same model, noise +1000: 29/50 (0.44-0.71); paired vs 33/50: 22 both, 11 vs 7, 10 neither; pooled 62/100. Headline = 'about 30 of 50 (29-33)'. Chain: all probes done.
