#!/usr/bin/env bash
#
# Install cgm_insights into a Canvas sandbox.
#
# The one piece we cannot infer is your Canvas instance subdomain (e.g. for
# https://acme-dev.canvasmedical.com it is "acme-dev"). Pass it as the first
# argument. This script ensures ~/.canvas/credentials.ini has a section named
# exactly that subdomain (renaming a single placeholder section if needed,
# preserving your client_id/client_secret), then validates and installs.
#
# Usage:
#   scripts/install_to_sandbox.sh <canvas-subdomain> [nightscout_url] [nightscout_token]
#
# Nightscout values are optional; the plugin no-ops gracefully until they are
# set (you can also set them later with `canvas config set`).
#
set -euo pipefail

SUB="${1:-${CANVAS_SUBDOMAIN:-}}"
NS_URL="${2:-${NIGHTSCOUT_URL:-}}"
NS_TOKEN="${3:-${NIGHTSCOUT_TOKEN:-}}"

if [ -z "$SUB" ]; then
  echo "usage: $0 <canvas-subdomain> [nightscout_url] [nightscout_token]" >&2
  echo "  e.g. $0 acme-dev https://my-ns.example MY_READ_TOKEN" >&2
  exit 2
fi

CRED="$HOME/.canvas/credentials.ini"
if [ ! -f "$CRED" ]; then
  echo "error: $CRED not found. Create it with your client_id/client_secret first." >&2
  exit 1
fi

# Ensure a [<SUB>] section exists with client_id/client_secret. If there is
# exactly one section with a different name (e.g. the docs placeholder), rename
# it to <SUB>, preserving credentials.
python3 - "$SUB" "$CRED" <<'PY'
import configparser, sys
sub, path = sys.argv[1], sys.argv[2]
cp = configparser.ConfigParser()
cp.read(path)
secs = cp.sections()
if sub in cp:
    pass  # already correct
elif len(secs) == 1:
    old = secs[0]
    cp[sub] = dict(cp[old])
    cp.remove_section(old)
    print(f"renamed credentials section [{old}] -> [{sub}]")
else:
    raise SystemExit(
        f"error: no [{sub}] section and {len(secs)} sections present; "
        f"add a [{sub}] section with client_id/client_secret to {path}."
    )
cp[sub]["is_default"] = "true"
for key in ("client_id", "client_secret"):
    if not cp[sub].get(key):
        raise SystemExit(f"error: [{sub}] is missing {key} in {path}.")
with open(path, "w") as fh:
    cp.write(fh)
print(f"credentials section [{sub}] is ready (client_id/client_secret present).")
PY

echo "==> validating manifest"
canvas validate-manifest cgm_insights

INSTALL_ARGS=(cgm_insights --host "$SUB")
[ -n "$NS_URL" ]   && INSTALL_ARGS+=(--variable "NIGHTSCOUT_URL=$NS_URL")
[ -n "$NS_TOKEN" ] && INSTALL_ARGS+=(--variable "NIGHTSCOUT_TOKEN=$NS_TOKEN")

echo "==> installing into $SUB.canvasmedical.com"
canvas install "${INSTALL_ARGS[@]}"

echo "==> installed plugins on $SUB:"
canvas list --host "$SUB"

cat <<EOF

Done. Next:
  * Open a patient chart in Canvas  -> the CGM summary section renders.
  * Create an encounter note         -> triage card (+ hypo banner) and, when
                                         data is sufficient, the billing card.
  * Stream logs while you interact:  canvas logs --host $SUB
  * Set/update Nightscout config:    canvas config set cgm_insights \\
        NIGHTSCOUT_URL=https://my-ns.example NIGHTSCOUT_TOKEN=token --host $SUB
EOF
