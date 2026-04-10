import argparse
import os
import sys
from typing import Any

from supabase import create_client


DEFAULT_SUPABASE_URL = "https://bqumqfdisvihzknhaaej.supabase.co"


def get_nested_value(value: Any, key: str, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    if hasattr(value, key):
        return getattr(value, key)
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump().get(key, default)
        except Exception:
            return default
    return default


def normalize_users(response: Any) -> list[Any]:
    if response is None:
        return []
    if isinstance(response, list):
        return response

    users = get_nested_value(response, "users")
    if isinstance(users, list):
        return users

    try:
        return list(response)
    except TypeError:
        return []


def list_users(admin_client) -> list[Any]:
    try:
        return normalize_users(admin_client.auth.admin.list_users())
    except TypeError:
        return normalize_users(admin_client.auth.admin.list_users(page=1, per_page=200))


def find_user_by_email(users: list[Any], email: str):
    target = email.strip().lower()
    for user in users:
        current_email = str(get_nested_value(user, "email", "") or "").strip().lower()
        if current_email == target:
            return user
    return None


def parse_args():
    parser = argparse.ArgumentParser(description="Create or promote a Supabase admin user.")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", help="Password to use when creating a new user")
    parser.add_argument("--first-name", default="Admin", help="First name for a newly created user")
    parser.add_argument("--last-name", default="User", help="Last name for a newly created user")
    parser.add_argument("--url", default=os.getenv("SUPABASE_URL", DEFAULT_SUPABASE_URL), help="Supabase project URL")
    parser.add_argument(
        "--service-role-key",
        default=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        help="Supabase service role key",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.url:
        print("Missing Supabase URL. Pass --url or set SUPABASE_URL.", file=sys.stderr)
        raise SystemExit(1)

    if not args.service_role_key:
        print(
            "Missing service role key. Pass --service-role-key or set SUPABASE_SERVICE_ROLE_KEY.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    admin_client = create_client(args.url, args.service_role_key)
    users = list_users(admin_client)
    existing_user = find_user_by_email(users, args.email)

    metadata = {
        "first_name": args.first_name.strip(),
        "last_name": args.last_name.strip(),
        "full_name": f"{args.first_name.strip()} {args.last_name.strip()}".strip(),
    }

    if existing_user:
        existing_app_metadata = get_nested_value(existing_user, "app_metadata", {}) or {}
        existing_user_metadata = get_nested_value(existing_user, "user_metadata", {}) or {}
        admin_client.auth.admin.update_user_by_id(
            get_nested_value(existing_user, "id", ""),
            {
                "app_metadata": {**existing_app_metadata, "role": "admin"},
                "user_metadata": {**existing_user_metadata, **metadata},
            },
        )
        print(f"Promoted existing user {args.email} to admin.")
        return

    if not args.password:
        print(
            "User does not exist yet. Pass --password so the bootstrap script can create the account.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    admin_client.auth.admin.create_user(
        {
            "email": args.email.strip().lower(),
            "password": args.password,
            "email_confirm": True,
            "app_metadata": {"role": "admin"},
            "user_metadata": metadata,
        }
    )
    print(f"Created new admin user {args.email}.")


if __name__ == "__main__":
    main()
