---
name: tighten
description: Rewrites a draft prompt to be sharper using this repo's context (file names, components, app_config.h constants, PLAN task IDs). Returns only the improved prompt; does not run it.
disable-model-invocation: true
---

# tighten

Input: a draft prompt (the skill arguments or the text after `/tighten`). Output: a better version of it. **Never execute the prompt.**

## Steps

1. Read `CLAUDE.md`, `docs/CONTEXT.md` and `docs/PLAN.md`. Skim `main/app_config.h` and the relevant `components/*/include/*.h` if the draft touches them.
2. Rewrite the draft so it uses the real names:
   - file paths (`components/<name>/include/<name>.h`, `main/app_config.h`, `docs/CDIO/*.txt`, `docs/evidence/...`)
   - component names (`scan_map`, `sweep_plan`, `target_track`, `mode_fsm`, `radar_gfx`, `servo`, `hcsr04`, `joystick`, `button`, and the tasks `scan_task`, `display_task`, `input_task`)
   - `app_config.h` constants, with their PROPOSED / SIM / MEASURE status
   - PLAN task IDs (e.g. S1, B2, I5)
   If it is unclear which PLAN task the draft belongs to, ask Joe which one before rewriting. Do not guess.
3. Add the rules that apply to this draft (only the ones that are relevant):
   - Headers are the contract: implement against `components/*/include/*.h` and `main/*.h`; change a header only for a real reason and say why.
   - Ask Joe before changing anything in the decision log, the options table, the success criteria (`docs/CDIO/CONCEIVE.txt`) or the wiring.
   - Build and run host tests before handing over: `idf.py build` and `cd host_tests && make`; fix errors first.
   - Update `docs/CONTEXT.md` (tick the task in `docs/PLAN.md`, log it).
   - Simulations (outputs in `docs/evidence/sim/`): state the question, the assumptions, and what the hardware must confirm.
   - Layout rules, if code is involved: `components/` never include from `main/`; pure components use only the C standard library; only `scan_task` touches `servo`/`hcsr04`, only `input_task` touches `joystick`/`button`.
   - Report back: what was written, each design choice and why, what Joe must do or record next.
4. Remove redundancy and vagueness. Keep Joe's intent and scope; do not add new goals.

## Output

Show only the improved prompt, in one code block. If a task ID question is needed, ask it instead and show nothing else. No commentary, no execution.
