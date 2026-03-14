 # Ideas Backlog

  Rules:
  - Operator may add ideas at any time.
  - Ideas here are not approved work by default.
  - Merlin must review ideas before turning them into tasks or decisions.
  - If an idea changes architecture or stream scope, record the final outcome in `decisions.md`.

  ---

  ## Idea Template

  IDEA ID: I-001
  Date:
  Raised by: Operator
  Status: TRIAGED 

  Title:
  Local file video player (currently player.sh with very limited functionality) is upgraded to act as a video player with touch controls and file selection, sitting next to Photos on the menu card
  
  Problem:
  Inability to play choppy low quality videos on a tiny bad screen

  Idea:
  Still fairly limited in use, but expanded video player next to photo slideshow

  Notes:
  @Merlin review:
  - Good architectural fit as a future shell child app because the shell now already supports top-level app tiles and child lifecycle control.
  - Not a small add-on. This is medium/high scope because it likely needs a new app entrypoint, touch controls, file selection UI, lifecycle handling, config/docs updates, and hardware validation.
  - Main risk is hardware playback quality. A richer UI will not fix choppy playback by itself if the real bottleneck is codec choice, rendering path, storage throughput, or Pi-class hardware limits.
  - Recommended as a post-rebuild feature, not something to fold into the current migration.
  - Stronger v1 framing would be: local pre-encoded files only, simple touch controls, simple file selection, no streaming/transcoding/library complexity.
  - Before acceptance, define success criteria in hardware terms: supported codecs/containers, target resolution, and what counts as acceptable smooth playback on the real device.

 IDEA ID: I-002
  Date:
  Raised by: Operator
  Status: NEW 

  Title: Menu functionality upgrades
  

  Problem: Very limited functionality of main menu, many essential functions missing or unavailable, Poor user experience

  Idea: Keeping the 4 per page divide, introducing pages or scrollable screen (whichever less problematic with hardware limitations). Makes the design more future proof and introduces other use cases than only dashboards, ie. photo display, video playback (however shitty looking), possibly lightweight python games with touch controls

  Notes: PERFECT TIME TO IMPLEMENT WHILE REBUILDING THE WHOLE THING :)