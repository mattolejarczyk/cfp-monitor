# ACT-25 (b): the six sites with no usable links (2026-10-05)

Source of the list: `experiments/sitemap_discovery/RESULT.md` UPDATE 3 (four redirect aliases, two sites whose menu returned no links) and failure point B8. Each site was re-probed today with a plain HTTP request
(read-only). I tried to render the two 'script-built' sites in the dedicated Chrome as well; that failed in this session (Playwright 'Browser.new_context ... NoneType' on every call), so the two rows below are
plain-HTTP findings only and say so.

| Site | Events we hold on it | What it is today | Cause (checked 2026-10-05) | Recommendation |
|---|---|---|---|---|
| carboncapture-expo.com | Carbon Capture Technology Expo Europe 2026 (Closed) | redirects to www.hydrogen-worldexpo.com/carbon-capture-world (HTTP 200) | ALIAS: the menu and sitemap belong to another domain | follow the redirect once and use the LANDED origin for the sitemap and the same-site test |
| cloudsecurityexpo.com | Cloud & Cyber Security Expo London 2027 (Open, start 2027-03-10) | redirects to www.techshowlondon.co.uk/cloud-cyber-security (200) | ALIAS (the event lives on a multi-event site) | same; also the landed host serves several co-located shows, so scope by path |
| sustainablefuelsglobal.com | Sustainable Fuels Global Summit 2027 and SAF Europe Summit 2027 (both start 2027-04-13) | redirects to www.safeusummit.com | ALIAS; two of our rows point at the same site and start date | same; the pair is one event under two names (see ACT-47 and the Wave 1 same-site detector) |
| cloud.withgoogle.com | Google Cloud Next '26 (Closed) | redirects to cloud.google.com | ALIAS, a past edition | nothing: a past edition |
| hceeweek.com | Horizons Clean Energy Expansion Week 2026 (Upcoming, start 2026-11-24) | apex fails TLS (handshake failure); www answers 200 with a 1.26 MB Next.js page built with Cvent whose raw HTML holds 19 links: 13 to spglobal.com hosts (full agenda, speakers, sponsors, pass options, exhibitors), 1 to wh2cweek.com, 5 page fragments or relative, none to a sub-page of its own | NOT a script-built menu so much as OFF-SITE links: the same-host filter in the finder throws them away | allow a menu link to another host when the host is an organiser we already know (spglobal.com) and the link text says speakers, agenda or call |
| ushydrogenforum.com | American Hydrogen & CCUS Forum 2026 (two rows, both Closed, 2026-04-22) | HTTP 403 with a 'Checking your browser... Just a moment' challenge page on both paths tried (the root and /forum-speakers/) | ANTI-BOT WALL, not a script-built menu (this corrects the earlier note) | add to the hard anti-bot list so it is skipped without touching the network; both rows are past editions |

## Summary
- **Four are redirect aliases and one is an off-site menu; one is a bot wall.** None is 'a site with no links': each has a cause that differs and a different fix.
- The fix that matters is the alias one: `find_and_read` takes the origin from the stored address BEFORE the redirect (`sitewalk.origin(ev["home"])`), so the sitemap it collects is the alias's. Resolving the landed URL once per
  event (the render already returns it) and using that origin and host fixes three of the six and would also fix the `hosts` filter.
- Only two of the six events are live (Cloud & Cyber Security Expo London 2027, HCEE Week 2026) plus the SAF pair; the rest are past editions, so the practical gain is small. **Recommendation: do the landed-origin fix when
  next touching `find_and_read`; do not spend a wave on it.**
