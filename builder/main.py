# Copyright 2022-present Maximilian Gerhardt <maximilian.gerhardt@rub.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import subprocess
import json
import semantic_version
from platform import system
from os import makedirs
from os.path import basename, isdir, join, isfile

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

from platformio.util import get_serial_ports
from platformio.package.version import get_original_version, pepver_to_semver


def BeforeUpload(target, source, env):  # pylint: disable=W0613,W0621
    env.AutodetectUploadPort()

    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})

    if not bool(upload_options.get("disable_flushing", False)):
        env.FlushSerialBuffer("$UPLOAD_PORT")

    before_ports = get_serial_ports()

    if bool(upload_options.get("use_1200bps_touch", False)):
        env.TouchSerialPort("$UPLOAD_PORT", 1200)

    if bool(upload_options.get("wait_for_upload_port", False)):
        env.Replace(UPLOAD_PORT=env.WaitForNewSerialPort(before_ports))

env = DefaultEnvironment()
env.SConscript("compat.py", exports="env")
platform = env.PioPlatform()
board = env.BoardConfig()

env.Replace(
    AR="arm-none-eabi-gcc-ar",
    AS="arm-none-eabi-as",
    CC="arm-none-eabi-gcc",
    CXX="arm-none-eabi-g++",
    GDB="arm-none-eabi-gdb",
    OBJCOPY="arm-none-eabi-objcopy",
    RANLIB="arm-none-eabi-gcc-ranlib",
    SIZETOOL="arm-none-eabi-size",

    ARFLAGS=["rc"],

    SIZEPROGREGEXP=r"^(?:\.text|\.data|\.rodata|\.init_section|\.ARM.exidx)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.bss|\.noinit)\s+(\d+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',
    SPKSIZEPRINTCMD='%s %s "$SOURCES"' % (
        '"$PYTHONEXE"',
        '"%s"' % join(platform.get_package_dir("tool-spresense") or "", "getspkinfo", "src", "getspkinfo.py"),
    ),

    PROGSUFFIX=".elf"
)

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

# for referencing the right precompiled tool in spresense-tools
os_folder_map = {
    "Windows": "windows",
    "Linux": "linux",
    "Darwin": "macosx"
}
os_folder = os_folder_map.get(system(), "unknown_os")

env.Append(
    BUILDERS=dict(
        ElfToBin=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "binary",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".bin"
        ),
        ElfToHex=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-R",
                ".eeprom",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".hex"
        ),
        ElfToSpk=Builder(
            action=env.VerboseAction(" ".join([
                join(platform.get_package_dir("tool-spresense") or "", "mkspk", os_folder, "mkspk.exe" if system() == "Windows" else "mkspk"),
                "-c",
                "2",
                "$SOURCES",
                "$FLASH_NAME",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".spk"
        )
    )
)

if not env.get("PIOFRAMEWORK"):
    env.SConscript("frameworks/_bare.py")

#
# Target: Build executable and linkable firmware
#

target_elf = None
target_spk = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.bin")
    target_spk = join("$BUILD_DIR", "${PROGNAME}.spk")
else:
    target_elf = env.BuildProgram()
    target_firm = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    target_spk = env.ElfToSpk(join("$BUILD_DIR", "${PROGNAME}"), target_elf)

bootloader_actions = None
erase_actions = None
if "bootloader" in COMMAND_LINE_TARGETS:
    SDK_DIR = platform.get_package_dir("tool-arduinosonyspresensesdk")
    firmware_dir = join(SDK_DIR, "firmware")
    fw_files = [
        "loader.espk",
        "gnssfw.espk",
        "dnnrt-mp.espk",
        "AESM.espk",
        "sysutil.spk",
    ]
    bootloader_actions = [ 
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload port..."),
        env.VerboseAction(" ".join([
            '"$PYTHONEXE"',
            '"%s"' % join(platform.get_package_dir("tool-spresense") or "", "flash_writer", "scripts", "flash_writer.py"),
            "-b", str(board.get("upload.speed", "115200")),
            "-c", 
            '"$UPLOAD_PORT"',
            "-d",
            "-n"] + ['"%s"' % join(firmware_dir, fw) for fw in fw_files]
        ), "Burning bootloader")
    ]
if "erase" in COMMAND_LINE_TARGETS:
    erase_targets = ["nuttx"] + ["sub" + str(i) for i in range(1, 6)]
    erase_actions = [ 
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload port..."),
        env.VerboseAction(" ".join([
            '"$PYTHONEXE"',
            '"%s"' % join(platform.get_package_dir("tool-spresense") or "", "flash_writer", "scripts", "flash_writer.py"),
            "-b", str(board.get("upload.speed", "115200")),
            "-c", 
            '"$UPLOAD_PORT"',
            "-d",
            "-n",
            "-e", "nuttx",
            "-e", "sub1",
            "-e", "sub2",
            "-e", "sub3",
            "-e", "sub4",
            "-e", "sub5",
        ]), "Erasing flash")
    ]

env.AddPlatformTarget("bootloader", None, bootloader_actions, "Burn Bootloader")
env.AddPlatformTarget("erase", None, erase_actions, "Erase")

AlwaysBuild(env.Alias("nobuild", [target_firm, target_spk]))
target_buildprog = env.Alias("buildprog", [target_firm, target_spk])

#
# Target: Print binary size
#

target_size = env.Alias(
    "size", target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"))
target_spk_size = env.Alias(
    "spksize", target_spk,
    env.VerboseAction("$SPKSIZEPRINTCMD", "Printing size $SOURCE"))
env.Depends("checkprogsize", target_spk_size)
AlwaysBuild(target_size)
AlwaysBuild(target_spk_size)

#
# Target: Upload by default .bin file
#

upload_protocol = env.subst("$UPLOAD_PROTOCOL")
debug_tools = board.get("debug.tools", {})
upload_source = target_firm
upload_actions = []

if upload_protocol == "mbed":
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload disk..."),
        env.VerboseAction(env.UploadToDisk, "Uploading $SOURCE")
    ]

elif upload_protocol.startswith("blackmagic"):
    env.Replace(
        UPLOADER="$GDB",
        UPLOADERFLAGS=[
            "-nx",
            "--batch",
            "-ex", "target extended-remote $UPLOAD_PORT",
            "-ex", "monitor %s_scan" %
            ("jtag" if upload_protocol == "blackmagic-jtag" else "swdp"),
            "-ex", "attach 1",
            "-ex", "load",
            "-ex", "compare-sections",
            "-ex", "kill"
        ],
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS $SOURCE"
    )
    upload_source = target_elf
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for BlackMagic port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]

