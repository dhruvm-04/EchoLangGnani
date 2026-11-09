# Pilot priorities and evidence

This project is a local, voice-first services directory. Keep the first pilot to one city or compact area and a few service categories. Recruit providers directly with their consent; do not scrape phone numbers or import unapproved listings. The directory remains in SQLite. Gnani and the configured reasoning service still process spoken requests.

## Why these changes

- Research with novice and low-literacy mobile users found that text interfaces caused major task barriers, while speech helped some users and human assistance remained valuable. A later study of emergent smartphone users in India found code-mixed voice use and reliance on family or other intermediaries. This supports spoken onboarding, a replayable readback, and an operator recovery path. Sources: [Microsoft Research, Designing Mobile Interfaces](https://www.microsoft.com/en-us/research/publication/designing-mobile-interfaces-for-novice-and-low-literacy-users/), [Microsoft Research, Sophistication with Limitation](https://www.microsoft.com/en-us/research/publication/sophistication-with-limitation-understanding-smartphone-usage-by-emergent-users-in-india/).
- W3C WCAG 2.2 recommends adequate touch targets and input assistance. This supports large controls, visible correction paths, and explicit confirmation before public posting. Source: [WCAG 2.2](https://www.w3.org/TR/WCAG22/).
- The Digital Personal Data Protection Act, 2023 describes consent and withdrawal. The product now states what becomes public and lets the listing owner pause or delete an entry. The actual legal obligations and commencement status should be reviewed before a public launch. Source: [India Code, DPDP Act](https://www.indiacode.nic.in/indiacode/handle/123456789/22037?view_type=browse).

## What to measure in the pilot

The operator page counts starts, published submissions, searches with and without results, call taps, and reports over 30 days. These are directional product signals, not unique people or completed jobs. Track manually, with participants' permission:

1. Whether a provider can create, correct, pause, and delete a listing without typing.
2. Whether a customer can find a suitable provider and place a call without typing.
3. Whether a callback confirms the provider's number and service area.
4. Whether a reported or stale listing is resolved promptly.
5. Which spoken words, accents, code-mixed phrases, and place names repeatedly fail; retain recordings only with explicit study consent.

Use a small real-world session with providers and customers in the intended locality. Include participants with different languages, literacy levels, and phone familiarity. Record task success and observed friction, then fix the largest observed failure before adding external platforms.

## Current boundaries

Phone ownership is checked manually by an operator; no OTP or automated verification exists. A browser token controls the listing on its device, and an operator can rotate it after a callback. A recovery link is a bearer credential. The local database needs scheduled backups and a tested restore process. The app has no transactional booking, payment, reputation system, or proof that a job was completed.
