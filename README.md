# Understudy (replay build)

This copy of Understudy shows the policy, not the footage: each scenario tile on the site is the fine-tuned SmolVLA
itself running that scenario in MuJoCo. The run `put-the-red-block-in-the-bowl` keeps only its 4 accepted clips
(v01 v03 v06 v07). Typing the same sentence, or "More scenarios" on the site, adds NEW clips after the highest id
(v08, v09, ...); nothing already made is regenerated.

- Tile films: `data/web-runs/<run>/media/vla/<clip>.mp4` + `<clip>.json` ({clip, success, frames, cube_xy, model}).
  A tile without one says "VLA film rendering" and the page picks the film up within 5 s of it landing.
- Make them with the model (Linux GPU box: `MUJOCO_GL=egl` is the default there):
  `PYTHONPATH=src python scripts/vla_tiles.py data/web-runs/put-the-red-block-in-the-bowl --ckpt <checkpoints/last> --device cuda`
- Or film the evaluated episodes (no model): `... --from-eval <eval.json> <eval_traj.npz>` (add `--dry-run` to see the picks).
- Live: start the server with `UNDERSTUDY_VLA_CKPT=<checkpoints/last>` and the site runs SmolVLA on each newly accepted
  scenario after its dataset (POST /api/vla). Without it, new tiles say "VLA film rendering" and the side panel shows
  the command. `UNDERSTUDY_HEAVY_LOCK=0` skips waiting for ~/helloworld/.heavy-lock.

# Understudy

An understudy learns the role by watching the lead. Here the lead is a person that Runway made up, and the
understudy is a LeRobot SO-101 arm. Type a task; Runway generates people doing it; the pipeline measures the hand,
throws out every clip a robot should not learn from, retargets the rest onto the SO-101, writes a LeRobot v3.0
dataset, trains a small policy and runs it in MuJoCo.

AI video now models gravity, contact and grasping well enough to look real at a glance. The natural next step is
to use it as data, not only as media, and robotics is the first field that needs it: robots learn skills from
demonstrations, and today people record those one take at a time, by teleoperating a robot or filming
themselves. Understudy makes the demonstrations from one sentence, for a low-cost arm anyone can buy.

Generated video is not always physical, so the gates are the core of the tool, and the rejections are shown as
proudly as the acceptances. **Runway imagines the demonstration. Physics decides if it counts.**

Built for the Runway API hackathon (theme: build the tool you wish existed). Local only.

## Run it

```
bin/understudy serve                                            # the web app: http://127.0.0.1:8765
bin/understudy run "put the red block in the bowl" --clips 7   # everything, cached stage by stage
bin/understudy budget                                           # live Runway balance vs the floor (25)
bin/understudy train put-the-red-block-in-the-bowl              # the small MLP baseline on a run's dataset + MuJoCo eval
scripts/train_smolvla.sh                                        # fine-tune SmolVLA (lerobot/smolvla_base) on it
scripts/eval_smolvla.sh                                         # SmolVLA on the MLP's 50 unseen positions in MuJoCo
scripts/crosscheck.sh                                           # replay every episode in MuJoCo and PyBullet
.venv/bin/python -m pytest                                      # 22 tests
.venv/bin/python scripts/build_site.py                          # the static report of one CLI run (site/report/)
.venv/bin/python scripts/film.py                                # media/understudy-demo.mp4
```

`bin/understudy` reads the Runway key from the macOS Keychain (`RUNWAY_API_KEY`) into the process environment
only. It is never written anywhere. Re-running the same prompt spends nothing: Runway outputs are cached by
request hash, landmarks and the Claude audit by clip hash.

## Pipeline and tools

| stage | what | tool |
|---|---|---|
| 1 prompt | parse the task, refuse what a 5-DOF two-finger arm cannot do, before any credit is spent | `plan.py` |
| 2 lead | first frame with **gen4_image**, restyles (table, bowl, light) with **gen4_image_turbo**, 5 s of motion with **gen4_turbo** | Runway API |
| 3 skeleton | 21 hand landmarks + arm pose per frame; red block by colour | **MediaPipe** Hand Landmarker + Pose heavy, OpenCV |
| 4 audit | counts blocks, bowls and hands in the first frame, finds the bowl, checks the last frame | **Claude** (sonnet, headless Claude Code) |
| 5 gates | 21 gates, clip side and robot side, each with a reason | `gates.py`, docs/DATA-SPEC.md |
| 6 retarget | grasp point to grasp point, 1:1 in metres, physics replay | **MuJoCo** 3, SO-101 MJCF |
| 7 dataset | accepted episodes, `so101_follower` keys and units | **LeRobot** 0.6.1, `LeRobotDataset.create`, format v3.0 |
| 7b check | every episode replayed in an independent second engine; flagged where the engines disagree | **PyBullet** 3.2.7 |
| 8a policy | robot foundation model, fine-tuned with the stock `lerobot-train` on the dataset (camera + joints + sentence) | **SmolVLA** `lerobot/smolvla_base`, PyTorch (MPS) |
| 8b baseline | MLP with action chunks and ACT-style temporal ensembling, CPU (joints + cube position) | PyTorch |
| 9 rollout | trained policies on the same 50 unseen cube positions | MuJoCo |

## The task, and why it maps 1:1

"Put the red block in the bowl": one hand, pinch grasp of a 3 cm cube, lift, carry about 10 cm, release into a
bowl on a table, well inside the SO-101's roughly 30 cm reach.

