# The usage panel by account: one block per login, the machines named beneath it

**Status:** a design written 2026-09-19 on the manager's dispatch from the user's screenshot of the usage panel with three machines on one account; the code rides the same pull request as its second commit. The rail's meter itself does not change.

## The ask

The user's dashboard has three machines attached, all logged into one Claude account. The usage panel (the hover over the rail's meter, and the same HTML in the phone's usage modal) drew three columns, one per machine, each carrying the same 5-hour, 7-day and per-model meters, the same login line and the same reset times. The user called it duplication: the meters are the account's allowance, so one account is one set of numbers, however many machines share it.

## The panel today, read in code

`kernel/kernel.py`'s `_LANDING_USAGE_JS` builds the panel. `/usage/fleet` answers one row per machine whose usage is known (`_fleet_usage`, local first, then the attached machines in name order). `shareFreshest` already groups the rows by the account digest and gives every member of a group the freshest member's window readings, so the columns agreed; `setHTML` then drew one column per machine (`.ru-tip-col`), the machine's name as its heading, the account line under it, the meters, and its own updated-ago line. The key spend was already one section for every machine (`fleetSpendHTML`), and the rail's aggregate bars were already one set.

## The re-cut

**One block per distinct login.** The rows with window readings group by the account digest, in the panel's order (the first machine of each account fixes the account's place). Each group is one block: the account line as its head (the login's label, when the kernel knows it), the meters written once (5 hours, 7 days, the per-model meter, each with its reset), and beneath them one line naming the machines logged into that account, in the panel's order, each name in the tab strip's quiet host dress (the `.host-prefix` declarations of `ui/webview/styles.css`, byte for byte). A machine on its own account is its own block. Two accounts are two blocks, side by side in the same flex columns the machines used to take, folding to a stack on a narrow screen as before. A machine with a key and no login has no block; its dollars stay in the spend section, which is unchanged.

**One updated-ago line per block, the oldest report of the group.** The block shows the freshest member's readings; its age line says the age of the group's oldest report, so a block never claims to be fresher than its least fresh machine.

**A lagging machine is named.** The meters are per account and should agree across the machines on it; a machine whose own snapshot lagged (its own reading differed from the freshest member's) is resolved to the freshest, as before, and named as lagging beside its name in the machines line, with its own report's age. Nothing else in the block changes for it.

**A machine not reporting is named, never a column.** `/usage/fleet` carries `noReport`: the machines attached and up with no usage report yet (`_usage_no_report`, read from the poll's cache like the rows). The panel names them in one line after the blocks. Their account is unknown, so they belong to no block.

**The single-machine case is unchanged.** The machines line appears only when the mesh has more than one machine (rows and unreported machines together); one machine on one account reads as it did.

## Privacy

The panel names machines by the names the user gave their rows and logins by the label the kernel already served; nothing new travels. The lab, the body and the commits use `TESTHOST` names and a synthetic login label; the user's screenshot's names stay out of the repository.

## Tests

- Source pins (`ui/webview/rail-spend.test.ts`, `tests/test_usage_per_account.py`): the block builder, the grouping by digest in the panel's order, the machines line with the lagging note, the oldest-report age line, the not-reporting line, the strip's host dress byte for byte, the per-host column and heading gone; the route's `noReport`.
- A served lab (`tests/test_usage_by_account_served.py`): the landing page from a hermetic kernel module with a fake `/usage/fleet`; two machines on one account render one block with two names and one set of meters; a third machine on another account a second block beside it; a machine that lags is named lagging with its age; a machine not reporting is named with its state; the rail's aggregate bars are unchanged. Red first at main for each, executed.

## Tier

Feature, unarmed: the panel's shape changes; the route's one new key is additive.
