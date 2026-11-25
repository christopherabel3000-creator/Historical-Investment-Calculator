# Fills in What If I'd Invested's App Store listing through the App Store Connect API, from appstore/listing.md.
# Run by .github/workflows/appstore-metadata.yml with the signing secrets. Prints what it did, never the key.
# Covers: version text, subtitle and privacy URL, categories, copyright, release type, content rights,
# price (free), regions (all but the EU and China mainland), the newest build, the review contact and notes,
# and the screenshots in appstore/screenshots.
# Not covered (done in App Store Connect itself): age rating, App Privacy and accessibility answers.
import os, re, sys, time, glob, hashlib, jwt, requests

APP_BUNDLE = "com.playbyear.whatifinvested"
TEMPLATE_APP = "com.playbyear.hiddenranks"   # review contact details are copied from this app
API = "https://api.appstoreconnect.apple.com"
EU = "AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE".split()
EXCLUDE = set(EU + ["CHN"])

def say(t):
    print(t)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(t + "\n\n")

token = jwt.encode({"iss": os.environ["ASC_ISSUER_ID"].strip(), "iat": int(time.time()), "exp": int(time.time()) + 1100, "aud": "appstoreconnect-v1"},
                   os.environ["ASC_KEY_P8"].strip(), algorithm="ES256", headers={"kid": os.environ["ASC_KEY_ID"].strip(), "typ": "JWT"})
S = requests.Session(); S.headers.update({"Authorization": "Bearer " + token, "Content-Type": "application/json"})
problems = []

def call(method, path, **kw):
    r = S.request(method, API + path, timeout=60, **kw)
    if r.status_code >= 400:
        msg = "; ".join(e.get("detail") or e.get("title", "") for e in r.json().get("errors", [])) if r.text.startswith("{") else r.text[:300]
        raise RuntimeError(f"{method} {path.split('?')[0]} -> {r.status_code}: {msg}")
    return r.json() if r.text else {}

def step(name, fn):
    try:
        out = fn(); say(f"OK: {name}" + (f" ({out})" if out else ""))
    except Exception as e:
        problems.append(name); say(f"PROBLEM: {name}: {e}")

