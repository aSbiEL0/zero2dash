You are an autonomous coding agent working inside the zero2dash repository with permission to inspect files, edit code, execute commands, run tests, deploy locally, and debug iteratively.

Your task is to implement a GBP/PLN currency display feature by following the same architecture and conventions used by other existing modules in this repo.

Core implementation shape:
- A rate-checking script should fetch the latest GBP to PLN exchange rate from the NBP API.
- That script should generate the image file:
  ~/zero2dash/images/current-currency.png
- The background image source is:
  ~/zero2dash/images/currency-bkg.png
- The display module is:
  ~/zero2dash/scripts/currency.py
- currency.py should only display the generated image during normal operation.

Required display content:
- today’s date in DD/MM/YYYY format
- the label: 1 GBP =
- the current GBP to PLN rate
- exactly 2 decimal places
- the suffix: zł
- styling close to the provided mock-up

Visual requirements:
- full background image
- large high-contrast overlaid text
- main rate value is the dominant visual element
- preserve original image resolution where possible
- if display-time scaling is needed, shrink for display rather than pre-degrading the source asset
- no interactivity, no controls, no touch behaviour

Mock-up fidelity requirements:
- Use the supplied mockup as the primary visual reference.
- Match the composition closely:
  - date at the upper left area
  - `1 GBP =` on the same top row toward the right
  - the exchange value as the dominant central text
  - `zł` on the same main value line
  - `source: api.nbp.pl` centered near the bottom
- Preserve the simple signage look.
- Use large bold white text with strong readability over the background image.
- Do not add charts, icons, controls, menus, or extra labels.
- Keep the layout visually close to the mockup even if exact pixel matching is not practical within repo conventions.

Operating model:
You are not only writing code. You must complete the full implementation loop:
1. inspect the repository
2. identify the equivalent existing module pattern
3. identify how similar modules fetch, generate images, and display them
4. identify how display selector invokes scripts
5. implement the feature using existing repo conventions
6. run relevant local commands and tests
7. deploy locally / run through the repo’s normal local execution flow
8. test again
9. debug iteratively until working or until you hit a real blocker
10. report blockers precisely with evidence

Repository-first instructions:
Before editing anything, inspect:
- AGENTS.md and repo instructions
- README and setup/run docs
- scripts/ and display selector code
- existing modules similar to fetch + generate + display
- any image generation utilities
- any font/text rendering helpers
- any caching / polling / change-detection patterns
- test conventions
- local deployment/run scripts and commands

Functional requirements:
- GBP/PLN only
- use the NBP API
- always show today’s date
- show the current rate for today when available
- scheduled update time is every morning at 06:00
- follow existing repo/module patterns rather than inventing a new architecture

Update logic requirements:
Regenerate or refresh only when needed. Treat the display as needing amendment if any of these are true:
- generated image is missing
- date changed
- rate changed by more than 0.01

Use the simplest compatible persistence/change-detection mechanism already used elsewhere in the repo. If none exists, add the smallest reasonable mechanism and explain it.

Display/runtime behaviour:
- currency.py should only display the generated image during normal operation
- if the generated image does not exist, currency.py should trigger the rate-checker
- then wait 30 seconds
- then retry displaying the image once
- if the image is still unavailable after that retry, exit/fail gracefully and do nothing until the next scheduled update time
- do not create a loop that hammers the API or repeatedly retries forever

Data freshness and fallback rules:
- if today’s rate is available, use it
- if today’s rate is not available, use the last available rate only if it is no older than 24 hours
- otherwise generate/display an update error message until the next scheduled update time
- temporary API failure must not crash the display loop or selector
- preserve the last known good image/data if that is the least risky repo-compatible fallback

Scheduling expectations:
- updates should run every morning at 06:00
- inspect the repo to determine whether this should be implemented via an existing scheduler, cron integration, timer mechanism, or deployment script
- prefer the repo’s existing scheduling/deployment conventions over inventing a new scheduler

Naming and file-layout rule:
- The user suggested a rate-catcher/rate-checker script pattern.
- Inspect the repo first and follow its naming/location conventions if similar modules already establish a pattern.
- If the exact filename should differ for consistency, choose the repo-consistent name and explain why.
- Do not force a bad filename just because it was mentioned informally.

Compatibility constraints:
- prioritise compatibility with the rest of the product as much as output quality
- preserve existing behaviour unless a change is strictly required for this feature
- avoid unrelated refactors
- keep dependencies minimal
- do not add new dependencies unless clearly justified and consistent with existing repo patterns

Testing and execution requirements:
- add or update focused tests in the existing repo style
- mock the NBP API in automated tests where appropriate
- run relevant local tests yourself
- run the feature locally through the repo’s normal workflow
- perform any local setup/deploy step the repo expects
- rerun after setup/deploy
- debug using real command output, logs, and generated files

Definition of done:
- a working GBP/PLN currency feature exists following existing repo patterns
- the fetch/generate/display flow is implemented
- ~/zero2dash/scripts/currency.py displays ~/zero2dash/images/current-currency.png
- missing-image fallback behaves as specified
- update detection behaves as specified
- scheduled update path for 06:00 is implemented in the repo-compatible way
- date format is DD/MM/YYYY
- rate is displayed to 2 decimal places
- stale fallback and error behaviour follow the specified 24-hour rule
- relevant tests pass
- the feature has been run locally through the repo’s normal workflow
- any unresolved blocker is documented with exact evidence

Output format:
Return these sections only:

1. Repo Findings
- files and module patterns inspected
- existing similar modules found
- chosen integration path
- chosen NBP endpoint and reason
- chosen update-detection strategy and reason
- chosen scheduling integration point and reason

2. Implementation Plan
- minimal set of changes to make

3. Commands Run
- important commands executed
- why each was run
- key result

4. Changes Made
- for each changed file:
  - path
  - reason
  - concise summary

5. Validation
- tests added or updated
- local test results
- local runtime/deployment validation
- whether the feature was exercised end-to-end

6. Debugging Notes
- issues encountered
- how they were investigated
- what was fixed

7. Remaining Risks or Blockers
- only real unresolved items with evidence

Behavioural rules:
- inspect before editing
- follow repo conventions over generic preferences
- prefer minimal targeted changes
- do not invent architecture the repo does not already support unless required
- do not fabricate commands or file paths
- surface uncertainty explicitly
- avoid unrelated refactors