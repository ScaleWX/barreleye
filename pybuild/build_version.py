"""
Version of Corals
"""
import os
import sys
import traceback
from fire import Fire
# Local libs
from pycoral import ssh_host
from pycoral import clog
from pycoral import cmd_general
from pybuild import build_common


# The Coral version file
CORAL_VERSION_FPATH = "version"
# To show this git tree is dirty and different from the "git describe"
VERSION_EXTRA_GIT_DIRTY = "dirty"


def coral_uniformed_version(version):
    """
    Char '-' is illegal for RPM. Replace it to "_". So
    in version field "-" is the same with "_".
    """
    return version.replace("-", "_")


def coral_assemble_version(version, major, minor, extra):
    """
    Assume version string that is acceptable for RPM.
    Char '-' is illegal.
    """
    version_string = "%s.%s.%s" % (version, major, minor)
    if extra is not None:
        version_string += "-" + extra
    return version_string


def coral_version_from_git(log, local_host, source_dir):
    """
    Get coral version from git.
    Two possible version formats:
        version.major.minor
        version.major.minor-extra
    In the first format, return (version, major, minor, None)

    The extra could be the same with the extra field in the tag, if there is
    no commit after git tag, e.g. when the "git describe" string is e.g.
    "2.0.0-rc1".

    The extra could also include other things, if there are one or commits
    after git tag, e.g. when the "git describe" string is e.g.
    "2.0.0-rc1-1-g8f66f7e".

    Return (version, major, minor, extra)
    """
    command = "cd %s && git describe" % source_dir
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return None, None, None, None

    lines = retval.cr_stdout.strip().splitlines()
    if len(lines) != 1:
        log.cl_error("unexpected output line number [%s] of command [%s] "
                     "on host [%s]",
                     len(lines), command, local_host.sh_hostname)
        return None, None, None, None

    git_version_line = lines[0]
    git_version, git_major, git_minor, git_extra = \
        cmd_general.coral_parse_version(log, git_version_line,
                                        minus_as_delimiter=True)
    if git_version is None:
        log.cl_error("invalid revision [%s] got from command [%s]",
                     git_version_line, command)
        return None, None, None, None

    rc = git_tree_is_clean(log, local_host, source_dir)
    if rc < 0:
        log.cl_error("failed to check whether git tree is clean or not")
        return None, None, None, None
    if rc == 1:
        return git_version, git_major, git_minor, git_extra

    if git_extra is None:
        git_extra = VERSION_EXTRA_GIT_DIRTY
    else:
        git_extra += "-" + VERSION_EXTRA_GIT_DIRTY
    return git_version, git_major, git_minor, git_extra


def read_version_file(log, local_host, source_dir):
    """
    Read version file
    """
    command = "cat %s/%s" % (source_dir, CORAL_VERSION_FPATH)
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return None
    return retval.cr_stdout


def coral_get_version(log, source_dir):
    """
    Get coral version from git.
    Two possible version formats:
        version.major.minor
        version.major.minor-extra
    In the first format, return (version, major, minor, None)
    Return (version, major, minor, extra)
    """
    # pylint: disable=too-many-locals,too-many-branches
    local_host = ssh_host.get_local_host(ssh=False)
    version_fpath = CORAL_VERSION_FPATH

    version_data = read_version_file(log, local_host, source_dir)
    if version_data is None:
        log.cl_error("failed to read version file")
        return None, None, None, None

    version_line = None
    lines = version_data.strip().splitlines()
    for line in lines:
        if line.startswith("#"):
            continue
        if version_line is not None:
            log.cl_error("version file [%s] has multiple uncommented lines",
                         version_fpath)
            return None, None, None, None
        version_line = line

    if version_line is None:
        log.cl_error("version file [%s] has no uncommented line",
                     version_fpath)
        return None, None, None, None

    version, major, minor, extra = \
        cmd_general.coral_parse_version(log, version_line,
                                        minus_as_delimiter=True)
    if version is None:
        log.cl_error("invalid version [%s] in file [%s]",
                     version_line, version_fpath)
        return None, None, None, None

    path = source_dir + "/.git"
    has_git = local_host.sh_path_exists(log, path)
    if has_git < 0:
        log.cl_error("failed to check whether path [%s] exists",
                     path)
        return None, None, None, None

    if not has_git:
        return version, major, minor, extra

    git_version, git_major, git_minor, git_extra = \
        coral_version_from_git(log, local_host, source_dir)
    if git_version is None:
        log.cl_error("failed to get version from git")
        return None, None, None, None

    if git_version != version:
        log.cl_error("inconsistent version numbers got from file [%s] "
                     "and git, [%s] vs. [%s]", version_fpath,
                     version, git_version)
        return None, None, None, None

    if git_major != major:
        log.cl_error("inconsistent major numbers got from file [%s] "
                     "and git, [%s] vs. [%s]", version_fpath,
                     major, git_major)
        return None, None, None, None

    if git_minor != minor:
        log.cl_error("inconsistent minor numbers got from file [%s] "
                     "and git, [%s] vs. [%s]", version_fpath,
                     minor, git_minor)
        return None, None, None, None

    if extra is None or extra == git_extra:
        return version, major, minor, git_extra

    # If extra field from git has more things than extra field from file, the
    # it should be seperated by the first "-"
    minus_index = git_extra.find("-")
    if minus_index < 0:
        log.cl_error("the extra field [%s] from git is not equal to the "
                     "extra field [%s] from file, and does not have [-]",
                     git_extra, extra)
        return None, None, None, None

    git_extra_start = git_extra[:minus_index]
    if git_extra_start != extra:
        log.cl_error("the extra field [%s] from git does not start "
                     "with [%s-] which is the extra field from file",
                     git_extra, extra)
        return None, None, None, None

    return version, major, minor, git_extra


