# Checks that What If I'd Invested's version is ready, then submits it for App Store review through the App Store
# Connect API. Run by .github/workflows/appstore-submit.yml. Stops without submitting if anything is missing.
import os, sys, time, jwt, requests
API = "https://api.appstoreconnect.apple.com"
def say(t):
    print(t)
    if os.environ.get("GITHUB_STEP_SUMMARY"): open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(t + "\n\n")
token = jwt.encode({"iss": os.environ["ASC_ISSUER_ID"].strip(), "iat": int(time.time()), "exp": int(time.time()) + 1100, "aud": "appstoreconnect-v1"},
                   os.environ["ASC_KEY_P8"].strip(), algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"].strip(), "typ": "JWT"})
S = requests.Session(); S.headers.update({"Authorization": "Bearer " + token, "Content-Type": "application/json"})
def call(method, path, **kw):
    r = S.request(method, API + path, timeout=60, **kw)
    if r.status_code >= 400:
        errs = r.json().get("errors", []) if r.text.startswith("{") else []
        raise SystemExit(say(f"STOPPED: {method} {path.split('?')[0]} -> {r.status_code}: " + "; ".join((e.get("detail") or e.get("title", "")) for e in errs)[:1500]) or 1)
    return r.json() if r.text else {}

APP = call("GET", "/v1/apps?filter[bundleId]=com.playbyear.whatifinvested")["data"][0]["id"]
ver = [v for v in call("GET", f"/v1/apps/{APP}/appStoreVersions?filter[platform]=IOS")["data"] if v["attributes"]["appStoreState"] in ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED")]
if not ver: raise SystemExit(say("STOPPED: no version waiting to be submitted.") or 1)
VER = ver[0]["id"]
# Checks before submitting
build = call("GET", f"/v1/appStoreVersions/{VER}/build").get("data")
say("Build: " + (build["attributes"]["version"] if build else "MISSING"))
notes = call("GET", f"/v1/appStoreVersions/{VER}/appStoreReviewDetail")["data"]["attributes"]["notes"] or ""
link = os.environ.get("EXPECT_LINK", "").strip()
say("Review notes: " + str(len(notes)) + " characters; recording link " + ("present" if link and link in notes else "MISSING"))
sets = call("GET", f"/v1/appStoreVersionLocalizations/{[l for l in call('GET', f'/v1/appStoreVersions/{VER}/appStoreVersionLocalizations')['data'] if l['attributes']['locale']=='en-US'][0]['id']}/appScreenshotSets")["data"]
counts = {s["attributes"]["screenshotDisplayType"]: len(call("GET", f"/v1/appScreenshotSets/{s['id']}/appScreenshots")["data"]) for s in sets}
say("Screenshots: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
if not build or (link and link not in notes) or not counts:
    raise SystemExit(say("STOPPED before submitting: something above is missing.") or 1)
if os.environ.get("CHECK_ONLY") == "true":
    raise SystemExit(say("Check only: not submitted.") or 0)
# Submit
open_subs = call("GET", f"/v1/reviewSubmissions?filter[app]={APP}&filter[state]=READY_FOR_REVIEW,UNRESOLVED_ISSUES")["data"]
sub = open_subs[0]["id"] if open_subs else call("POST", "/v1/reviewSubmissions", json={"data": {"type": "reviewSubmissions",
      "attributes": {"platform": "IOS"}, "relationships": {"app": {"data": {"type": "apps", "id": APP}}}}})["data"]["id"]
items = call("GET", f"/v1/reviewSubmissions/{sub}/items")["data"]
if not items:
    call("POST", "/v1/reviewSubmissionItems", json={"data": {"type": "reviewSubmissionItems", "relationships": {
         "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": sub}},
         "appStoreVersion": {"data": {"type": "appStoreVersions", "id": VER}}}}})
r = call("PATCH", f"/v1/reviewSubmissions/{sub}", json={"data": {"type": "reviewSubmissions", "id": sub, "attributes": {"submitted": True}}})
time.sleep(5)
state = call("GET", f"/v1/appStoreVersions/{VER}")["data"]["attributes"]["appStoreState"]
say(f"SUBMITTED. Review submission state: {r['data']['attributes']['state']}; version state: {state}")
