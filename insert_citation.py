import sublime
import sublime_plugin
import os
import sys

if os.name == 'nt':
    from ctypes import windll, create_unicode_buffer


def add_to_path(path):
    # Python 2.x on Windows can't properly import from non-ASCII paths, so
    # this code added the DOC 8.3 version of the lib folder to the path in
    # case the user's username includes non-ASCII characters
    if os.name == 'nt':
        buf = create_unicode_buffer(512)
        if windll.kernel32.GetShortPathNameW(path, buf, len(buf)):
            path = buf.value

    if path not in sys.path:
        sys.path.append(path)

lib_folder = os.path.join(sublime.packages_path(), 'ZoteroCite', 'lib')
add_to_path(os.path.join(lib_folder, 'pyzotero'))
add_to_path(os.path.join(lib_folder, 'feedparser'))
add_to_path(os.path.join(lib_folder, 'pytz-2013b'))
add_to_path(os.path.join(lib_folder, 'poster-0.8.1'))
add_to_path(os.path.join(lib_folder, 'ordereddict-1.1'))


from pyzotero import zotero


class InsertCitationCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        zot = zotero.Zotero('1197522', 'user', 'FUWTcdnRvb1bFy8ugDudDDhA')
        first_ten = zot.items(limit=10)
        print first_ten
        self.view.insert(edit, 0, "Hello, World!")
