# Strava live check (optional, maintainer's)

## 1. This writes to a real account

This procedure writes to a real Strava account: the account that grants
consent in step 1, for the Strava application it is carried out against.
Connecting grants the relay access to that account, publishing changes one
real activity's title and description (or, if the activity is missing on
Strava and uploads are enabled, uploads a new one), and disconnecting revokes
the grant. Use an application and an account whose activities may be edited,
pick one activity that may be edited, and expect the change to stay on Strava
after the check.

It is optional. It is for the maintainer to carry out, against the
maintainer's own Strava application and account and a relay connected to that
application. It is never run by the test suite or by CI, and no
implementation, review or validation session carries out any of its steps.

What is recorded afterwards is fitdocs codes and yes/no answers only, in
[`LIVE_CHECK_STRAVA_RECORD.md`](LIVE_CHECK_STRAVA_RECORD.md). Nothing Strava
returned (names, descriptions, identifiers, tokens, counts, response bodies)
is copied into the record, a commit, a queue item or a session.

## 2. Before starting

- A relay with the Strava target enabled: `FITDOCS_RELAY_STRAVA_CLIENT_ID`
  set to the application's client id, together with every variable the
  relay requires "with Strava" (the client secret, the webhook token, the
  public address, the encryption keys, the operator name and the support
  contact). `FITDOCS_RELAY_PUBLIC_URL` is the relay's public address, and the
  relay instance in the fitdocs install uses that same address as its url.
- The relay's link setting, `FITDOCS_RELAY_STRAVA_LINKS`, decides what the
  page links to. This check runs under the default, `activity`: the link is
  the activity's own page address on Strava. Under `relay` the link is the
  relay's `/go/<publication id>` address instead, and a loopback `http`
  relay set to `relay` yields no link at all (the row reports the link as
  refused and the page carries no "View on Strava" link). Steps 2 and 3
  below are written for `activity`; to cover `relay` as well, repeat them
  with that setting and record the differences as printed.
- The relay serving, and its webhook subscription created and confirmed:
  run `fitdocs-relay strava webhook create` (it prints `subscribed` or
  `already subscribed`), then `fitdocs-relay strava webhook show`, which
  prints `subscribed`. Record that `show` answer; `subscribed elsewhere` or
  `not subscribed` is a finding.
- A fitdocs install with a Strava connector instance bound to a relay
  instance (`<name>` below is the Strava instance's name). The relay instance
  must hold a relay token; otherwise connect prints "the relay instance X has
  no stored token." and exits 1.
- One workout page with a `post` region, opted in to the Strava target, whose
  activity exists on Strava and may be edited.
- A terminal where each command's exit code is visible.

## 3. The four steps

For each step, note the exit code and the code or codes printed, then write
them into the record template. The observations below say what to look for;
anything different is a finding to record as the printed code.

### Step 1: connect

1. Run `fitdocs connect <name>`.
2. Observe:
   - a consent address is printed, then `Code: <code>. Continue only if the
     page shows this same code.`, and a browser opens unless `--no-browser`
     was given; the printed code is the one the consent page shows;
   - after consent is granted, the command prints `<name>: connected.`,
     `Credentials: <path>` and `Relay: <url>`, and ends with exit code 0;
   - a refusal or an expiry prints `<name>: <code>: ...` (for example
     `connect-refused` or `connect-expired`) and ends with exit code 1: a
     finding, not a pass;
   - no token or poll secret is printed.
3. Run `fitdocs publish --targets`: the instance's line shows
   `state: ready`.

### Step 2: publish an update to one activity

1. Run `fitdocs publish <page> --to <name>` without `--yes`: the outcome
   is `would_post` for a page never published, otherwise `would_update`;
   nothing is sent.
2. Run `fitdocs publish <page> --to <name> --yes`.
3. Observe:
   - the fitdocs outcome is `posted` (or `uploaded`, only when the activity
     was missing and uploads are enabled); exit code 0;
   - the page's `published` region now holds the link (the activity's page
     address on Strava), and the page itself is otherwise unchanged;
   - repeating the `--yes` run ends `unchanged`;
   - other outcomes are findings, recorded as printed: `not_found`,
     `ambiguous`, `not_updatable`, `auth_rejected`, `permission_denied`,
     `rate_limited`, `unavailable`, `rejected`, `unconfirmed`,
     `target_error`.

### Step 3: follow the link

1. Open the link in the page's `published` region (labelled "View on
   Strava").
2. Observe, answering yes or no only:
   - the link opens the activity that was updated;
   - the title and description on Strava are the ones the page sent.

### Step 4: disconnect

1. Run `fitdocs disconnect <name>`.
2. Observe:
   - the command prints `<name>: disconnected.`, `Credentials removed:
     <path>` and `Relay code: ok`, and ends with exit code 0;
   - a relay code of `token-unknown` or `token-revoked`, with a `Note:`
     line, means the relay had already forgotten the token: expected, not a
     finding;
   - `<name>: <code>: ...` with exit code 1 is a finding (the credentials
     are kept);
   - `fitdocs publish --targets` now shows the instance with
     `state: not_connected`.
3. Revoke the application's access from the Strava account's own settings if
   the grant should not remain.

## 4. Verification points on Strava's side

Record each as yes or no (or the fitdocs code), never as Strava's text:

- The activity's start was matched on the field the adapter reads
  (`start_date`, the UTC instant, not `start_date_local`): yes/no.
- The activity's sport was read from `sport_type` (not the older `type`):
  yes/no.
- Duration was read from `elapsed_time` and distance from `distance`: yes/no.
- The subscription route is `/push_subscriptions`, and the `callback_url`
  field is the one Strava accepts for a subscription: yes/no.
- The sport-type names the adapter accepts match the list Strava documents
  for `sport_type`: yes/no (and, if no, the fitdocs code that surfaced it).

## 5. Afterwards

Fill [`LIVE_CHECK_STRAVA_RECORD.md`](LIVE_CHECK_STRAVA_RECORD.md) with the
codes observed. A finding becomes a queue item that names the code and the
step, never Strava's text.
