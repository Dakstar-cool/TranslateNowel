from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class SimpleTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str], rows: list[dict[str, Any]] | None = None):
        super().__init__()
        self.headers = headers
        self.rows = rows or []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        value = self.rows[index.row()].get(self.headers[index.column()], "")
        return "" if value is None else str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.headers[section]
        return str(section + 1)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def row_dict(self, row: int) -> dict[str, Any]:
        return self.rows[row]


def rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in rows]

