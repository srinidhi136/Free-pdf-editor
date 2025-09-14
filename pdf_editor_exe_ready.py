import sys, io, os
import fitz  # PyMuPDF
from PIL import Image
from PyQt5 import QtWidgets, QtGui, QtCore

class LazyPageWidget(QtWidgets.QLabel):
    def __init__(self, page_index, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self.base_pixmap = None
        self.overlay = None
        self.pen_color = QtGui.QColor(0,0,0)
        self.pen_width = 4
        self.mode = "pen"
        self.text_to_add = None
        self.pen_down = False
        self.last_pt = None
        self.setAlignment(QtCore.Qt.AlignTop)
        self.setStyleSheet("border: 1px solid #aaa; border-radius:4px;")
        # Shadow effect
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(2,2)
        self.setGraphicsEffect(shadow)

    def load_pixmap(self, pixmap):
        self.base_pixmap = pixmap
        if self.overlay is None:
            self.overlay = QtGui.QPixmap(pixmap.size())
            self.overlay.fill(QtCore.Qt.transparent)
        self.update_display()

    def update_display(self):
        if self.base_pixmap is None:
            return
        composed = QtGui.QPixmap(self.base_pixmap.size())
        painter = QtGui.QPainter(composed)
        painter.drawPixmap(0,0,self.base_pixmap)
        painter.drawPixmap(0,0,self.overlay)
        # Page number
        font = QtGui.QFont("Arial", 12, QtGui.QFont.Bold)
        painter.setFont(font)
        painter.setPen(QtGui.QPen(QtGui.QColor(80,80,80)))
        painter.drawText(10, 20, f"Page {self.page_index +1}")
        painter.end()
        self.setPixmap(composed)

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self.pen_down = True
            self.last_pt = ev.pos()
            if self.text_to_add:
                painter = QtGui.QPainter(self.overlay)
                font = QtGui.QFont()
                font.setPointSize(14)
                painter.setFont(font)
                painter.setPen(QtGui.QPen(self.pen_color))
                painter.drawText(ev.pos(), self.text_to_add)
                painter.end()
                self.text_to_add = None
                self.update_display()

    def mouseMoveEvent(self, ev):
        if not self.pen_down or self.base_pixmap is None:
            return
        painter = QtGui.QPainter(self.overlay)
        pen = QtGui.QPen(QtCore.Qt.white if self.mode=="erase" else self.pen_color,
                         self.pen_width*3 if self.mode=="erase" else self.pen_width,
                         QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(self.last_pt, ev.pos())
        painter.end()
        self.last_pt = ev.pos()
        self.update_display()

    def mouseReleaseEvent(self, ev):
        self.pen_down = False
        self.last_pt = None

    def clear_overlay(self):
        if self.overlay:
            self.overlay.fill(QtCore.Qt.transparent)
            self.update_display()

    def export_overlay_image(self):
        if self.base_pixmap is None:
            return None
        composed = QtGui.QImage(self.base_pixmap.size(), QtGui.QImage.Format_ARGB32)
        painter = QtGui.QPainter(composed)
        painter.drawPixmap(0,0,self.base_pixmap)
        painter.drawPixmap(0,0,self.overlay)
        painter.end()
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QBuffer.ReadWrite)
        composed.save(buffer,"PNG")
        return buffer.data()


class PDFEditorExe(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Editor - EXE Ready")
        self.resize(1100,750)
        self.doc = None
        self.pages = []
        self.zoom_factor = 2.0
        self.current_file_path = None

        # Scroll area
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.container = QtWidgets.QWidget()
        self.v_layout = QtWidgets.QVBoxLayout(self.container)
        self.v_layout.setSpacing(20)
        self.v_layout.setContentsMargins(10,10,10,10)
        self.scroll_area.setWidget(self.container)
        self.setCentralWidget(self.scroll_area)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.check_visible_pages)

        # Toolbar
        toolbar = QtWidgets.QToolBar()
        self.addToolBar(toolbar)

        # Add buttons (text-only)
        self.add_toolbar_button(toolbar, "Open PDF", self.open_pdf)
        self.add_toolbar_button(toolbar, "Save PDF", self.save_pdf)
        self.add_toolbar_button(toolbar, "Exit", self.close)
        self.add_toolbar_button(toolbar, "Pen", lambda: self.set_mode("pen"))
        self.add_toolbar_button(toolbar, "Eraser", lambda: self.set_mode("erase"))
        self.add_toolbar_button(toolbar, "Add Text", self.add_text)
        self.add_toolbar_button(toolbar, "Clear All", self.clear_all)
        self.add_toolbar_button(toolbar, "Zoom In", lambda: self.zoom_visible_pages(1.25))
        self.add_toolbar_button(toolbar, "Zoom Out", lambda: self.zoom_visible_pages(0.8))

    def add_toolbar_button(self, toolbar, text, callback):
        btn = QtWidgets.QToolButton()
        btn.setText(text)
        btn.setToolTip(text)
        btn.clicked.connect(callback)
        btn.setStyleSheet("""
            QToolButton { padding:5px; border:none; font-weight:bold; }
            QToolButton:hover { background-color:#ddd; border-radius:4px; }
        """)
        toolbar.addWidget(btn)

    def open_pdf(self):
        path,_ = QtWidgets.QFileDialog.getOpenFileName(self,"Open PDF","","PDF Files (*.pdf)")
        if not path:
            return
        self.current_file_path = path
        try:
            self.doc = fitz.open(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self,"Error",f"Cannot open PDF: {e}")
            return
        for w in self.pages:
            w.deleteLater()
        self.pages.clear()
        self.v_layout.update()
        for i,_ in enumerate(self.doc):
            page_widget = LazyPageWidget(i)
            self.v_layout.addWidget(page_widget)
            self.pages.append(page_widget)
        self.check_visible_pages()

    def check_visible_pages(self):
        if not self.doc:
            return
        scroll_value = self.scroll_area.verticalScrollBar().value()
        viewport_height = self.scroll_area.viewport().height()
        for page_widget in self.pages:
            pos = page_widget.pos().y()
            if pos + page_widget.height() >= scroll_value - 200 and pos <= scroll_value + viewport_height + 200:
                if page_widget.base_pixmap is None:
                    self.render_page(page_widget)

    def render_page(self, page_widget):
        page = self.doc.load_page(page_widget.page_index)
        mat = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        qimg = QtGui.QImage(pix.samples,pix.width,pix.height,pix.stride,QtGui.QImage.Format_RGB888).copy()
        pixmap = QtGui.QPixmap.fromImage(qimg)
        page_widget.load_pixmap(pixmap)

    def set_mode(self, mode):
        for page in self.pages:
            page.mode = mode

    def add_text(self):
        text, ok = QtWidgets.QInputDialog.getText(self,"Add Text","Text to add:")
        if ok and text:
            for page in self.pages:
                page.text_to_add = text

    def clear_all(self):
        for page in self.pages:
            page.clear_overlay()

    def zoom_visible_pages(self,factor):
        self.zoom_factor *= factor
        for page_widget in self.pages:
            if page_widget.base_pixmap is not None:
                page_widget.base_pixmap = None
        self.check_visible_pages()

    def save_pdf(self):
        if not self.doc:
            return
        if self.current_file_path:
            default_name = os.path.splitext(self.current_file_path)[0]+"_edited.pdf"
        else:
            default_name = "edited.pdf"
        out_path,_ = QtWidgets.QFileDialog.getSaveFileName(self,"Save PDF",default_name,"PDF Files (*.pdf)")
        if not out_path:
            return
        new_doc = fitz.open()
        for page_widget in self.pages:
            overlay_bytes = page_widget.export_overlay_image()
            if overlay_bytes is None:
                continue
            im = Image.open(io.BytesIO(overlay_bytes))
            w,h = im.size
            rect = fitz.Rect(0,0,w,h)
            new_page = new_doc.new_page(width=w,height=h)
            new_doc.insert_image(rect, stream=overlay_bytes)
        new_doc.save(out_path)
        new_doc.close()
        QtWidgets.QMessageBox.information(self,"Saved",f"Saved PDF to {out_path}")


def main():
    app = QtWidgets.QApplication(sys.argv)
    editor = PDFEditorExe()
    editor.show()
    sys.exit(app.exec_())

if __name__=="__main__":
    main()