def update_version_file(log, local_host, version_string, source_dir):
    """
    Update the version file
    """
    version_data = read_version_file(log, local_host, source_dir)
    if version_data is None:
        log.cl_error("failed to read version file")
        return None, None, None, None

    lines = version_data.strip().splitlines()
    version_data = ""
    for line in lines:
        if line.startswith("#"):
            version_data += line + "\n"
    version_data += version_string + "\n"
    version_fpath = CORAL_VERSION_FPATH
    try:
        with open(version_fpath, 'w', encoding='utf-8') as version_file:
            version_file.write(version_data)
    except:
        log.cl_error("failed to write version to file [%s] on host [%s]: %s",
                     version_fpath, local_host.sh_hostname,
                     traceback.format_exc())
        return -1
    return 0


def coral_get_version_string(log, source_dir):
    """
    Get the version string
    """
    version, major, minor, extra = coral_get_version(log, source_dir)
    if version is None:
        log.cl_error("failed to get version")
        return None
    version_string = coral_assemble_version(version, major, minor,
                                            extra)
    return version_string


def check_tag_meaningful(log, local_host, source_dir):
    """
    Check the new tag is not right on top another commit tag. That is
    meaningless because no change since last tag.
    """
    command = "cd %s && git describe --abbrev=0 --tags" % source_dir

    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return -1
    lines = retval.cr_stdout.strip().splitlines()
    if len(lines) != 1:
        log.cl_error("unexpected line number [%s] of command [%s] on "
                     "host [%s]",
                     len(lines), command, local_host.sh_hostname)
        return -1
    last_tag_name = lines[0]

    command = "cd %s && git rev-list -n 1 %s" % (source_dir, last_tag_name)
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return -1
    lines = retval.cr_stdout.strip().splitlines()
    if len(lines) != 1:
        log.cl_error("unexpected line number [%s] of command [%s] on "
                     "host [%s]",
                     len(lines), command, local_host.sh_hostname)
        return -1
    last_tag_commit = lines[0]

    command = "cd %s && git rev-parse HEAD" % source_dir
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return -1
    lines = retval.cr_stdout.strip().splitlines()
    if len(lines) != 1:
        log.cl_error("unexpected line number [%s] of command [%s] on "
                     "host [%s]",
                     len(lines), command, local_host.sh_hostname)
        return -1
    last_commit = lines[0]

    if last_commit == last_tag_commit:
        log.cl_error("adding new tag is meaningless since last commit is a "
                     "tag [%s]", last_tag_name)
        return -1
    return 0


def get_git_tags(log, local_host, source_dir):
    """
    Return list of tag names
    """
    command = "cd %s && git tag" % source_dir

    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return None
    return retval.cr_stdout.strip().splitlines()


def get_git_user_name(log, local_host):
    """
    Return git user name
    """
    command = "git config --get user.name"

    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return None
    lines = retval.cr_stdout.strip().splitlines()
    if len(lines) != 1:
        log.cl_error("unexpected line number [%s] of command [%s] on "
                     "host [%s]",
                     len(lines), command, local_host.sh_hostname)
        return -1
    return lines[0]


