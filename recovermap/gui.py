"""GUI RecoverMap — PySide6.

Recuperação ILIMITADA de arquivos com visual claro/escuro.
Fontes: imagens (E01/RAW/img/dd) ou dispositivos (Windows: \\\\.\\PhysicalDriveN).
"""
from __future__ import annotations

import os
import sys
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QTableView,
    QVBoxLayout, QWidget, QAbstractItemView, QCheckBox,
)
from PySide6.QtGui import QStandardItemModel, QStandardItem

from . import __version__, themes
from .core import RecoverMapEngine

PREVIEW_ROWS = 1000  # linhas mostradas na tabela (mapa completo fica no export)


class _Signals(QObject):
    map_done = Signal(list)
    recover_done = Signal(dict)
    progress = Signal(int, int, str)
    failed = Signal(str)


class _MapWorker(threading.Thread):
    def __init__(self, source, offset, sig):
        super().__init__(daemon=True)
        self.source, self.offset, self.sig = source, offset, sig

    def run(self):
        try:
            eng = RecoverMapEngine(self.source, self.offset)
            entries = eng.walk(
                on_progress=lambda n, d: self.sig.progress.emit(n, d, ""))
            self.sig.map_done.emit(entries)
        except Exception as exc:
            self.sig.failed.emit(f"Falha ao ler a fonte: {exc}")


