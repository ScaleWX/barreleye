#!/usr/bin/env python
import argparse
import glob
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from os import path


class Collectd:
    def __init__(self, conf, pid):
        self.pid = pid
        subprocess.check_call(
            ["collectd", "-C", conf, "-P", self.pid],
            stdout=sys.stdout.fileno(),
            stderr=sys.stderr.fileno(),
        )

    def stop(self):
        os.kill(int(open(self.pid, "r").read().strip()), signal.SIGTERM)


def parse_rrd(rrd):
    tree = ET.fromstring(
        subprocess.check_output(["rrdtool", "dump", rrd], stderr=sys.stderr.fileno())
    )

    return tree.find("ds").find("last_ds").text.strip().split(".")[0]


def check_result(logger, dmission, tests):
    failures = 0
    missings = 0
    successes = 0

    for test in tests.findall("test"):
        test_path = test.find("path").text
        test_pattern = test.find("pattern").text
        failed = False
        succeeded = False

        for rrd in glob.iglob(path.join(dmission, test_path)):
            content = parse_rrd(rrd)
            match = re.match(test_pattern, content)
            if match is None or match.end(0) != len(content):
                logger.info(
                    "FAIL: rrdtool file: '%s', Got: '%s', Expected '%s'"
                    % (rrd, content, test_pattern)
                )
                failed = True
            elif not failed:
                succeeded = True

        if succeeded:
            successes += 1
        elif failed:
            failures += 1
        else:
            logger.info("MISSING: rrdtool file '%s'does not exist" % test_path)
            missings += 1

    return failures, missings, successes


def make_conf(testconf, conf, data, definition, root, log, interval, hostname):
    inside_filedata = False
    file = open(testconf, "w")
    for line in open(conf, "r"):
        pattern_load_plugin = r'\s*loadPlugin\s+"write_tsdb"\s*'
        pattern_plugin_start = r'\s*<Plugin\s+"write_tsdb">\s*'
        pattern_plugin_end = r"\s*</Plugin>\s*"
        pattern_definition_file = r'\s*DefinitionFile\s+".+"\s*'
        pattern_log = r'\s*File\s+".+"\s*'
        pattern_interval = r"\s*Interval\s+\d+\s*"
        if re.match(pattern_load_plugin, line):
            continue
        elif inside_filedata:
            if re.match(pattern_plugin_end, line):
                inside_filedata = False
            continue
        elif re.match(pattern_plugin_start, line):
            inside_filedata = True
            continue
        elif re.match(pattern_definition_file, line):
            file.write("""DefinitionFile "%s"\n""" % definition)
            file.write("""Rootpath "%s"\n""" % root)
            continue
        elif re.match(pattern_log, line):
            file.write("""File "%s"\n""" % log)
            continue
        elif re.match(pattern_interval, line):
            file.write("""Interval %d\n""" % interval)
            continue
        else:
            file.write(line)
    file.write("""Hostname "%s"\n""" % hostname)
    file.write(
        """LoadPlugin rrdtool
<Plugin rrdtool>
Datadir "%s"
</Plugin>\n"""
        % data,
    )
    file.close()


def run():
    def receive_signal(signum, stack):
        collectd.stop()

    logger = logging.getLogger()
    logger.addHandler(logging.StreamHandler())
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log_level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="log level",
    )
    parser.add_argument(
        "--directory",
        "-d",
        default="/",
        help="working directory where pseduo stats directory is located",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="/etc/collectd.conf",
        help="collectd configuration file",
    )
    parser.add_argument(
        "--definition_file",
        "-f",
        default="/etc/lustre.xml",
        help="Lustre Definition file for collectd",
    )
    parser.add_argument(
        "--test_file",
        "-t",
        default="./tests.xml",
        help="test cases for verification",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=10,
        help="collectd collection interval",
    )
    parser.add_argument(
        "--hostname",
        "-n",
        default="collection",
        help="hostname for collection",
    )
    args = parser.parse_args()
    level = args.log_level
    definition = args.definition_file
    conf = args.config
    content = args.directory
    tests = ET.parse(args.test_file).getroot()
    interval = args.interval
    hostname = args.hostname
    dtemp = tempfile.mkdtemp()
    log = path.join(dtemp, "collectd.log")
    logger.setLevel(level)
    logger.info("working in %s", dtemp)
    logger.info("investigate and then delete the directory after running tests")

    pid = path.join(dtemp, "collectd.pid")
    test_conf = path.join(dtemp, "collectd.conf")

    make_conf(
        test_conf,
        conf,
        dtemp,
        path.abspath(definition),
        path.abspath(content),
        log,
        interval,
        hostname,
    )

    signal.signal(signal.SIGINT, receive_signal)
    signal.signal(signal.SIGTERM, receive_signal)

    collectd = Collectd(test_conf, pid)

    time.sleep(interval + 3)
    collectd.stop()

    failures, missings, successes = check_result(
        logger, path.join(dtemp, hostname), tests
    )

    logger.error(
        "total %d, failed: %d, missing: %d, success: %d"
        % (failures + missings + successes, failures, missings, successes)
    )
    if failures or missings:
        sys.exit(1)


run()
