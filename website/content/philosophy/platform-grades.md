---
title: Platform grades
description: How 18 fitness platforms grade on programmatic access to your own data and on what their terms let you do with it, as of October 2026.
section: Why
order: 2
---

# Platform grades

This page grades 18 fitness platforms, as of 2026-10-18, on two questions: can you write a program that pulls your own data out, and once it's out, what do the platform's terms let you do with it? Terms change, often without notice, so every entry links the documents it rests on, with their dates. Claims from secondary sources are marked as reported, and none of this is legal advice.

## The two criteria

### Access

Can you, as one person, write a program that pulls your own data out of the platform's service, by a route the platform sanctions?

| Grade | What it means |
|---|---|
| A | Self-serve and complete. Any account holder can get their own credentials at no extra cost and pull full-fidelity data: original activity files or full per-second streams. |
| B | Self-serve, with a real catch: a paid subscription, short history, credentials that expire often, or streams but no original files. |
| C | A narrow path. Summaries only, approval required, a vendor-run channel of limited or unknown fidelity, or on-device access through an app you build and sign yourself as a test build. |
| D | No sanctioned personal path. The official API is for businesses or professionals only. |
| F | Closed. No sanctioned personal path, and the terms ban scripting your own account or the platform actively blocks it. |

### Freedom

Once your data is out by that route, what do the platform's terms let you do with it? This grades the terms on the sanctioned programmatic route or, where there isn't one, the terms on data that leaves by the routes the platform allows: partner apps, exports and consumer terms.

| Grade | What it means |
|---|---|
| A | No strings beyond the law. Keep it, analyze it, share it, give it to any AI. |
| B | Light obligations: attribution, security, deletion when access is revoked, no resale, no competing service. Storage and AI use stay open. |
| C | Purpose and consent limits. Use only for stated purposes or features you can see, transfers or AI sharing only with disclosure and consent, or a banned storage location. |
| D | Core uses restricted. Storing some of the data is banned, deletion is due on short notice, or AI training is banned. |
| F | No personal LLM archive. The terms forbid putting the data into an AI model at all (prompts and context, not only training), or forbid keeping any lasting copy, or both. |

### What isn't graded

- **Manual export, for Access.** Every platform here offers some manual way to copy your own data, but a download button isn't a program, so it earns no Access credit. Its terms count toward Freedom only where a platform has no programmatic route, and they're almost never restrictive. The exceptions are consumer terms that reach "Content": Peloton's includes your "User Content", Oura's reserves the "data" in its Content to Oura, and WHOOP's licenses "data, analyses, reports" "solely for your personal use".
- **Files you copy off your own device**, over USB or out of an app's folder.
- **Legal rights** such as GDPR portability or the EU Data Act, which are requests, not a sync.
- **Rate limits.** Strict ones don't lower the Access grade, as long as a personal sync can work.

### How the ranking works

Grades score A = 4, B = 3, C = 2, D = 1, F = 0, and platforms rank by the sum. Ties go to the better Access grade, then alphabetical order. The two count equally because each is weak alone: data you can't get out is hard to use, and data you can get out but may not keep or analyze isn't really yours.

## The grades

| Rank | Platform | Access | Freedom | In one line |
|---|---|---|---|---|
| 1 | COROS | A | A | Free official MCP serves original FIT; consumer terms only. |
| 2 | Hammerhead (SRAM) | A | A | Self-serve API with FIT; the license is silent on your data. |
| 3 | Intervals.icu | A | A | Free personal key, original files, "any lawful purpose". |
| 4 | Polar | B | B | Free API with original FIT, last 30 days only. |
| 5 | Google (Fitbit / Google Health API) | B | C | Personal-use API, no FIT; use tied to visible features. |
| 6 | Samsung Health | C | B | Test-mode SDK on the phone; few rules on the data. |
| 7 | Suunto | C | B | No personal Cloud API; new MCP of unknown fidelity. |
| 8 | Apple Health | C | C | Your own on-device app; consent for third-party AI. |
| 9 | Stryd | F | A | No API, scraping banned; your exports are yours. |
| 10 | TrainingPeaks | F | A | No personal API; you keep all rights in your files. |
| 11 | Zwift | F | A | No API, bots banned; your FIT files are yours. |
| 12 | Oura | B | F | Membership required; no prompting AI with API data. |
| 13 | Strava | B | F | Subscription, streams only; no AI, no archive. |
| 14 | Garmin | F | B | Business-only and paused; attribution on partner data. |
| 15 | Wahoo | C | F | API by request; no storing user information from it. |
| 16 | WHOOP | C | F | Summaries only; no AI systems, no permanent copies. |
| 17 | Withings | D | F | Professionals only; no prompting AI with API data. |
| 18 | Peloton | F | F | No API; terms reach your own data and bar storing it. |

