# Matrix Extended v0.3 Interactive Design

## Goal
Add safe bidirectional Matrix interaction while preserving v0.2 E2EE behavior.

## Boundaries
- Inbound events require both user and room allowlists.
- Echoes from this Matrix device are ignored using transaction IDs.
- Arbitrary inbound text never invokes Home Assistant services.
- Reaction actions only execute service calls explicitly attached by HA to a specific outbound event and are one-shot.
- Inbound encrypted media is decrypted locally after an authorized sender/room check.

## Surfaces
Services: send, reply, react, edit, redact.
HA events: matrix_extended_message, matrix_extended_reply, matrix_extended_reaction, matrix_extended_media.
Options: require E2EE, incoming enable, allowed users, allowed rooms, incoming media download.
