# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, unicode_literals

import fnmatch
import io
import os
import re
import shutil
import sys
from glob import glob
from subprocess import Popen, call
from tempfile import mkdtemp

from future import standard_library

from paver.easy import *
from pyload import info

standard_library.install_aliases()


# patch to let it support list of patterns


def new_fnmatch(self, pattern):
    if isinstance(pattern, list):
        for p in pattern:
            if fnmatch.fnmatch(self.name, p):
                return True
        return False
    else:
        return fnmatch.fnmatch(self.name, pattern)


path.fnmatch = new_fnmatch


PACKDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


options = environment.options
options(
    sphinx=Bunch(
        builddir="_build",
        sourcedir=""
    ),
    apitypes=Bunch(
        path="thrift",
    ),
    virtualenv=Bunch(
        dir="env",
        python="python2",
        virtual="virtualenv2",
    ),
    cog=Bunch(
        pattern=["*.py", "*.rst"],
    )
)

# xgettext args
xargs = ["--language=Python", "--add-comments=L10N",
         "--from-code=utf-8", "--copyright-holder=The pyLoad Team", "--package-name=pyload",
         "--package-version={0}".format(info().version), "--msgid-bugs-address='dev@pyload.net'"]

# Modules replace rules
module_replace = [
    ('from pyload.plugins.hook import threaded, Expose, Hook',
     'from pyload.plugins.addon import threaded, Expose, Addon'),
    ('from pyload.plugins.hook import Hook',
     'from pyload.plugins.addon import Addon'),
    ('from pyload.common.json_layer import json_loads, json_dumps',
     'from pyload.utils import json_loads, json_dumps'),
    ('from pyload.common.json_layer import json_loads',
     'from pyload.utils import json_loads'),
    ('from pyload.common.json_layer import json_dumps',
     'from pyload.utils import json_dumps'),
    ('from pyload.utils import parseFileSize',
     'from pyload.utils import parseFileSize'),
    ('from pyload.utils import save_join, save_path',
     'from pyload.utils.fs import save_join, safe_filename as save_path'),
    ('from pyload.utils import save_join, fs_encode',
     'from pyload.utils.fs import save_join, fs_encode'),
    ('from pyload.utils import save_join', 'from pyload.utils.fs import save_join'),
    ('from pyload.utils import fs_encode', 'from pyload.utils.fs import fs_encode'),
    ('from pyload.unescape import unescape',
     'from pyload.utils import html_unescape as unescape'),
    ('self.account.get_account_info(self.user, ',
     'self.account.get_account_data('),
    ('self.account.get_account_info(self.user)', 'self.account.get_account_data()'),
    ('self.account.accounts[self.user]["password"]', 'self.account.password'),
    ("self.account.accounts[self.user]['password']", 'self.account.password'),
    (".can_use()", '.is_usable()'),
    ('from pyload.', 'from pyload.')  # This should be always the last one
]


@task
@needs('cog')
def html():
    """Build html documentation"""
    module = os.path.join(path("docs"), "pyload")
    module.rmtree()
    call_task('paver.doctools.html')


@task
@cmdopts([
    ('path=', 'p', 'Thrift path'),
])
def apitypes(options):
    """ Generate data types stubs """

    outdir = PACKDIR / "pyload" / "remote"

    if (os.path.join(outdir, "gen-py")).exists():
        (os.path.join(outdir, "gen-py")).rmtree()

    cmd = [options.apitypes.path, "-strict", "-o", outdir, "--gen",
           "py:slots,dynamic", os.path.join(outdir, "pyload.thrift")]

    print("running", cmd)

    p = Popen(cmd)
    p.communicate()

    (os.path.join(outdir, "thriftgen")).rmtree()
    (os.path.join(outdir, "gen-py")).move(os.path.join(outdir, "thriftgen"))

    # create light ttypes
    from pyload.remote.create_apitypes import main

    main()
    from pyload.remote.create_jstypes import main

    main()


