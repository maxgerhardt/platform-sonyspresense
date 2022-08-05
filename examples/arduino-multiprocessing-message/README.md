Multi Processing Message Example
================================

**Important:** This example's `platformio.ini` contains two configurations:
1. `spresense_mainCore` for the main core
2. `spresense_subCore1` for the sub core 1

**Both** firmwares must be built and uploaded for this sketch to work. Use the [project tasks](https://docs.platformio.org/en/latest/integration/ide/vscode.html#project-tasks) for each respective environment for this, and switch into the environment you want to work in with the project environment switcher detailed in the last link.

How to build PlatformIO based project
=====================================

1. [Install PlatformIO Core](https://docs.platformio.org/page/core.html)
2. Download [development platform with examples](https://github.com/maxgerhardt/platform-sonyspresense/archive/main.zip)
3. Extract ZIP archive
4. Run these commands:

```shell
# Change directory to example
$ cd platform-sonyspresense/examples/arduino-blink

# Build project
$ pio run

# Upload firmware
$ pio run --target upload

# Build specific environment
$ pio run -e spresense_mainCore
$ pio run -e spresense_subCore1

# Upload firmware for the specific environment
$ pio run -e spresense_mainCore --target upload
$ pio run -e spresense_subCore1 --target upload

# Clean build files
$ pio run --target clean
```
