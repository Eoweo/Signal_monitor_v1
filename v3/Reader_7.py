import sys
import time
import os
import serial
import serial.serialutil
import serial.tools.list_ports
import csv
from PyQt6.QtCore import (pyqtSignal, QThread)
from PyQt6.QtGui import (QIcon, QAction, QColor, QPalette)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QMessageBox,
    QHBoxLayout, QVBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox
)
import pyqtgraph as pg
from pyqtgraph import PlotWidget, PlotDataItem, InfiniteLine, TextItem


def timeformat(seconds):
    m = int(seconds // 60)
    h = int(m // 60)
    s_string = "{0:.1f}".format(seconds % 60)
    h_string = "{0:02d}".format(h)
    m_string = "{0:02d}".format(m % 60)
    return h_string + ":" + m_string + ":" + s_string


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
                    packet = self.serialCom.readline().decode("utf-8").strip()
                    self.readings.emit(packet)
            except serial.SerialException:
                print("Serial disconnected. Trying to reconnect...")
                time.sleep(2)
                try:
                    self.serialCom.open()
                except:
                    pass

    def end_reading(self):
        self.stop = True
        try:
            if self.serialCom.is_open:
                self.serialCom.close()
        except:
            pass


class CalibrationWindow(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("Calibración")
        self.valor_raw_0 = 1

        vbox = QVBoxLayout()
        self.mn_label = QLabel("Editar directamente:")
        self.m_input = QLineEdit(f"{self.parent.m:.3f}", self)
        self.n_input = QLineEdit(f"{self.parent.n:.3f}", self)
        hbox_mn = QHBoxLayout()
        hbox_mn.addWidget(QLabel("m:"))
        hbox_mn.addWidget(self.m_input)
        hbox_mn.addWidget(QLabel("n:"))
        hbox_mn.addWidget(self.n_input)
        vbox.addWidget(self.mn_label)
        vbox.addLayout(hbox_mn)

        self.ok_button = QPushButton("Establecer manual", self)
        self.ok_button.clicked.connect(self.establecer_manual)
        vbox.addWidget(self.ok_button)

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

        self.ok_button2 = QPushButton("Cerrar", self)
        self.ok_button2.clicked.connect(self.close)
        vbox.addWidget(self.ok_button2)
        self.setLayout(vbox)

    def fijar_cero(self):
        if len(self.parent.raw_pressure) > 0:
            self.valor_raw_0 = float(self.parent.raw_pressure[-1])
            self.update_status_label(extra=" (cero fijado)")

    def send_calibration_to_arduino(self):
        try:
            mensaje = f"{self.parent.m:.5f} {self.parent.n:.5f}\n"
            self.parent.serial_reader.serialCom.write(mensaje.encode())
            print(f"Enviado a Arduino: {mensaje.strip()}")
        except Exception as e:
            print(f"Error enviando datos al Arduino: {e}")

    def fijar_otro_punto(self):
        if len(self.parent.raw_pressure) > 0 and self.k_input.text() != "":
            try:
                k = float(self.k_input.text())
                valor_raw_1 = float(self.parent.raw_pressure[-1])
                delta_raw = valor_raw_1 - self.valor_raw_0
                if delta_raw == 0:
                    raise ValueError("Los valores del sensor son iguales")
                m = k / delta_raw
                n = -m * self.valor_raw_0
                self.parent.m = m
                self.parent.n = n
                self.m_input.setText(f"{m:.3f}")
                self.n_input.setText(f"{n:.3f}")
                self.update_status_label(extra=" (calculado)")
                self.send_calibration_to_arduino()
            except ValueError:
                error = ErrorWindow("Error: valores no válidos o división por cero")
                error.exec()

    def establecer_manual(self):
        try:
            m = float(self.m_input.text())
            n = float(self.n_input.text())
            self.parent.m = m
            self.parent.n = n
            self.send_calibration_to_arduino()
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
        self.target_menu.addItems(["Presión", "Temperatura", "Flujo"])
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
            elif target == "Temperatura":
                self.parent.manual_ylim_temp = (lower, upper)
            else:
                self.parent.manual_ylim_flow = (lower, upper)
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
        self.flow = []
        self.time_range = 7 * 24 * 60 * 60
        self.serial_reader = SerialReader(port)
        self.stop_recording_signal.connect(self.serial_reader.end_reading)
        self.serial_reader.readings.connect(self.prosses_new_data)
        self.path = path

        # Calibration
        self.m = 1
        self.n = 0

        # Units
        self.unit_factors = {"kPa": 1.0, "bar": 0.01, "mmHg": 7.50062}
        self.current_unit = "mmHg"

        # Manual Y limits
        self.manual_ylim_pressure = None
        self.manual_ylim_temp = None
        self.manual_ylim_flow = None

        # Events
        self.current_hito = ""
        self.hitos = []

        # CSV file
        with open(self.path, "w", newline="") as file:
            writer = csv.writer(file, delimiter=",")
            writer.writerow(["Time", f"Pressure ({self.current_unit})", "Temperature", "Flow", "Events"])

        self.init_gui()

    def init_gui(self):
        self.setWindowTitle(f'Eoweo Recorder ({self.path})')
        vbox = QVBoxLayout()

        # --- Controls ---
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
        hbox1.addWidget(self.label_t_window)
        hbox1.addWidget(self.seconds_box)
        hbox1.addWidget(self.scale_drop)
        hbox1.addWidget(self.set_button)
        hbox1.addWidget(self.hito_input)
        hbox1.addWidget(self.hito_button)
        vbox.addLayout(hbox1)

        # --- PyQtGraph setup ---
        pg.setConfigOptions(antialias=True, background='k', foreground='w')

        self.pressure_plot = PlotWidget(title="Presión")
        self.flow_plot = PlotWidget(title="Flujo")
        self.temperature_plot = PlotWidget(title="Temperatura")

        for plot in [self.pressure_plot, self.flow_plot, self.temperature_plot]:
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.hideButtons()

        self.pressure_curve = self.pressure_plot.plot(pen=pg.mkPen('r', width=2))
        self.flow_curve = self.flow_plot.plot(pen=pg.mkPen('g', width=2))
        self.temperature_curve = self.temperature_plot.plot(pen=pg.mkPen('b', width=2))

        self.gbox = QGridLayout()
        self.gbox.addWidget(self.pressure_plot)
        self.gbox.addWidget(self.flow_plot)
        self.gbox.addWidget(self.temperature_plot)
        vbox.addLayout(self.gbox)

        # --- Labels ---
        self.time_label = QLabel("none", self)
        self.time_label.hide()
        vbox.addWidget(self.time_label)

        self.current_value_label = QLabel("Valor actual: -- kPa, -- °C, -- mL/min", self)
        font = self.current_value_label.font()
        font.setPointSize(font.pointSize() + 5)
        self.current_value_label.setFont(font)
        self.current_value_label.hide()
        vbox.addWidget(self.current_value_label)

        # --- Buttons ---
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
        hbox_controls.addWidget(self.start_button)
        hbox_controls.addWidget(self.stop_button)
        hbox_controls.addWidget(self.calib_button)
        hbox_controls.addWidget(self.unit_label)
        hbox_controls.addWidget(self.unit_menu)
        hbox_controls.addWidget(self.limits_button)
        vbox.addLayout(hbox_controls)
        self.setLayout(vbox)

    def add_hito(self):
        self.current_hito = self.hito_input.text()
        if self.current_hito and self.time:
            self.hitos.append((self.time[-1], self.current_hito))
        self.hito_input.clear()
        self.update_graphs()

    def full_mode(self, index):
        self.seconds_box.setDisabled(index == 0)

    def prosses_new_data(self, data):
        if not data or not data[0].isdigit():
            return
        parts = data.split(" ")
        if len(parts) < 4:
            return
        try:
            self.time.append(float(parts[0]) / 1000)
            x = float(parts[1])
            self.raw_pressure.append(x)
            self.pressure.append(x * self.m + self.n)
            self.temperature.append(float(parts[2]))
            self.flow.append(float(parts[3]))
        except ValueError:
            return

        factor = self.unit_factors[self.current_unit]
        with open(self.path, "a", newline="") as file:
            writer = csv.writer(file, delimiter=",")
            writer.writerow([self.time[-1], round(self.pressure[-1] * factor, 3),
                              self.temperature[-1], self.flow[-1], self.current_hito])
        self.current_hito = ""
        self.update_graphs()

    def _update_hitos(self):
        for plot in [self.pressure_plot, self.flow_plot, self.temperature_plot]:
            for item in getattr(plot, "hito_items", []):
                plot.removeItem(item)
            plot.hito_items = []

        for t, label in self.hitos:
            for plot in [self.pressure_plot, self.flow_plot, self.temperature_plot]:
                line = InfiniteLine(pos=t, angle=90, pen=pg.mkPen(color=(150, 150, 150), style=pg.QtCore.Qt.PenStyle.DashLine))
                text = TextItem(label, anchor=(0, 1), color=(200, 200, 200))
                text.setPos(t, plot.viewRange()[1][1] if plot.viewRange()[1] else 0)
                plot.addItem(line)
                plot.addItem(text)
                plot.hito_items.extend([line, text])

    def update_graphs(self):
        if not self.time:
            return

        factor = self.unit_factors[self.current_unit]
        unit = self.current_unit
        scaled_pressure = [p * factor for p in self.pressure]
        t0 = max(0, self.time[-1] - self.time_range)

        self.pressure_curve.setData(self.time, scaled_pressure)
        self.pressure_plot.setLabel('left', f"Presión ({unit})")
        self.pressure_plot.setXRange(t0, self.time[-1])
        if self.manual_ylim_pressure:
            self.pressure_plot.setYRange(*self.manual_ylim_pressure)
        else:
            self.pressure_plot.enableAutoRange(axis='y')

        self.flow_curve.setData(self.time, self.flow)
        self.flow_plot.setLabel('left', "Flujo (L/min)")
        self.flow_plot.setXRange(t0, self.time[-1])
        if self.manual_ylim_flow:
            self.flow_plot.setYRange(*self.manual_ylim_flow)
        else:
            self.flow_plot.enableAutoRange(axis='y')

        self.temperature_curve.setData(self.time, self.temperature)
        self.temperature_plot.setLabel('left', "Temperatura (°C)")
        self.temperature_plot.setXRange(t0, self.time[-1])
        if self.manual_ylim_temp:
            self.temperature_plot.setYRange(*self.manual_ylim_temp)
        else:
            self.temperature_plot.enableAutoRange(axis='y')

        self._update_hitos()

        self.time_label.setText(f"Tiempo Actual: {timeformat(self.time[-1])}")
        self.current_value_label.setText(
            f"Presión: {scaled_pressure[-1]:.2f} {unit}   |   "
            f"Temperatura: {self.temperature[-1]:.2f} °C   |   "
            f"Flujo: {self.flow[-1]:.2f} L/min"
        )

    def adjust_time(self):
        if self.scale_drop.currentIndex() == 0:
            self.time_range = 7 * 24 * 60 * 60
        else:
            try:
                t = int(self.seconds_box.text())
                if self.scale_drop.currentIndex() == 2:
                    t *= 60
                elif self.scale_drop.currentIndex() == 3:
                    t *= 3600
                self.time_range = t
            except:
                ErrorWindow("Ventana de tiempo debe ser un número").exec()
        self.update_graphs()

    def stop_recording(self):
        self.stop_recording_signal.emit()
        self.close()

    def start_recording(self):
        self.setGeometry(200, 100, 800, 600)
        self.serial_reader.start()
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
        hbox1.addWidget(self.port_label)
        hbox1.addWidget(self.port_menu)
        vbox.addLayout(hbox1)
        self.name_box = QLineEdit("Nombre", self)
        self.new_button = QPushButton('Nuevo', self)
        self.new_button.clicked.connect(self.start_recroding)
        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.name_box)
        hbox2.addWidget(self.new_button)
        vbox.addLayout(hbox2)
        self.setLayout(vbox)

    def start_recroding(self):
        if "." in self.name_box.text():
            ErrorWindow("Nombre inválido").exec()
        else:
            port = self.port_menu.currentText().split(" ")[0]
            os.makedirs("tests", exist_ok=True)
            self.recoring_window = RecordingWindow(os.path.join("tests", f'{self.name_box.text()}.csv'), port)
            self.recoring_window.show()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Eoweo Recorder')
        self.setGeometry(200, 100, 300, 250)
        salir = QAction(QIcon(None), '&Exit', self)
        salir.setShortcut('Ctrl+Q')
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
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
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
