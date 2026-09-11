[app]
title = CelS - Scrcpy Heartbeat
package.name = scrcpyheartbeat
package.domain = henryjayz.celsuite
source.dir = android
source.include_exts = py,png,jpg,kv,atlas,jpeg
version = 269.11.0
android.numeric_version = 269.11.0
requirements = python3,kivy==2.2.1,pyjnius
orientation = portrait
fullscreen = 0
osx.python_version = 3
osx.kivy_version = 1.11.1
android.archs = arm64-v8a
p4a.hook = p4a_hook.py

android.gradle_dependencies = dev.rikka.shizuku:api:13.1.5, dev.rikka.shizuku:provider:13.1.5
android.add_repositories = mavenCentral()
android.enable_androidx = True
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,moe.shizuku.manager.permission.API_V23
android.meta_data = moe.shizuku.client.V3_SUPPORT=true,com.thedjchi.shizuku.client.V3_SUPPORT=true
android.api = 33
android.minapi = 26
android.ndk_api = 26
android.ndk = 25b
p4a.branch = v2024.01.21
android.accept_sdk_license = True
android.add_src = android/src/java
android.application = org.kivy.android.ScrcpyApplication
android.entrypoint = henryjayz.celsuite.scrcpyheartbeat.ScrcpyActivity
android.activity_class_name = henryjayz.celsuite.scrcpyheartbeat.ScrcpyActivity

# App icon - use local icon in repo
icon.filename = icon.png

# Size optimizations - exclude unused directories and patterns
android.exclude_dirs = tests,__pycache__,.git,.github,docs,examples
android.exclude_patterns = *.pyc,*.pyo,*.pyd,*.so,*.dylib,*.dll,*.a,*.lib

# Conservative exclusions - only exclude truly unused large modules
android.exclude_modules = tkinter,test,unittest,doctest,pdb,profile,cProfile,lib2to3,distutils,venv,ensurepip
