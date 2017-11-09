#!/usr/bin/env python3

""" TODO
    ✓ sqlite3 for cover images cache
    ✓ sqlite3 for storing metadata
    ✓ Drop down for SortBy (library view)
    ✓ Define every widget in code because you're going to need to create separate tabs
    ✓ Override the keypress event of the textedit
    ✓ Search bar in toolbar
    ✓ Shift focus to the tab that has the book open
    ✓ Search bar in toolbar
    ✓ Drop down for TOC (book view)

    mobi support
    txt, doc support
    pdf support?
    Goodreads API: Ratings, Read, Recommendations
    Get ISBN using python-isbnlib
    All ebooks should first be added to the database and then returned as HTML
    Theming
    Pagination
    Use format* icons for toolbar buttons
    Information dialog widget
    Check file hashes upon restart
    Recursive file addition
    Library context menu: Cache, Read, Edit database, delete
    Set context menu for definitions and the like
"""

import os
import sys

from PyQt5 import QtWidgets, QtGui, QtCore

import mainwindow
import database
import book_parser

from widgets import LibraryToolBar, BookToolBar, Tab


class MainUI(QtWidgets.QMainWindow, mainwindow.Ui_MainWindow):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)

        # Initialize application
        Settings(self).read_settings()  # This should populate all variables that need
                                        # to be remembered across sessions

        # Create the database in case it doesn't exist
        database.DatabaseInit(self.database_path)

        # Create and right align the statusbar label widget
        self.statusMessage = QtWidgets.QLabel()
        self.statusMessage.setObjectName('statusMessage')
        self.statusBar.addPermanentWidget(self.statusMessage)

        # Init the QListView
        self.viewModel = None
        self.lib_ref = Library(self)

        # Create toolbars
        self.libraryToolBar = LibraryToolBar(self)
        self.libraryToolBar.addButton.triggered.connect(self.add_books)
        self.libraryToolBar.deleteButton.triggered.connect(self.delete_books)
        self.libraryToolBar.filterEdit.textChanged.connect(self.reload_listview)
        self.libraryToolBar.sortingBox.activated.connect(self.reload_listview)
        self.addToolBar(self.libraryToolBar)

        self.bookToolBar = BookToolBar(self)
        self.bookToolBar.fullscreenButton.triggered.connect(self.set_fullscreen)
        self.addToolBar(self.bookToolBar)

        # Make the correct toolbar visible
        self.tab_switch()
        self.tabWidget.currentChanged.connect(self.tab_switch)

        # New tabs and their contents
        self.current_tab = None
        self.current_textEdit = None

        # Tab closing
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabBar().setTabButton(0, QtWidgets.QTabBar.RightSide, None)
        self.tabWidget.tabCloseRequested.connect(self.close_tab)

        # ListView
        # self.listView.setSpacing(0)
        self.listView.setGridSize(QtCore.QSize(175, 250))
        self.listView.verticalScrollBar().setSingleStep(7)
        self.listView.doubleClicked.connect(self.list_doubleclick)
        self.reload_listview()
        self.resizeEvent()

        # Keyboard shortcuts
        self.exit_all = QtWidgets.QShortcut(QtGui.QKeySequence('Ctrl+Q'), self)
        self.exit_all.activated.connect(self.closeEvent)

    def resizeEvent(self, event=None):
        # The hackiness of this hack is just...
        default_size = 175  # This is size of the QIcon (160 by default) +
                            # minimum margin is needed between thumbnails

        # for n icons, the n + 1th icon will appear at > n +1.11875
        # First, calculate the number of images per row
        i = self.listView.viewport().width() / default_size
        rem = i - int(i)
        if rem >= .11875 and rem <= .9999:
            num_images = int(i)
        else:
            num_images = int(i) - 1

        # The rest is illustrated using informative variable names
        space_occupied = num_images * default_size
        space_left = (
            self.listView.viewport().width() - space_occupied - 19)  # 19 is the scrollbar width
        try:
            layout_extra_space_per_image = space_left // num_images
            self.listView.setGridSize(
                QtCore.QSize(default_size + layout_extra_space_per_image, 240))
        except ZeroDivisionError:  # Initial resize is ignored
            return

    def add_books(self):
        # TODO
        # Maybe expand this to traverse directories recursively
        self.statusMessage.setText('Adding books...')
        my_file = QtWidgets.QFileDialog.getOpenFileNames(
            self, 'Open file', self.last_open_path, "eBooks (*.epub *.mobi *.txt)")
        if my_file[0]:
            self.listView.setEnabled(False)
            self.last_open_path = os.path.dirname(my_file[0][0])
            books = book_parser.BookSorter(my_file[0])
            parsed_books = books.initiate_threads()
            database.DatabaseFunctions(self.database_path).add_to_database(parsed_books)
            self.listView.setEnabled(True)
            self.viewModel = None
        self.reload_listview()

    def delete_books(self):
        selected_books = self.listView.selectedIndexes()
        if selected_books:
            def ifcontinue(box_button):
                if box_button.text() == '&Yes':
                    selected_hashes = []
                    for i in selected_books:
                        book_data = i.data(QtCore.Qt.UserRole + 3)
                        selected_hashes.append(book_data['book_hash'])
                    database.DatabaseFunctions(
                        self.database_path).delete_from_database(selected_hashes)
                    self.viewModel = None
                    self.reload_listview()

            selected_number = len(selected_books)
            msg_box = QtWidgets.QMessageBox()
            msg_box.setText('Delete %d book(s)?' % selected_number)
            msg_box.setIcon(QtWidgets.QMessageBox.Question)
            msg_box.setWindowTitle('Confirm deletion')
            msg_box.setStandardButtons(
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg_box.buttonClicked.connect(ifcontinue)
            msg_box.show()
            msg_box.exec_()

    def reload_listview(self):
        if not self.viewModel:
            self.lib_ref.generate_model()
        self.lib_ref.update_listView()

    def tab_switch(self):
        if self.tabWidget.currentIndex() == 0:
            self.bookToolBar.hide()
            self.libraryToolBar.show()
            if self.lib_ref.proxy_model:
                # Making the proxy model available doesn't affect
                # memory utilization at all. Bleh.
                self.statusMessage.setText(
                    str(self.lib_ref.proxy_model.rowCount()) + ' Books')
        else:
            self.bookToolBar.show()
            self.libraryToolBar.hide()
            current_metadata = self.tabWidget.widget(
                self.tabWidget.currentIndex()).book_metadata
            current_title = current_metadata['book_title']
            current_author = current_metadata['book_author']
            self.statusMessage.setText(
                current_author + ' - ' + current_title)

    def set_fullscreen(self):
        self.current_tab = self.tabWidget.currentIndex()
        self.current_textEdit = self.tabWidget.widget(self.current_tab)

        self.exit_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence('Escape'), self.current_textEdit)
        self.exit_shortcut.activated.connect(self.set_normalsize)

        self.current_textEdit.setWindowFlags(QtCore.Qt.Window)
        self.current_textEdit.setWindowState(QtCore.Qt.WindowFullScreen)
        self.hide()
        self.current_textEdit.show()

    def set_normalsize(self):
        self.current_textEdit.setWindowState(QtCore.Qt.WindowNoState)
        self.current_textEdit.setWindowFlags(QtCore.Qt.Widget)
        self.show()
        self.current_textEdit.show()

    def list_doubleclick(self, myindex):
        # TODO
        # Load the book.
        index = self.listView.model().index(myindex.row(), 0)
        book_metadata = self.listView.model().data(index, QtCore.Qt.UserRole + 3)

        # Shift focus to the tab that has the book open (if there is one)
        for i in range(1, self.tabWidget.count()):
            tab_book_metadata = self.tabWidget.widget(i).book_metadata
            if tab_book_metadata['book_hash'] == book_metadata['book_hash']:
                self.tabWidget.setCurrentIndex(i)
                return

        tab_ref = Tab(book_metadata, self.tabWidget)
        self.tabWidget.setCurrentWidget(tab_ref)
        print(tab_ref.book_metadata)  # Metadata upon tab creation

    def close_tab(self, tab_index):
        print(self.tabWidget.widget(tab_index).book_metadata)  # Metadata upon tab deletion
        self.tabWidget.removeTab(tab_index)

    def closeEvent(self, event=None):
        Settings(self).save_settings()
        QtWidgets.qApp.exit()