# ---- read the listing text ----
md = open("appstore/listing.md").read()
def section(title):
    m = re.search(r"^## " + re.escape(title) + r"[^\n]*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1).strip()
subtitle = section("Subtitle")
promo = section("Promotional text")
description = section("Description")
keywords = section("Keywords")
notes = section("Notes for the reviewer")
notes = notes[notes.index("What If I'd Invested is an educational"):].strip()
link = os.environ.get("RECORDING_LINK", "").strip()
if link: notes = notes.replace("RECORDING_LINK", link)
fields = dict(re.findall(r"^- ([^:]+): (.+)$", section("Other fields"), re.M))
for name, val, cap in (("subtitle", subtitle, 30), ("promotional text", promo, 170), ("description", description, 4000), ("keywords", keywords, 100), ("review notes", notes, 4000)):
    if len(val) > cap: say(f"PROBLEM: {name} is {len(val)} characters, over Apple's {cap}"); sys.exit(1)

app = call("GET", f"/v1/apps?filter[bundleId]={APP_BUNDLE}")["data"][0]; APP = app["id"]
ver = [v for v in call("GET", f"/v1/apps/{APP}/appStoreVersions?filter[platform]=IOS")["data"] if v["attributes"]["appStoreState"] in ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED")][0]
VER = ver["id"]
say(f"App {APP}, version {ver['attributes']['versionString']} ({ver['attributes']['appStoreState']})")

step("copyright and automatic release", lambda: call("PATCH", f"/v1/appStoreVersions/{VER}", json={"data": {"type": "appStoreVersions", "id": VER,
     "attributes": {"copyright": fields["Copyright"], "releaseType": "AFTER_APPROVAL"}}}) and None)

def version_text():
    loc = [l for l in call("GET", f"/v1/appStoreVersions/{VER}/appStoreVersionLocalizations")["data"] if l["attributes"]["locale"] == "en-US"][0]
    call("PATCH", f"/v1/appStoreVersionLocalizations/{loc['id']}", json={"data": {"type": "appStoreVersionLocalizations", "id": loc["id"],
         "attributes": {"description": description, "keywords": keywords, "promotionalText": promo, "supportUrl": fields["Support URL"],
                        "marketingUrl": fields["Marketing URL"]}}})
step("description, keywords, promotional text, support and marketing URLs", version_text)

infos = call("GET", f"/v1/apps/{APP}/appInfos")["data"]
INFO = [i for i in infos if i["attributes"].get("appStoreState", i["attributes"].get("state")) not in ("READY_FOR_SALE", "READY_FOR_DISTRIBUTION")][0]["id"] if len(infos) > 1 else infos[0]["id"]
def info_text():
    loc = [l for l in call("GET", f"/v1/appInfos/{INFO}/appInfoLocalizations")["data"] if l["attributes"]["locale"] == "en-US"][0]
    call("PATCH", f"/v1/appInfoLocalizations/{loc['id']}", json={"data": {"type": "appInfoLocalizations", "id": loc["id"],
         "attributes": {"subtitle": subtitle, "privacyPolicyUrl": fields["Privacy policy URL"]}}})
step("subtitle and privacy policy URL", info_text)

step("categories Finance and Education", lambda: call("PATCH", f"/v1/appInfos/{INFO}", json={"data": {"type": "appInfos", "id": INFO, "relationships": {
     "primaryCategory": {"data": {"type": "appCategories", "id": "FINANCE"}},
     "secondaryCategory": {"data": {"type": "appCategories", "id": "EDUCATION"}}}}}) and None)

step("content rights: third-party data, with rights", lambda: call("PATCH", f"/v1/apps/{APP}", json={"data": {"type": "apps", "id": APP,
     "attributes": {"contentRightsDeclaration": "USES_THIRD_PARTY_CONTENT"}}}) and None)

def price():
    pts = call("GET", f"/v1/apps/{APP}/appPricePoints?filter[territory]=USA&limit=200")["data"]
    free = [p for p in pts if float(p["attributes"]["customerPrice"]) == 0][0]
    call("POST", "/v1/appPriceSchedules", json={"data": {"type": "appPriceSchedules", "relationships": {
        "app": {"data": {"type": "apps", "id": APP}},
        "baseTerritory": {"data": {"type": "territories", "id": "USA"}},
        "manualPrices": {"data": [{"type": "appPrices", "id": "${price}"}]}}},
        "included": [{"type": "appPrices", "id": "${price}", "attributes": {"startDate": None},
                      "relationships": {"appPricePoint": {"data": {"type": "appPricePoints", "id": free["id"]}}}}]})
    return "free"
step("price", price)

def regions():
    terr, url = [], "/v1/territories?limit=200"
    while url:
        r = call("GET", url); terr += [t["id"] for t in r["data"]]
        nxt = r.get("links", {}).get("next"); url = nxt.replace(API, "") if nxt else None
    data, inc = [], []
    for t in terr:
        lid = "${" + t + "}"
        data.append({"type": "territoryAvailabilities", "id": lid})
        inc.append({"type": "territoryAvailabilities", "id": lid, "attributes": {"available": t not in EXCLUDE},
                    "relationships": {"territory": {"data": {"type": "territories", "id": t}}}})
    existing = requests.get(API + f"/v1/apps/{APP}/appAvailabilityV2", headers=S.headers, timeout=60)
    if existing.status_code == 200 and existing.json().get("data"):
        return "already set; change them in App Store Connect, Pricing and Availability"
    call("POST", "/v2/appAvailabilities", json={"data": {"type": "appAvailabilities", "attributes": {"availableInNewTerritories": False},
         "relationships": {"app": {"data": {"type": "apps", "id": APP}}, "territoryAvailabilities": {"data": data}}}, "included": inc})
    return f"{len(terr) - len(EXCLUDE & set(terr))} of {len(terr)} regions"
step("regions (all but the EU and China mainland)", regions)

def build():
    b = call("GET", f"/v1/builds?filter[app]={APP}&filter[processingState]=VALID&sort=-uploadedDate&limit=1")["data"]
    if not b: raise RuntimeError("no processed build yet")
    call("PATCH", f"/v1/appStoreVersions/{VER}/relationships/build", json={"data": {"type": "builds", "id": b[0]["id"]}})
    return "build " + b[0]["attributes"]["version"]
step("build for this version", build)

def review():
    tapp = call("GET", f"/v1/apps?filter[bundleId]={TEMPLATE_APP}")["data"][0]["id"]
    tver = call("GET", f"/v1/apps/{tapp}/appStoreVersions?filter[platform]=IOS&limit=1")["data"][0]["id"]
    t = call("GET", f"/v1/appStoreVersions/{tver}/appStoreReviewDetail")["data"]["attributes"]
    attrs = {k: t.get(k) for k in ("contactFirstName", "contactLastName", "contactPhone", "contactEmail")}
    attrs.update({"demoAccountRequired": False, "notes": notes})
    cur = requests.get(API + f"/v1/appStoreVersions/{VER}/appStoreReviewDetail", headers=S.headers, timeout=60)
    if cur.status_code == 200 and cur.json().get("data"):
        rid = cur.json()["data"]["id"]
        call("PATCH", f"/v1/appStoreReviewDetails/{rid}", json={"data": {"type": "appStoreReviewDetails", "id": rid, "attributes": attrs}})
    else:
        call("POST", "/v1/appStoreReviewDetails", json={"data": {"type": "appStoreReviewDetails", "attributes": attrs,
             "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": VER}}}}})
    return "contact copied from Hidden Ranks; notes " + ("waiting for the recording link" if "RECORDING_LINK" in notes else "with the recording link")
