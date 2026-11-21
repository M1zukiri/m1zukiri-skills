---
name: stacks/flutter
inline-when:
  any:
    - has-file: "**/pubspec.yaml"
    - project-flag: flutter
exclude-when:
  any:
    - project-flag: no-flutter
last-verified: 2026-11-21
---

# stacks/flutter

**适用**：Dart / Flutter 实现的移动端或桌面端入口。
**来源**：notekiri（Flutter 3.47 / Dart 3.13）、mozunitor（Android 构建与 WebView 认证）。

<!-- anchor: toolchain -->
## 工具链

- Flutter / Dart / platform / build-tools 的版本必须**成套**记录；缺 build-tools 时报的是
  「No valid Android SDK platforms found」，与 platform 本身无关。
- 项目路径含非 ASCII 字符会让 AGP 在配置阶段失败：
  `mobile/android/gradle.properties` 里 `android.overridePathCheck=true` 实测能过
  `flutter build apk --debug`，但它只是绕过检查，aapt2 / NDK 层面仍可能出问题。
- 本机 `flutter analyze` 若因语言服务器崩溃不可用，用 `dart analyze` 替代，并在文档里写明
  这是本机限制而非项目问题。

<!-- anchor: plugins-security -->
## 插件与安全

- `flutter_secure_storage` 在部分 Windows 环境不可用；平台侧密钥优先用系统原生方案
  （Windows 上是 DPAPI）。
- WebView 场景要覆盖认证挑战（`onReceivedHttpAuthRequest`）；Cookie 与 basicAuth 的接管
  方式要按实际平台逐一验证，不要只测一个平台。
- 权限与存储的失败路径要有回退方案，不能让「加密存储不可用」变成启动崩溃。

<!-- anchor: layout-build -->
## 目录与构建

- `mobile/` 与后端分离；构建产物不入库。
- 发布前固定 `pubspec.lock`，记录 Flutter SDK 版本。
