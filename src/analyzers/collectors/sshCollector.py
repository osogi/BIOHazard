from __future__ import annotations
from argparse import Namespace
from queue import Queue
import logging
import random
import stat
from pathlib import Path
import sys
import time
from typing import Dict, List

import paramiko

from src.analyzers.collectors.perfParser import PerfParser, TestRes
from src.helpers.backGroundBuilder import CSignal


class SshCollector:
    def __init__(self, settings: Namespace, bin_dir: Path | None = None):
        self.settings = settings
        self.max_test_launches = settings.__dict__.get("max_test_launches", -1)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.settings.log_level)
        self.is_tmp_created = False

        host = settings.__dict__.get("host", "127.0.0.1")
        user = settings.__dict__.get("username", "root")
        path_to_key = settings.__dict__.get("path_to_key", "~/.ssh/id_rsa")
        password = settings.__dict__.get("password", "toor")

        self.sftp: paramiko.SFTPClient

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=user, key_filename=path_to_key, password=password)

        transport = client.get_transport()
        if transport is None:
            raise Exception("Can't get transport for ssh")

        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            raise Exception("Can't open sftp session")

        self.transport = transport
        self.sftp = sftp
        self.client = client

        if bin_dir is None:
            bin_dir = self.mkdtemp()
            self.is_tmp_created = True
        self.bin_dir = bin_dir

    # TODO: understand why it isn't called
    def __del__(self):
        if self.is_tmp_created:
            c = self.execute_command(f"rm -r {self.bin_dir}")
            c.recv_exit_status()

        # TODO: find how to find out if it is defined or not, may be try catch
        if self.sftp is not None:
            self.sftp.close()

        if self.client is not None:
            self.client.close()

    def execute_command(self, comm: str) -> paramiko.Channel:
        chan = self.transport.open_session()
        self.logger.info(f"Executing: {comm}")
        chan.exec_command(comm)
        return chan

    def mkdtemp(self) -> Path:
        tmpdir = f"/tmp/chapy-{random.getrandbits(16)}"
        self.sftp.mkdir(tmpdir)
        return Path(tmpdir)

    def tab_lines(self, lines: str):
        return "\t" + lines.replace("\n", "\n\t")[:-1]

    def execute_test(self, execute_line: List[str], timeout: float) -> TestRes:
        execute_str = " ".join(execute_line)
        chan = self.execute_command(f"timeout -s SIGINT {timeout}s {execute_str}")

        is_full = True
        ret_code = chan.recv_exit_status()
        if ret_code == 2:
            is_full = False
            ret_code = 0

        com_stderr = chan.makefile_stderr()
        test_errors = com_stderr.read().decode()
        if (len(test_errors) > 0) and (not test_errors.isspace()):
            print(f"[-]: Some error occurred during launching '{execute_str}':", file=sys.stderr)
            print(self.tab_lines(test_errors), file=sys.stderr, end="")
        if ret_code != 0:
            print(
                "[?]: Maybe perf don't have enough capabilities or your CPU don't have special debug counters\n",
                file=sys.stderr,
            )
        return (chan.recv(1024), is_full)

    def get_stat(self, binary: Path, number_executes: int, cpu_core: int = 0) -> List[TestRes]:
        stats: List[TestRes] = []
        execute_line = list(map(str, [binary, cpu_core]))
        execute_string = " ".join(map(str, execute_line))
        self.logger.info(f"[sshProfiler]: Executing: {execute_string}")

        left_time = self.settings.timeout
        timeout = time.time() + self.settings.timeout
        while (left_time > 0) and (number_executes != 0):
            stats.append(self.execute_test(execute_line, left_time))
            left_time = timeout - time.time()
            number_executes -= 1
        return stats

    def update_capabilities(self, target_file: Path):
        # use_sudo = False
        suc_launch = False
        used_max_perm = False

        execute_line = ["setcap", "-q", "cap_sys_admin,cap_sys_nice=ep", str(target_file)]
        while (not suc_launch) and (not used_max_perm):
            # TODO: need think how to check that sudo on server is waiting for password or not.
            # if use_sudo:
            #     execute_line = ["sudo"] + execute_line
            used_max_perm = True

            chan = self.execute_command(" ".join(execute_line))
            returncode = chan.recv_exit_status()
            if returncode == 0:
                suc_launch = True
            else:
                if used_max_perm:
                    proc_err = chan.makefile_stderr().read().decode()
                    print(f"[-]: Error during seting capability:\n {self.tab_lines(proc_err)}", file=sys.stderr)
                # use_sudo = True

    def send_binary(self, loc_path: Path, host_path: Path):
        self.sftp.put(str(loc_path), str(host_path))
        self.sftp.chmod(str(host_path), stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH)

    def collect(self, build_channel: Queue[CSignal.End | CSignal.BuiltFile]) -> Dict[str, Dict]:
        analyzed: Dict[str, List[TestRes]] = {}

        while True:
            sign = build_channel.get()
            match sign:
                case CSignal.End():
                    break
                case CSignal.BuiltFile(binary):
                    host_binary = self.bin_dir.joinpath(binary.name)
                    self.send_binary(binary, host_binary)
                    self.update_capabilities(host_binary)
                    data = self.get_stat(host_binary, self.max_test_launches)
                    analyzed[host_binary.name.split(".")[0]] = data
                case _:
                    raise Exception(f"Get unexpected channel signal {sign}")

        return PerfParser.correct(analyzed)