class Library:
    def __init__(self, parent):
        self.parent_window = parent
        self.proxy_model = None

    def generate_model(self):
        # TODO
        # Use QItemdelegates to show book read progress

        # The QlistView widget needs to be populated
        # with a model that inherits from QStandardItemModel
        self.parent_window.viewModel = QtGui.QStandardItemModel()
        books = database.DatabaseFunctions(
            self.parent_window.database_path).fetch_data(
                ('*',),
                'books',
                {'Title': ''},
                'LIKE')

        if not books:
            print('Database returned nothing')
            return

        for i in books:
            # The database query returns a tuple with the following indices
            # Index 0 is the key ID is ignored
            book_title = i[1]
            book_author = i[2]
            book_year = i[3]
            book_cover = i[8]
            book_tags = i[6]
            all_metadata = {
                'book_title': i[1],
                'book_author': i[2],
                'book_year': i[3],
                'book_path': i[4],
                'book_isbn': i[5],
                'book_tags': i[6],
                'book_hash': i[7]}

            tooltip_string = book_title + '\nAuthor: ' + book_author + '\nYear: ' + str(book_year)
            if book_tags:
                tooltip_string += ('\nTags: ' + book_tags)

            # This remarkably ugly hack is because the QSortFilterProxyModel
            # doesn't easily allow searching through multiple item roles
            search_workaround = book_title + ' ' + book_author
            if book_tags:
                search_workaround += book_tags

            # Generate image pixmap and then pass it to the widget
            # as a QIcon
            # Additional data can be set using an incrementing
            # QtCore.Qt.UserRole
            # QtCore.Qt.DisplayRole is the same as item.setText()
            # The model is a single row and has no columns
            img_pixmap = QtGui.QPixmap()
            img_pixmap.loadFromData(book_cover)
            img_pixmap = img_pixmap.scaled(420, 600, QtCore.Qt.IgnoreAspectRatio)
            item = QtGui.QStandardItem()
            item.setToolTip(tooltip_string)
            # The following order is needed to keep sorting working
            item.setData(book_title, QtCore.Qt.UserRole)
            item.setData(book_author, QtCore.Qt.UserRole + 1)
            item.setData(book_year, QtCore.Qt.UserRole + 2)
            item.setData(all_metadata, QtCore.Qt.UserRole + 3)
            item.setData(search_workaround, QtCore.Qt.UserRole + 4)
            item.setIcon(QtGui.QIcon(img_pixmap))
            self.parent_window.viewModel.appendRow(item)


    def update_listView(self):
        self.proxy_model = QtCore.QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.parent_window.viewModel)
        self.proxy_model.setFilterRole(QtCore.Qt.UserRole + 4)
        self.proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.proxy_model.setFilterWildcard(self.parent_window.libraryToolBar.filterEdit.text())

        self.parent_window.statusMessage.setText(
            str(self.proxy_model.rowCount()) + ' books')

        # Sorting according to roles and the drop down in the library
        self.proxy_model.setSortRole(
            QtCore.Qt.UserRole + self.parent_window.libraryToolBar.sortingBox.currentIndex())
        self.proxy_model.sort(0)

        s = QtCore.QSize(160, 250)  # Set icon sizing here
        self.parent_window.listView.setIconSize(s)
        self.parent_window.listView.setModel(self.proxy_model)


