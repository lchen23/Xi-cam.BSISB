import numpy as np
from xicam.BSISB.widgets.imshowwidget import SlimImageView
from xicam.core import msg
from xicam.core.data import NonDBHeader
from pyqtgraph import ArrowItem, TextItem, PlotDataItem
from qtpy.QtCore import Signal
from lbl_ir.data_objects.ir_map import val2ind

def toHtml(txt, size=12):
    return f'<div style="text-align: center"><span style="color: #FFF; font-size: {size}pt">{txt}</div>'

class MapViewWidget(SlimImageView):
    sigShowSpectra = Signal(int)

    def __init__(self, *args, **kwargs):
        super(MapViewWidget, self).__init__(*args, **kwargs)
        # self.scene.sigMouseMoved.connect(self.showSpectra)
        self.scene.sigMouseClicked.connect(self.showSpectra)
        self.view.invertY(True)
        # add arrow
        self.cross = PlotDataItem([0], [0], symbolBrush=(200, 0, 0), symbolPen=(200, 0, 0), symbol='+', symbolSize=16)
        self.view.addItem(self.cross)
        self.cross.hide()
        #add txt
        self.txt = TextItem('', anchor=(0, 0))
        self.addItem(self.txt)

    def setEnergy(self, lineobject):
        E = lineobject.value()
        # map E to index
        idx = val2ind(E, self.wavenumbers)
        self._image = self._data[idx]
        self.setCurrentIndex(idx)

    def showSpectra(self, event):
        pos = event.pos()
        if self.view.sceneBoundingRect().contains(pos):  # Note, when axes are added, you must get the view with self.view.getViewBox()
            mousePoint = self.view.mapSceneToView(pos)
            x, y = int(mousePoint.x()), int(mousePoint.y())
            y = self.row - y - 1
            try:
                ind = self.rc2ind[(y,x)]
                self.sigShowSpectra.emit(ind)
                # print(x, y, ind, x + y * self.n_col)
                #update crosshair
                self.cross.setData([x + 0.5], [self.row - y - 0.5])
                self.cross.show()
                # update text
                self.txt.setHtml(toHtml(f'Point: #{ind}', size=8)
                                 + toHtml(f'X: {x}', size=8)
                                 + toHtml(f'Y: {y}', size=8)
                                 + toHtml(f'Val: {self._image[self.row - y -1, x]: .4f}', size=8)
                                 )
            except Exception:
                self.cross.hide()


    def setHeader(self, header: NonDBHeader, field: str, *args, **kwargs):
        self.header = header
        self.field = field

        imageEvent = next(header.events(fields=['image']))
        self.rc2ind = imageEvent['rc_index']
        self.wavenumbers = imageEvent['wavenumbers']
        # make lazy array from document
        data = None
        try:
            data = header.meta_array(field)
            self.row = data.shape[1]
            self.col = data.shape[2]
            self.txt.setPos(self.col, 0)
        except IndexError:
            msg.logMessage('Header object contained no frames with field ''{field}''.', msg.ERROR)

        if data is not None:
            # kwargs['transform'] = QTransform(1, 0, 0, -1, 0, data.shape[-2])
            self.setImage(img=data, *args, **kwargs)
            self._data = data
            self._image = self._data[0]

    def updateImage(self, autoHistogramRange=True):
        super(MapViewWidget, self).updateImage(autoHistogramRange)
        self.ui.roiPlot.setVisible(False)

    def setImage(self, img, **kwargs):
        super(MapViewWidget, self).setImage(img, **kwargs)
        self.ui.roiPlot.setVisible(False)

    def makeMask(self, thresholds):
        peak1550 = val2ind(1550, self.wavenumbers)
        thr1550 = thresholds[0]
        mask = self._data[peak1550] > thr1550
        mask = mask.astype(np.int)
        return mask