## Platform by platform

### 1. COROS

**Access: A · Freedom: A**

**Access.** COROS's official MCP server, launched 2026-05-05, is free for any account, from an AI client or your own OAuth app: "No application or approval required." It returns original FIT files "including GPS and second-by-second data", up to 50 files per 24 hours.

**Freedom.** Only the consumer Terms of Service and Privacy Policy govern the MCP, and neither limits AI use, retention or display of your data. COROS says "athletes should own their own data". Its stricter partner agreement binds companies, not you. Unexplained: the terms bar copying "account information for the benefit of a third party".

Terms: [Terms of Service](https://coros.com/terms), last updated 2023-04-23; [COROS-MCP README](https://github.com/coroslab/COROS-MCP), undated; [partner API agreement](https://www.dropbox.com/scl/fi/pqrgalut8k63gr8aslp3i/COROS-API-Agreement.pdf?rlkey=h8qlr5dmokd2f8orfjchey8xk&dl=0), an undated template (PDF created 2026-04-04).

### 2. Hammerhead (SRAM)

**Access: A · Freedom: A**

**Access.** Since 2025-11-21 Hammerhead has documented self-serve developer accounts: accept the API license on the Dashboard and you get OAuth credentials. The API returns each activity's FIT file, free, with no documented limits. The license still says to request a key "by emailing", and whether SRAM reviews new accounts isn't stated.

**Freedom.** The API License Agreement says nothing about user data: no rules on AI, storage, display or deletion. Its limits are on the API: "internal business purposes", no reverse engineering, and no apps that "replicate or attempt to replace the user experience" of the Karoo.

Terms: [API License Agreement](https://support.hammerhead.io/hc/en-us/articles/42738760915099-API-Licence-Document), last modified 2025-05-22; [Creating a Developer Account](https://support.hammerhead.io/hc/en-us/articles/43558376710683-Creating-a-Developer-Account), 2025-11-21; [Terms of Use](https://support.hammerhead.io/hc/en-us/articles/115006125208), undated (last edited 2020-08-19).

### 3. Intervals.icu

**Access: A · Freedom: A**

**Access.** Every account, free or paid, gets a personal API key. It pulls each activity's original file, full streams and wellness data, with no documented history window. Two gaps come from upstream: Strava-sourced activities come back as empty stubs, by Strava's rule, and the developer says Garmin has filtered the FIT files it sends since about March 2026.

**Freedom.** The API terms allow use "for any lawful purpose, including commercial use", and let you "distribute, and sublicense outputs derived from the API without restriction or attribution". There's no AI clause. The one string is Garmin's, passed through: credit Garmin when you display data derived from it. On 2026-10-09 the developer warned Garmin data might be blocked, then wrote on 2026-10-14 that the requirements "are not new".

Terms: [API Terms and Conditions](https://forum.intervals.icu/t/intervals-icu-api-terms-and-conditions/114087), effective 2025-10-23; [Privacy Policy](https://www.intervals.icu/privacy-policy/), effective 2025-12-11.

### 4. Polar

**Access: B · Freedom: B**

**Access.** Any Polar Flow user can register a free AccessLink client. It returns original FIT, TCX and GPX files with per-second samples. The catch: you only see exercises uploaded in the last 30 days, and only those uploaded after you registered the client. Your back catalog has to come from Polar's account export.

**Freedom.** There's no AI clause and no storage cap. You must "credit Polar Ecosystem as the source of Data", share data only with the member's permission, not build "a service similar to or competing with Polar Ecosystem", and delete everything if the agreement ends.

Terms: [API Limited License Agreement](https://www.polar.com/en/legal/polar-api-agreement), latest update 2025-08-22; [Terms of Use](https://www.polar.com/en/legal/terms-of-use), latest update 2026-02-18.

### 5. Google (Fitbit / Google Health API)

**Access: B · Freedom: C**

**Access.** The Google Health API replaces the Fitbit Web API, which turns off on 2026-10-30. An app in your own Cloud project counts as a "Personal Use" app (fewer than 100 users) and skips verification. Left in Testing, its tokens "expire after 7 days". You get JSON, including intraday heart rate, and routes as TCX. No FIT.

**Freedom.** Limited Use rules bind your app even if you're its only user. Data may serve only "features that are visible and prominent in the requesting application's user interface", and go to third parties only for those features "and only with the user's consent". There's no health-specific AI clause, so a model powering a feature you see reads as allowed.

Terms: [Health API Developer and User Data Policy](https://developers.google.com/health/policies/health-api-developer-user-data-policy), effective 2026-03-24; [Health API Developer Terms & Conditions](https://developers.google.com/health/policies/health-api-developer-terms-and-conditions), effective 2026-03-24.

### 6. Samsung Health

**Access: C · Freedom: B**

**Access.** Samsung has no cloud API. You build an Android app with the free Samsung Health Data SDK and read in Samsung Health's developer mode, which "is ONLY intended for testing or debugging your app". Data is per-record on the phone, with per-sample workout streams. No FIT.

**Freedom.** The SDK agreement has no AI clause and no retention limit. You may process data only "for the purpose of providing the Service", and never use or disclose it for advertising, marketing, selling or data mining. Sending it to a third party, such as a cloud model, needs a written agreement with terms "no less restrictive". Storage and local analysis stay open.

Terms: [Partner Service & SDK License Agreement](https://developer.samsung.com/health/data/overview.html) (click-through on the SDK download), updated 2021-10-07; [developer mode](https://developer.samsung.com/health/data/guide/developer-mode.html), undated; [Terms of Service](https://content.samsungknowledge.com/agreement/terms/tc/samsunghealth.oobe.tc_others/8.0.0/en-US.html), last updated 2018-10-17.

### 7. Suunto

**Access: C · Freedom: B**

**Access.** Suunto's Cloud API serves full FIT files, but "We currently don't offer the API access for personal use." What's open is a new read-only MCP server for any Suunto account, whose guide was first archived on 2026-10-11. It supports dynamic client registration, so your own client can connect, but its data fidelity isn't documented.

**Freedom.** No published terms attach to the MCP. The Terms of Service say "nothing in these Terms is intended to restrict any rights that You may have to use and exploit Your User Material". One clause limits "the outcomes of the Service" to "personal use only and not for redistribution", which may reach Suunto-computed metrics.

Terms: [Terms of Service](https://www.suunto.com/Terms-of-use/), effective 2025-09-01; [API Zone](https://apizone.suunto.com/), undated; [MCP guide](https://mcp.suunto.com/mcpguide), undated.

### 8. Apple Health

**Access: C · Freedom: C**

**Access.** There's no cloud API. You build your own iPhone or Watch app in Xcode to read HealthKit on the device. Free provisioning profiles "expire 7 days from issuance", and the free agreement allows HealthKit "only for internal testing and development purposes"; the paid program is $99 a year. You get per-sample records, not FIT.

**Freedom.** HealthKit data may serve only "health, motion, and/or fitness services", reach a third party only with "prior express end user consent", and never be stored in iCloud. Since 2025-11-13, Guideline 5.1.2(i) requires disclosing sharing "with third-party AI" and getting "explicit permission". Keeping data on your own disk isn't banned.

Terms: [Developer Program License Agreement](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/), last updated 2026-10-13; [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), last updated 2026-10-16; [Xcode and Apple SDKs Agreement](https://www.apple.com/legal/sla/docs/xcode.pdf), dated 2026-06-08.

### 9. Stryd

**Access: F · Freedom: A**

**Access.** Stryd publishes no API. A 2021 Stryd support email, quoted on the Intervals.icu forum, said it had "no plans for such API". The Terms of Use ban "web scraping, web harvesting, or web data extraction methods from Stryd even if an account owner gives permission". Stryd does document manual FIT and CSV export.

**Freedom.** Pod data, "statistics and measurements, wellness information and recovery scores" are your "User Content", carved out of the limits on Stryd's own content. There's no AI clause and no limit on storing or sharing your own data. Whether Stryd-computed metrics count as yours is ambiguous.

Terms: [Terms of Use](https://storage.googleapis.com/stryd_static_assets/legal/stryd-terms-of-use-4-6-21.pdf), served from [stryd.com/terms-of-use](https://www.stryd.com/terms-of-use), last revised 2021-04-06.

### 10. TrainingPeaks

**Access: F · Freedom: A**

**Access.** "At this time access to the API is not available for personal use." The Terms of Use ban bots and automated scripts, and the 2026-07-28 revision added a ban on "using such third-party services to scrape data from your Account". Manual export returns your original files. Garmin announced its acquisition of TrainingPeaks on 2026-07-22.

**Freedom.** "You retain all rights in and to your User Content", which includes "training logs, training data and analysis". The terms never mention AI. TrainingPeaks-computed CSV fields such as TSS® are arguably its content and not yours to redistribute.

Terms: [Terms of Use](https://www.trainingpeaks.com/terms-of-use/), last updated 2026-07-28; [An Update on TrainingPeaks Partner API](https://www.trainingpeaks.com/blog/an-update-on-trainingpeaks-partner-api/), updated 2026-09-12.

### 11. Zwift

**Access: F · Freedom: A**

**Access.** Zwift has no personal API. The Terms of Service ban "data mining, robots or similar data gathering or extraction methods", "bots, scripts, automated programs" and unauthorized apps. By hand you get full fidelity: "DOWNLOAD FIT FILE" for each activity, the original .fit files Zwift writes to your device, and automatic upload to other platforms.

**Freedom.** "You retain all rights in and to your User Content." No AI, storage or display rule touches your data.

Terms: [Terms of Service](https://support.zwift.com/terms-of-service-HJt7VBYyH), last updated 2026-06-02.

### 12. Oura

**Access: B · Freedom: F**

**Access.** Any account holder can register an OAuth app; personal access tokens went away in December 2025. Gen3 and later rings need a paid membership ($5.99 a month in the US) for any API access. You get derived JSON: scores, sleep stages, heart-rate samples and workout summaries. No FIT, no raw sensor data.

**Freedom.** The API and MCP Agreement binds individuals, and §4(d) bars using the API to "prompt, or otherwise provide input or data to any AI Model or AI Platform". LLM use is allowed only "through the MCP Server", whose data may not be stored; no public endpoint for it was found. API data can't be kept "beyond the duration strictly necessary", and the listed prohibited uses apply "regardless of whether a User has purportedly consented".

Terms: [API and MCP Agreement](https://cloud.ouraring.com/legal/api-agreement), effective 2026-06-08; [Terms of Use in force](https://ouraring.com/previous-terms-and-conditions), last updated 2026-04-20 (a [new version](https://ouraring.com/terms-and-conditions) takes effect 2026-11-04).

### 13. Strava

**Access: B · Freedom: F**

**Access.** Your own API app in "Single Player Mode" has needed a paid Strava subscription since June 2026 ("no additional fee"). It returns summaries and per-activity streams, but never the original file. "Export Original" is website-only, and the terms ban automated access "regardless of whether you are logged into a Strava account".

**Freedom.** The API Policy bans using Strava data with any "AI Application", including "ingestion into a context window" (§5.3). It bans storing it in any "Persistent Index" (§5.5), caching it beyond seven days (§6.2), and passing it to AI providers "even if a user ... consents" (§5.10). Strava's own subscriber MCP lifts only the AI ban; it runs "in accordance with this Policy".

Terms: [API Policy](https://www.strava.com/legal/api_policy), effective 2026-06-01; [API Agreement](https://www.strava.com/legal/api), effective 2026-06-01; [Terms of Service](https://www.strava.com/legal/terms), effective 2026-09-28.

### 14. Garmin

**Access: F · Freedom: B**

**Access.** The developer program is "only for business use", and applications have been paused since spring 2026, applicants and press report. The Terms of Use ban scraping "through any means not purposely made available", and unofficial login libraries have been failing since 2026-03-17, their maintainers report. On 2026-10-14 Intervals.icu's developer reported hearing of "an easier path for individuals"; Garmin hasn't announced one.

**Freedom.** With no personal API, this grades data from partners and exports. Partners must credit "Garmin" and the device model on displays, exports and AI outputs. A 2026-03-03 version of the agreement adds explicit consent before AI processing; whether it binds US developers is unconfirmed. Your own exports carry no restriction.

Terms: [Terms of Use](https://www.garmin.com/en-US/legal/terms-of-use/), effective 2026-04-01; [Connect Developer Program Agreement](https://developerportal.garmin.com/sites/default/files/Garmin%20Connect%20Developer%20Program%20Agreement.pdf), undated (file dated 2023-10-04); [2026 version](https://www8.garmin.com/en-US/GARMINCONNECTDEVELOPERPROGRAMAGREEMENT/GARMINCONNECTDEVELOPERPROGRAMAGREEMENT_EN.pdf), undated (file dated 2026-03-03); [API Brand Guidelines](https://developer.garmin.com/downloads/brand/Garmin-Developer-API-Brand-Guidelines.pdf), V 6.30.2025.

### 15. Wahoo

**Access: C · Freedom: F**

**Access.** The Cloud API returns a FIT file for each workout, but Wahoo is "currently limiting use of the API to those who request it". Individuals can sign the agreement. Since 2025-04-01 the API skips workouts recorded by third-party apps.

**Freedom.** The agreement bars using the API "to aggregate, cache, or store geographic location information or other user information accessible via the Wahoo API". Your ride files carry GPS tracks, and "other user information" covers the rest. Caching is "encouraged" only "within the limits outlined", and Wahoo can demand deletion within 48 hours. As written, no lasting archive fits; a looser reading would give D. There's no AI clause.

Terms: [API Agreement](https://www.wahoofitness.com/wahoo-api-agreement), undated (text unchanged since at least 2021-04-18); [Cloud API](https://developers.wahooligan.com/cloud), undated; [Terms of Service](https://www.wahoofitness.com/terms-of-service), effective 2023-12-05.

### 16. WHOOP

**Access: C · Freedom: F**

**Access.** You need a paid membership, and a new app's 10-member sandbox is enough for one person. Data is summary JSON: cycle, sleep, recovery and workout scores. "Continuous heart rate data is not available via the WHOOP API." No FIT. Limits are 100 requests a minute and 10,000 a day.

**Freedom.** Since 2026-10-06 the API terms bar using WHOOP data "to create, develop, test, train, fine-tune or improve any large language model or any other machine learning or artificial intelligence model, application, or system". They also forbid you to "build databases, or otherwise create permanent copies of WHOOP Data". The bans open with "Unless expressly authorized by the WHOOP Data owner"; WHOOP doesn't say whether that's you.

Terms: [API Terms of Use](https://developer.whoop.com/api-terms-of-use/), effective 2026-10-06; [Terms of Use](https://www.whoop.com/us/en/whoop-terms-of-use/), last updated 2026-04-13.

### 17. Withings

**Access: D · Freedom: F**

**Access.** Since 2026-10-13 the API terms admit only "a legal entity, or a natural person acting in the course of a professional activity", which on its face excludes hobbyists. Accounts created after 2026-10-12 also need Withings+. Withings' own MCP connector, for Withings+ members, is documented for four named AI assistants and returns aggregated values.

**Freedom.** §11.2: the API "may not be used to develop, train, evaluate, prompt or otherwise provide input or data to an AI Model". §8.3 bars disclosure to any third party "even where ... the User has authorised it". Manual CSV export stays free and unrestricted.

Terms: General Terms of Use for the Withings API, effective 2026-10-13, in the create-app form of the [developer dashboard](https://developer.withings.com/dashboard/); [API plans](https://static.withings.com/content/api/plans/plans.html), undated; [Terms and Conditions of Use](https://www.withings.com/us/en/legal/services-terms-and-conditions), updated 2026-01-05.

### 18. Peloton

**Access: F · Freedom: F**

**Access.** Peloton has no API or developer program, and the Terms of Service ban scraping or downloading Content with "spiders, robots, crawlers, data mining tools". The official paths are sync to Apple Health, Garmin Connect or Fitbit, a web "Download Workouts" CSV of summaries (reported), and a privacy request.

**Freedom.** Peloton's "Content" includes your "User Content". Since 2025-10-01 the terms bar "using Content to train artificial intelligence models or systems". They also forbid you to "Copy, use, index, disclose or distribute any information or data obtained from the Peloton Service", or to "store" Content, without written consent. Read literally, there's no carve-out for your own data.

Terms: [Terms of Service](https://www.onepeloton.com/terms-of-service), last updated 2025-10-01.

## Reading these grades

These grades are as of 2026-10-18, and several moved in 2026: Oura, Strava, WHOOP and Withings tightened their API terms on AI, while COROS and Suunto now run official MCP servers. The pattern is consistent. Piping your data out of a platform keeps getting harder, while a file you export by hand is almost always yours to keep. Check the linked terms before you rely on any grade.
