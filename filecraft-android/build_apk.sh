#!/usr/bin/env bash
# FileCraft Android 壳打包：免 Gradle，直接用本机 Android SDK 工具链。
# aapt2 编译链接 → javac → d8 → 装包 → zipalign → apksigner 签名。
set -euo pipefail
cd "$(dirname "$0")"

SDK="$(cygpath -u "$LOCALAPPDATA")/Android/Sdk"
BT="$SDK/build-tools/35.0.0"
AJAR="$SDK/platforms/android-34/android.jar"
export JAVA_HOME="/c/Program Files/Android/Android Studio/jbr"
export PATH="$JAVA_HOME/bin:$PATH"

VERSION_NAME="1.0.0"
VERSION_CODE=1
OUT="FileCraft-v${VERSION_NAME}.apk"
BUILD=build

rm -rf "$BUILD"
mkdir -p "$BUILD/classes" "$BUILD/gen" "$BUILD/dex"

echo "[1/6] aapt2 compile resources"
"$BT/aapt2.exe" compile --dir res -o "$BUILD/res.zip"

echo "[2/6] aapt2 link"
"$BT/aapt2.exe" link -o "$BUILD/base.apk" \
  -I "$AJAR" \
  --manifest AndroidManifest.xml \
  --min-sdk-version 24 --target-sdk-version 34 \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" \
  --java "$BUILD/gen" \
  "$BUILD/res.zip"

echo "[3/6] javac"
find src "$BUILD/gen" -name "*.java" > "$BUILD/sources.txt"
if ! javac -source 1.8 -target 1.8 -encoding UTF-8 -classpath "$AJAR" \
     -d "$BUILD/classes" @"$BUILD/sources.txt" 2> "$BUILD/javac.log"; then
  cat "$BUILD/javac.log"
  exit 1
fi
grep -iE "warning|deprecat" "$BUILD/javac.log" | head -3 || true

echo "[4/6] d8 dex"
find "$BUILD/classes" -name "*.class" > "$BUILD/classes.txt"
# shellcheck disable=SC2046
"$BT/d8.bat" --release --min-api 24 --lib "$AJAR" --output "$BUILD/dex" \
  $(cat "$BUILD/classes.txt")

echo "[5/6] package + zipalign"
python - "$BUILD" <<'PY'
import sys, zipfile, shutil, os
b = sys.argv[1]
shutil.copyfile(os.path.join(b, "base.apk"), os.path.join(b, "unsigned.apk"))
with zipfile.ZipFile(os.path.join(b, "unsigned.apk"), "a", zipfile.ZIP_DEFLATED) as z:
    z.write(os.path.join(b, "dex", "classes.dex"), "classes.dex")
print("classes.dex added")
PY
"$BT/zipalign.exe" -f -p 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk"

echo "[6/6] sign"
if [ ! -f debug.keystore ]; then
  keytool -genkeypair -keystore debug.keystore -alias filecraft \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass filecraft123 -keypass filecraft123 \
    -dname "CN=FileCraft, OU=Dev, O=vibenav, C=CN"
fi
"$BT/apksigner.bat" sign --ks debug.keystore \
  --ks-pass pass:filecraft123 --key-pass pass:filecraft123 \
  --out "$OUT" "$BUILD/aligned.apk"
"$BT/apksigner.bat" verify "$OUT"
echo "== done: $OUT =="
