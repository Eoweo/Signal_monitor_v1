import sys
import time
import os
import serial
import serial.serialutil
import serial.tools.list_ports
import csv
from PyQt6.QtCore import (pyqtSignal, QThread)
from PyQt6.QtGui import (QIcon, QAction)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox)
from PyQt6.QtWidgets import (QHBoxLayout, QVBoxLayout, QGridLayout)
from PyQt6.QtWidgets import (QPushButton, QLabel, QLineEdit, QComboBox)
from PyQt6.QtGui import QColor, QPalette
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.ticker as mticker


def timeformat(s, pos=None):
    m = int(s // 60)
    h = int(m // 60)
    s_string = "{0:.1f}".format(s % 60)
    h_string = "{0:2d}".format(h)
    m_string = "{0:2d}".format(m % 60)
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
            self.serialCom = serial.Serial(port, 115200)
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

        self.valor_raw_0 = 1  # Lectura del sensor para el punto cero

        vbox = QVBoxLayout()

        # m y n manuales
        self.mn_label = QLabel("Editar directamente:")
        self.m_input = QLineEdit(f"{self.parent.m:.3f}", self)
        self.m_input.setPlaceholderText("m")

        self.n_input = QLineEdit(f"{self.parent.n:.3f}", self)
        self.n_input.setPlaceholderText("n")

        hbox_mn = QHBoxLayout()
        hbox_mn.addWidget(QLabel("m:"))
        hbox_mn.addWidget(self.m_input)
        hbox_mn.addWidget(QLabel("n:"))
        hbox_mn.addWidget(self.n_input)

        vbox.addWidget(self.mn_label)
        vbox.addLayout(hbox_mn)

        # Establecer y cerrar
        self.ok_button = QPushButton("Establecer manual", self)
        self.ok_button.clicked.connect(self.establecer_manual)
        vbox.addWidget(self.ok_button)

        # Estado actual
        self.status_label = QLabel(f"m = {self.parent.m:.3f}, n = {self.parent.n:.3f}", self)
        vbox.addWidget(self.status_label)

        # Botón fijar cero
        self.zero_button = QPushButton("Fijar cero", self)
        self.zero_button.clicked.connect(self.fijar_cero)
        vbox.addWidget(self.zero_button)

        # Ingreso de otro punto
        self.k_input = QLineEdit("", self)
        self.k_input.setPlaceholderText("Valor real (k)")
        self.point_button = QPushButton("Fijar otro punto", self)
        self.point_button.clicked.connect(self.fijar_otro_punto)
        vbox.addWidget(self.k_input)
        vbox.addWidget(self.point_button)

        # Establecer y cerrar
        self.ok_button = QPushButton("Establecer", self)
        self.ok_button.clicked.connect(self.close)
        vbox.addWidget(self.ok_button)

        self.setLayout(vbox)

    def fijar_cero(self):
        if len(self.parent.raw_pressure) > 0:
            self.valor_raw_0 = float(self.parent.raw_pressure[-1])
            self.update_status_label(extra=" (cero fijado)")
    def send_calibration_to_arduino(self):
        """Envía los valores actuales de m y n al Arduino por serial."""
        try:
            # Redondear a 5 decimales y enviar en formato "m n"
            mensaje = f"{self.parent.m:.5f} {self.parent.n:.5f}\n"
            self.parent.serial_reader.serialCom.write(mensaje.encode())
            print(f"Enviado a Arduino: {mensaje.strip()}")
        except Exception as e:
            print(f"Error enviando datos al Arduino: {e}")

    def fijar_otro_punto(self):
        if len(self.parent.raw_pressure) > 0 and self.k_input.text() != "":
            try:
                k = float(self.k_input.text())  # valor real (presión conocida)
                valor_raw_1 = float(self.parent.raw_pressure[-1])
                delta_raw = valor_raw_1 - self.valor_raw_0

                if delta_raw == 0:
                    raise ValueError("Los valores del sensor son iguales")

                m = k / delta_raw
                n = -m * self.valor_raw_0

                self.parent.m = m
                self.parent.n = n
                print(f"m = {round(m, 5)}")
                print(f"n = {round(n, 5)}")
                print(type(m), type(n))

                self.m_input.setText(f"{m:.3f}")
                self.n_input.setText(f"{n:.3f}")
                self.update_status_label(extra=" (calculado)")
                self.send_calibration_to_arduino()  # 🔹 Enviar al Arduino
            except ValueError:
                error = ErrorWindow("Error: valores no válidos o división por cero")
                error.exec()

    def establecer_manual(self):
        try:
            m = float(self.m_input.text())
            n = float(self.n_input.text())
            self.parent.m = m
            self.parent.n = n
            self.send_calibration_to_arduino()  # 🔹 Enviar al Arduino
            print(type(m), type(n))
            self.close()
        except ValueError:
            error = ErrorWindow("Debe ingresar valores válidos para m y n")
            error.exec()

    def update_status_label(self, extra=""):
        self.status_label.setText(
            f"m = {self.parent.m:.6f}, n = {self.parent.n:.6f}{extra}"
        )

class LimitsWindow(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("Fijar límites eje Y")

        vbox = QVBoxLayout()

        self.target_label = QLabel("Seleccionar gráfica:", self)
        self.target_menu = QComboBox()
        self.target_menu.addItems(["Presión", "Temperatura"])
        vbox.addWidget(self.target_label)
        vbox.addWidget(self.target_menu)

        self.lower_label = QLabel("Límite inferior:", self)
        self.lower_input = QLineEdit("", self)
        vbox.addWidget(self.lower_label)
        vbox.addWidget(self.lower_input)

        self.upper_label = QLabel("Límite superior:", self)
        self.upper_input = QLineEdit("", self)
        vbox.addWidget(self.upper_label)
        vbox.addWidget(self.upper_input)

        self.apply_button = QPushButton("Fijar límites", self)
        self.apply_button.clicked.connect(self.apply_limits)
        vbox.addWidget(self.apply_button)

        self.setLayout(vbox)

    def apply_limits(self):
        try:
            lower = float(self.lower_input.text())
            upper = float(self.upper_input.text())
            if lower >= upper:
                raise ValueError("El límite inferior debe ser menor al superior")

            target = self.target_menu.currentText()
            if target == "Presión":
                self.parent.manual_ylim_pressure = (lower, upper)
            else:
                self.parent.manual_ylim_temp = (lower, upper)

            self.close()
            self.parent.update_graphs()

        except ValueError as e:
            error = ErrorWindow(str(e))
            error.exec()


class RecordingWindow(QWidget):
    stop_recording_signal = pyqtSignal()

    def __init__(self, path, port):
        super().__init__()
        self.time = []
        self.raw_pressure = []
        self.pressure = []
        self.temperature = []
        self.time_range = 7 * 24 * 60 * 60
        self.serial_reader = SerialReader(port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.prosses_new_data)
        self.path = path

        # Calibración
        self.m = 0.90043
        self.n = -0.01500

        # Unidades
        self.unit_factors = {"kPa": 1.0, "bar": 1.0, "mmHg": 1.0}
        self.current_unit = "mmHg"

        # Límites manuales
        self.manual_ylim_pressure = None
        self.manual_ylim_temp = None

        # Hitos
        self.current_hito = ""
        self.hitos = []  # lista de (tiempo, texto)

        # Crear archivo CSV con cabecera
        with open(self.path, "w", newline="") as file:
            writer = csv.writer(file, delimiter=" ")
            writer.writerow(["Tiempo", f"Presión ({self.current_unit})", "Temperatura", "Hitos"])

        self.init_gui()

    def init_gui(self):
        self.setWindowTitle(f'Eoweo Recorder ({self.path})')
        vbox = QVBoxLayout()

        # --- Configuración de tiempo y Hitos ---
        self.label_t_window = QLabel("Ventana de tiempo (s)", self)
        self.seconds_box = QLineEdit("", self)
        self.seconds_box.setDisabled(True)
        self.set_button = QPushButton("Aplicar", self)
        self.set_button.clicked.connect(self.adjust_time)
        self.scale_drop = QComboBox()
        self.scale_drop.addItems(["Completo", "Segundos", "Minutos", "Horas"])
        self.scale_drop.currentIndexChanged.connect(self.full_mode)

        self.hito_input = QLineEdit("", self)
        self.hito_input.setPlaceholderText("Escribir hito")
        self.hito_button = QPushButton("Hito", self)
        self.hito_button.clicked.connect(self.add_hito)

        hbox1 = QHBoxLayout()
        hbox1.addStretch(1)
        hbox1.addWidget(self.label_t_window)
        hbox1.addWidget(self.seconds_box)
        hbox1.addWidget(self.scale_drop)
        hbox1.addWidget(self.set_button)
        hbox1.addWidget(self.hito_input)
        hbox1.addWidget(self.hito_button)
        hbox1.addStretch(1)
        vbox.addLayout(hbox1)

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

        # --- Botones y menú en la misma fila ---
        self.start_button = QPushButton("Empezar", self)
        self.start_button.clicked.connect(self.start_recording)

        self.stop_button = QPushButton("Parar", self)
        self.stop_button.clicked.connect(self.stop_recording)
        self.stop_button.hide()

        self.calib_button = QPushButton("Calibración", self)
        self.calib_button.clicked.connect(self.open_calibration)

        self.unit_label = QLabel("Unidad:", self)
        self.unit_menu = QComboBox()
        self.unit_menu.addItems(["kPa", "bar", "mmHg"])
        self.unit_menu.currentTextChanged.connect(self.change_unit)

        self.limits_button = QPushButton("Fijar límites Y", self)
        self.limits_button.clicked.connect(self.open_limits_window)

        hbox_controls = QHBoxLayout()
        hbox_controls.addStretch(1)
        hbox_controls.addWidget(self.start_button)
        hbox_controls.addWidget(self.stop_button)
        hbox_controls.addWidget(self.calib_button)
        hbox_controls.addWidget(self.unit_label)
        hbox_controls.addWidget(self.unit_menu)
        hbox_controls.addWidget(self.limits_button)
        hbox_controls.addStretch(1)
        vbox.addLayout(hbox_controls)

        self.setLayout(vbox)

    def add_hito(self):
        self.current_hito = self.hito_input.text()
        if self.current_hito and self.time:  # Solo si ya hay datos
            self.hitos.append((self.time[-1], self.current_hito))
        self.hito_input.clear()

    def full_mode(self, index):
        self.seconds_box.setDisabled(index == 0)

    def prosses_new_data(self, data):
        meassures = data.split(" ")
        self.time.append(float(meassures[0]) / 1000)
        x = float(meassures[1])
        self.raw_pressure.append(x)
        self.pressure.append(x * self.m + self.n)
        self.temperature.append(float(meassures[2]))

        factor = self.unit_factors[self.current_unit]
        with open(self.path, "a", newline="") as file:
            writer = csv.writer(file, delimiter=" ")
            writer.writerow([self.time[-1], round(self.pressure[-1] * factor,3), self.temperature[-1], self.current_hito])
            self.current_hito = ""  # reset después de escribir

        self.update_graphs()

    def update_graphs(self):
        factor = self.unit_factors[self.current_unit]
        unit = self.current_unit
        scaled_pressure = [p * factor for p in self.pressure]

        # --- Gráfico de Presión ---
        self.pressure_canvas.axes.cla()
        self.pressure_canvas.axes.plot(self.time, scaled_pressure, 'r')
        self.pressure_canvas.axes.set_ylabel(f"Presión ({unit})")
        self.pressure_canvas.axes.xaxis.set_major_formatter(mticker.FuncFormatter(timeformat))
        self.pressure_canvas.axes.set_xlim((max(0, self.time[-1] - self.time_range), self.time[-1]))
        if self.manual_ylim_pressure:
            self.pressure_canvas.axes.set_ylim(self.manual_ylim_pressure)

        # Dibujar hitos
        for t, label in self.hitos:
            self.pressure_canvas.axes.axvline(x=t, color="gray", linestyle="--", alpha=0.7)
            self.pressure_canvas.axes.text(t, self.pressure_canvas.axes.get_ylim()[1],
                                           label, rotation=90, verticalalignment='bottom',
                                           fontsize=8, color="gray")

        self.pressure_canvas.draw()

        # --- Gráfico de Temperatura ---
        self.temperature_canvas.axes.cla()
        self.temperature_canvas.axes.plot(self.time, self.temperature, 'b')
        self.temperature_canvas.axes.set_ylabel("Temperatura °C")
        self.temperature_canvas.axes.xaxis.set_major_formatter(mticker.FuncFormatter(timeformat))
        self.temperature_canvas.axes.set_xlim((max(0, self.time[-1] - self.time_range), self.time[-1]))
        if self.manual_ylim_temp:
            self.temperature_canvas.axes.set_ylim(self.manual_ylim_temp)

        # Dibujar hitos
        for t, label in self.hitos:
            self.temperature_canvas.axes.axvline(x=t, color="gray", linestyle="--", alpha=0.7)
            self.temperature_canvas.axes.text(t, self.temperature_canvas.axes.get_ylim()[1],
                                              label, rotation=90, verticalalignment='bottom',
                                              fontsize=8, color="gray")

        self.temperature_canvas.draw()

        # Labels
        self.time_label.setText(f"Tiempo Actual: {timeformat(self.time[-1])}")
        self.current_value_label.setText(
            f"Presión: {scaled_pressure[-1]:.2f} {unit}   |   Temperatura: {self.temperature[-1]:.2f} °C"
        )

    def adjust_time(self):
        if self.scale_drop.currentIndex() == 0:
            self.time_range = 7 * 24 * 60 * 60
        else:
            try:
                t = int(self.seconds_box.text())
                if self.scale_drop.currentIndex() == 2:
                    t = t * 60
                elif self.scale_drop.currentIndex() == 3:
                    t = t * 60 * 60
                self.time_range = t
            except:
                self.error_win = ErrorWindow("Ventana de tiempo debe ser un número")
                self.error_win.exec()
        self.update_graphs()

    def stop_recording(self):
        self.stop_recording_signal.emit()
        self.close()

    def start_recording(self):
        self.setGeometry(200, 100, 500, 500)
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

    def open_limits_window(self):
        self.limits_window = LimitsWindow(self)
        self.limits_window.show()

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

        self.name_box = QLineEdit("Nombre", self)
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Eoweo Recorder')
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

def set_dark_mode(app):
    dark_palette = QPalette()

    # Colores base
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))

    # Links
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

    app.setPalette(dark_palette)


if __name__ == '__main__':
    app = QApplication([])
    app.setStyle("Fusion")
    set_dark_mode(app)
    form = MainWindow()
    form.show()
    sys.exit(app.exec())
