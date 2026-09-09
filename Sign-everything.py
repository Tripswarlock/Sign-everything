#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QTextEdit, QPushButton, QComboBox, QLineEdit, QFileDialog,
    QProgressBar, QGroupBox, QGridLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

class SignWorker(QThread):
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(self, folder, dn, pin):
        super().__init__()
        self.folder = folder
        self.dn = dn
        self.pin = pin
        self.is_running = True
        self.files_to_sign = []
        self.total_files = 0
        self.processed_files = 0

    def stop(self):
        self.is_running = False

    def scan_files(self):
        files = []
        for root, _, filenames in os.walk(self.folder):
            for file in filenames:
                if not file.lower().endswith(".sig"):
                    files.append(os.path.join(root, file))
        return files

    def run(self):
        self.files_to_sign = self.scan_files()
        self.total_files = len(self.files_to_sign)

        if self.total_files == 0:
            self.log_message.emit("Нет файлов для подписания (все файлы уже имеют подписи .sig)")
            self.finished.emit()
            return

        self.log_message.emit(f"Найдено файлов для подписания: {self.total_files}")

        for idx, file_path in enumerate(self.files_to_sign, 1):
            if not self.is_running:
                self.log_message.emit("Подписание остановлено пользователем")
                self.stopped.emit()
                return

            self.log_message.emit(f"Подписание ({idx}/{self.total_files}): {file_path}")
            try:
                subprocess.run([
                    "/opt/cprocsp/bin/amd64/cryptcp",
                    "-sign", "-detach",
                    "-dn", self.dn,
                    "-pin", self.pin,
                    file_path, file_path + ".sig"
                ], check=True, timeout=60)
                self.log_message.emit(f"OK: {os.path.basename(file_path)} подписан")
            except subprocess.TimeoutExpired:
                self.log_message.emit(f"Ошибка: тайм-аут при подписании {os.path.basename(file_path)}")
            except subprocess.CalledProcessError as e:
                self.log_message.emit(f"Ошибка: при подписании {os.path.basename(file_path)} (код {e.returncode})")
            except Exception as e:
                self.log_message.emit(f"Ошибка: {e}")

            self.processed_files = idx
            progress = int((idx / self.total_files) * 100)
            self.progress.emit(progress)

        if self.is_running:
            self.log_message.emit("Подписание завершено")
            try:
                subprocess.run(["notify-send", "Подписание завершено"], check=False)
            except:
                pass
            self.finished.emit()