elif upload_protocol == "serial":
    def __configure_upload_port(env):
        return env.subst("$UPLOAD_PORT")

    env.Replace(
        __configure_upload_port=__configure_upload_port,
        UPLOADER=" ".join([
            '"$PYTHONEXE"',
            '"%s"' % join(platform.get_package_dir("tool-spresense") or "", "flash_writer", "scripts", "flash_writer.py"),
            ]),
        UPLOADERFLAGS=[
            "-s", 
            "-b", board.get("upload.speed", "115200"),
            "-d",
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -c "${__configure_upload_port(__env__)}" -n "$SOURCE"'
    )

    upload_source = target_spk
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]

elif upload_protocol in debug_tools:

    openocd_args = [
        "-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)
    ]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
    if env.GetProjectOption("debug_speed"):
        openocd_args.extend(
            ["-c", "adapter speed %s" % env.GetProjectOption("debug_speed")]
        )
    openocd_args.extend([
        "-c", "program {$SOURCE} %s verify reset; shutdown;" %
        board.get("upload.offset_address", "")
    ])
    openocd_args = [
        f.replace("$PACKAGE_DIR",
                  platform.get_package_dir("tool-openocd") or "")
        for f in openocd_args
    ]
    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")

    if not board.get("upload").get("offset_address"):
        upload_source = target_elf
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias("upload", upload_source, upload_actions))

#
# Information about obsolete method of specifying linker scripts
#

if any("-Wl,-T" in f for f in env.get("LINKFLAGS", [])):
    print("Warning! '-Wl,-T' option for specifying linker scripts is deprecated. "
          "Please use 'board_build.ldscript' option in your 'platformio.ini' file.")

#
# Install wxPython dependency of tool-spresense
#
def install_python_deps():
    def _get_installed_pip_packages():
        result = {}
        packages = {}
        pip_output = subprocess.check_output(
            [env.subst("$PYTHONEXE"), "-m", "pip", "list", "--format=json"]
        )
        pip_output = pip_output.decode('latin-1').strip()
        if "[notice]" in pip_output:
            ind = pip_output.index("[notice]")
            pip_output = pip_output[:ind].strip()
        try:
            packages = json.loads(pip_output)
        except Exception as exc:
            print("Warning! Couldn't extract the list of installed Python packages.")
            print("Output: " + str(pip_output))
            print("Exception: " + repr(exc))
            return {}
        for p in packages:
            result[p["name"]] = pepver_to_semver(p["version"])

        return result

    deps = {
        "wxPython": ">=4.1.0",
    }

    installed_packages = _get_installed_pip_packages()
    packages_to_install = []
    for package, spec in deps.items():
        if package not in installed_packages:
            packages_to_install.append(package)
        else:
            version_spec = semantic_version.Spec(spec)
            if not version_spec.match(installed_packages[package]):
                packages_to_install.append(package)

    if packages_to_install:
        env.Execute(
            env.VerboseAction(
                (
                    '"$PYTHONEXE" -m pip install -U --force-reinstall '
                    + " ".join(['"%s%s"' % (p, deps[p]) for p in packages_to_install])
                ),
                "Installing Spresense tools's Python dependencies (wxPython)",
            )
        )

install_python_deps()

#
# Default targets
#

Default([target_buildprog, target_size])
