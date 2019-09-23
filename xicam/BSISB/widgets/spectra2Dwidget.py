from pyqtgraph import TextItem, PlotDataItem
from xicam.core import msg
from xicam.core.data import NonDBHeader
import numpy as np
from qtpy.QtCore import Signal
from xicam.gui.widgets.imageviewmixins import BetterButtons



class Spectra2DImageView(BetterButtons):
    sigEnergyChanged = Signal(object)

    def __init__(self, invertY=True, *args, **kwargs):
        super(Spectra2DImageView, self).__init__(*args, **kwargs)

        self.setPredefinedGradient("viridis")
        self.view.invertY(invertY)
        self.imageItem.setOpts(axisOrder="row-major")
        # add arrow
        self.cross = PlotDataItem([0], [0], symbolBrush=(200, 0, 0), symbolPen=(200, 0, 0), symbol='+', symbolSize=16)
        self.view.addItem(self.cross)
        self.cross.hide()
        # add txt
        self.E_txt = TextItem(html=self.formatTxt('E'))
        self.K_txt = TextItem(html=self.formatTxt('K'))
        self.title = TextItem('')
        self.legend_ = TextItem('')
        self.addItem(self.E_txt)
        self.addItem(self.K_txt)
        self.addItem(self.title)
        self.addItem(self.legend_)
        self.wavenumbers = None
        self._meanSpec = False  # whether current spectrum is a mean spectrum
        self.selectedPixels = None
        self._y = None
        self.spectrumInd = 0
        # connect signal
        self.scene.sigMouseClicked.connect(self.getEnergy)

    def getEnergy(self, event):
        pos = event.pos()
        if self.view.sceneBoundingRect().contains(pos):  # Note, when axes are added, you must get the view with self.view.getViewBox()
            mousePoint = self.view.mapSceneToView(pos)
            x, y = int(mousePoint.x()), int(mousePoint.y())
            y = self.row - y - 1
            try:
                ind = self.spec_rc2ind[(y, x)]
                self.sigEnergyChanged.emit(ind)
                # update crosshair
                self.cross.setData([x + 0.5], [self.row - y - 0.5])
                self.cross.show()
                # update text
                self.title.setHtml(self.formatTxt(f'Spectrum #{self.spectrumInd}'))
                self.title.setPos(self.col // 4, -3)
                self.legend_.setHtml(self.formatTxt(f'K = {x}', size=8)
                                     + self.formatTxt(f'E = {y}', size=8)
                                     + self.formatTxt(f'Val: {self._image[self.row - y - 1, x]: .4f}', size=8))
                # self.txt.setHtml(
                #     f'<div style="text-align: center"><span style="color: #FFF; font-size: 8pt">Point: #{ind}</div>\
                #     <div style="text-align: center"><span style="color: #FFF; font-size: 8pt">X: {x}</div>\
                #     <div style="text-align: center"><span style="color: #FFF; font-size: 8pt">Y: {y}</div>\
                #     <div style="text-align: center"><span style="color: #FFF; font-size: 8pt">Val: {self._image[self.row - y - 1, x]: .4f}</div>')
            except Exception:
                self.cross.hide()

    def setHeader(self, header: NonDBHeader, field: str, *args, **kwargs):
        self.header = header
        self.field = field
        # get wavenumbers
        spectraEvent = next(header.events(fields=['spectra']))
        self.wavenumbers = spectraEvent['wavenumbers']
        self.N_w = len(self.wavenumbers)
        self.specShape = spectraEvent['specShape']
        self.row, self.col = self.specShape[0], self.specShape[1]
        self.E_txt.setPos(-3, self.row // 3)
        self.K_txt.setPos(self.col // 2, self.row)
        self.title.setPos(self.col // 4, -3)
        self.legend_.setPos(self.col, 0)
        self.img_rc2ind = spectraEvent['rc_index']
        self.spec_rc2ind = spectraEvent['spec_rc_index']
        # make lazy array from document
        data = None
        try:
            data = header.meta_array(field)
        except IndexError:
            msg.logMessage(f'Header object contained no frames with field {field}.', msg.ERROR)

        if data is not None:
            # kwargs['transform'] = QTransform(1, 0, 0, -1, 0, data.shape[-2])
            self._data = data
            self._image = data[0].reshape(self.row, self.col)
            self.setImage(img=self._image, *args, **kwargs)

    def showSpectra(self, i=0):
        if (self._data is not None) and (i < len(self._data)):
            self._meanSpec = False
            self.spectrumInd = i
            self._y = self._data[i]
            self._image =self._y.reshape(self.row, self.col)
            self.setImage(img=self._image)

    def getSelectedPixels(self, selectedPixels):
        self.selectedPixels = selectedPixels

    def showMeanSpectra(self):
        self._meanSpec = True
        msg.showMessage('Start calculating mean spectrum')
        if self.selectedPixels is not None:
            n_spectra = len(self.selectedPixels)
            tmp = np.zeros((n_spectra, self.N_w))
            for j in range(n_spectra):  # j: jth selected pixel
                row_col = tuple(self.selectedPixels[j])
                tmp[j, :] = self._data[self.img_rc2ind[row_col]]
            self.title.setHtml(self.formatTxt(f'ROI mean of {n_spectra} spectra'))
        else:
            n_spectra = len(self._data)
            tmp = np.zeros((n_spectra, self.N_w))
            for j in range(n_spectra):
                tmp[j, :] = self._data[j]
            self.title.setHtml(self.formatTxt(f'Total mean of {n_spectra} spectra'))

        self.title.setPos(0, -3)
        if n_spectra > 0:
            meanSpec = np.mean(tmp, axis=0)
        else:
            meanSpec = np.zeros_like(self.wavenumbers) + 1e-3

        self._image = meanSpec.reshape(self.row, self.col)
        self.setImage(img=self._image)
        msg.showMessage('Finished calculating mean spectrum')

    def formatTxt(self, txt, size=12):
        return f'<div style="text-align: center"><span style="color: #FFF; font-size: {size}pt">{txt}</div>'

    def updateImage(self, autoHistogramRange=True):
        super(Spectra2DImageView, self).updateImage(autoHistogramRange)
        self.ui.roiPlot.setVisible(False)

    def setImage(self, img, **kwargs):
        super(Spectra2DImageView, self).setImage(img, **kwargs)
        self.ui.roiPlot.setVisible(False)
