import os
import sys
import numpy as np
from qtpy.QtCore import *
from qtpy.QtWidgets import *
from qtpy.QtGui import *
from pyqtgraph import TextItem
from xicam.core import msg
from xicam.BSISB.widgets.spectraplotwidget import SpectraPlotWidget
from xicam.BSISB.widgets.mapviewwidget import MapViewWidget
from xicam.BSISB.widgets.uiwidget import uiGetFile, MsgBox
from lbl_ir.data_objects import ir_map
from lbl_ir.data_objects.ir_map import val2ind
from lbl_ir.io_tools.read_numpy import read_npz
from lbl_ir.io_tools.read_XAS import read_xasH5


class xasSpectraWidget(SpectraPlotWidget):
    def __init__(self):
        super(xasSpectraWidget, self).__init__()
        self.line.setValue(7000)
        self.getViewBox().invertX(False)

    def plot(self, x, y, *args, **kwargs):
        # set up infinity line and get its position
        self.plotItem.plot(x, y, *args, **kwargs)
        self.addItem(self.line)
        self.addItem(self.cross)
        x_val = self.line.value()
        if x_val == 0:
            y_val = 0
        else:
            idx = val2ind(x_val, self.wavenumbers)
            x_val = self.wavenumbers[idx]
            y_val = y[idx]

        if not self._meanSpec:
            txt_html = f'<div style="text-align: center"><span style="color: #FFF; font-size: 12pt">\
                            Spectrum #{self.spectrumInd}</div>'
        else:
            txt_html = f'<div style="text-align: center"><span style="color: #FFF; font-size: 12pt">\
                             {self._mean_title}</div>'

        txt_html += f'<div style="text-align: center"><span style="color: #FFF; font-size: 12pt">\
                             X = {x_val: .2f}, Y = {y_val: .4f}</div>'
        self.txt = TextItem(html=txt_html, anchor=(0, 0))
        ymax = np.max(y)
        self._y = y
        self.txt.setPos(x[0], 0.95 * ymax)
        self.cross.setData([x_val], [y_val])
        self.addItem(self.txt)


