#!/usr/bin/env bash
# Download pinned jars from Maven Central and verify each against its published SHA-1.
set -euo pipefail
LOCK="$1"; DEST="$2"; mkdir -p "$DEST"
REPO="https://repo1.maven.org/maven2"
grep -v '^#' "$LOCK" | grep -v '^\s*$' | while IFS=: read -r g a v; do
  path="${REPO}/${g//.//}/${a}/${v}/${a}-${v}.jar"
  out="${DEST}/${a}-${v}.jar"
  curl -fsSL --retry 5 --retry-delay 3 -o "$out" "$path"
  expected="$(curl -fsSL --retry 5 "${path}.sha1" | awk '{print $1}')"
  actual="$(sha1sum "$out" | awk '{print $1}')"
  if [ "$expected" != "$actual" ]; then echo "SHA1 mismatch for $a-$v: $expected != $actual" >&2; exit 1; fi
  echo "verified $a-$v sha1=$actual"
done
