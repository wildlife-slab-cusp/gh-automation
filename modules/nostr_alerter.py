# Multi-relay broadcaster with confirmation (tries one by one)

import sys
import os
import ssl
import time
import datetime
import json

# Add vendor path - go up one level from modules/ to repo root, then into vendor/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor"))

from nostr.event import Event
from nostr.relay_manager import RelayManager
from nostr.key import PrivateKey

# Ordered relay list (damus.io first)
RELAY_URLS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.snort.social",
    "wss://relay.0xchat.com",
    "wss://auth.nostr1.com",
    "wss://relay.nostr.band",
]


def send_encrypted_alert(message: str) -> None:
    """Send encrypted Nostr DM using a list of relays until one confirms."""

    sender_key_hex = os.getenv("NOSTR_SENDER_PRIVATE_KEY_HEX")
    receiver_key_hex = os.getenv("NOSTR_RECEIVER_PUBLIC_KEY_HEX")

    if not sender_key_hex or not receiver_key_hex:
        print("[nostr_alerter] DM failed: missing Nostr environment variables", file=sys.stderr)
        sys.exit(1)

    if not message.strip():
        print("[nostr_alerter] DM failed: empty message", file=sys.stderr)
        sys.exit(1)

    try:
        private_key = PrivateKey(bytes.fromhex(sender_key_hex))
        sender_public_key = private_key.public_key
    except Exception as e:
        print(f"[nostr_alerter] DM failed: key error: {e}", file=sys.stderr)
        sys.exit(1)

    # Create unique message
    current_time = datetime.datetime.now().strftime("%H:%M")
    unique_message = f"{current_time} {message}"

    try:
        encrypted_content = private_key.encrypt_message(unique_message, receiver_key_hex)
    except Exception as e:
        print(f"[nostr_alerter] DM failed: encryption error: {e}", file=sys.stderr)
        sys.exit(1)

    event = Event(
        content=encrypted_content,
        public_key=sender_public_key.hex(),
        kind=4,
        tags=[["p", receiver_key_hex]],
    )

    private_key.sign_event(event)

    # Try each relay in order
    for relay_url in RELAY_URLS:
        relay_manager = RelayManager()
        relay_manager.add_relay(relay_url)
        relay_manager.open_connections({"cert_reqs": ssl.CERT_REQUIRED})

        time.sleep(2)  # wait for connection
        relay_obj = relay_manager.relays.get(relay_url)

        if not (relay_obj and relay_obj.ws and relay_obj.ws.sock and relay_obj.ws.sock.connected):
            relay_manager.close_connections()
            continue  # try next relay

        try:
            relay_obj.publish(event.to_message())
        except Exception:
            relay_manager.close_connections()
            continue  # try next relay

        # Wait for confirmation
        confirmed = False
        start_time = time.time()

        while time.time() - start_time < 10:  # 10s timeout
            # read raw ws messages directly
            if relay_obj.ws and relay_obj.ws.sock and relay_obj.ws.sock.connected:
                try:
                    raw_msg = relay_obj.ws.sock.recv()
                    if raw_msg:
                        try:
                            msg = json.loads(raw_msg.decode() if isinstance(raw_msg, (bytes, bytearray)) else raw_msg)
                            if (
                                isinstance(msg, list)
                                and len(msg) >= 3
                                and msg[0] == "OK"
                                and msg[1] == event.id
                            ):
                                if msg[2] is True:
                                    print(f"[nostr_alerter] DM confirmed: {relay_url.replace('wss://', '')}")
                                    relay_manager.close_connections()
                                    sys.exit(0)
                                else:
                                    relay_manager.close_connections()
                                    break  # try next relay
                        except Exception:
                            pass
                except Exception:
                    pass
            time.sleep(0.2)

        relay_manager.close_connections()

    # If all relays exhausted
    print("[nostr_alerter] DM failed: all relays exhausted", file=sys.stderr)
    sys.exit(1)


def main():
    """Entry point"""
    if len(sys.argv) != 2:
        print("Usage: python nostr_alerter.py 'message'", file=sys.stderr)
        sys.exit(1)

    message = sys.argv[1]
    send_encrypted_alert(message)


if __name__ == "__main__":
    main()