class _RecoverWorker(threading.Thread):
    def __init__(self, source, offset, outdir, only_deleted, sig):
        super().__init__(daemon=True)
        self.source, self.offset = source, offset
        self.outdir, self.only_deleted, self.sig = outdir, only_deleted, sig

    def run(self):
        try:
            eng = RecoverMapEngine(self.source, self.offset)
            entries = eng.walk()
            res = eng.recover(
                self.outdir, entries, only_deleted=self.only_deleted,
                on_progress=lambda i, t, p: self.sig.progress.emit(i, t, p),
                report_path=os.path.join(self.outdir, "recovermap-report.csv"))
            self.sig.recover_done.emit(res)
        except Exception as exc:
            self.sig.failed.emit(f"Falha na recuperação: {exc}")


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.dark = False
        self.entries = []
        self.sig = _Signals()
        self.worker = None
        self.setWindowTitle(f"RecoverMap {__version__} — recuperação sem limites")
        self.resize(860, 600)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # --- linha 1: fonte
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Disco/imagem:"))
        self.ed_source = QLineEdit()
        self.ed_source.setPlaceholderText(
            "imagem.raw, .img, .dd, .E01 — ou \\\\.\\PhysicalDrive2 (Windows, admin)")
        row1.addWidget(self.ed_source, 1)
        b_src = QPushButton("Abrir…")
        b_src.clicked.connect(self._pick_source)
        row1.addWidget(b_src)
        root.addLayout(row1)

        # --- linha 2: destino
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Salvar em:"))
        self.ed_out = QLineEdit()
        row2.addWidget(self.ed_out, 1)
        b_out = QPushButton("Pasta…")
        b_out.clicked.connect(self._pick_out)
        row2.addWidget(b_out)
        root.addLayout(row2)

        # --- linha 3: ações
        row3 = QHBoxLayout()
        self.btn_map = QPushButton("🗺  Gerar mapa")
        self.btn_map.clicked.connect(self._do_map)
        self.btn_recover = QPushButton("♻  Recuperar TUDO")
        self.btn_recover.clicked.connect(self._do_recover)
        self.btn_recover.setEnabled(False)
        self.chk_deleted_only = QCheckBox("somente deletados")
        row3.addWidget(self.btn_map)
        row3.addWidget(self.btn_recover)
        row3.addWidget(self.chk_deleted_only)
        row3.addStretch(1)
        self.btn_theme = QPushButton("🌙  Tema escuro")
        self.btn_theme.clicked.connect(self._toggle_theme)
        row3.addWidget(self.btn_theme)
        root.addLayout(row3)

        # --- status
        self.lbl_status = QLabel("Abra um disco ou imagem para começar.")
        root.addWidget(self.lbl_status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        root.addWidget(self.bar)

        # --- tabela
        self.table = QTableView()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.model = QStandardItemModel(0, 3, self)
        self.model.setHorizontalHeaderLabels(["Arquivo", "Tamanho", "Estado"])
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        self.setCentralWidget(central)

        # sinais
        self.sig.map_done.connect(self._on_map_done)
        self.sig.recover_done.connect(self._on_recover_done)
        self.sig.progress.connect(self._on_progress)
        self.sig.failed.connect(self._on_failed)

    # ------------------------------------------------------------- temas
    def _toggle_theme(self):
        self.dark = not self.dark
        themes.apply_theme(self.app, self.dark)
        self.btn_theme.setText("☀️  Tema claro" if self.dark else "🌙  Tema escuro")

    # ------------------------------------------------------------ ações
    def _pick_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher imagem/disco")
        if path:
            self.ed_source.setText(path)

    def _pick_out(self):
        path = QFileDialog.getExistingDirectory(self, "Pasta de destino")
        if path:
            self.ed_out.setText(path)

    def _source(self):
        src = self.ed_source.text().strip()
        if not src:
            QMessageBox.warning(self, "RecoverMap", "Informe o disco/imagem.")
            raise SystemExit
        return src

    def _busy(self, on: bool, text: str):
        self.btn_map.setEnabled(not on)
        self.btn_recover.setEnabled(not on and bool(self.entries))
        self.lbl_status.setText(text)

    def _do_map(self):
        src = self._source()
        self._busy(True, "Lendo o disco e montando o mapa…")
        self.bar.setRange(0, 0)
        self.worker = _MapWorker(src, 0, self.sig)
        self.worker.start()

    def _on_map_done(self, entries):
        self.entries = entries
        files = [e for e in entries if not e.is_dir]
        deleted = [e for e in files if e.deleted]
        self.model.setRowCount(0)
        for e in files[:PREVIEW_ROWS]:
            self.model.appendRow([
                QStandardItem(e.path),
                QStandardItem(f"{e.size:,}".replace(",", ".")),
                QStandardItem("🗑 deletado" if e.deleted else "ok"),
            ])
        extra = f"  ·  (mostrando {PREVIEW_ROWS} na tabela)" if len(files) > PREVIEW_ROWS else ""
        self.lbl_status.setText(
            f"{len(files):,} arquivos no mapa · {len(deleted):,} deletados"
            f"{extra}".replace(",", "."))
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self._busy(False, self.lbl_status.text())

    def _do_recover(self):
        src = self._source()
        out = self.ed_out.text().strip()
        if not out:
            QMessageBox.warning(self, "RecoverMap", "Informe a pasta de destino.")
            return
        self._busy(True, "Recuperando arquivos… (sem limite de quantidade)")
        self.bar.setRange(0, 0)
        self.worker = _RecoverWorker(src, 0, out,
                                     self.chk_deleted_only.isChecked(),
                                     self.sig)
        self.worker.start()

    def _on_recover_done(self, res):
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.lbl_status.setText(
            f"✔ {res['ok']:,} arquivos recuperados · {res['fail']:,} falhas · "
            f"{res['bytes']:,} bytes · relatório: recovermap-report.csv"
        ).replace(",", ".")
        self._busy(False, self.lbl_status.text())
        if res["fail"]:
            QMessageBox.warning(self, "RecoverMap",
                                f"{res['fail']} arquivo(s) falharam — veja o CSV.")

    def _on_progress(self, done, total, name):
        if total:
            self.lbl_status.setText(f"{done:,}/{total:,}  {name}".replace(",", "."))

    def _on_failed(self, msg):
        self.bar.setRange(0, 1)
        self._busy(False, "Erro.")
        QMessageBox.critical(self, "RecoverMap", msg)


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("RecoverMap")
    themes.apply_theme(app, False)
    win = MainWindow(app)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
