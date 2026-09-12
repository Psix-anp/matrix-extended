# Disposable Synapse E2E server

The CI harness generates a fresh Synapse configuration into `.ci/synapse-data`
using the pinned `matrixdotorg/synapse:v1.160.0` image. The generated config is
patched only for the disposable E2E server: public registration stays disabled,
while a one-time shared-registration secret is stored in `.ci/synapse-shared-secret`
(mode `0600`) for bootstrap scripts. Nothing under `.ci/` is committed.