@task
def webapp():
    """ Builds the pyload web app. Nodejs and npm must be installed """

    os.chdir(PACKDIR / "pyload" / "web")

    # Preserve exit codes
    ret = call(["npm", "install", "--no-color"])
    if ret:
        exit(ret)
    ret = call(["bower", "install", "--no-color"])
    if ret:
        exit(ret)
    ret = call(["bower", "update", "--no-color"])
    if ret:
        exit(ret)
    ret = call(["grunt", "--no-color"])
    if ret:
        exit(ret)


@task
def generate_locale():
    """ Generates localisation files """

    EXCLUDE = ["pyload/lib", "pyload/setup", "pyload/plugins", "setup.py"]

    makepot("pyload", path("pyload"), EXCLUDE)
    makepot("plugins", os.path.join(path("pyload"), "plugins"))
    makepot("setup", "", [], includes="./pyload/setup/Setup.py\n")
    makepot("webui", path("pyload") / "web" / "app", ["components", "vendor", "gettext"], endings=[".js", ".html"],
            xxargs="--language=Python --force-po".split(" "))

    makehtml("webui", path("pyload") / "web" / "app" / "templates")

    path("includes.txt").remove()

    print("Locale generated")


@task
@cmdopts([
    ('key=', 'k', 'api key')
])
def upload_translations(options):
    """ Uploads the locale files to translation server """
    tmp = path(mkdtemp())

    shutil.copy('locale/crowdin.yaml', tmp)
    os.mkdir(os.path.join(tmp, 'pyLoad'))
    for f in glob('locale/*.pot'):
        if os.path.isfile(f):
            shutil.copy(f, os.path.join(tmp, 'pyLoad'))

    config = os.path.join(tmp, 'crowdin.yaml')
    content = io.open(config, 'rb').read()
    content = content.format(key=options.key, tmp=tmp)
    fp = io.open(config, 'wb')
    fp.write(content)
    fp.close()

    call(['crowdin-cli', '-c', config, 'upload', 'source'])

    shutil.rmtree(tmp)

    print("Translations uploaded")


@task
@cmdopts([
    ('key=', 'k', 'api key')
])
def download_translations(options):
    """ Downloads the translated files from translation server """
    tmp = path(mkdtemp())

    shutil.copy('locale/crowdin.yaml', tmp)
    os.mkdir(os.path.join(tmp, 'pyLoad'))
    for f in glob('locale/*.pot'):
        if os.path.isfile(f):
            shutil.copy(f, os.path.join(tmp, 'pyLoad'))

    config = os.path.join(tmp, 'crowdin.yaml')
    content = io.open(config, 'rb').read()
    content = content.format(key=options.key, tmp=tmp)
    f = io.open(config, 'wb')
    fp.write(content)
    f.close()

    call(['crowdin-cli', '-c', config, 'download'])

    for language in (os.path.join(tmp, 'pyLoad')).listdir():
        if not language.isdir():
            continue

        target = os.path.join(path('locale'), language.basename())
        print("Copy language {0}".format(target))
        if target.exists():
            shutil.rmtree(target)

        shutil.copytree(language, target)

    shutil.rmtree(tmp)


@task
def compile_translations():
    """ Compile PO files to MO """
    for language in path('locale').listdir():
        if not language.isdir():
            continue

        for f in glob(language / 'LC_MESSAGES' / '*.po'):
            print("Compiling {0}".format(f))
            call(['msgfmt', '-o', f.replace('.po', '.mo'), f])


@task
def tests():
    """ Run complete test suite """
    call(["tests/run_pyload.sh"])
    call(["tests/nosetests.sh"])
    call(["tests/quit_pyload.sh"])


@task
@cmdopts([
    ('virtual=', 'v', 'virtualenv path'),
    ('python=', 'p', 'python path')
])
def virtualenv(options):
    """Setup virtual environment"""
    if path(options.dir).exists():
        return

    call([options.virtual, "--no-site-packages",
          "--python", options.python, options.dir])
    print("$ source {0}/bin/activate".format(options.dir))