step("review contact and notes", review)

# ---- screenshots ----
# Each device's screenshots go in one set. The set type for a size isn't always obvious, so a few are tried
# until Apple accepts the first image; existing sets for this device are replaced.
SHOT_TYPES = {"iphone": ["APP_IPHONE_61", "APP_IPHONE_67", "APP_IPHONE_65"], "ipad": ["APP_IPAD_PRO_3GEN_129"]}
def upload(set_id, path):
    data = open(path, "rb").read()
    a = call("POST", "/v1/appScreenshots", json={"data": {"type": "appScreenshots", "attributes": {"fileName": os.path.basename(path), "fileSize": len(data)},
             "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": set_id}}}}})["data"]
    for op in a["attributes"]["uploadOperations"]:
        h = {x["name"]: x["value"] for x in op.get("requestHeaders", [])}
        r = requests.request(op["method"], op["url"], headers=h, data=data[op["offset"]:op["offset"] + op["length"]], timeout=120)
        if r.status_code >= 400: raise RuntimeError(f"upload of {os.path.basename(path)} -> {r.status_code}")
    call("PATCH", f"/v1/appScreenshots/{a['id']}", json={"data": {"type": "appScreenshots", "id": a["id"],
         "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
    for _ in range(30):
        st = call("GET", f"/v1/appScreenshots/{a['id']}")["data"]["attributes"]["assetDeliveryState"]
        if st["state"] in ("COMPLETE", "FAILED"): break
        time.sleep(3)
    if st["state"] != "COMPLETE":
        raise RuntimeError(f"{os.path.basename(path)}: " + "; ".join(e.get("description", e.get("code", "")) for e in st.get("errors") or []) or st["state"])
def screenshots():
    loc = [l for l in call("GET", f"/v1/appStoreVersions/{VER}/appStoreVersionLocalizations")["data"] if l["attributes"]["locale"] == "en-US"][0]["id"]
    existing = {s["attributes"]["screenshotDisplayType"]: s["id"] for s in call("GET", f"/v1/appStoreVersionLocalizations/{loc}/appScreenshotSets")["data"]}
    done = []
    for device, types in SHOT_TYPES.items():
        files = sorted(glob.glob(f"appstore/screenshots/{device}-*.png"))
        last = None
        for t in types:
            if t in existing: call("DELETE", f"/v1/appScreenshotSets/{existing[t]}"); existing.pop(t)
            sid = call("POST", "/v1/appScreenshotSets", json={"data": {"type": "appScreenshotSets", "attributes": {"screenshotDisplayType": t},
                       "relationships": {"appStoreVersionLocalization": {"data": {"type": "appStoreVersionLocalizations", "id": loc}}}}})["data"]["id"]
            try:
                for f in files: upload(sid, f)
                done.append(f"{len(files)} {device} as {t}"); last = None; break
            except RuntimeError as e:
                last = e; call("DELETE", f"/v1/appScreenshotSets/{sid}")
        if last: raise last
    return ", ".join(done)
step("screenshots", screenshots)

say("Done with " + (f"{len(problems)} problem(s): " + ", ".join(problems) if problems else "no problems."))
sys.exit(1 if problems else 0)
