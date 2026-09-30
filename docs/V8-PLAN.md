# Understudy v8 plan (Runway Hackathon, Wed 2026-09-30)

Written 2026-09-24. Zero Runway credits spent preparing it (balance 48). Every Runway fact below was read from
Runway's own docs on 2026-09-24 (docs.dev.runwayml.com: /guides/pricing, /guides/models, /assets/inputs, /api.md;
help.runwayml.com "Creating with Edit Studio"; runway.com/research/introducing-runway-aleph), not from memory.

His new direction: (1) scrape real videos of people doing the task, (2) MediaPipe isolates the hand/arm motion,
(3) Runway generates footage around those key positions, possibly with a robot arm or a Unitree G1 following them,
(4) train and show before/after scores and how fast training is.

## A. The BEFORE number (measured)

**`lerobot/smolvla_base` with no fine-tuning: 0/50 (Wilson 95% 0.00-0.07).** Same MuJoCo harness
(src/understudy/vla.py), same 50 unseen cube positions (seeds 10000-10049, asserted equal to train.json), same
success rule (lifted > 2 cm, then resting in the bowl), same 25 s cap, MPS, nice 19 + taskpolicy -b, 2723 s.
Command: scripts/eval_smolvla_base.sh (recorded verbatim to data/term/smolvla-base-zeroshot-eval.jsonl);
result data/smolvla/base-zeroshot/eval.json (+ eval_traj.npz, every episode's qpos).

Fairness: the network weights are the stock `lerobot/smolvla_base`; the processors (camera rename front ->
camera1, our dataset's mean/std for state and action) are the fine-tuned checkpoint's, which is exactly what
`lerobot-train` builds at step 0. So the ONLY difference between BEFORE and AFTER is the 1000 gradient steps
on Understudy data.

What the base model does: it moves (episode 0: elbow swings through 2.6 rad, gripper opens and closes), touches
the cube in 8/50 episodes (cube pushed > 1 cm), and lifts it in 0/50. It has never seen this scene, this
camera or this arm in simulation, so this is the expected zero-shot floor, not a straw man.

Robustness check, "out of the box" (base weights AND the base model's own processors, i.e. its SO-100
pretraining mean/std for state and action; our camera renamed to camera1): **also 0/50 (0.00-0.07)**, lifted 0/50,
cube pushed > 1 cm in 8/50 (scripts/eval_smolvla_base_ootb.sh -> data/smolvla/base-ootb/; 6701 s wall because
the research render was running and this job was at background priority). So the BEFORE number does not depend
on which normalisation stats the base model is given.

The reframed v7 headline:

| | Model | Sees | Unseen positions in the bowl |
|---|---|---|---|
| BEFORE | SmolVLA (`lerobot/smolvla_base`), no Understudy data | camera + joints + sentence | **0/50** (0.00-0.07) |
| AFTER | same model, 1000 steps on Understudy data, **49 min 28 s on the M4 laptop** | camera + joints + sentence | **16/50** (0.21-0.46) |
| Privileged reference (not a competitor) | 2-layer MLP, 26.5 s training | the simulator's cube position, no camera | 46/50 |

0/50 vs 16/50: Fisher exact two-sided p = 7e-6. Say: "Same foundation model, before and after Understudy data:
0 of 50 to 16 of 50 in 49 minutes on a laptop." Do not say "16/50 is good"; the MLP shows how much headroom a
policy with the cube position has, and the MLP is privileged, so it is a ceiling hint, not a rival.

## B. Where Runway fits

### What the Runway API actually offers today (verified 2026-09-24)

| Model (API id) | Endpoint | Inputs | Limits | Cost |
|---|---|---|---|---|
| Aleph 2.0 (`aleph2`) | `POST /v1/video_to_video` | `videoUri` (required, the video to edit) + `promptText` and/or up to 5 timed `keyframes` (guidance images at given seconds, optional edit window), optional `seed`, `targetAspectRatio` (outpaint) | input 2-30 s, <= 30 fps; output keeps the input resolution up to 1080p; Edit Studio asks for 480p-1080p input | **28 credits/s, 56-credit minimum per generation** |
| Act-Two (`act_two`) | `POST /v1/character_performance` | `character` image (API field enum is `image`; the doc text also mentions a video) + `reference` performance video; `bodyControl` (apply body gestures, not only the face), `expressionIntensity` 1-5 | reference 3-30 s; **"A visually recognizable face must be visible and stay within the frame"** | 5 credits/s |
| Gen-4 Turbo (`gen4_turbo`) | `POST /v1/image_to_video` | first-frame image + text (what v1-v7 used) | 5 or 10 s | 5 credits/s (+ 2-5 per start frame) |
| `gemini_omni_flash` (Google's model, sold through the Runway API) | `POST /v1/video_to_video` | `videoUri` + `promptText` + up to 5 reference images | input <= 10 s, 720p out | 11 credits/s for video-to-video (no minimum listed) |

Notes that change the plan:
- **`gen4_aleph` is no longer a request model on `/v1/video_to_video`.** The endpoint's models are `aleph2`,
  `hailuo3`, `seedance2*`, `gemini_omni_flash*`; `gen4_aleph` survives only as a historical value in the usage
  report. Any v8 code must call `aleph2`.
- **Balance 48 is below Aleph's 56-credit minimum, so not even one Aleph call is possible without a top-up.**
  Credits are $0.01 each; a top-up is money, so it is Pranav's call, not the session's.
- What each model is designed for (Runway's words, paraphrased): Aleph is an in-context video model for editing
  an input video: add, remove and transform objects, new camera angles, restyle, relight, swap backgrounds.
  Act-Two drives a character from a person's performance video (face first; body with `bodyControl`).
  Gen-4 Turbo animates a still.

### The three options

**Option 1: Aleph (or Act-Two) re-renders the scraped human video as a robot arm or a G1 following the motion.**
- Act-Two is ruled out by its own contract: the character must show a recognisable face that stays in frame.
  An SO-101 arm has no face; a G1's head has no face either. It is built for faces and people.
- Aleph can be asked to "replace the hand with a robot gripper", but nothing constrains the generated robot to
  a real kinematic chain. The pixels are a plausible robot; the labels would be our retargeted joint angles.
  The two come from different processes and nothing forces them to agree: a policy trained on the pair learns
  a mapping from images to actions that were never the actions that made those images (label noise
  correlated with the image, the worst kind). There is also no physics: nothing checks the grasp holds.
- Where it is still useful: the demo moment ("here is the human, here is the same motion as a robot"), not
  training data. It has no physics reference to gate against, so it never enters the dataset.

**Option 2 (recommended main path): our retargeted trajectory drives the SO-101 in MuJoCo (exact kinematics and
physics), then Aleph turns the sim render photoreal and varies the scene, keeping the geometry.**
- The labels are exact by construction: the actions are the joint targets that produced the robot's motion in
  the physics engine, and the physics already decides success (the MuJoCo gate, plus the PyBullet cross-check).
- Runway only changes appearance (materials, lighting, table, background, clutter). That is exactly Aleph's
  documented job (restyle, relight, swap backgrounds on an input video), not something it has to invent.
- This is the Cosmos-Transfer idea. Verified primary source: Cosmos-Transfer1, NVIDIA, arXiv:2503.14492
  (Mar 2025): a conditional world model driven by segmentation, depth and edge controls, evaluated on
  "robotics Sim2Real" and AV data enrichment. Difference to be honest about: Cosmos-Transfer conditions on the
  sim's own depth/segmentation maps; Aleph only sees RGB (+ optional keyframe images), so geometry is kept by
  the prompt and the model's tendencies, not by a hard control signal. Hence the gate below is mandatory.
- **Pose-consistency gate (a clip counts only if the robot in the Runway video is the robot in the physics):**
  1. MuJoCo renders, for every frame, the RGB clip that goes to Aleph *and* a segmentation mask of the arm
     (MuJoCo's segmentation render, geom ids of the SO-101 bodies) and of the cube.
  2. On the Aleph output, segment the arm (a promptable video segmenter such as SAM 2, prompted once with a
     point on the gripper from the known sim mask; or a colour key if the prompt keeps the arm's colour).
  3. Per-frame IoU(sim arm mask, Runway arm mask). Accept the clip only if the median IoU >= 0.80 and the worst
     frame >= 0.60 (thresholds to be fixed on the first 2 clips and then frozen, as for every other gate), the
     cube centroid stays within 1 cube width (3 cm in image px) of the sim cube, and there is exactly one cube.
  4. The existing Claude scene audit on first/last frame (one red block, one bowl, block in bowl at the end).
  Anything failing is logged as a rejection with the reason, like the v1-v7 rejected clips.
- **What it can and cannot show on Wednesday.** Our eval is in simulation with the sim camera, so photoreal
  frames cannot raise the sim success rate by themselves; claiming they did would be wrong. What they buy is
  visual diversity for a real SO-101 (not arrived yet). What we *can* measure on Wednesday: (a) the gate pass
  rate (how often Aleph keeps the geometry), and (b) a visual-robustness test: the fine-tuned SmolVLA's
  offline action error on the Aleph-restyled frames of held-out episodes (same actions, new look), before vs
  after adding restyled frames to training. That is an honest before/after for what Runway adds.
- Cost: input <= 30 fps, 2-30 s. Our episodes average 11.4 s at 30 fps (14,985 frames / 44); a 5 s window (reach, grasp, carry,
  release) at 720p costs 140 credits; the 2 s minimum is 56. See the budget table.

**Option 3 (fallback, what v1-v7 do): text/image-to-video human demos with Gen-4 Turbo when no internet footage
exists.** 27 credits per 5 s clip (turbo frame 2 + video 25). Proven path: 4 of 7 clips passed the gates in v7.
Of the Runway-native models it is the only one the current balance (48) pays for: exactly one clip.

### Recommendation

Option 2 as the main path, Option 3 as the fallback, Option 1 only as a visual in the film, never as training data (and
labelled as such). Reasons, in order: labels stay exact (physics generated them); Runway is used for what its
docs say Aleph is for; the pose gate makes any Runway drift visible and rejectable; the claim we make ("Runway
changes the look, physics owns the motion") is one we can measure.

### Credit estimate for a Wednesday run

| Plan | Calls | Credits | $ at $0.01 | Fits balance 48? |
|---|---|---|---|---|
| Option 2, minimum probe | 1 x Aleph 2 s | 56 | $0.56 | No (needs +8) |
| Option 2, demo run | 4 x Aleph 5 s (4 looks of 1-2 episodes) | 560 | $5.60 | No |
| Option 2, small dataset slice | 8 x Aleph 5 s | 1,120 | $11.20 | No |
| Zero-top-up probe (not Runway's own model) | 1 x `gemini_omni_flash` v2v 4 s | 44 | $0.44 | Yes |
| Option 3 fallback | 1 x Gen-4 Turbo 5 s clip + turbo frame | 27 | $0.27 | Yes (one clip) |
| Option 1 demo visual | 1 x Aleph 5 s on a scraped clip | 140 | $1.40 | No |

Suggested ask to Pranav: a top-up of about 700 credits ($7) buys the 4-clip Option 2 demo run plus one
Option 1 visual; everything else is already built and costs 0 credits. Hackathon organisers may also hand out
credits on the day; do not plan on it.

## C. Scraper feasibility (real footage through the unchanged gates)

Search (scout search over SearXNG, plus the Wikimedia Commons API). Candidates with licences:

| # | Clip | Source | Licence | Fit for "put X in a bowl" |
|---|---|---|---|---|
| 1 | Person Putting Strawberries on a Cup (15 s, 1080p) | pexels.com/video/5944803 | Pexels License (free use + modification, no attribution; NOT Creative Commons) | close: pinch, place into a small cup |
| 2 | A Person Putting Sliced Fruits in a Bowl (10 s, portrait) | pexels.com/video/8802375 | Pexels License | close (not inspected frame by frame) |
| 3 | Person Putting a Fruit Bowl on a Table | pexels.com/video/4075020 | Pexels License | places the bowl itself |
| 4 | Preparing a bowl with yogurt and fruit | mixkit.co/free-stock-video/...-43925 | Mixkit Free License (terms page did not render; not verified) | loose |
| 5 | Grasp-and-lift example trial (13 s, 720p), Luciw, Jarocka, Edin, Scientific Data 2014, supplementary file 4 | commons.wikimedia.org (File:...sdata201447-s4.ogv) | **CC BY 4.0** | grasp + lift + replace of an instrumented object, no bowl |

Commons has almost no everyday "hand puts object in bowl" video; the true-CC hit is a lab grasp-and-lift trial.
YouTube CC search was not tried (needs yt-dlp licence filtering; next step if we go this way).

Downloaded (data/scraped/, gitignored, licences in data/scraped/LICENSES.md): #1 (SD 960x540, 2.6 MB) and #5
(re-encoded to mp4, 2.7 MB). Run through the UNCHANGED clip path (scripts/scraped_probe.py: MediaPipe ->
events -> Claude audit -> clip gates -> retarget -> MuJoCo replay gates), nothing tuned. Log:
data/scraped/probe.log.

**Result: both REJECTED.** Why, gate by gate:

| Gate | Strawberries (#1) | Grasp-lift (#5) | What it means |
|---|---|---|---|
| length 3-12 s | FAIL 14.9 s | FAIL 13.0 s | trivial: trim to the event window |
| hand visible >= 95% of frames | FAIL 59% | FAIL 73% | real hands enter/leave frame and are occluded; generated clips keep the hand in view |
| scene audit (1 red block, 1 bowl, 1 hand) | FAIL 0 blocks | FAIL 0 blocks, 0 bowls | the audit prompt is hard-coded to our red block |
| no second red object | FAIL 40 frames | FAIL 271 frames | the colour tracker assumes ONE red object; a bowl of strawberries is many |
| events (grasp, lift, release) | PASS | FAIL (no hand at grasp) | |
| lift >= 3 cm / carry >= 5 cm | FAIL 0.8 cm / 0.1 cm | n/a | the tracker followed a strawberry that never moved, not the one in the hand |
| IK in SO-101 limits, velocity, acceleration, jerk | PASS (0 ticks at limit, 0.6 mm IK error, 1.5 rad/s, 27.8 rad/s^2, 1328 rad/s^3) | n/a | the human motion itself retargets to a feasible SO-101 motion |
| MuJoCo replay: cube in bowl | FAIL | n/a | follows from the wrong object |

Reading: the motion side works on real footage (MediaPipe finds the hand on 59-73% of frames, and the one clip
with events retargets within the arm's limits and smoothness gates). The object side does not: the tracker,
audit and duplicate gate were written for one red cube in a generated clip. To make scraped footage pass,
three changes, all 0 credits: (1) cut each clip to [hand enters, release + 1 s]; (2) track "the object in the
pinch at the grasp frame" (seed the object track from the pinch point, any colour; e.g. a promptable video
segmenter) instead of "the largest red blob"; (3) make the audit task-generic (one graspable object in hand,
one container). The hand-visibility gate should stay strict on the demonstration window only (after the trim
it may pass). Until those land, real footage cannot feed the dataset; saying otherwise would be false.

## D. Privacy: the accurate version

- Scraped videos are real people. Synthetic data does not make that go away; what we can do is keep only
  motion numbers. The pipeline stores per-frame hand/arm landmarks (pixel and metric keypoints, joint
  angles after retargeting). It stores no face crops, no face landmarks, no names or account handles, and the
  raw clips stay local (data/scraped/, gitignored) and are never shown in the film or on the site.
- Skeletons are much less identifying than video, but not provably anonymous (gait and motion style can
  identify people in some settings), so we say "we keep only the motion", not "it is anonymous".
- Runway-generated humans (Option 3) are not real people. Runway-restyled sim renders (Option 2) contain no
  person at all: the only body in the frame is the robot.
- Licences still apply: scraped clips need a licence that allows the use (CC BY needs attribution; the Pexels
  License is free use but not Creative Commons; videos YouTube marks with its Creative Commons (CC BY) option can be reused with credit, other
  YouTube videos cannot). Generated clips are governed by Runway's terms.

**The sentence he can say:** "From real videos we keep only the motion, the joint angles of the hand and arm,
never faces or identities; the people in our generated clips are not real, and every clip we use is licensed
for it."
