[app]
android.accept_sdk_license = True
# (str) Title of your application
title = SpotiClone Pro

# (str) Package name
package.name = spoticlone

# (str) Package domain (needed for android/ios packaging)
package.domain = org.ganesh

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (letting it grab HTML and JSON)
source.include_exts = py,png,jpg,html,json

# (str) Application versioning
version = 1.0

# (list) Application requirements
requirements = python3,flask,requests,yt-dlp,ytmusicapi

# (str) Supported orientation
orientation = portrait

# (list) Permissions
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, WAKE_LOCK

# (list) The Android architectures to build for
android.archs = arm64-v8a, armeabi-v7a

# (bool) enables Android auto backup feature
android.allow_backup = True
