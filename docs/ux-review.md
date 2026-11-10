# EchoLang UX review

This is a heuristic review of the current mobile and desktop flows, grounded in the app screens and code. It is not a substitute for watching providers and customers use the product in a real locality.

## What works

- The first decision is clear: find help or offer a service. The language picker shows all ten options in their own scripts, and the choice changes both UI and speech language.
- The search flow reads back and confirms the request before showing entries. Listing creation separates collection from public review and publication.
- Large microphone and call controls suit touch use. A text path exists when microphone access is unavailable, including on a phone using a LAN HTTP address.

## Friction found and addressed

| Finding | Why it matters | Change |
| --- | --- | --- |
| The large microphone remained above results and listing review. | People had to scroll past the input they had already used to reach the outcome. | The microphone becomes a compact follow-up control after confirmation, results, and listing review. |
| Text entry sat below results and long listing details. | The answer field was far from the question; on LAN HTTP, typing is the only usable input. | The field now appears near the current prompt, before results or review details. |
| Search results and listing review repeated the last transcript or result instruction. | Repetition used mobile space without helping the next decision. | Redundant transcript/result text is hidden in those outcome states. |
| An empty search had only a quiet reset action. | The recovery step was hard to spot. | New search becomes a prominent action when no entries match. |
| Correcting a draft listing required a spoken or typed command. | It was unclear how to target a specific public detail. | Every review field now has a Change action that opens the matching question directly. |
| Input controls could appear usable while the reasoning service was unavailable. | A person could type an answer that the backend could not process. | Text submission is disabled until that service is configured. |
| Operator queues looked empty before they had been loaded, and actions silently removed items. | An operator could mistake missing data for a clear queue or wonder whether an action succeeded. | The unloaded and empty states are distinct, and review actions show a status message. |

## Choices and limits to validate with users

- The four-second intro plays on every reload without a Skip control, as requested. That adds time before the task begins. Observe whether returning users become impatient; reconsider the rule if they do.
- The listing owner token lives in one browser. Test whether providers can return to the same device and understand recovery if they lose it.
- The operator can review entries and reports, but the app does not automatically verify phone ownership, job quality, or completed work. Results should not be described as verified providers.
- The text fallback is useful for access and reliability, but the product promise depends on successful voice tasks. Test with the actual languages, accents, code mixing, phones, and network conditions of the pilot area.

## Next usability session

Start with one area and a few service categories. Ask providers to create, correct, pause, and recover a listing; ask customers to search, judge a result, and initiate a call. Observe where they hesitate, whether they can complete each task without help or typing, and whether the details read back match what they intended. See [pilot priorities](pilot-research-and-measures.md) for the measurement plan.
