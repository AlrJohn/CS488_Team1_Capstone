
import sys
import csv
from history_store import FIELDNAMES
from branding import logo_label
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QFrame, QAbstractItemView
)
from PySide6.QtCore import Qt


class InspectionHistory(QWidget):
    def __init__(self, history_file=None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setWindowTitle("Can Inspection System - History")
        self.resize(1050, 720)

        self.history_file = (Path(history_file) if history_file else
                             Path(__file__).resolve().parent / 'local/inspection_history.csv')

        self.setup_ui()
        self.load_history()

    def setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0B2239;
                color: white;
                font-family: Arial;
                font-size: 14px;
            }
            QLabel {
                background: transparent;
            }
            QPushButton {
                background-color: #1765A8;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2583D0;
            }
            QTableWidget {
                background-color: #F2F6FA;
                alternate-background-color: #E4ECF4;
                color: #172B42;
                gridline-color: #C8D4DF;
                border: none;
                selection-background-color: #3478B8;
                selection-color: white;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #C9D8E6;
                color: #102B45;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)

        main = QVBoxLayout(self)
        main.setContentsMargins(30, 25, 30, 25)
        main.setSpacing(18)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(24)
        # This page uses a 1200px canvas, scaled with the rest of its contents.
        header_layout.addWidget(logo_label(self, 225, 76))

        header = QLabel("CAN INSPECTION SYSTEM")
        header.setStyleSheet(
            "font-size: 25px; font-weight: bold;"
        )

        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignRight)
        self.date_label.setStyleSheet(
            "color: #B5C7D9; font-size: 12px;"
        )

        from datetime import datetime
        self.date_label.setText(
            datetime.now().strftime("%m/%d/%Y\n%I:%M %p")
        )

        header_layout.addWidget(header)
        header_layout.addStretch()
        header_layout.addWidget(self.date_label)
        main.addLayout(header_layout)

        title = QLabel("Inspection History")
        title.setStyleSheet(
            "font-size: 25px; font-weight: bold;"
        )

        subtitle = QLabel(
            "View previous inspection results and batch reports"
        )
        subtitle.setStyleSheet(
            "color: #B5C7D9; font-size: 14px;"
        )

        main.addWidget(title)
        main.addWidget(subtitle)

        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(15)

        self.total_label = self.create_summary(
            "TOTAL BATCHES", "#1765A8"
        )
        self.passed_label = self.create_summary(
            "MATCHED COUNTS", "#138A43"
        )
        self.failed_label = self.create_summary(
            "COUNT DIFFERENCES", "#C92A35"
        )

        summary_layout.addWidget(self.total_label)
        summary_layout.addWidget(self.passed_label)
        summary_layout.addWidget(self.failed_label)

        main.addLayout(summary_layout)

        table_title = QLabel("Previous Inspections")
        table_title.setStyleSheet(
            "font-size: 19px; font-weight: bold;"
        )
        main.addWidget(table_title)

        self.table = QTableWidget(0, 6)

        self.table.setHorizontalHeaderLabels([
            "Date",
            "Time",
            "Batch ID",
            "Matched",
            "Difference",
            "Status"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(42)

        main.addWidget(self.table)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.details_button = QPushButton("View Details")
        self.export_button = QPushButton("Export Report")
        self.refresh_button = QPushButton("Refresh History")
        self.clear_button = QPushButton("Clear History")
        self.back_button = QPushButton("Back to Home")

        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #C92A35;
                color: white;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #E13C48;
            }
        """)

        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #536D85;
                color: white;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6D859B;
            }
        """)

        for button in [
            self.details_button,
            self.export_button,
            self.refresh_button,
            self.clear_button,
            self.back_button
        ]:
            button_layout.addWidget(button)

        main.addLayout(button_layout)

        self.details_button.clicked.connect(self.view_details)
        self.export_button.clicked.connect(self.export_history)
        self.refresh_button.clicked.connect(self.load_history)
        self.clear_button.clicked.connect(self.clear_history)
        self.back_button.clicked.connect(self.close)

    def create_summary(self, title, color):
        label = QLabel(f"{title}\n0")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(95)
        label.setStyleSheet(f"""
            background-color: {color};
            color: white;
            border-radius: 10px;
            font-size: 19px;
            font-weight: bold;
        """)
        return label

    def load_history(self):
        self.table.setRowCount(0)
        self._records = []

        if not self.history_file.exists():
            self.update_summary()
            return

        try:
            with open(
                self.history_file,
                "r",
                newline="",
                encoding="utf-8"
            ) as file:
                reader = csv.DictReader(file)

                for record in reader:
                    self._records.append(record)
                    self.add_row([
                        record.get("Date", ""),
                        record.get("Time", ""),
                        record.get("Batch ID", ""),
                        record.get("Passed", "0"),
                        record.get("Failed", "0"),
                        record.get("Status", "")
                    ])

        except (OSError, csv.Error) as error:
            QMessageBox.warning(
                self, "History Error", str(error)
            )

        self.update_summary()

    def add_row(self, values):
        row = self.table.rowCount()
        self.table.insertRow(row)

        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)

            if column == 5:
                if str(value).upper() == "PASS":
                    item.setForeground(Qt.darkGreen)
                elif str(value).upper() == "FAIL":
                    item.setForeground(Qt.red)

            self.table.setItem(row, column, item)

    def update_summary(self):
        total = self.table.rowCount()
        passed = 0
        failed = 0

        for row in range(total):
            try:
                passed += int(self.table.item(row, 3).text())
                failed += int(self.table.item(row, 4).text())
            except (ValueError, AttributeError):
                continue

        self.total_label.setText(
            f"TOTAL BATCHES\n{total}"
        )
        self.passed_label.setText(
            f"MATCHED COUNTS\n{passed}"
        )
        self.failed_label.setText(
            f"COUNT DIFFERENCES\n{failed}"
        )

    def view_details(self):
        row = self.table.currentRow()

        if row == -1:
            QMessageBox.information(
                self,
                "Inspection Details",
                "Please select an inspection first."
            )
            return

        details = []

        for column in range(self.table.columnCount()):
            heading = self.table.horizontalHeaderItem(
                column
            ).text()

            item = self.table.item(row, column)
            value = item.text() if item else ""

            details.append(f"{heading}: {value}")

        if hasattr(self, '_records') and row < len(self._records):
            record = self._records[row]
            for key in ('Recipe','Mode','Expected Red','Expected Green','Expected Blue',
                        'Observed Red','Observed Green','Observed Blue'):
                if record.get(key, '') != '':
                    details.append(f'{key}: {record[key]}')
        QMessageBox.information(
            self,
            "Inspection Details",
            "\n".join(details)
        )

    def export_history(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Inspection History",
            "inspection_history_export.csv",
            "CSV Files (*.csv)"
        )

        if not filename:
            return

        try:
            with open(
                filename, "w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
                writer.writeheader()
                for record in self._records:
                    writer.writerow({key: record.get(key, '') for key in FIELDNAMES})

            QMessageBox.information(
                self,
                "Export Complete",
                "Inspection history exported successfully."
            )

        except OSError as error:
            QMessageBox.warning(
                self, "Export Error", str(error)
            )

    def clear_history(self):
        answer = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to delete all inspection records?",
            QMessageBox.Yes | QMessageBox.No
        )

        if answer != QMessageBox.Yes:
            return

        try:
            if self.history_file.exists():
                self.history_file.unlink()
            self._records = []
            self.table.setRowCount(0)
            self.update_summary()

        except OSError as error:
            QMessageBox.warning(
                self, "Clear Error", str(error)
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = InspectionHistory()
    window.show()

    sys.exit(app.exec())
