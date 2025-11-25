import os
from typing import Literal

from plexapi.myplex import MyPlexAccount

# Environment variables (set these in Render)
PLEX_TOKEN = os.getenv("PLEX_TOKEN", "")
PLEX_SERVER_NAME = os.getenv("PLEX_SERVER_NAME", "REELSPACE")  # default for your setup


def _get_account() -> MyPlexAccount:
    """Return an authenticated MyPlexAccount."""
    if not PLEX_TOKEN:
        raise RuntimeError("PLEX_TOKEN environment variable is not set")
    return MyPlexAccount(token=PLEX_TOKEN)


def _get_server_resource(account: MyPlexAccount):
    """Find the Plex server resource by friendly name."""
    if not PLEX_SERVER_NAME:
        raise RuntimeError("PLEX_SERVER_NAME environment variable is not set")

    # Use resource() helper if available, fall back to manual loop
    try:
        resource = account.resource(PLEX_SERVER_NAME)
    except Exception:
        resource = None

    if not resource:
        for r in account.resources():
            if r.name == PLEX_SERVER_NAME and "server" in r.provides:
                resource = r
                break

    if not resource:
        raise RuntimeError(f"Plex server '{PLEX_SERVER_NAME}' not found in Plex account resources.")

    return resource


InviteStatus = Literal["sent", "already_shared", "already_invited"]


def invite_user(email: str, full_name: str = "") -> InviteStatus:
    """
    Invite a user to your Plex server.

    Returns one of:
      - 'sent'             -> invite sent now
      - 'already_shared'   -> user already has access to this server
      - 'already_invited'  -> pending invite already exists
    """
    account = _get_account()
    resource = _get_server_resource(account)
    server = resource.connect()

    email_lower = email.lower()

    # 1) Check if they already have access (shared user)
    for u in account.users():
        # u.username is Plex username, u.email is their email address
        if (u.email and u.email.lower() == email_lower) or (u.username and u.username.lower() == email_lower):
            # Already a friend with access to at least one server
            return "already_shared"

    # 2) Check for an existing pending invite
    for inv in account.pendingInvites(includeSent=True, includeReceived=False):
        if inv.username.lower() == email_lower or (inv.email and inv.email.lower() == email_lower):
            return "already_invited"

    # 3) Send a new invite
    # Newer plexapi versions support server= PlexServer object directly
    account.inviteFriend(
        user=email,
        server=server,
        allowSync=False,
        allowCameraUpload=False,
        allowChannels=False,
        sections=None,  # None => all libraries
    )
    return "sent"


def revoke_user(email: str) -> bool:
    """
    Temporarily disable a user's access to your server.

    Implementation: we remove them as a friend; when they pay again,
    invite_user(email) will just send a fresh invite.
    """
    account = _get_account()

    # If they don't exist as a user/friend, this will raise, so we wrap it
    try:
        account.removeFriend(email)
        return True
    except Exception:
        # If they're already gone (or never accepted), just treat as success.
        return False
