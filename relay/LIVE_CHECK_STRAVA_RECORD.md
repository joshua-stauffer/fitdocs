# Strava live check: record

Template for [`LIVE_CHECK_STRAVA.md`](LIVE_CHECK_STRAVA.md). A session fills
it only with the codes the maintainer reports, never with Strava Data
(names, descriptions, identifiers, tokens, counts or response bodies). The
note column holds fitdocs-written text.

- Date of the check:
- fitdocs version:
- Relay version:

| Step | fitdocs code observed | fitdocs-written note |
| --- | --- | --- |
| 1. connect | | |
| 2. publish an update to one activity | | |
| 3. follow the link | | |
| 4. disconnect | | |

## Verification points (yes / no)

| Point | Answer |
| --- | --- |
| Webhook `show` printed `subscribed` | |
| Start read from `start_date` | |
| Sport read from `sport_type` | |
| Duration from `elapsed_time`, distance from `distance` | |
| Subscription route `/push_subscriptions` and field `callback_url` accepted | |
| Accepted sport-type names match the documented list | |