class xasImageView(QSplitter):
    def __init__(self):
        super(xasImageView, self).__init__()

        self.setOrientation(Qt.Vertical)
        self.imageview = MapViewWidget()
        self.imageTitle = TextItem('')
        self.imageview.addItem(self.imageTitle)
        # spectra tab
        self.spectraTab = QTabWidget()
        self.tabDict = {0: 'Cu-K', 1: 'V-K', 2: 'Fe-K'}
        for i in self.tabDict:
            setattr(self, self.tabDict[i], xasSpectraWidget())
            self.spectraTab.addTab(getattr(self, self.tabDict[i]), self.tabDict[i])

        self.imageview_and_toolbar = QSplitter()
        self.imageview_and_toolbar.setOrientation(Qt.Horizontal)
        self.toolbar_and_text = QSplitter()
        self.toolbar_and_text.setOrientation(Qt.Vertical)
        # define tool bar
        self.toolBar = QWidget()
        self.toollayout = QGridLayout()
        self.toolBar.setLayout(self.toollayout)
        # add tool bar buttons
        self.openH5Btn = QToolButton()
        self.openH5Btn.setText('Open XAS h5')
        self.openNpzBtn = QToolButton()
        self.openNpzBtn.setText('Open np array')
        self.saveBtn = QToolButton()
        self.saveBtn.setText('Save HDF5')
        # define sample name input
        self.sampleName = QLineEdit()
        self.sampleName.setText('None')
        # Assemble widgets
        self.toollayout.addWidget(self.openH5Btn)
        self.toollayout.addWidget(self.openNpzBtn)
        self.toollayout.addWidget(self.saveBtn)
        self.toollayout.addWidget(QLabel('Sample Name:'))
        self.toollayout.addWidget(self.sampleName)
        self.toollayout.setAlignment(Qt.AlignVCenter)
        # Assemble widgets
        self.toolbar_and_text.addWidget(self.toolBar)
        self.imageview_and_toolbar.addWidget(self.toolbar_and_text)
        self.imageview_and_toolbar.addWidget(self.imageview)
        self.imageview_and_toolbar.setSizes([1, 1000])  # adjust initial splitter size
        self.addWidget(self.imageview_and_toolbar)
        self.addWidget(self.spectraTab)
        self.setSizes([1000, 1000])

        # Connect signals
        for i in self.tabDict:
            self.imageview.sigShowSpectra.connect(getattr(self, self.tabDict[i]).showSpectra)
            getattr(self, self.tabDict[i]).sigEnergyChanged.connect(self.imageview.setEnergy)
        self.spectraTab.currentChanged.connect(self.tabChanged)
        self.openH5Btn.clicked.connect(self.openH5)
        self.openNpzBtn.clicked.connect(self.openNpz)
        self.saveBtn.clicked.connect(self.saveBtnClicked)

        # Constants
        self.path = os.path.dirname(sys.path[1])
        self.fileFormat = 'h5'

    def openNpz(self):
        self.fileFormat = 'npz'
        self.openH5()
        self.fileFormat = 'h5'

    def saveBtnClicked(self):
        if hasattr(self, 'irMap') and (self.filePath != ''):
            h5Name = self.fileName[:-3] + '_Cu-k.h5'
            try:
                self.irMap.write_as_hdf5(self.filePath + h5Name)
                MsgBox(f'Map to HDF5 conversion complete! \nFile Location: {self.filePath + h5Name}')
                msg.showMessage(f'HDF5 File Location: {self.filePath + h5Name}')
            except Exception as error:
                MsgBox(error.args[0], 'error')

        if hasattr(self, 'irMaps') and (self.filePath != ''):
            for k in self.irMaps:
                h5Name = self.fileName[:-3] + '_' + k + '.h5'
                try:
                    self.irMaps[k].write_as_hdf5(self.filePath + h5Name)
                    msg.showMessage(f'HDF5 File Location: {self.filePath + h5Name}')
                except Exception as error:
                    MsgBox(error.args[0], 'error')
                    break
            MsgBox(f'Map to HDF5 conversion complete! \nFile Location: {self.filePath + h5Name}')

    def openH5(self):
        """
         open XAS HDF5 file
        :return:
        """
        if self.fileFormat == 'h5':
            self.filePath, self.fileName, canceled = uiGetFile('Open HDF5 file', self.path, "HDF5 Files (*.h5)")
        elif self.fileFormat == 'npz':
            self.filePath, self.fileName, canceled = uiGetFile('Open npz file', self.path, "Numpy arrays (*.npz)")

        if canceled:
            msg.showMessage('Open file canceled.')
            return

        # set sample_id
        if self.sampleName.text() == 'None':
            sample_info = ir_map.sample_info(sample_id=self.fileName[:-3] + '_Cu-k')
        else:
            sample_info = ir_map.sample_info(sample_id=self.sampleName.text() + '_Cu-k')

        if self.fileFormat == 'npz':
            # open npz file
            try:
                self.irMap = read_npz(self.filePath + self.fileName, sample_info=sample_info)
            except Exception as error:
                MsgBox(error.args[0] + f'\nFailed to open file: {self.filePath + self.fileName}.')
                return
            # keep only 1 spectra display tab
            self.adjustTabNumber()
            self.dataCube = np.moveaxis(np.flipud(self.irMap.imageCube), -1, 0)
            # set up required data/properties in self.imageview
            rows, col = self.irMap.imageCube.shape[0], self.irMap.imageCube.shape[1]
            wavenumbers = self.irMap.wavenumbers
            rc2ind = {tuple(x[1:]): x[0] for x in self.irMap.ind_rc_map}
            self.updateImage(rows, col, wavenumbers, rc2ind, self.dataCube)
            # set up required data/properties in self.spectra
            getattr(self, self.tabDict[0]).wavenumbers = self.imageview.wavenumbers
            getattr(self, self.tabDict[0]).rc2ind = self.imageview.rc2ind
            getattr(self, self.tabDict[0])._data = self.irMap.data
        elif self.fileFormat == 'h5':
            try:
                self.irMaps = read_xasH5(self.filePath + self.fileName)
            except Exception as error:
                MsgBox(error.args[0] + f'\nFailed to open file: {self.filePath + self.fileName}.')
                return
            # adjust number of tabs to match number of bands in self.irMaps
            self.adjustTabNumber()
            self.rows, self.cols, self.wavenumbers, self.rc2inds, self.dataCubes = {}, {}, {}, {}, {}
            for i, k in enumerate(self.irMaps):
                self.spectraTab.setTabText(i, k)
                self.rows[k], self.cols[k] = self.irMaps[k].imageCube.shape[0], self.irMaps[k].imageCube.shape[1]
                self.dataCubes[k] = np.moveaxis(np.flipud(self.irMaps[k].imageCube), -1, 0)
                self.wavenumbers[k] = self.irMaps[k].wavenumbers
                self.rc2inds[k] = {tuple(x[1:]): x[0] for x in self.irMaps[k].ind_rc_map}
                self.updateImage(self.rows[k], self.cols[k], self.wavenumbers[k], self.rc2inds[k], self.dataCubes[k])
                self.imageTitle.setPos(self.cols[k] / 3, -4)
                self.imageTitle.setHtml(
                    f'<div style="text-align: center"><span style="color: #FFF; font-size: 12pt">{k} Map</div>')
                # set up required data/properties in self.spectra
                getattr(self, self.tabDict[i]).wavenumbers = self.wavenumbers[k]
                getattr(self, self.tabDict[i]).rc2ind = self.rc2inds[k]
                getattr(self, self.tabDict[i])._data = self.irMaps[k].data
                self.spectraTab.setCurrentIndex(i)

    def updateImage(self, row, col, wavenumbers, rc2ind, dataCube, title='Cu-K'):
        """
        draw a new image in imageview window
        :param row: number of rows
        :param col: number of cols
        :param wavenumbers: x-axis of a spectrum
        :param rc2ind: (row, col):spectrum index mapping
        :param dataCube: imageCube
        :param title: title of the image
        :return: None
        """
        self.imageview.row, self.imageview.col = row, col
        self.imageview.txt.setPos(col, 0)
        self.imageview.wavenumbers = wavenumbers
        self.imageview.rc2ind = rc2ind
        self.imageview._data = dataCube
        self.imageview._image = self.imageview._data[0]
        self.imageview.setImage(img=dataCube)
        self.imageTitle.setPos(col / 3, -4)
        self.imageTitle.setHtml(
            f'<div style="text-align: center"><span style="color: #FFF; font-size: 12pt">{title} Map</div>')

    def tabChanged(self, tabIdx):
        """
        synchronize spectra tab and imageview
        :param tabIdx: index of the current active tab
        :return: None
        """
        k = self.tabDict[tabIdx]
        if self.fileFormat == 'h5' and (k in self.irMaps):
            self.updateImage(self.rows[k], self.cols[k], self.wavenumbers[k], self.rc2inds[k], self.dataCubes[k], k)

    def adjustTabNumber(self):
        """
        adjust number of tabs to match number of bands
        :return: None
        """
        if self.fileFormat == 'npz':
            for i in self.tabDict.copy():  # remove tabs
                if i > 0:
                    self.spectraTab.removeTab(1)
                    self.tabDict.pop(i)
        elif self.fileFormat == 'h5':
            if len(self.tabDict) > len(self.irMaps):  # remove tabs
                for i in self.tabDict.copy():
                    if i >= len(self.irMaps):
                        self.spectraTab.removeTab(len(self.irMaps))
                        self.tabDict.pop(i)
            elif len(self.tabDict) < len(self.irMaps):  # add tabs
                for i, k in enumerate(self.irMaps):
                    if i >= len(self.tabDict):
                        self.tabDict[i] = k
                        setattr(self, self.tabDict[i], xasSpectraWidget())
                        self.spectraTab.addTab(getattr(self, self.tabDict[i]), self.tabDict[i])
                        self.imageview.sigShowSpectra.connect(getattr(self, self.tabDict[i]).showSpectra)
                        getattr(self, self.tabDict[i]).sigEnergyChanged.connect(self.imageview.setEnergy)
