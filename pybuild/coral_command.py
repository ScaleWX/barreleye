"""
Coral command
"""
# pylint: disable=unused-import
import sys
import os
from fire import Fire
from pycoral import constant
from pycoral import cmd_general
from pybuild import coral_build
from pybuild import build_common


def build(coral_command,
          cache=constant.CORAL_BUILD_CACHE,
          lustre=None,
          e2fsprogs=None,
          collectd=None,
          enable_zfs=False, enable_devel=False,
          disable_plugin=None,
          tsinghua_mirror=False):
    """
    Build the Coral ISO.
    :param debug: Whether to dump debug logs into files, default: False.
    :param cache: The dir that caches build RPMs. Default:
        /var/log/coral/build_cache.
    :param lustre: The dir of Lustre RPMs (usually generated by lbuild).
        Default: /var/log/coral/build_cache/$type/lustre.
    :param e2fsprogs: The dir of E2fsprogs RPMs.
        Default: /var/log/coral/build_cache/$type/e2fsprogs.
    :param collectd: The Collectd source codes.
        Default: https://github.com/LiXi-storage/collectd/releases/$latest.
        A local source dir or .tar.bz2 generated by "make dist" of Collectd
        can be specified if modification to Collectd is needed.
    :param enable_zfs: Whether enable ZFS support. Default: False.
    :param enable_devel: Whether enable development support. Default: False.
    :param disable_plugin: Disable one or more plugins. To disable multiple
        plugins, please provide a list seperated by comma. Default: None.
    :param tsinghua_mirror: Whether use YUM and pip mirrors from Tsinghua
        Univeristy. If specified, will replace mirrors for possible speedup.
        Default: False.
    """
    # pylint: disable=unused-argument,protected-access,too-many-locals
    if not isinstance(coral_command._cc_log_to_file, bool):
        print("ERROR: invalid debug option [%s], should be a bool type" %
              (coral_command._cc_log_to_file), file=sys.stderr)
        sys.exit(1)

    source_dir = os.getcwd()
    identity = build_common.get_build_path()
    logdir_is_default = True
    log, workspace = cmd_general.init_env_noconfig(source_dir,
                                                   coral_command._cc_log_to_file,
                                                   logdir_is_default,
                                                   identity=identity)

    cache = cmd_general.check_argument_str(log, "cache", cache)
    if lustre is not None:
        cmd_general.check_argument_fpath(lustre)
        lustre = lustre.rstrip("/")
    if e2fsprogs is not None:
        cmd_general.check_argument_fpath(e2fsprogs)
        e2fsprogs = e2fsprogs.rstrip("/")
    if collectd is not None:
        cmd_general.check_argument_fpath(collectd)
        collectd = collectd.rstrip("/")

    cmd_general.check_argument_bool(log, "enable_zfs", enable_zfs)
    cmd_general.check_argument_bool(log, "enable_devel", enable_devel)
    if disable_plugin is not None:
        disable_plugin = cmd_general.check_argument_list_str(log, "disable_plugin",
                                                             disable_plugin)
    cmd_general.check_argument_bool(log, "tsinghua_mirror", tsinghua_mirror)
    rc = coral_build.build(log, source_dir, workspace, cache=cache,
                           lustre_rpms_dir=lustre,
                           e2fsprogs_rpms_dir=e2fsprogs,
                           collectd=collectd,
                           enable_zfs=enable_zfs,
                           enable_devel=enable_devel,
                           disable_plugin=disable_plugin,
                           tsinghua_mirror=tsinghua_mirror)
    cmd_general.cmd_exit(log, rc)


build_common.coral_command_register("build", build)


def plugins(coral_command):
    """
    List the plugins of Coral.
    """
    # pylint: disable=unused-argument
    plugin_str = ""
    for plugin in build_common.CORAL_RELEASE_PLUGIN_DICT.values():
        if plugin_str == "":
            plugin_str = plugin.cpt_plugin_name
        else:
            plugin_str += "," + plugin.cpt_plugin_name
    sys.stdout.write(plugin_str + '\n')


build_common.coral_command_register("plugins", plugins)


def main():
    """
    main routine
    """
    Fire(build_common.CoralCommand)
