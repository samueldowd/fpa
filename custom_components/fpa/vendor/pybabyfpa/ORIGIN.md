# Maintained pybabyfpa protocol subset

Origin: [joncar/pybabyfpa](https://github.com/joncar/pybabyfpa), MIT license,
copyright 2021 Jon Caruana. Reviewed upstream revision:
`8f91cdbc38025d753dcd437f15fedeea5c63253a` (version 0.0.7).

The adjacent LICENSE preserves the original license and attribution. This
integration distributes the controlled protocol subset locally; it does not load
or modify an installed PyPI copy.

Changes:

- Keep the existing cloud discovery, authentication, account/details read,
  saved-preset start and `shadow-update` WebSocket protocol endpoints.
- Return independent wire dictionaries to the integration's typed state layer;
  preserve heating/cooling and last-preparation fields rather than dropping them.
- Require an injected shared HTTP session and leave its lifetime with the caller.
- Add finite HTTP/handshake/close timeouts, typed errors with safe text, and
  serialized refresh-token rotation with a persistence callback.
- Own one idempotent listener per device. Include establishment failures in capped
  reconnect backoff, validate message identity, and tolerate malformed messages.
- Deliver owned unknown JSON subjects for sanitized diagnostic capture while
  excluding authentication/transport-control frames and unassociated messages.
- Notify a safe runtime error callback when listeners fail. A rejected reconnect
  refresh invalidates cached authentication; an expired socket access token first
  gets a refresh attempt before account reauthentication is requested.
- Delegate ping/heartbeat scheduling to each aiohttp WebSocket. Closing that owned
  socket stops its heartbeat; close cancels and awaits all owned listeners/backoff.
- Never replay dispensing writes and never log raw responses, errors, credentials,
  identities, headers or credential-bearing WebSocket URLs.
- Remove old device object/merge/presentation helpers. Device state, preparation
  history and command safety belong to the integration runtime.

Keep future edits restricted to this boundary so the client can be extracted or
upstreamed without tying its API to Home Assistant.
