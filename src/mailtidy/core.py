"""Conservative, reviewable Gmail cleanup operations."""
import collections
import datetime as dt
import email.utils
import re

PROTECTED = {"UNREAD", "STARRED", "IMPORTANT", "TRASH", "SPAM", "DRAFT", "SENT"}
HEADERS = ["From", "Subject", "List-Unsubscribe", "List-Unsubscribe-Post"]


def metadata(service, message_id):
    return service.users().messages().get(userId="me", id=message_id, format="metadata", metadataHeaders=HEADERS).execute()


def eligible(message, cutoff, keep):
    labels = set(message.get("labelIds", []))
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    sender = email.utils.parseaddr(headers.get("from", ""))[1].lower()
    if not sender or sender in keep or sender.split("@")[-1] in keep:
        return False
    return ("CATEGORY_PROMOTIONS" in labels and not labels.intersection(PROTECTED)
            and int(message.get("internalDate", "0")) > 0
            and int(message["internalDate"]) <= cutoff)


def scan(service, days=30, keep=()):
    if days < 1:
        raise ValueError("days must be at least 1")
    account = service.users().getProfile(userId="me").execute()["emailAddress"].lower()
    cutoff = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).timestamp() * 1000)
    messages, token = [], None
    while True:
        args = {"userId": "me", "q": f"category:promotions is:read older_than:{days}d -is:starred -is:important", "maxResults": 500}
        if token:
            args["pageToken"] = token
        page = service.users().messages().list(**args).execute()
        for item in page.get("messages", []):
            m = metadata(service, item["id"])
            if eligible(m, cutoff, {x.lower() for x in keep}):
                h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
                messages.append({"id": m["id"], "sender": email.utils.parseaddr(h.get("from", ""))[1].lower(),
                                 "subject": h.get("subject", "(no subject)"),
                                 "one_click_available": bool(re.search(r"<https://[^>]+>", h.get("list-unsubscribe", ""), re.I) and h.get("list-unsubscribe-post", "").strip().lower() == "list-unsubscribe=one-click")})
        token = page.get("nextPageToken")
        if not token:
            break
    return {"version": 1, "account": account, "cutoff_ms": cutoff, "keep": list(keep), "messages": messages}


def review(plan):
    groups = collections.defaultdict(list)
    for m in plan["messages"]:
        groups[m["sender"]].append(m)
    return [{"sender": sender, "count": len(items), "samples": [x["subject"] for x in items[:3]],
             "one_click_available": any(x["one_click_available"] for x in items)} for sender, items in sorted(groups.items())]


def apply(service, plan, record):
    account = service.users().getProfile(userId="me").execute()["emailAddress"].lower()
    if account != plan["account"]:
        raise ValueError("Plan belongs to another Gmail account")
    keep = {x.lower() for x in plan.get("keep", [])}
    for entry in plan["messages"]:
        try:
            m = metadata(service, entry["id"])
            if not eligible(m, plan["cutoff_ms"], keep):
                record({"id": entry["id"], "status": "skipped"})
                continue
            service.users().messages().trash(userId="me", id=entry["id"]).execute()
            record({"id": entry["id"], "status": "trashed"})
        except Exception as exc:
            record({"id": entry["id"], "status": "error", "error": str(exc)})