def get_git_user_email(log, local_host):
    """
    Return git user email
    """
    command = "git config --get user.email"

    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return None
    lines = retval.cr_stdout.strip().splitlines()
    if len(lines) != 1:
        log.cl_error("unexpected line number [%s] of command [%s] on "
                     "host [%s]",
                     len(lines), command, local_host.sh_hostname)
        return -1
    return lines[0]


def git_tree_is_clean(log, local_host, source_dir):
    """
    Check if git working tree is dirty
    """
    command = ("cd %s && git status --untracked-files=no --porcelain" %
               source_dir)
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return -1
    if retval.cr_stdout == "":
        return 1
    return 0


def _update_version(log, workspace, source_dir, add_version=False,
                    add_major=False, add_minor=False,
                    new_extra=None):
    """
    Update the version
    """
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    # pylint: disable=unused-argument
    add_number = 0
    changing = False
    if add_version:
        add_number += 1
        changing = True
    if add_major:
        add_number += 1
        changing = True
    if add_minor:
        add_number += 1
        changing = True
    if add_number > 1:
        log.cl_error("it is not reasonable to update multiple numbers of "
                     "revision")
        return -1
    if new_extra is not None:
        changing = True
        if len(new_extra) != 0:
            rc = cmd_general.check_version_extra(log, new_extra)
            if rc:
                log.cl_error("extra part [%s] of reviesion is illegal",
                             new_extra)
                return -1
            uniformed_extra = coral_uniformed_version(new_extra)

    if not changing:
        log.cl_error("please specify which part of revision do you want "
                     "to update by:\n"
                     "    --add_version, --add_major, --add_minor, or/and --new_extra")
        return -1

    local_host = ssh_host.get_local_host(ssh=False)
    path = source_dir + "/" + ".git"
    has_git = local_host.sh_path_exists(log, path)
    if has_git < 0:
        log.cl_error("failed to check whether path [%s] exists",
                     path)
        return -1

    if not has_git:
        log.cl_error("current directory is not a git repository")
        return -1

    rc = git_tree_is_clean(log, local_host, source_dir)
    if rc < 0:
        log.cl_error("failed to check whether git tree is clean or not")
        return -1
    if rc == 0:
        log.cl_error("git tree is not clean")
        return -1

    ret = check_tag_meaningful(log, local_host, source_dir)
    if ret:
        log.cl_error("please do not add meaningless empty tags")
        return -1

    version, major, minor, extra = coral_get_version(log, source_dir)
    if version is None:
        log.cl_error("failed to get version")
        return -1
    old_version_string = coral_assemble_version(version, major, minor,
                                                extra)
    message = ""
    if add_version:
        version += 1
        major = 0
        minor = 0
        message = "Version part of revision has been increased.\n"
    elif add_major:
        major += 1
        minor = 0
        message = "Major part of revision has been increased.\n"
    elif add_minor:
        minor += 1
        message = "Minor part of revision has been increased.\n"
    if new_extra is not None:
        if len(new_extra) == 0:
            message += ("Extra part of revision has been cleaned, "
                        "old: [%s].\n" % (extra))
            extra = None
        else:
            if (not add_number) and uniformed_extra == extra:
                log.cl_error("the current reversion has identical extra field [%s]",
                             extra)
                return -1
            message += ("Extra part of revision has been changed from "
                        "[%s] to [%s].\n" % (extra, uniformed_extra))
            extra = new_extra
    else:
        extra = None
    version_string = coral_assemble_version(version, major, minor, extra)

    tags = get_git_tags(log, local_host, source_dir)
    if tags is None:
        log.cl_error("failed to get git tags")
        return -1

    for tag in tags:
        if (coral_uniformed_version(tag) ==
                coral_uniformed_version(version_string)):
            log.cl_error("old tag [%s] has identical reversion",
                         tag)
            return -1

    user_name = get_git_user_name(log, local_host)
    if user_name is None:
        log.cl_error("failed to get git user name")
        return -1

    user_email = get_git_user_email(log, local_host)
    if user_email is None:
        log.cl_error("failed to get git user email")
        return -1

    input_result = input("Are you sure to update the version from [%s] to "
                         "[%s]? [y/N] " % (old_version_string, version_string))
    if ((not input_result.startswith("y")) and
            (not input_result.startswith("Y"))):
        log.cl_info("quiting without touching anything")
        return -1

    rc = update_version_file(log, local_host, version_string, source_dir)
    if rc:
        log.cl_error("failed to update version file")
        return -1

    message += "Tag [%s] has been added\n" % version_string

    command = ("""cd %s && git commit -av -m "release: new tag %s

%s
Signed-off-by: %s <%s>
" """ % (source_dir, version_string, message, user_name, user_email))
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return -1

    command = ('cd %s && git tag -a %s -m "%s"' %
               (source_dir, version_string, version_string))
    retval = local_host.sh_run(log, command)
    if retval.cr_exit_status:
        log.cl_error("failed to run command [%s] on host [%s], "
                     "ret = [%d], stdout = [%s], stderr = [%s]",
                     command,
                     local_host.sh_hostname,
                     retval.cr_exit_status,
                     retval.cr_stdout,
                     retval.cr_stderr)
        return -1

    new_version_string = coral_get_version_string(log, source_dir)
    if new_version_string is None:
        log.cl_error("failed to get version after adding tag")
        return -1

    if new_version_string != version_string:
        log.cl_error("got different version [%s] after tagging with [%s]",
                     new_version_string, version_string)
        return -1
    log.cl_info("tag [%s] has been added", version_string)
    return 0


