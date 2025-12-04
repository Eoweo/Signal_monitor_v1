import sys
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QComboBox, QLineEdit, QHBoxLayout
from PyQt6.QtGui import QPalette, QColor, QAction, QIcon
import serial.tools.list_ports
from frontend import RecordingWindow


def set_dark_mode(app):
    """Applies a consistent dark theme to all widgets, including buttons."""
    dark_palette = QPalette()

    # --- General colors ---
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))

    # --- Links & highlights ---
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

    app.setPalette(dark_palette)

    # --- Force dark style for widgets that ignore palette ---
    app.setStyleSheet("""
        QWidget {
            background-color: #2D2D2D;
            color: #DDDDDD;
            selection-background-color: #2A82DA;
        }
        QPushButton {
            background-color: #353535;
            border: 1px solid #444;
            padding: 4px 8px;
            border-radius: 6px;
        }
        QPushButton:hover {
            background-color: #3E3E3E;
        }
        QPushButton:pressed {
            background-color: #2A82DA;
        }
        QLineEdit, QComboBox, QTextEdit {
            background-color: #3A3A3A;
            color: #FFFFFF;
            border: 1px solid #555;
            border-radius: 4px;
        }
        QComboBox QAbstractItemView {
            background-color: #2D2D2D;
            color: #FFFFFF;
            selection-background-color: #2A82DA;
        }
        QLabel {
            color: #DDDDDD;
        }
        QToolTip {
            background-color: #2A82DA;
            color: #000000;
            border: none;
        }
    """)



class StartWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        vbox = QVBoxLayout()
        ports = [str(port) for port in serial.tools.list_ports.comports()]
        self.port_label = QLabel("Seleccionar puerto:")
        self.port_menu = QComboBox()
        self.port_menu.addItems(ports)
        self.name_box = QLineEdit("Nombre")
        self.new_button = QPushButton('Nuevo')
        self.new_button.clicked.connect(self.start_recording)
        hbox = QHBoxLayout()
        hbox.addWidget(self.port_label)
        hbox.addWidget(self.port_menu)
        vbox.addLayout(hbox)
        vbox.addWidget(self.name_box)
        vbox.addWidget(self.new_button)
        self.setLayout(vbox)

    def start_recording(self):
        port = self.port_menu.currentText().split(" ")[0]
        os.makedirs("tests", exist_ok=True)
        path = os.path.join("tests", f"{self.name_box.text()}.csv")
        self.recorder_window = RecordingWindow(path, port)
        self.recorder_window.show()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Eoweo Recorder")
        self.setGeometry(200, 100, 300, 200)
        salir = QAction(QIcon(None), '&Exit', self)
        salir.setShortcut('Ctrl+Q')
        salir.triggered.connect(QApplication.quit)
        menubar = self.menuBar()
        archivo_menu = menubar.addMenu('&Archivo')
        archivo_menu.addAction(salir)
        self.setCentralWidget(StartWindow())


if __name__ == "__main__":
    app = QApplication([])
    set_dark_mode(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
