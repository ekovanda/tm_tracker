"""Connection and Environment Verification Script for Trackmania Bingo.

Run this script to verify your local setup, .env credentials, and connection
to Nadeo Live Services:

    uv run --active python scripts/verify_connection.py
"""

import sys
from pathlib import Path

import requests

# Ensure repo root is on sys.path so project modules can be imported
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Color formatting helpers for Windows & Linux terminals
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step(title: str) -> None:
    """Print section step title."""
    print(f"\n{BOLD}{BLUE}--> {title}{RESET}")


def print_pass(msg: str) -> None:
    """Print success message."""
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def print_fail(msg: str) -> None:
    """Print error failure message."""
    print(f"  {RED}[FAIL]{RESET} {msg}")


def print_warn(msg: str) -> None:
    """Print warning message."""
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def _check_python_version() -> bool:
    print_step("Step 1: Checking Python Environment")
    py_ver = sys.version.split()[0]
    if sys.version_info < (3, 13):  # noqa: UP036
        print_fail(f"Python version {py_ver} is too old. Python 3.13+ required.")
        return False
    print_pass(f"Python version: {py_ver}")
    return True


def _check_env_file() -> tuple[bool, object | None]:
    print_step("Step 2: Checking Local .env Configuration")
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        print_fail("No '.env' file found in the project root.")
        print(
            "         Please create a '.env' file using the credentials "
            "provided by the maintainer."
        )
        return False, None

    print_pass(f"Found '.env' at: {env_file.name}")
    try:
        import authentication  # pylint: disable=import-outside-toplevel

        return True, authentication
    except ImportError as exc:
        print_fail(f"Could not import application modules: {exc}")
        print('         Ensure dependencies are installed: uv pip install -e ".[dev]"')
        return False, None


def _validate_secrets(auth_mod: object) -> bool:
    basic_auth = getattr(auth_mod, "BASIC_AUTH", None)
    if not basic_auth:
        print_fail("BASIC_AUTH is missing or empty in .env.")
        return False

    if not basic_auth.startswith("Basic "):
        print_warn(
            "BASIC_AUTH does not start with 'Basic '. Ensure it includes the 'Basic ' prefix."
        )
    else:
        masked = basic_auth[:10] + "..." + basic_auth[-4:]
        print_pass(f"BASIC_AUTH configured ({masked})")

    try:
        auth_mod.verify_app_password("test-check")  # type: ignore[attr-defined]
        print_pass("APP_PASSWORD_HASH is valid PBKDF2 format.")
    except auth_mod.PasswordConfigurationError as exc:  # type: ignore[attr-defined]
        print_fail(f"APP_PASSWORD_HASH is invalid: {exc}")
        return False

    user_agent = auth_mod.get_user_agent()  # type: ignore[attr-defined]
    print_pass(f"API User-Agent: {user_agent}")
    return True


def _authenticate_nadeo(auth_mod: object) -> str | None:
    print_step("Step 3: Authenticating with Nadeo Service Account")
    try:
        token_data = auth_mod.get_nadeo_service_token()  # type: ignore[attr-defined]
        access_token = token_data.get("accessToken")
        if not access_token:
            print_fail("Nadeo response did not contain an accessToken.")
            return None
        print_pass("Authentication ticket received successfully from Nadeo!")
        return str(access_token)
    except auth_mod.UbisoftAuthenticationError as exc:  # type: ignore[attr-defined]
        print_fail(f"Authentication failed: {exc}")
        print(
            "         Double check that BASIC_AUTH matches the secret "
            "provided by the maintainer."
        )
        return None
    except requests.RequestException as exc:
        print_fail(f"Network error connecting to Nadeo authentication: {exc}")
        print("         Check your internet connection.")
        return None


def _query_live_services(access_token: str) -> bool:
    print_step("Step 4: Querying Official Campaigns from Live Services")
    try:
        import live_services  # pylint: disable=import-outside-toplevel

        campaigns = live_services.get_official_campaigns(access_token, length=3)
        if not campaigns:
            print_warn("Nadeo API returned an empty campaigns list.")
        else:
            campaign_names = ", ".join(f"'{c.name}'" for c in campaigns)
            print_pass(f"Successfully retrieved official campaigns: {campaign_names}")
        return True
    except live_services.LiveServiceError as exc:
        print_fail(f"Live Services API call failed: {exc}")
        return False
    except requests.RequestException as exc:
        print_fail(f"Network error while querying Live Services: {exc}")
        return False


def main() -> int:
    """Run connection and environment checks."""
    print(f"{BOLD}===================================================={RESET}")
    print(f"{BOLD}  Trackmania Bingo - Setup & Connection Checker     {RESET}")
    print(f"{BOLD}===================================================={RESET}")

    if not _check_python_version():
        return 1

    env_ok, auth_mod = _check_env_file()
    if not env_ok or auth_mod is None:
        return 1

    if not _validate_secrets(auth_mod):
        print(
            f"\n{RED}{BOLD}Environment check failed. Fix the issues above and try again.{RESET}"
        )
        return 1

    access_token = _authenticate_nadeo(auth_mod)
    if not access_token or not _query_live_services(access_token):
        return 1

    print(f"\n{BOLD}{GREEN}===================================================={RESET}")
    print(f"{BOLD}{GREEN}  ALL CHECKS PASSED! Your setup is working!         {RESET}")
    print(f"{BOLD}{GREEN}===================================================={RESET}")
    print("\nYou can now start the local Bingo application:")
    print(f"  {BOLD}uv run --active uvicorn api:app --reload --port 8080{RESET}")
    print("\nThen open your browser at: http://localhost:8080\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
