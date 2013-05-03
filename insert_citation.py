import sublime
import sublime_plugin
from library import Library
import threading


class InsertCitationCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        library = self.getLibrary()
        self.selectionList = library.LibraryItems
        self.selectionList.sort(key=lambda x: x.menuRows[0])
        selectFrom = [item.menuRows for item in self.selectionList]
        #BibTexEntry.writeToFile([item.bibTexEntry for item in first_ten], "/Users/jan/Desktop/test.bib")
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

    def insertCitation(self, key):
        edit = self.view.begin_edit("Insert Citation")
        for region in self.view.sel():
            self.view.replace(edit, region, key)
        self.view.sel().clear()
        self.view.end_edit(edit)


class PluginEventHandler(sublime_plugin.EventListener):
    def on_activated(self, view):
        if Library.hasLibraryForView(view):
            UpdateThread(Library.getLibraryForView(view)).start()

    def on_pre_save(self, view):
        if Library.hasLibraryForView(view):
            Library.getLibraryForView(view).save()


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