- A thumb-index pinch is a two-finger parallel grasp, which is exactly what the SO-101's gripper is. The pinch
  point (midpoint of thumb tip and index tip) maps to the point between the gripper pads, and "fingers closed on
  the block" maps to "gripper closed".
- The human's wrist can orient freely; the SO-101 has 5 joints. The task only needs "jaws down, closing across
  two faces of the cube", which the SO-101 can always reach in its workspace, so the arm's own IK chooses the
  joints and the human's elbow and shoulder angles are not copied (their kinematics differ).
- The block is the ruler: a 3 cm cube gives metres per pixel, so the lift height and carry distance are the
  human's, in metres, on the robot.

Refused before spending credits: two hands, liquids and pouring, cloth and rope, tool use, finger dexterity
(buttons, typing, threading), articulated objects (jars, drawers), and any colour but red in this build (the
colour tracker and the audit are red-only). See `tests/test_pipeline.py`.

## How a clip becomes robot data

- **Events come from the object.** The grasp is when the fingers reach the block just before it starts moving;
  the release is when the block is back at rest. Finger aperture was measured and is useless for this on
  generated hands (docs/POSE-COMPARE.md).
- **Object-anchored.** While the block is held, the grasp point is the block's own measured centre (fingertips
  slide and hide; the block does not). Before the grasp and after the release it is the hand's path, shifted so
  it meets the block exactly at the grasp.
- **Depth is not measured.** One camera cannot see depth; each demonstration is assumed to stay in the plane of
  the block and the bowl. The sim bowl stays at a fixed spot and the cube starts at the bowl plus the offset
  measured in the clip.
- **Declared additions** (the robot is not a hand): a reach from the home pose to where the hand is first seen;
  0.3 s to settle and 0.4 s to close the gripper at the grasp, 0.4 s to open at the release; the still hold
  between grasp and lift is dropped (nothing moves, and in the sim a gripper squeezing a resting cube walks up
  it); a 60 ms smoothing across the joins; the whole demo plays 2x slower than the human; a return home.
- **Re-anchored copies.** Each accepted clip's path is replayed with the cube moved up to 3 cm / 2 cm, shifted
  onto the cube before the grasp and fading back to the human's release point. Every copy goes through the same
  robot gates; failures are dropped and counted. They are labelled in `understudy_episodes.json`.

## Measured (run of 2026-09-23)

RESULTS_PLACEHOLDER

## The site

`bin/understudy serve` runs a small FastAPI server (src/understudy/web.py) around the real pipeline, and the page in
`site/` (index.html, app.css, app.js) in the Player Two look. Type the task after "I want to train an SO-101 to";
the planner checks it live and the page shows what the next run will really cost (cached requests are free).

1. **Generate Footage**: Runway, live task status per clip (after the base frame the clips run in parallel).
2. **Generate Training Data**: MediaPipe + OpenCV tracking, the Claude scene audit, 21 gates, MuJoCo retarget and
   re-anchoring, the LeRobot v3.0 dataset; every verdict with its reason; click "gates" on a clip for all of them.
3. **Dataset**: the LeRobot v3.0 dataset of the clips that passed (counts from its own meta/info.json), a Download
   button (GET /api/runs/<slug>/dataset.zip; it loads back with `LeRobotDataset`) and the commands to train on it.
   Training happens in a terminal, not on the site (see "Train on the dataset").

Each stage runs as a child process that streams its real progress events (Server-Sent Events); nothing on the page
is simulated. Runs land in data/web-runs/<slug>/ with every stage's events in jobs/*.jsonl, and `/?run=<slug>`
reopens a saved run. Heavy stages run at nice 19 with background QoS. The old static page is in site/report/.

## Demo video

`media/understudy-demo.mp4`, built by `scripts/film.py` in the Player Two pop-up language: real plates from the
run with tool chips (top left), captions (bottom) and pop-up stat boxes, all HTML rendered to transparent PNGs by
headless Chrome and composited with ffmpeg alpha fades. No zoompan. No voice-over.

## Runway budget

Rule since 2026-09-24: spend down to a balance of 25 credits, no lower (it replaced a 350-credit cap). Every call is
in `data/runway-ledger.jsonl` with the balance before and after; `runway.py` checks the live balance (GET
/v1/organization) and submits under one lock, so parallel calls can never take the balance below the floor.
Seeds come from the sentence, so a new sentence gets new footage and a repeated one comes from the cache for free.

## Honest limits

- The MLP baseline reads joint angles and the cube position from the simulator, not pixels. SmolVLA reads the sim
  camera (320x240), the joints and the sentence; it is fine-tuned for under an hour on a laptop, so its score is far
  from converged.
- The PyBullet cross-check converts the MuJoCo scene; Bullet has no joint armature (added to link inertia) and its
  own contact model. Where the engines disagree the episode is flagged, not silently dropped.
- Depth is not measured (see above); cube x is the same in every clip.
- Grasp success in MuJoCo depends on contact settings copied from the scripted expert; it is a sim result.
- Nothing has run on a physical SO-101 yet.
- The Claude audit is a model's judgement on two stills; the pixel gates run independently of it.

## Layout

`src/understudy/` plan, runway, generate, audit, track, retarget, gates, dataset, policy, pipeline, media, cli,
plus the SO-101 scene, IK and scripted expert copied from `player-two/sim/so101` (unchanged apart from package
imports). `src/pose/extract.py` runs in `.venv-pose` (Python 3.11, mediapipe 0.10.14, rtmlib).
`vendor/so101/` is the SO-ARM100 MJCF (Apache-2.0).
