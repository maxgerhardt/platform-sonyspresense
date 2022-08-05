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
import copy
import json
import os

from platform import system

from platformio.managers.platform import PlatformBase
from platformio.util import get_systype

class SonyspresensePlatform(PlatformBase):

    def configure_default_packages(self, variables, targets):
        board = variables.get("board")
        board_config = self.board_config(board)
        default_protocol = board_config.get("upload.protocol") or ""
        frameworks = variables.get("pioframework", [])
        # we need the SDK to build the Arduino core
        if "arduino" in frameworks:
            self.packages["tool-arduinosonyspresensesdk"]["optional"] = False

        return PlatformBase.configure_default_packages(self, variables,
                                                       targets)

    def get_boards(self, id_=None):
        result = PlatformBase.get_boards(self, id_)
        if not result:
            return result
        if id_:
            return self._add_default_debug_tools(result)
        else:
            for key, value in result.items():
                result[key] = self._add_default_debug_tools(result[key])
        return result

    def _add_default_debug_tools(self, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        # BlackMagic, J-Link, CMSIS-DAP
        # Note that ST-Link cannot be support because it cannot access an AP other than 0,
        # and the 6 cores of the chip are all on different APs starting at 3.
        for link in ("blackmagic", "jlink", "cmsis-dap"):
            if link not in upload_protocols or link in debug["tools"]:
                continue
            if link == "blackmagic":
                debug["tools"]["blackmagic"] = {
                    "hwids": [["0x1d50", "0x6018"]],
                    "require_debug_port": True
                }
            else:
                # add our openocd config files to the search path
                server_args = ["-s", "$PACKAGE_DIR/scripts", "-s", os.path.join(os.path.dirname(os.path.realpath(__file__)), "misc", "openocd")]
                assert debug.get("openocd_target"), (
                    "Missed target configuration for %s" % board.id)
                server_args.extend([
                    "-f", "interface/%s.cfg" % link,
                    "-c", "transport select swd",
                ])
                server_args.extend(debug.get("openocd_extra_pre_target_args", []))
                server_args.extend([
                    "-f", "%s.cfg" % debug.get("openocd_target")
                ])
                server_args.extend(debug.get("openocd_extra_args", []))

                debug["tools"][link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": server_args
                    }
                }
                # todo: add "init_cmds" argument with https://github.com/sonydevworld/spresense/blob/master/sdk/tools/.gdbinit
                # to get NuttX thread support
            debug["tools"][link]["onboard"] = link in debug.get("onboard_tools", [])
            debug["tools"][link]["default"] = link in debug.get("default_tools", [])

        board.manifest["debug"] = debug
        return board

    def configure_debug_options(self, initial_debug_options, ide_data):
        debug_options = copy.deepcopy(initial_debug_options)
        adapter_speed = initial_debug_options.get("speed")
        if adapter_speed:
            server_options = debug_options.get("server") or {}
            server_executable = server_options.get("executable", "").lower()
            if "openocd" in server_executable:
                debug_options["server"]["arguments"].extend(
                    ["-c", "adapter speed %s" % adapter_speed]
                )
        return debug_options
