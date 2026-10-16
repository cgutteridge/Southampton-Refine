---
name: human-confirm-fix
description: After applying a fix to an issue the user reported, ask whether they want to check it, then take them to the spot in Minecraft. Also usable before a fix, rarely, with a good reason.
---

A **quick** human check that saves the user time. Debugging only: the user reported an issue and a fix is applied. Skip it in unattended or first-time builds; the user is not there. Before a fix, use it only when you can name the reason the user's eyes are needed (the report is unclear in a way chat can't resolve); the steps are the same, with the question asking what they see.

## 1. Ask first
Send one line naming the fix and the place in plain words, e.g. "Fixed the roof at the badger building, want to check?" or "Fixed the tree issues near Bluebell Road, want to check?". Rough is fine; the user can ask for clarification.

Done when that line is sent. Stop and wait for the answer.

- **Later, no, or no reply:** add `FIXED <date>, awaiting user check` under the issue in `site/ISSUES.txt`, keep it `open`, and carry on.

## 2. Show it (user said yes)
1. Teleport the player (`player_list_online` for the uuid, `entity_teleport` with `facing`) to a vantage near the fix, looking at it. Take a `view_capture`.
2. Put in chat only the images that bear on the question: the capture, plus the aerial, Street View or lidar grid already listed in `site/cells/<tx>_<tz>-SOURCES.txt`. Fetch nothing new (`rules/reference-token-budget.md`).
3. Ask **one** question stating what changed and where, written so "yes" accepts your recommendation, e.g. "Dense woodland near Bluebell Road now has ~40 crowns (was 6). Right?"

Done when the question is in chat with its images. Stop and wait.

## 3. Record
- **Yes:** set the issue `done` in `site/ISSUES.txt` with the date and "user confirmed".
- **Anything else:** it is steering. Keep the issue `open`, add their words as a note, and fix again.

Only the user's "yes" closes an issue.