class DropArea(QLabel):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAlignment(Qt.AlignCenter)
        self.setText("Перетащите папку сюда\nили нажмите кнопку 'Выбрать папку'")
        self.setStyleSheet("border: 2px dashed #aaa; padding: 20px;")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.main_window.select_folder_path(path)
                break

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Подписание файлов (КриптоПро)")
        self.setGeometry(100, 100, 700, 650)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self.drop_area = DropArea(self)
        main_layout.addWidget(self.drop_area)

        btn_layout = QHBoxLayout()
        self.btn_folder = QPushButton("Выбрать папку")
        self.btn_folder.clicked.connect(self.select_folder)
        btn_layout.addWidget(self.btn_folder)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.folder_info = QLabel("Папка не выбрана")
        main_layout.addWidget(self.folder_info)

        stats_group = QGroupBox("Статистика")
        stats_layout = QGridLayout()
        self.label_total_files = QLabel("Всего файлов: 0")
        stats_layout.addWidget(self.label_total_files, 0, 0)
        self.label_files_to_sign = QLabel("Будет подписано: 0")
        stats_layout.addWidget(self.label_files_to_sign, 0, 1)
        self.label_already_signed = QLabel("Уже подписано: 0")
        stats_layout.addWidget(self.label_already_signed, 1, 0)
        self.label_processed = QLabel("Обработано: 0")
        stats_layout.addWidget(self.label_processed, 1, 1)
        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        settings_layout = QHBoxLayout()
        self.cert_combo = QComboBox()
        self.cert_combo.setEditable(True)
        self.cert_combo.setMinimumWidth(300)
        settings_layout.addWidget(QLabel("Сертификат (DN):"))
        settings_layout.addWidget(self.cert_combo)
        self.refresh_btn = QPushButton("Обновить список")
        self.refresh_btn.clicked.connect(self.load_certificates)
        settings_layout.addWidget(self.refresh_btn)
        self.pin_edit = QLineEdit()
        self.pin_edit.setPlaceholderText("Введите PIN")
        self.pin_edit.setEchoMode(QLineEdit.Password)
        self.pin_edit.setText("11111111")
        settings_layout.addWidget(QLabel("PIN:"))
        settings_layout.addWidget(self.pin_edit)
        main_layout.addLayout(settings_layout)

        control_layout = QHBoxLayout()
        self.btn_sign = QPushButton("Подписать")
        self.btn_sign.clicked.connect(self.start_signing)
        self.btn_sign.setEnabled(False)
        control_layout.addWidget(self.btn_sign)
        self.btn_stop = QPushButton("Остановить")
        self.btn_stop.clicked.connect(self.stop_signing)
        self.btn_stop.setEnabled(False)
        control_layout.addWidget(self.btn_stop)
        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        main_layout.addWidget(self.log)

        btn_clear = QPushButton("Очистить лог")
        btn_clear.clicked.connect(self.log.clear)
        main_layout.addWidget(btn_clear)

        self.current_folder = None
        self.sign_worker = None
        self.total_files = 0
        self.already_signed = 0

        self.load_certificates()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.select_folder_path(folder)

    def select_folder_path(self, folder_path):
        self.current_folder = folder_path
        self.folder_info.setText(f"Выбрана папка: {folder_path}")
        self.log.append(f"Выбрана папка: {folder_path}")
        self.progress_bar.setValue(0)
        self.label_processed.setText("Обработано: 0")
        self.scan_folder()  # автоматическое сканирование

    def scan_folder(self):
        if not self.current_folder:
            self.log.append("Ошибка: папка не выбрана")
            return

        self.log.append(f"Сканирование папки: {self.current_folder}")

        files_to_scan = []
        already_signed = 0
        for root, _, files in os.walk(self.current_folder):
            for file in files:
                file_path = os.path.join(root, file)
                files_to_scan.append(file_path)
                if file.lower().endswith(".sig"):
                    already_signed += 1

        self.total_files = len(files_to_scan)
        self.already_signed = already_signed
        files_to_sign = self.total_files - self.already_signed

        self.label_total_files.setText(f"Всего файлов: {self.total_files}")
        self.label_already_signed.setText(f"Уже подписано: {self.already_signed}")
        self.label_files_to_sign.setText(f"Будет подписано: {files_to_sign}")
        self.label_processed.setText("Обработано: 0")

        self.log.append(f"Найдено файлов: {self.total_files}")
        self.log.append(f"Уже подписано: {self.already_signed}")
        self.log.append(f"Будет подписано: {files_to_sign}")

        if files_to_sign > 0:
            self.btn_sign.setEnabled(True)
            self.log.append("Нажмите 'Подписать' для начала процесса")
        else:
            self.btn_sign.setEnabled(False)
            self.log.append("Нет файлов для подписания")

    def start_signing(self):
        if not self.current_folder:
            self.log.append("Ошибка: папка не выбрана")
            return

        dn = self.cert_combo.currentText().strip()
        if not dn:
            self.log.append("Ошибка: не указан сертификат (DN).")
            return
        pin = self.pin_edit.text().strip()
        if not pin:
            self.log.append("Ошибка: не указан PIN.")
            return

        self.btn_sign.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_folder.setEnabled(False)
        self.progress_bar.setValue(0)
        self.label_processed.setText("Обработано: 0")

        self.sign_worker = SignWorker(self.current_folder, dn, pin)
        self.sign_worker.progress.connect(self.update_progress)
        self.sign_worker.log_message.connect(self.log.append)
        self.sign_worker.finished.connect(self.signing_finished)
        self.sign_worker.stopped.connect(self.signing_stopped)
        self.sign_worker.start()

    def stop_signing(self):
        if self.sign_worker and self.sign_worker.isRunning():
            self.log.append("Останавливаем подписание...")
            self.sign_worker.stop()
            self.btn_stop.setEnabled(False)

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        if self.sign_worker:
            self.label_processed.setText(f"Обработано: {self.sign_worker.processed_files}")

    def signing_finished(self):
        self.btn_sign.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_folder.setEnabled(True)
        self.log.append("Процесс подписания завершён")
        self.scan_folder()

    def signing_stopped(self):
        self.btn_sign.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_folder.setEnabled(True)
        self.log.append("Подписание остановлено пользователем")
        self.scan_folder()

    def load_certificates(self):
        self.log.append("Загрузка списка сертификатов...")
        try:
            result = subprocess.run(
                ["/opt/cprocsp/bin/amd64/certmgr", "-list", "-u"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                self.log.append("Ошибка выполнения certmgr. Проверьте установку КриптоПро.")
                self.log.append(result.stderr)
                return

            output = result.stdout
            raw_certs = re.findall(r'CN=([^,\n]*)', output)
            if not raw_certs:
                self.log.append("Сертификаты не найдены. Введите DN вручную.")
                self.cert_combo.clear()
                return

            certs = [c.strip() for c in raw_certs if c.strip().count(' ') >= 2]
            if not certs:
                certs = [c.strip() for c in raw_certs if c.strip()]

            certs = sorted(set(certs))
            self.cert_combo.clear()
            for cert in certs:
                self.cert_combo.addItem(f"CN={cert}")
            self.log.append(f"Найдено {len(certs)} сертификатов.")
        except FileNotFoundError:
            self.log.append("Утилита certmgr не найдена. Проверьте путь /opt/cprocsp/bin/amd64/certmgr")
        except Exception as e:
            self.log.append(f"Ошибка при загрузке сертификатов: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
