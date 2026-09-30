# Understudy deck / video notes (Pranav, 2026-09-25)

Format: a slideshow (or video of it) that copies the Player Two deck almost 1:1
(~/helloworld/player-two-deck, player-two-deck.vercel.app): the same animated, code-built slide style he called
"probably the best slideshow we had". Reuse its engine, layout and pacing; change only content.

Must include, as the measures we took to make generated video trustworthy as robot training data:
1. PhyT2V-style prompt rules (Xue et al., CVPR 2025): object inventory with exact counts, positive physical rules,
   and gate rejection reasons fed back as corrective rules.
2. Two independent physics engines (MuJoCo + PyBullet) re-simulate every episode; disagreements are flagged, not hidden.
3. The 21 automatic gates (hand visible, one object, joint limits, speed, grip timing, object ends in target).
4. MimicGen-style multiplication: each accepted clip replayed with the object moved, every copy re-checked by physics.
5. Wrist camera: a second camera on the robot's gripper (recorded alongside the front camera) so the model sees the
   cube up close.
6. Training for multiple full passes over the data (the 16/50 run covered half of one pass).
Numbers only from measured artifacts (RESEARCH-PIPELINE.md, STATUS.md). No MLP comparison on screen (his call).
