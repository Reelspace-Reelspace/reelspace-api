import os, datetime
from plexapi.myplex import MyPlexAccount

PLEX_TOKEN = os.getenv("PLEX_TOKEN")
PLEX_SERVER_NAME = os.getenv("PLEX_SERVER_NAME")

def invite_user(email: str):
    account = MyPlexAccount(token=PLEX_TOKEN)
    resource = None
    for r in account.resources():
        if r.name == PLEX_SERVER_NAME and "server" in r.provides:
            resource = r
            break
    if not resource:
        raise RuntimeError(f"Plex server '{PLEX_SERVER_NAME}' not found in account resources.")
    server = resource.connect()
    # If already shared, this will no-op by raising a message; we catch upstream.
    account.inviteFriend(email, [server.machineIdentifier])
    return True
