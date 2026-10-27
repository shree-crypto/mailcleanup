import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from . import core, unsubscribe

STATE = Path(os.environ.get("MAILTIDY_HOME", Path.home() / ".mailtidy"))
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def write_private(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, indent=2)


def service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    token = STATE / "token.json"
    if not token.exists():
        raise ValueError("Run mailtidy auth --credentials CLIENT_SECRET.json first")
    credentials = Credentials.from_authorized_user_file(str(token), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        write_private(token, json.loads(credentials.to_json()))
    if not credentials.valid:
        raise ValueError("Credentials invalid; run mailtidy auth again")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def main():
    p = argparse.ArgumentParser(prog="mailtidy")
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("auth"); auth.add_argument("--credentials", required=True)
    sub.add_parser("disconnect")
    scan = sub.add_parser("scan"); scan.add_argument("--days", type=int, default=30); scan.add_argument("--keep", action="append", default=[]); scan.add_argument("--output", default="plan.json")
    review = sub.add_parser("review"); review.add_argument("plan")
    apply = sub.add_parser("apply"); apply.add_argument("plan"); apply.add_argument("--confirm", action="store_true")
    unsub = sub.add_parser("unsubscribe"); unsub.add_argument("plan"); unsub.add_argument("--sender", required=True); unsub.add_argument("--confirm", action="store_true")
    undo = sub.add_parser("undo"); undo.add_argument("run_id"); undo.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    try:
        if args.command == "auth":
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(args.credentials, SCOPES)
            credentials = flow.run_local_server(port=0, open_browser=True)
            write_private(STATE / "token.json", json.loads(credentials.to_json()))
            print("Gmail connected.")
        elif args.command == "disconnect":
            (STATE / "token.json").unlink(missing_ok=True)
            print("Local token removed. Revoke Google access separately in your Google account.")
        elif args.command == "scan":
            plan = core.scan(service(), args.days, args.keep)
            write_private(Path(args.output), plan)
            print(f"Saved {len(plan['messages'])} candidates to {args.output}")
        elif args.command == "review":
            plan = json.loads(Path(args.plan).read_text())
            print(json.dumps({"account": plan["account"], "senders": core.review(plan)}, indent=2))
        elif args.command == "apply":
            if not args.confirm:
                raise ValueError("Review the plan first, then pass --confirm")
            plan = json.loads(Path(args.plan).read_text()); api = service()
            run_id = uuid.uuid4().hex
            STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = STATE / f"run-{run_id}.jsonl"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as out:
                out.write(json.dumps({"account": plan["account"]}) + "\n"); out.flush(); os.fsync(out.fileno())
                def record(result):
                    out.write(json.dumps(result) + "\n"); out.flush(); os.fsync(out.fileno())
                core.apply(api, plan, record)
            print(f"Run {run_id}; results: {path}")
        elif args.command == "unsubscribe":
            if not args.confirm:
                raise ValueError("Review the sender and pass --confirm to unsubscribe")
            plan = json.loads(Path(args.plan).read_text())
            status = unsubscribe.unsubscribe(service(), plan, args.sender)
            print(f"Unsubscribe request accepted (HTTP {status}); the sender controls whether it takes effect.")
        elif args.command == "undo":
            if not args.confirm or not all(c in "0123456789abcdef" for c in args.run_id) or len(args.run_id) != 32:
                raise ValueError("Provide a valid run ID and --confirm")
            entries = [json.loads(x) for x in (STATE / f"run-{args.run_id}.jsonl").read_text().splitlines()]
            api = service()
            if api.users().getProfile(userId="me").execute()["emailAddress"].lower() != entries[0]["account"]:
                raise ValueError("Run belongs to another account")
            for entry in entries[1:]:
                if entry.get("status") == "trashed":
                    try:
                        m = core.metadata(api, entry["id"])
                        if "TRASH" in m.get("labelIds", []):
                            api.users().messages().untrash(userId="me", id=entry["id"]).execute()
                            print(f"Restored {entry['id']}")
                    except Exception as exc:
                        print(f"Failed {entry['id']}: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
