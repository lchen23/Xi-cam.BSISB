import numpy as np
from qtpy.QtCore import *
from qtpy.QtWidgets import *
from qtpy.QtGui import *
from xicam.gui.widgets.tabview import TabView
from xicam.BSISB.widgets.mapconvertwidget import mapToH5
from xicam.BSISB.widgets.spectraplotwidget import SpectraPlotWidget
from xicam.BSISB.widgets.uiwidget import uiGetFile
from lbl_ir.data_objects import ir_map
from lbl_ir.io_tools.read_omnic import read_npy


class xasImageView(mapToH5):
    def __init__(self):
        super(xasImageView, self).__init__()

        self.T2AConvert.setChecked(False)
        self.T2AConvert.hide()
        self.openMapBtn.hide()
        self.fileFormat = 'npy'
        # Data model
        self.headermodel = QStandardItemModel()
        # Selection model
        self.selectionmodel = QItemSelectionModel(self.headermodel)

        self.spectra = TabView(self.headermodel, self.selectionmodel, SpectraPlotWidget, 'image')

    def openNpy(self):
        self.openBtnClicked()

    def openBtnClicked(self):
        # open file
        self.filePath, self.fileName, canceled = uiGetFile('Open npy file', self.path, "Numpy array Files (*.npy)")

        if canceled:
            self.infoBox.setText('Open file canceled.')
            return

        item = QStandardItem(self.fileName[:-4] + '_' + str(self.headermodel.rowCount()))
        self.headermodel.appendRow(item)
        self.headermodel.dataChanged.emit(QModelIndex(), QModelIndex())

        # set sample_id
        if self.sampleName.text() == 'None':
            sample_info = ir_map.sample_info(sample_id=self.fileName[:-4])
        else:
            sample_info = ir_map.sample_info(sample_id=self.sampleName.text())

        #open npy file
        self.irMap = read_npy(self.filePath + self.fileName, sample_info=sample_info)

        self.dataCube = np.moveaxis(np.flipud(self.irMap.imageCube), -1, 0)
        # set up required data/properties in self.imageview
        row, col = self.irMap.imageCube.shape[0], self.irMap.imageCube.shape[1]
        wavenumbers = self.irMap.wavenumbers
        rc2ind = {tuple(x[1:]): x[0] for x in self.irMap.ind_rc_map}
        self.updateImage(row, col, wavenumbers, rc2ind, self.dataCube)
        # set up required data/properties in self.spectra
        self.spectra.currentWidget().wavenumbers = self.imageview.wavenumbers
        self.spectra.currentWidget().rc2ind = self.imageview.rc2ind
        self.spectra.currentWidget()._data = self.irMap.data

        # Connect signals
        self.imageview.sigShowSpectra.connect(self.spectra.currentWidget().showSpectra)
        self.spectra.currentWidget().sigEnergyChanged.connect(self.imageview.setEnergy)