class Settings:
    def __init__(self, parent):
        self.parent_window = parent
        self.settings = QtCore.QSettings('Lector', 'Lector')

    def read_settings(self):
        self.settings.beginGroup('mainWindow')
        self.parent_window.resize(self.settings.value(
            'windowSize',
            QtCore.QSize(1299, 748)))
        self.parent_window.move(self.settings.value(
            'windowPosition',
            QtCore.QPoint(286, 141)))
        self.settings.endGroup()

        self.settings.beginGroup('runtimeVariables')
        self.parent_window.last_open_path = self.settings.value(
            'lastOpenPath', os.path.expanduser('~'))
        self.parent_window.database_path = self.settings.value(
            'databasePath',
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppDataLocation))
        self.settings.endGroup()

    def save_settings(self):
        self.settings.beginGroup('mainWindow')
        self.settings.setValue('windowSize', self.parent_window.size())
        self.settings.setValue('windowPosition', self.parent_window.pos())
        self.settings.endGroup()

        self.settings.beginGroup('runtimeVariables')
        self.settings.setValue('lastOpenPath', self.parent_window.last_open_path)
        self.settings.setValue('databasePath', self.parent_window.database_path)
        self.settings.endGroup()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName('Lector')  # This is needed for QStandardPaths
                                      # and my own hubris
    form = MainUI()
    form.show()
    app.exec_()


if __name__ == '__main__':
    main()
