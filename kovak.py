import os
import sys
import json
import hashlib
import keyboard
from PyQt5.QtGui import QBrush, QColor, QIcon, QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt, QMimeData, QUrl, QBuffer, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QWidget, QListWidget, QVBoxLayout, QLineEdit, QDialog, QAbstractItemView, QPushButton, QSystemTrayIcon, QMenu, QMessageBox, QLabel


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_settings_path():
    home_dir = os.path.expanduser('~')
    app_dir = os.path.join(home_dir, "Kovak")
    
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)
    
    return os.path.join(app_dir, "settings.json")


SETTINGS_PATH = get_settings_path()


def load_settings():
    default_settings = {"hotkey": "shift+space"}
    
    try: 
        with open(SETTINGS_PATH, "r") as file:
            settings = json.load(file)
    
    except (FileNotFoundError, json.JSONDecodeError):
        settings = default_settings
    
    return settings


def save_settings(settings):
    with open(SETTINGS_PATH, "w") as file:
        json.dump(settings, file)


class HotkeyThread(QThread):
    hotkey_signal = pyqtSignal()

    def __init__(self, hotkey):
        super().__init__()
        self.hotkey = hotkey

    
    def run(self):
        keyboard.add_hotkey(self.hotkey, lambda: self.hotkey_signal.emit())


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.layout = QVBoxLayout(self)
        
        self.subheading_label = QLabel("Global hotkey for toggling app visibility (e.g., shift+space)", self)
        self.layout.addWidget(self.subheading_label)
        
        self.hotkey_input = QLineEdit(self)
        self.hotkey_input.setText(self.parent().settings["hotkey"])

        self.layout.addWidget(self.hotkey_input)
        self.apply_button = QPushButton("Apply", self)
        
        self.layout.addWidget(self.apply_button)
        self.apply_button.clicked.connect(self.apply_changes)
        
        self.setFixedWidth(400)
        self.setFixedHeight(120)

        self.setWindowIcon(QIcon(resource_path("settings.png")))
    

    def apply_changes(self):
        new_hotkey = self.hotkey_input.text()
        current_hotkey = self.parent().settings["hotkey"]
        
        if new_hotkey == current_hotkey:
            QMessageBox.information(self, "Info", "The new hotkey is the same as the current one")
            return

        try:
            keyboard.add_hotkey(new_hotkey, lambda: None)
            keyboard.remove_hotkey(new_hotkey)
            keyboard.remove_hotkey(current_hotkey) 
            self.parent().update_hotkey(new_hotkey)
            self.close()
        
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid hotkey entered")
            self.hotkey_input.setFocus()


