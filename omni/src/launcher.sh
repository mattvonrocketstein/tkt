#!/bin/sh
# tkt, as a file a host can execute: runs the tkt binary, or hands the tkt library to a plugin that sources it.
if [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE:-}" != "$0" ]; then
  source /zip/libexec/tkt
  return
fi
# fossil clears the environment for a CGI program; serve left the one to restore beside the tracker
if [ -n "${GATEWAY_INTERFACE:-}" ] && [ -z "${HOME:-}" ] && [ -r "${DOCUMENT_ROOT:-}/../serve.env" ]; then
  . "$DOCUMENT_ROOT/../serve.env"
fi
export PATH="${PATH:-/usr/bin:/bin}"
export TKT_SELF='@LAUNCHER@'
exec '@SELF@' "$@"