class CoralVersionCommand():
    """
    Commands to for managing version.
    """
    # pylint: disable=too-few-public-methods
    def _init(self, log_to_file):
        # pylint: disable=attribute-defined-outside-init
        self._cvc_log_to_file = log_to_file

    def save(self, path):
        """
        Save the version to dest .py file. This is a command for internal
        build process.

        :param path: the python file to save the version.
        """
        # pylint: disable=no-self-use,unused-argument
        log = clog.get_log(console_format=clog.FMT_NORMAL, overwrite=True)
        local_host = ssh_host.get_local_host(ssh=False)
        source_dir = os.path.dirname(os.path.dirname(__file__))
        version_string = coral_get_version_string(log, source_dir)
        if version_string is None:
            cmd_general.cmd_exit(log, -1)
        version_string = coral_uniformed_version(version_string)
        version_data = '"""'
        version_data += """
Please DO NOT edit this file directly!
This file is generated by "coral" command.
"""
        version_data += '"""'
        version_data += "\n"
        version_data += "CORAL_VERSION = \"%s\"\n" % (version_string)

        try:
            with open(path, 'w', encoding='utf-8') as version_file:
                version_file.write(version_data)
        except:
            log.cl_error("failed to write version to file [%s] on host [%s]: %s",
                         path, local_host.sh_hostname,
                         traceback.format_exc())
            cmd_general.cmd_exit(log, -1)
        cmd_general.cmd_exit(log, 0)

    def show(self):
        """
        Print version to stdout.

        All '-' will be replaced to "_" to make RPM naming happy.
        """
        # pylint: disable=no-self-use
        log = clog.get_log(console_format=clog.FMT_NORMAL, overwrite=True)
        source_dir = os.getcwd()
        version_string = coral_get_version_string(log, source_dir)
        if version_string is None:
            cmd_general.cmd_exit(log, -1)
        sys.stdout.write(coral_uniformed_version(version_string))
        cmd_general.cmd_exit(log, 0)

    def update(self, add_version=False, add_major=False, add_minor=False,
               new_extra=None):
        """
        Update the revision.

        The current directory should be git repository of Coral.

        :param add_version: Increase the version number. Default: False.
        :param add_major: Increase the major number. Default: False.
        :param add_minor: Increase the minor number. Default: True.
        :param new_extra: Change extra part of reviesion. Default: None. To
            remove the existing extra field, specify --new-extra "".
        """
        # pylint: disable=no-self-use
        source_dir = os.getcwd()
        log, workspace = cmd_general.init_env_noconfig(source_dir,
                                                       self._cvc_log_to_file,
                                                       True)
        cmd_general.check_argument_bool(log, "add_version", add_version)
        cmd_general.check_argument_bool(log, "add_major", add_major)
        cmd_general.check_argument_bool(log, "add_minor", add_minor)
        if new_extra is not None:
            new_extra = cmd_general.check_argument_str(log, "new_extra",
                                                       new_extra)
            if "-" in new_extra:
                log.cl_error("character [-] is not allowed in extra field [%s]",
                             new_extra)
                cmd_general.cmd_exit(log, -1)
        rc = _update_version(log, workspace, source_dir,
                             add_version=add_version,
                             add_major=add_major, add_minor=add_minor,
                             new_extra=new_extra)
        cmd_general.cmd_exit(log, rc)


build_common.coral_command_register("version", CoralVersionCommand())


def main():
    """
    main routine
    """
    Fire(build_common.CoralCommand)
