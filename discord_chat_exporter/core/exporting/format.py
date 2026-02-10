"""Export format definitions."""

from enum import Enum


class ExportFormat(Enum):
    PLAIN_TEXT = "plaintext"
    HTML_DARK = "htmldark"
    HTML_LIGHT = "htmllight"
    CSV = "csv"
    JSON = "json"

    @property
    def file_extension(self) -> str:
        return {
            ExportFormat.PLAIN_TEXT: "txt",
            ExportFormat.HTML_DARK: "html",
            ExportFormat.HTML_LIGHT: "html",
            ExportFormat.CSV: "csv",
            ExportFormat.JSON: "json",
        }[self]

    @property
    def display_name(self) -> str:
        return {
            ExportFormat.PLAIN_TEXT: "TXT",
            ExportFormat.HTML_DARK: "HTML (Dark)",
            ExportFormat.HTML_LIGHT: "HTML (Light)",
            ExportFormat.CSV: "CSV",
            ExportFormat.JSON: "JSON",
        }[self]

    @property
    def is_html(self) -> bool:
        return self in (ExportFormat.HTML_DARK, ExportFormat.HTML_LIGHT)