@task
def clean_env():
    """Deletes the virtual environment"""
    env = path(options.virtualenv.dir)
    if env.exists():
        env.rmtree()


@task
def clean():
    """Cleans build directories"""
    path("build").rmtree()
    path("dist").rmtree()


@task
def replace_module_imports():
    """Replace imports from stable syntax to master"""
    for root, dirnames, filenames in os.walk('pyload/plugins'):
        for filename in fnmatch.filter(filenames, '*.py'):
            path = os.path.join(root, filename)
            fp = io.open(path)
            content = fp.read()
            fp.close()
            for rule in module_replace:
                content = content.replace(rule[0], rule[1])
            if '/addon/' in path:
                content = content.replace('(Hook):', '(Addon):')
            elif '/accounts/' in path:
                content = content.replace(
                    'self.accounts[user]["password"]', 'self.password')
                content = content.replace(
                    "self.accounts[user]['password']", 'self.password')
            f = io.open(path, 'w')
            fp.write(content)
            fp.close()


# helper functions

def walk_trans(path, excludes, endings=[".py"]):
    result = ""

    for f in path.walkfiles():
        if [True for x in excludes if x in f.dirname().relpath()]:
            continue
        if f.name in excludes:
            continue

        for e in endings:
            if f.name.endswith(e):
                result += "./{0}\n".format(f.relpath())
                break

    return result


def makepot(domain, p, excludes=[], includes="", endings=[".py"], xxargs=[]):
    print("Generate {0}.pot".format(domain))

    fp = io.open("includes.txt", "wb")
    if includes:
        fp.write(includes)

    if p:
        fp.write(walk_trans(path(p), excludes, endings))

    fp.close()

    call(["xgettext", "--files-from=includes.txt",
          "--default-domain={0}".format(domain)] + xargs + xxargs)

    # replace charset und move file
    with io.open("{0}.po".format(domain), "rb") as fp:
        content = fp.read()

    path("{0}.po".format(domain)).remove()
    content = content.replace("charset=CHARSET", "charset=UTF-8")

    with io.open("locale/{0}.pot".format(domain), "wb") as fp:
        fp.write(content)


def makehtml(domain, p):
    """ Parses entries from html and append them to existing pot file"""

    pot = path("locale") / "{0}.pot".format(domain)

    with io.open(pot, 'rb') as fp:
        content = fp.readlines()

    msgids = {}
    # parse existing ids and line
    for i, line in enumerate(content):
        if line.startswith("msgid "):
            msgid = line[6:-1].strip('"')
            msgids[msgid] = i

    # TODO: parses only n=2 plural
    single = re.compile(r'\{\{ ?(?:gettext|_) "((?:\\.|[^"\\])*)" ?\}\}')
    plural = re.compile(
        r'\{\{ ?(?:ngettext) *"((?:\\.|[^"\\])*)" *"((?:\\.|[^"\\])*)"')

    for f in p.walkfiles():
        if not f.endswith("html"):
            continue
        with io.open(f, "rb") as html:
            for i, line in enumerate(html.readlines()):
                key = None
                nmessage = plural.search(line)
                message = single.search(line)
                if nmessage:
                    key = nmessage.group(1)
                    keyp = nmessage.group(2)

                    if key not in msgids:
                        content.append("\n")
                        content.append("msgid \"{0}\"\n".format(key))
                        content.append("msgid_plural \"{0}\"\n".format(keyp))
                        content.append('msgstr[0] ""\n')
                        content.append('msgstr[1] ""\n')
                        msgids[key] = len(content) - 4

                elif message:
                    key = message.group(1)

                    if key not in msgids:
                        content.append("\n")
                        content.append("msgid \"{0}\"\n".format(key))
                        content.append('msgstr ""\n')
                        msgids[key] = len(content) - 2

                if key:
                    content.insert(msgids[key], "#: {0}:{1:d}\n".format(f, i))
                    msgids[key] += 1

        with io.open(pot, 'wb') as fp:
            fp.writelines(content)

    print("Parsed html files")
