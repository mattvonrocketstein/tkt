# The omnibus entry: give tkt a path to itself that a host can execute, name the plugins the binary carries, run the script.
self=${COSMOPOLITAN_INIT_ZIPOS:?not started by the tkt binary}
shipped=/zip/share/tkt/plugins
script=/zip/libexec/tkt
# the binary's tools, first on PATH, for tkt to keep when it resets PATH while serving a web request
if [ -x "${PATH%%:*}/fossil" ]; then export TKT_PATH=${PATH%%:*}; fi
# a caller that put a directory of its own ahead of those tools keeps that order, though the binary put them first again
case ":${PATH#*:}:" in *":${PATH%%:*}:"*) export PATH=${PATH#*:} ;; esac

# the launcher: a host shell script that is tkt to fossil, to jobs and to plugins, since nothing runs from /zip
if [ -z "${TKT_SELF:-}" ]; then
  launcher=${XDG_CACHE_HOME:-$HOME/.cache}/tkt/${self//\//%}
  if [ ! -x "$launcher" ] || ! cmp -s "$launcher" <(sed "s|@SELF@|$self|g; s|@LAUNCHER@|$launcher|g" /zip/libexec/launcher.sh); then
    mkdir -p "${launcher%/*}"
    sed "s|@SELF@|$self|g; s|@LAUNCHER@|$launcher|g" /zip/libexec/launcher.sh >"$launcher.$$"
    chmod +x "$launcher.$$"
    mv "$launcher.$$" "$launcher"
  fi
  export TKT_SELF=$launcher
fi

# micropython by that name, for a plugin whose entry asks for it: the binary's own, since a host need not have one
names=$TKT_SELF.bin
if [ ! -x "$names/micropython" ] || ! grep -qF "'$self'" "$names/micropython"; then
  mkdir -p "$names"
  printf '#!/bin/sh\nexec %s --micropy "$@"\n' "'$self'" >"$names/micropython.$$"
  chmod +x "$names/micropython.$$"
  mv "$names/micropython.$$" "$names/micropython"
fi
case ":$PATH:" in *":$names:"*) ;; *) export PATH=$names:$PATH ;; esac
case ":${TKT_PATH:-}:" in *":$names:"*) ;; *) export TKT_PATH=${TKT_PATH:+$TKT_PATH:}$names ;; esac

# the plugins the binary carries are found in place, after the tracker's own and any the caller already named
case ":${TKT_PLUGINS:-}:" in
  *":$shipped:"*) ;;
  *) export TKT_PLUGINS=${TKT_PLUGINS:+$TKT_PLUGINS:}$shipped ;;
esac

# fossil clears the environment of every program it starts for a web request, so the launcher restores this one
if [ "${1:-}" = serve ]; then
  { read -r repo; read -r home; } < <( (source "$script" && locate && printf '%s\n%s\n' "$REPO" "$TKT_DIR") 2>/dev/null)
  if [ -n "$home" ] && [ -f "$repo" ]; then
    mkdir -p "$home"
    (
      umask 077
      for name in HOME XDG_CACHE_HOME PATH LANG LC_ALL TMPDIR; do
        [ -n "${!name:-}" ] || continue
        value=${!name}
        printf "export %s='%s'\n" "$name" "${value//\'/\'\\\'\'}"
      done >"$home/serve.env.$$"
      mv "$home/serve.env.$$" "$home/serve.env"
    )
  fi
fi

exec bash "$script" "$@"
