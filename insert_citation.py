__author__ = "news.jan.vogt@me.com"
__version__ = "0.1"

import sublime
import sublime_plugin
from library import Library
import threading
import os
import re


class InsertBibHeaderAndFooterCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.insert(edit, 0, """\\usepackage[backend=biber, style=apa6, natbib=true]{biblatex}
        \\addbibresource{filename.bib}
        """)
        self.view.insert(edit, self.view.size(), """
        \\printbibliography""")


class InsertCitationCommand(sublime_plugin.TextCommand):
    def run(self, edit, citeType=None):
        """Offers dialog to select citation and isert selected in the format given by format. Format
        needs to contain %%s where the citation-key should be inserted"""
        library = self.getLibrary()
        self.citeType = citeType
        self.selectionList = library.LibraryItems
        self.selectionList.sort(key=lambda x: x.menuRows[0])
        selectFrom = [item.menuRows for item in self.selectionList]
        self.view.window().show_quick_panel(selectFrom, self.callBack)

    def getLibrary(self):
        try:
            self.__library
        except AttributeError:
            self.__library = Library.getLibraryForView(self.view)
        return self.__library

    def callBack(self, arg):
        if arg > -1:
            self.insertCitation(self.getLibrary().cite(self.selectionList[arg]))
        else:
            self.getLibrary().removeLibraryForView()

    def insertCitation(self, key):
        edit = self.view.begin_edit("Insert Citation")
        try:
            newRegions = []
            for region in self.view.sel():
                if re.search("[M|m]arkdown", self.view.scope_name(0)):
                    localCite, region = self.createPandocMarkdownCite(region)
                else:
                    localCite, region = self.createLatexCite(region)
                replaceString = localCite % key
                newPos = region.begin() + len(replaceString)
                self.view.replace(edit, region, replaceString)
                newRegions.append(sublime.Region(newPos, newPos))
            self.view.sel().clear()
            for region in newRegions:
                self.view.sel().add(region)
        finally:
            self.view.end_edit(edit)

    def createLatexCite(self, region):
        lineRegion = self.view.line(region)
        precedingText = self.view.substr(sublime.Region(lineRegion.begin(), region.begin()))
        precedingMatch = re.search("(?:\\\\([^\\s\\{\\[\\(]*?))?((?:\\[\\S*?\\])?\\[\\S*?\\])?(?:\\{(\\S*?)\\})?$", precedingText)
        if precedingMatch is None:
            if self.citeType is None:
                self.citeType = "cite"
            return "\\%s{%%s}" % self.citeType, region
        else:
            retRegion = sublime.Region(region.begin() - len(precedingMatch.group()), region.end())
            if self.citeType is None:
                self.citeType = self.getRegExGroup(precedingMatch, 1, "cite")
            if precedingMatch.group(3) is not None:
                return "\\%s%s{%s,%%s}" % (self.citeType, self.getRegExGroup(precedingMatch, 2, ""), precedingMatch.group(3)), retRegion
            else:
                return "\\%s%s{%%s}" % (self.citeType, self.getRegExGroup(precedingMatch, 2, "")), retRegion

    def createPandocMarkdownCite(self, region):
        lineRegion = self.view.line(region)
        precedingText = self.view.substr(sublime.Region(lineRegion.begin(), region.begin()))
        precedingMatch = re.search("\\[([^\\]]*)\\]?$", precedingText)
        if precedingMatch is None:
            return "@%s", region
        else:
            retRegion = sublime.Region(region.begin() - len(precedingMatch.group()), region.end())
            if precedingMatch.group(1) is not None:
                return "[%s @%%s]" % precedingMatch.group(1), retRegion
            else:
                return "[%s]", retRegion

    @staticmethod
    def getRegExGroup(match, groupNumber, default):
        try:
            if match.group(groupNumber) is not None:
                return match.group(groupNumber)
        except IndexError:
            pass
        return default


class PluginEventHandler(sublime_plugin.EventListener):
    def on_activated(self, view):
        if Library.hasLibraryForView(view):
            UpdateThread(Library.getLibraryForView(view)).start()

    def on_pre_save(self, view):
        if Library.hasLibraryForView(view):
            Library.getLibraryForView(view).save()

    def on_load(self, view):
        if Library.hasBibFile(os.path.splitext(view.file_name())[0] + '.bib'):
            UpdateThread(Library.getLibraryForView(view)).start()


class UpdateThread(threading.Thread):
    __updateLock = threading.Lock()

    def __init__(self, lib):
        self.lib = lib
        self.done = False
        self.__points = 0
        super(UpdateThread, self).__init__()

    def run(self):
        if self.__updateLock.acquire(False):
            sublime.set_timeout(self.update_status, 300)
            try:
                self.lib.update()
            finally:
                self.__updateLock.release()
                self.done = True

    def update_status(self):
        if self.done:
            sublime.status_message("")
            return
        self.__points = self.__points % 3 + 1
        sublime.status_message("Updating Library" + self.__points*".")
        sublime.set_timeout(self.update_status, 300)
