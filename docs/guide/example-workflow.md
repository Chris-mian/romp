# A worked example: an MNIST classifier across four agents

This walks through running a real project as a fleet: training a small MNIST
classifier, split across four agents that hand work off to each other. It is
both a tour of romp's main features and a script you can follow to record a
demo.

The one principle that makes it work: **give each agent one piece, and tell it
who to hand off to.** A single agent handed the whole task just does everything
itself, and there is nothing to coordinate. Four narrowly-scoped sessions, each
told to message the next, produce the real handoffs, the waiting, and the one
decision that only you can make.

## The fleet

Launch four sessions from the dashboard (type a name, choose New session):

- **`data`** — download MNIST, make a clean split, save it, hand the path to `trainer`.
- **`trainer`** — train a small model on that split (this is the long-running step).
- **`reviewer`** — check the split for leakage and re-verify the reported accuracy.
- **`report`** — gather everyone's results into a short `REPORT.md`.

The work runs `data → trainer → reviewer → report`, with a review back-channel
(`reviewer → trainer`) and one question for you (`trainer → you`).

## The prompts

Paste one prompt per session. The handoff instructions are what create the
coordination, so keep them.

**`data`**

> Download MNIST (torchvision or keras), make a clean train/val/test split, and
> save it to `data/mnist.npz`. Put a `load()` in `data.py`, and save a 5x5
> sample grid to `figures/samples.png`. When the split is ready, message the
> `trainer` session (kind: delegate) with the exact path and the split sizes.
> Do not train anything yourself.

**`trainer`**

> Wait for a message from `data` with the dataset path. Before training, ask me
> whether to run a quick baseline or a longer run. Then train a small CNN in the
> background, keeping the model small enough that training takes about a minute.
> Save the training curve to `figures/curve.png`. When it finishes, message the
> `reviewer` session (kind: question) with the test accuracy and the model path,
> and ask them to sanity-check it.

**`reviewer`**

> Wait for `data` and `trainer`. Review `data.py`'s split for any train/test
> leakage, and independently re-compute the test accuracy `trainer` reported. If
> anything looks off, message `trainer` (kind: coordinate). Then message the
> `report` session (kind: delegate) with your sign-off: the verified accuracy
> and any caveats. Review only; do not change the code.

**`report`**

> Wait for messages from `data`, `trainer`, and `reviewer`. Then write
> `REPORT.md`: the task, the split, the model, the verified test accuracy, and
> embed `figures/samples.png` and `figures/curve.png`. Keep it under a page.

## Walking it through

Each step is one thing you do, and the feature it shows.

1. **Launch `data`, then `trainer`, `reviewer`, `report`.** The fleet fills in,
   each agent colored, with a live status. (The fleet at a glance.)
2. **Open the feed.** A task card appears per session, each with a plain-language
   summary and a collapsible background. (Tasks, not transcripts.)
3. **Reply to a card by clicking its summary.** Clicking the summary line drops a
   context chip into the composer; type a follow-up from there. (Reply without
   hunting for the thread.)
4. **`data` hands off to `trainer`.** MNIST downloads in seconds, so the beat
   here is the message, not a wait: `data` sends the path and split sizes, and
   the handoff shows on the card. (The Postal Service.)
5. **Hover the timeline.** Hover a work bar to see what a session did, and a line
   between two lanes to see who told whom what. (Where sessions interact.)
6. **Answer `trainer`'s question.** Before the long run it asks baseline-or-longer;
   it surfaces as needs-you, and you answer in chat. (Interrupt only when you are
   the bottleneck.)
7. **`trainer` trains in the background.** It goes idle while the run proceeds, so
   its card shows a "Waiting on task" pill and its timeline lane shows a faded
   bar. (The fleet stays busy without you watching it.)
8. **`reviewer` pushes back, then signs off.** If it finds a discrepancy it
   messages `trainer`; otherwise it hands its verified result to `report`. (A
   real back-and-forth, tracked.)
9. **`report` gathers from all three and writes `REPORT.md`.** Open its card to
   see the produced artifacts (the sample grid, the training curve). (The payoff:
   completed cards with their outputs.)

## Tuning the timing

The training run is the one step whose length you control, and it is where the
"waiting on a background task" card shows. Aim for **about 60 to 120 seconds**:
long enough for that state to be visible, short enough not to drag. Knobs, from
fastest to slowest: shrink the training set to 10–20k images, use a small CNN,
and set 3–5 epochs on CPU. If a run finishes too fast to see the awaiting card,
add epochs or drop the subsampling.

## Recording this as a demo

Record the whole session in one take, then chop it into short clips (one action
each, a few seconds apart) for the parts above. Keep the fleet to these four
sessions so the feed, fleet, and timeline all fit on screen without scrolling.
Do a dry run first to settle the session names and the training time, then
record the real take clean.
