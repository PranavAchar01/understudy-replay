"""One pipeline stage as a child process of the web server. Prints every progress event as a line
`@@EV {json}` on stdout; anything else it prints is a plain log line. The server relays both to the page.

  python -m understudy.webjob footage '{"task": "...", "run_dir": "...", "clips": 5}'
  python -m understudy.webjob data    '{"task": "...", "run_dir": "..."}'
  python -m understudy.webjob vla     '{"run_dir": "...", "ckpt": "...", "clips": ["v08"]}'
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path

_OUT = threading.Lock()


def emit(ev: dict) -> None:
    ev = {"ts": round(time.time(), 3), **ev}
    with _OUT:
        sys.stdout.write("@@EV " + json.dumps(ev, default=float) + "\n")
        sys.stdout.flush()


def log(msg: str) -> None:
    with _OUT:
        print(msg, flush=True)


def main() -> None:
    stage, args = sys.argv[1], json.loads(sys.argv[2])
    from . import stages
    from .plan import parse_task

    run_dir = Path(args["run_dir"])
    emit({"type": "job_start", "stage": stage})
    t0 = time.time()
    try:
        if stage == "footage":
            task = parse_task(args["task"])
            fixes = None
            if args.get("refine"):  # PhyT2V Step 3: the last take's rejections rewrite the prompts
                from .plan import refine_fixes

                verdicts = json.loads((run_dir / "data.json").read_text())["clips"]
                fixes = refine_fixes(verdicts, task)
            recs = stages.footage(
                task, run_dir, int(args["clips"]), emit=emit, fixes=fixes, start=int(args.get("start", 0))
            )
            from . import runway

            emit(
                {
                    "type": "footage_done",
                    "clips": [r["clip_id"] for r in recs],
                    "balance": runway.balance(),
                }
            )
        elif stage == "data":
            stages.training_data(
                parse_task(args["task"]),
                run_dir,
                reanchor_n=int(args.get("reanchor", 15)),
                emit=emit,
                log=log,
            )
        elif stage == "vla":  # the fine-tuned SmolVLA runs each scenario in MuJoCo, filmed for the tiles
            from . import vla_tiles

            vla_tiles.web_stage(run_dir, args, emit=emit, log=log)
        else:
            raise ValueError(f"unknown stage {stage}")
    except Exception as e:  # reported to the page, then the job exits non-zero
        log(traceback.format_exc())
        emit({"type": "error", "message": f"{type(e).__name__}: {e}"})
        emit(
            {
                "type": "job_end",
                "stage": stage,
                "ok": False,
                "seconds": round(time.time() - t0, 1),
            }
        )
        sys.exit(1)
    emit(
        {
            "type": "job_end",
            "stage": stage,
            "ok": True,
            "seconds": round(time.time() - t0, 1),
        }
    )


if __name__ == "__main__":
    main()