class ClipboardManager(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.initUI()
        self.clipboard = QApplication.clipboard()
        self.previous_text = None
        self.history = []
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_clipboard)
        self.timer.start(1000)

        self.tray_icon = QSystemTrayIcon(QIcon(resource_path("logo.ico")), self)
        self.tray_icon.setToolTip("Kovak")
        tray_icon_menu = QMenu()
        tray_icon_menu.addAction("Exit", QApplication.instance().quit)
        self.tray_icon.setContextMenu(tray_icon_menu)
        self.tray_icon.show()
        
        self.setup_hotkey_thread()
    
    
    def setup_hotkey_thread(self):
        self.hotkey_thread = HotkeyThread(self.settings["hotkey"])
        self.hotkey_thread.hotkey_signal.connect(self.toggle_visibility)
        self.hotkey_thread.start()

    
    def open_settings_dialog(self):
        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show()

    
    def update_hotkey(self, new_hotkey):
        if self.settings["hotkey"] in keyboard._hotkeys: 
            keyboard.remove_hotkey(self.settings["hotkey"])
        
        self.settings["hotkey"] = new_hotkey
        save_settings(self.settings)
        self.setup_hotkey_thread()

    
    def toggle_visibility(self): 
        if self.isVisible():
            self.hide()
        
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()
            self.setFocus()

    
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Kovak",
            "Application was minimized to tray",
            QSystemTrayIcon.Information,
            2000
        )

    
    def initUI(self):
        self.setGeometry(300, 300, 1400, 900)
        self.setWindowTitle("Kovak")
        
        self.setWindowIcon(QIcon(resource_path("logo.ico")))
        self.layout = QVBoxLayout()
        
        self.listWidget = QListWidget()
        self.layout.addWidget(self.listWidget)
        
        self.setLayout(self.layout)
        self.listWidget.itemClicked.connect(self.copyToClipboard)

        self.settingsButton = QPushButton("Settings")
        self.settingsButton.clicked.connect(self.open_settings_dialog)
        self.layout.addWidget(self.settingsButton)

        self.clearButton = QPushButton("Clear History")
        self.layout.addWidget(self.clearButton)
        self.clearButton.clicked.connect(self.clearHistory)
        
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    

    def check_clipboard(self):
        mime_data = self.clipboard.mimeData()
        current_data = None

        if mime_data.hasImage():
            image = self.clipboard.image()
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            
            consistent_image = QImage(image.convertToFormat(QImage.Format_ARGB32))
            consistent_image.save(buffer, "PNG")
            buffer.seek(0)
            
            image_data = buffer.data()
            buffer.close()
            hash_md5 = hashlib.md5()
            
            hash_md5.update(image_data)
            image_hash = hash_md5.hexdigest()
            image_path = f"Image which has no path (hash: {image_hash})"
            
            if any(stored[0] == "image" and stored[1] == image_path for stored in self.history):
                return
            
            current_data = ("image", image_path, image)
        
        
        elif mime_data.hasUrls():
            urls = mime_data.urls()
            current_data = ("urls", ", ".join([url.toString() for url in urls]))
        
        
        elif mime_data.hasText():
            text = mime_data.text()
            current_data = ("text", text)

        
        if current_data and (current_data != self.previous_text):
            if self.previous_text is None:
                self.previous_text = current_data
            else:
                if current_data not in self.history:
                    self.history.append(current_data)
                    self.listWidget.addItem(current_data[1] if isinstance(current_data, tuple) else current_data)
                    self.listWidget.addItem("")
                self.previous_text = current_data

    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.openFindDialog()

    
    def openFindDialog(self):
        self.findDialog = QDialog(self)
        layout = QVBoxLayout()
        
        self.findDialog.setLayout(layout)
        self.searchField = QLineEdit()
        
        layout.addWidget(self.searchField)
        self.searchField.textChanged.connect(self.findInList)
        
        self.findDialog.rejected.connect(self.resetHighlighting)
        self.findDialog.setModal(False)
        
        self.findDialog.setWindowTitle("Find")
        self.findDialog.setWindowIcon(QIcon(resource_path("find.png")))
        
        self.findDialog.show()

    
    def findInList(self):
        search_term = self.searchField.text().lower()
        first_match = True
        
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            
            if search_term in item.text().lower():
                item.setBackground(QBrush(QColor(255, 255, 0)))
                item.setForeground(QBrush(QColor(0, 0, 0)))
                if first_match:
                    self.listWidget.scrollToItem(item, QAbstractItemView.PositionAtTop)
                    first_match = False
            else:
                item.setBackground(QBrush(QColor(255, 255, 255)))
                item.setForeground(QBrush(QColor(0, 0, 0)))

    
    def resetHighlighting(self):
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            item.setBackground(QBrush(QColor(255, 255, 255)))
            item.setForeground(QBrush(QColor(0, 0, 0)))
    
    
    
    def copyToClipboard(self, item):
        text = item.text()
        mime_data = QMimeData()

        for stored in self.history:
            if isinstance(stored, tuple) and stored[0] == "image" and stored[1] == text:
                image = stored[2]
                if not image.isNull():
                    self.clipboard.setPixmap(QPixmap.fromImage(image))
                    return

        
        if any(text == stored[1] for stored in self.history if isinstance(stored, tuple) and stored[0] == "urls"):
            url = QUrl(text)
            if not url.isValid():
                url = QUrl.fromLocalFile(text)
            mime_data.setUrls([url])

        
        elif any(text == stored for stored in self.history if isinstance(stored, str)):
            mime_data.setText(text)

        
        elif os.path.exists(text) and os.path.isfile(text):
            if text.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                image = QImage(text)
                
                if not image.isNull():
                    self.clipboard.setPixmap(QPixmap.fromImage(image))
                    return
            
            url = QUrl.fromLocalFile(text)
            mime_data.setUrls([url])

        
        else:
            mime_data.setText(text)

        self.clipboard.setMimeData(mime_data)

    
    def clearHistory(self):
       self.history.clear()
       self.listWidget.clear()  
       self.previous_text = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ex = ClipboardManager()
    ex.show()
    sys.exit(app.exec_())