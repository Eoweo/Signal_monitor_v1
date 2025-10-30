import sys
import time
import os
import serial
import serial.serialutil
import serial.tools.list_ports
import csv
from PyQt6.QtCore import (pyqtSignal, QThread)
from PyQt6.QtGui import (QIcon,QAction)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox)
from PyQt6.QtWidgets import (QHBoxLayout, QVBoxLayout, QGridLayout)
from PyQt6.QtWidgets import (QPushButton, QLabel, QLineEdit, QComboBox)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.ticker as mticker

def timeformat(s, pos=None):
    m = int(s//60)
    h = int(m//60)
    s_string = "{0:.1f}".format(s%60)
    h_string = "{0:2d}".format(h)
    m_string = "{0:2d}".format(m%60)
    return h_string + ":" + m_string + ":" + s_string

class FigureCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=5, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        fig.subplots_adjust(left=0.2, right=0.9, top=0.9, bottom=0.2)
        self.axes = fig.add_subplot(111)
        self.axes.tick_params(axis='x', rotation=70, labelsize=10)
        super(FigureCanvas, self).__init__(fig)
        self.hide()

class ErrorWindow(QMessageBox):
    def __init__(self, msg):
        super().__init__()
        self.setIcon(QMessageBox.Icon.Warning)
        self.setText("Error")
        self.setInformativeText(msg)
        self.setWindowTitle("Error")

class SerialReader(QThread):
    readings = pyqtSignal(str)
    def __init__(self, port):
        super().__init__()
        try:
            self.serialCom = serial.Serial(port,9600)
        except serial.serialutil.SerialException:
            error_window = ErrorWindow("Acceso denegado al puerto. Cerrando aplicación")
            error_window.exec()
            QApplication.quit()
        except:
            error_window = ErrorWindow("Error inesperado al iniciar el puerto")
            error_window.exec()
        self.stop = False

    def run(self):
        self.serialCom.setDTR(False)
        time.sleep(1)
        self.serialCom.flushInput()
        self.serialCom.setDTR(True)

        while not self.stop:
            try:
                if self.serialCom.in_waiting:
                    packet = self.serialCom.readline().decode("utf-8").strip("\r\n")
                    self.readings.emit(packet)
            except:
                print("oops")

    def end_reading(self):
        self.stop = True

class CalibrationWindow(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("Calibración")

        vbox = QVBoxLayout()

        self.status_label = QLabel(f"m = {self.parent.m:.3f}, n = {self.parent.n:.3f}", self)
        vbox.addWidget(self.status_label)

        self.zero_button = QPushButton("Fijar cero", self)
        self.zero_button.clicked.connect(self.fijar_cero)
        vbox.addWidget(self.zero_button)

        self.k_input = QLineEdit("", self)
        self.k_input.setPlaceholderText("Valor real (k)")
        self.point_button = QPushButton("Fijar otro punto", self)
        self.point_button.clicked.connect(self.fijar_otro_punto)
        vbox.addWidget(self.k_input)
        vbox.addWidget(self.point_button)

        self.ok_button = QPushButton("Establecer", self)
        self.ok_button.clicked.connect(self.close)
        vbox.addWidget(self.ok_button)

        self.setLayout(vbox)

    def fijar_cero(self):
        if len(self.parent.raw_pressure) > 0:
            x = float(self.parent.raw_pressure[-1])
            self.parent.n = -x
            self.update_status()

    def fijar_otro_punto(self):
        if len(self.parent.raw_pressure) > 0 and self.k_input.text() != "":
            try:
                k = float(self.k_input.text())
                x = float(self.parent.raw_pressure[-1])
                self.parent.m = (k - self.parent.n) / x
                self.update_status()
            except ValueError:
                error = ErrorWindow("El valor ingresado debe ser numérico")
                error.exec()

    def update_status(self):
        self.status_label.setText(f"m = {self.parent.m:.3f}, n = {self.parent.n:.3f}")

class RecordingWindow(QWidget):
    stop_recording_signal = pyqtSignal()
    def __init__(self, path, port):
        super().__init__()
        self.time = []
        self.raw_pressure = []
        self.pressure = []
        self.temperature = []
        self.time_range = 7*24*60*60
        self.serial_reader = SerialReader(port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.prosses_new_data)
        self.path = path

        # Calibración
        self.m = 1.0
        self.n = 0.0

        # Unidades
        self.unit_factors = {"kPa": 1.0, "bar": 0.01, "mmHg": 7.50062}
        self.current_unit = "kPa"

        # Crear archivo CSV con cabecera
        with open(self.path, "w", newline="") as file:
            writer = csv.writer(file, delimiter=" ")
            writer.writerow(["Tiempo", f"Presión ({self.current_unit})", "Temperatura"])

        self.init_gui()

    def init_gui(self):
        self.setWindowTitle(f'Borealis Recorder ({self.path})')
        vbox = QVBoxLayout()

        # --- Configuración de tiempo ---
        self.label_t_window = QLabel("Ventana de tiempo (s)", self)
        self.seconds_box = QLineEdit("", self)
        self.seconds_box.setDisabled(True)
        self.set_button = QPushButton("Aplicar", self)
        self.set_button.clicked.connect(self.adjust_time)
        self.scale_drop = QComboBox()
        self.scale_drop.addItems(["Completo", "Segundos", "Minutos", "Horas"])
        self.scale_drop.currentIndexChanged.connect(self.full_mode)

        hbox1 = QHBoxLayout()
        hbox1.addStretch(1)
        hbox1.addWidget(self.label_t_window)
        hbox1.addWidget(self.seconds_box)
        hbox1.addWidget(self.scale_drop)
        hbox1.addWidget(self.set_button)
        hbox1.addStretch(1)
        vbox.addLayout(hbox1)

        # --- Botones start/stop ---
        self.start_button = QPushButton("Empezar", self)
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button = QPushButton("Parar", self)
        self.stop_button.clicked.connect(self.stop_recording)

        # --- Plots ---
        self.gbox = QGridLayout()
        self.pressure_canvas = FigureCanvas()
        self.gbox.addWidget(self.pressure_canvas)
        self.temperature_canvas = FigureCanvas()
        self.gbox.addWidget(self.temperature_canvas)
        vbox.addLayout(self.gbox)

        # --- Labels tiempo y valor actual ---
        self.time_label = QLabel("none", self)
        self.time_label.hide()
        vbox.addWidget(self.time_label)

        self.current_value_label = QLabel("Valor actual: -- kPa, -- °C", self)
        font = self.current_value_label.font()
        font.setPointSize(font.pointSize() + 5)
        self.current_value_label.setFont(font)
        self.current_value_label.hide()
        vbox.addWidget(self.current_value_label)

        # --- Botones inferiores ---
        hbox2 = QHBoxLayout()
        hbox2.addStretch(1)
        hbox2.addWidget(self.start_button)
        hbox2.addWidget(self.stop_button)
        self.stop_button.hide()
        hbox2.addStretch(1)
        vbox.addLayout(hbox2)

        # --- Botones calibración y reescalar ---
        self.calib_button = QPushButton("Calibración", self)
        self.calib_button.clicked.connect(self.open_calibration)
        self.rescale_button = QPushButton("Reescalar vista", self)
        self.rescale_button.clicked.connect(self.rescale_view)

        hbox3 = QHBoxLayout()
        hbox3.addStretch(1)
        hbox3.addWidget(self.calib_button)
        hbox3.addWidget(self.rescale_button)
        hbox3.addStretch(1)
        vbox.addLayout(hbox3)

        # --- Menú de unidades ---
        self.unit_label = QLabel("Unidad de presión:", self)
        self.unit_menu = QComboBox()
        self.unit_menu.addItems(["kPa", "bar", "mmHg"])
        self.unit_menu.currentTextChanged.connect(self.change_unit)

        hbox_units = QHBoxLayout()
        hbox_units.addStretch(1)
        hbox_units.addWidget(self.unit_label)
        hbox_units.addWidget(self.unit_menu)
        hbox_units.addStretch(1)
        vbox.addLayout(hbox_units)

        self.setLayout(vbox)

    def full_mode(self, index):
        self.seconds_box.setDisabled(index == 0)

    def prosses_new_data(self, data):
        meassures = data.split(" ")
        self.time.append(float(meassures[0])/1000)
        x = float(meassures[1])
        self.raw_pressure.append(x)
        self.pressure.append(x * self.m + self.n)
        self.temperature.append(float(meassures[2]))

        factor = self.unit_factors[self.current_unit]
        with open(self.path, "a", newline="") as file:
            writer = csv.writer(file, delimiter=" ")
            writer.writerow([self.time[-1], self.pressure[-1]*factor, self.temperature[-1]])

        self.update_graphs()

    def update_graphs(self):
        factor = self.unit_factors[self.current_unit]
        unit = self.current_unit
        scaled_pressure = [p * factor for p in self.pressure]

        self.pressure_canvas.axes.cla()
        self.pressure_canvas.axes.plot(self.time, scaled_pressure, 'r')
        self.pressure_canvas.axes.set_ylabel(f"Presión ({unit})")
        self.pressure_canvas.axes.xaxis.set_major_formatter(mticker.FuncFormatter(timeformat))
        self.pressure_canvas.axes.set_xlim((max(0, self.time[-1] - self.time_range), self.time[-1]))
        self.pressure_canvas.draw()

        self.temperature_canvas.axes.cla()
        self.temperature_canvas.axes.plot(self.time, self.temperature, 'b')
        self.temperature_canvas.axes.set_ylabel("Temperatura °C")
        self.temperature_canvas.axes.xaxis.set_major_formatter(mticker.FuncFormatter(timeformat))
        self.temperature_canvas.axes.set_xlim((max(0, self.time[-1] - self.time_range), self.time[-1]))
        self.temperature_canvas.draw()

        self.time_label.setText(f"Tiempo Actual: {timeformat(self.time[-1])}")
        self.current_value_label.setText(
            f"Presión: {scaled_pressure[-1]:.2f} {unit}   |   Temperatura: {self.temperature[-1]:.2f} °C"
        )

    def adjust_time(self):
        if self.scale_drop.currentIndex() == 0:
            self.time_range = 7*24*60*60
        else:
            try:
                t = int(self.seconds_box.text())
                if self.scale_drop.currentIndex() == 2:
                    t = t*60
                elif self.scale_drop.currentIndex() == 3:
                    t = t*60*60
                self.time_range = t
            except:
                self.error_win = ErrorWindow("Ventana de tiempo debe ser un número")
                self.error_win.exec()
        self.update_graphs()

    def stop_recording(self):
        self.stop_recording_signal.emit()
        self.close()

    def start_recording(self):
        self.setGeometry(200,100,500,500)
        self.serial_reader.start()
        self.pressure_canvas.show()
        self.temperature_canvas.show()
        self.start_button.hide()
        self.stop_button.show()
        self.time_label.show()
        self.current_value_label.show()

    def closeEvent(self, event):
        self.stop_recording_signal.emit()
        event.accept()

    def open_calibration(self):
        self.calib_window = CalibrationWindow(self)
        self.calib_window.show()

    def rescale_view(self):
        if len(self.time) == 0:
            return
        self.pressure_canvas.axes.relim()
        self.pressure_canvas.axes.autoscale_view()
        self.pressure_canvas.draw()
        self.temperature_canvas.axes.relim()
        self.temperature_canvas.axes.autoscale_view()
        self.temperature_canvas.draw()

    def change_unit(self, new_unit):
        self.current_unit = new_unit
        self.update_graphs()

class StartWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_gui()

    def init_gui(self):
        vbox = QVBoxLayout()

        ports = [str(port) for port in serial.tools.list_ports.comports()]
        self.port_label = QLabel("Seleccionar puerto", self)
        self.port_menu = QComboBox()
        self.port_menu.addItems(ports)

        hbox1 = QHBoxLayout()
        hbox1.addStretch(1)
        hbox1.addWidget(self.port_label)
        hbox1.addWidget(self.port_menu)
        hbox1.addStretch(1)
        vbox.addLayout(hbox1)

        self.name_box= QLineEdit("Nombre", self)
        self.new_button = QPushButton('Nuevo', self)
        self.new_button.clicked.connect(self.start_recroding)

        hbox2 = QHBoxLayout()
        hbox2.addStretch(1)
        hbox2.addWidget(self.name_box)
        hbox2.addWidget(self.new_button)
        hbox2.addStretch(1)
        vbox.addLayout(hbox2)

        self.setLayout(vbox)
    
    def start_recroding(self):
        if "." in self.name_box.text():
            self.error_win = ErrorWindow("Nombre inválido")
            self.error_win.exec()
        else:
            port = self.port_menu.currentText().split(" ")[0]
            self.recoring_window = RecordingWindow(os.path.join("tests", f'{self.name_box.text()}.csv'), port)
            self.recoring_window.show()

    def cargar_status_bar(self, signal):
        self.status_bar = signal

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Borealis')
        self.setGeometry(200, 100, 300, 250)

        salir = QAction(QIcon(None), '&Exit', self)
        salir.setShortcut('Ctrl+Q')
        salir.setStatusTip('Salir de la aplicación')
        salir.triggered.connect(QApplication.quit)

        menubar = self.menuBar()
        archivo_menu = menubar.addMenu('&Archivo')
        archivo_menu.addAction(salir)

        toolbar = self.addToolBar('Toolbar')
        toolbar.addAction(salir)

        self.statusBar().showMessage('Listo')

        self.form = StartWindow()
        self.setCentralWidget(self.form)

if __name__ == '__main__':
    app = QApplication([])
    form = MainWindow()
    form.show()
    sys.exit(app.exec())
