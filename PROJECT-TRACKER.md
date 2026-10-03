# Project tracker

Last updated: September 29, 2026

## Current status

- Matthew’s September 18 “Updates” email and “Speaker’s Toolkit” materials are implemented in `site-mockup/site/` on PR #1. The earlier September 18 call changes and approved blue-suit hero are preserved.
- Applied supplied quote and method wording, NexPhrase, Inc. footer, REFRAME logo, October/November speaking events, named upcoming podcasts, and book-announcement signup wording.
- Speaker’s Toolkit provides the original supplied bio and speaker-introduction DOCX files and four original headshots. Lightweight thumbnails are used on the page.
- Deployed and verified at https://wysn-matthew-preview.vercel.app. Existing preview password screen and noindex behavior are preserved. The client-side password screen is not server-side authentication; only material intended for the site is included.
- Vercel project: `wysn-matthew-preview`, deployment `dpl_GejKkwP9qjueYA74YYnZ3GLWdSvZ`. This updates the preview project only.
- WhatYouSayNext.com is confirmed by Matthew’s July 15 email. Its existing GoDaddy site remains unchanged. No DNS changes or GitHub merge performed.

## Verification

- Desktop, 390px mobile, and 768px tablet rendering checked; no horizontal overflow. Mobile navigation opens and closes after selecting a section.
- Local asset paths and anchors resolve. Toolkit thumbnails render.
- All six deployed toolkit downloads return HTTP 200 and match the local originals by SHA-256. Deployed HTML matches the staged preview.
- Mailchimp hosted form loads for the supplied audience; no test subscription submitted.
- Supplied Calendly URL returns 404 in HTTP and browser checks. Contact currently uses Matthew’s supplied email.

## Waiting on Matthew

1. Fresh GoDaddy delegate access covering DNS for WhatYouSayNext.com. The August 5 website-collaboration invitation was found, but Matthew’s domain/account is absent from Antonio’s current delegated account list.
2. Working public Calendly booking URL. The previously supplied `/nexphrase-info/30min` link is unavailable.
3. Live HaltingWinter and Lead Well episode URLs when available; these remain labeled coming soon.

Antonio authorized the access request. Email “What You Say Next: domain access for launch” was sent September 29 to Matthew, verified in Gmail SENT (`1a0eea9cc7bcf041`). It includes the preview link and asks for DNS access and the current booking URL. No passwords requested.

## Next actions and release boundary

- Antonio chose “Finish the preview; I’ll get DNS access.” Preview work is complete.
- Once access arrives, verify the exact domain/DNS authority and preserve existing mail records before preparing the custom-domain connection.
- Keep PR #1 open for review. Confirm readiness under the existing quiet-launch constraints before connecting the public domain.
- Community/subscription work remains outside Phase 1. No ebook download was added without a canonical client-selected file.

## Durable source map

- `README.md`: current status and historical client context.
- `SOURCE-OF-TRUTH.md`: handling and authority rules.
- `site-mockup/site/`: static implementation and intended site downloads.
- Google Drive: source assets. Private legal records, raw emails, credentials, and unrelated files must not be deployed or committed.
