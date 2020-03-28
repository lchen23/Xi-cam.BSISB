from qtpy.QtWidgets import *
from qtpy.QtCore import Qt, QItemSelectionModel
from qtpy.QtGui import QStandardItemModel, QStandardItem, QFont
from pyqtgraph.parametertree import ParameterTree, Parameter
from pyqtgraph import PlotWidget, TextItem, mkPen
from xicam.core import msg
from xicam.BSISB.widgets.xasimagewidget import xasSpectraWidget
from larch import Group as lchGroup
from larch.xafs import pre_edge

class NormalizationParameters(ParameterTree):

    def __init__(self):
        super(NormalizationParameters, self).__init__()

        self.parameter = Parameter(name='params', type='group',
                                   children=[{'name': "Normalization method",
                                              'values': ['polynomial', 'mback'],
                                              'value': 'polynomial',
                                              'type': 'list'},
                                             {'name': "Polynomial type",
                                              'values': ['constant', 'linear','quadratic','cubic'],
                                              'value': 'linear',
                                              'type': 'list'},
                                             {'name': "E0",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Edge step",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Y offset",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Victoreen order",
                                              'values': [0, 1, 2, 3],
                                              'value': 0,
                                              'type': 'list'},
                                             {'name': "Pre-edge range",
                                              'value': '0.0 : 0.0',
                                              'type': 'str'},
                                             {'name': "Normalization range",
                                              'value': '0.0 : 0.0',
                                              'type': 'str'},
                                             ])
        self.setParameters(self.parameter, showTop=False)
        self.setIndentation(0)

class NormalizationWidget(QSplitter):
    def __init__(self, headermodel, selectionmodel):
        super(NormalizationWidget, self).__init__()
        self.headermodel = headermodel
        self.mapselectmodel = selectionmodel
        self.selectMapidx = 0

        # split between spectrum parameters and viewwindow, vertical split
        self.paramsplitter = QSplitter()
        self.paramsplitter.setOrientation(Qt.Vertical)
        # split between buttons and parameters
        self.buttons_and_params = QSplitter()
        self.buttons_and_params.setOrientation(Qt.Horizontal)
        # buttons layout
        self.buttons = QWidget()
        self.buttonlayout = QGridLayout()
        self.buttons.setLayout(self.buttonlayout)
        #set up buttons
        self.fontSize = 12
        font = QFont()
        font.setPointSize(self.fontSize)
        self.loadBtn = QToolButton()
        self.loadBtn.setText('Load spectra')
        self.loadBtn.setFont(font)
        self.removeBtn = QToolButton()
        self.removeBtn.setText('Remove spectrum')
        self.removeBtn.setFont(font)
        self.normBox = QComboBox()
        self.normBox.addItems(['Raw','Normalized', 'Flattened', 'mback', 'mback + poly normalized',
         '1st derivative', 'Normalized + derivative'])
        self.normBox.setFont(font)
        self.batchBtn = QToolButton()
        self.batchBtn.setText('Batch Process')
        self.batchBtn.setFont(font)
        # add all buttons
        self.buttonlayout.addWidget(self.loadBtn)
        self.buttonlayout.addWidget(self.removeBtn)
        self.buttonlayout.addWidget(self.normBox)
        self.buttonlayout.addWidget(self.batchBtn)

        # spectrum list view
        self.specItemModel = QStandardItemModel()
        self.specSelectModel = QItemSelectionModel(self.specItemModel)
        self.speclistview = QListView()
        self.speclistview.setModel(self.specItemModel)
        self.speclistview.setSelectionModel(self.specSelectModel)
        # spectrum plot
        self.rawSpectra = xasSpectraWidget()
        self.resultSpectra = xasSpectraWidget()
        # ParameterTree
        self.parametertree = NormalizationParameters()

        #assemble widgets
        self.buttons_and_params.addWidget(self.parametertree)
        self.buttons_and_params.addWidget(self.buttons)
        self.paramsplitter.addWidget(self.buttons_and_params)
        self.paramsplitter.addWidget(self.rawSpectra)
        self.paramsplitter.addWidget(self.resultSpectra)
        self.paramsplitter.setSizes([100, 50, 50])
        self.addWidget(self.paramsplitter)
        self.addWidget(self.speclistview)
        self.setSizes([1000, 200])

        # Connect signals
        self.specSelectModel.selectionChanged.connect(self.updateRawSpec)
        self.loadBtn.clicked.connect(self.loadData)
        self.normBox.currentIndexChanged.connect(self.updateResultSpec)
        self.removeBtn.clicked.connect(self.removeSpec)

    def setHeader(self, field: str):
        self.headers = [self.headermodel.item(i).header for i in range(self.headermodel.rowCount())]
        self.field = field
        self.energyList = []
        self.rc2indList = []
        self.dataSets = []

        # get wavenumbers, rc2ind
        for header in self.headers:
            dataEvent = next(header.events(fields=[field]))
            self.energyList.append(dataEvent['wavenumbers'])
            self.rc2indList.append(dataEvent['rc_index'])
            # get raw spectra
            data = None
            try:  # spectra datasets
                data = header.meta_array('spectra')
            except IndexError:
                msg.logMessage('Header object contained no frames with field ''{field}''.', msg.ERROR)
            if data is not None:
                self.dataSets.append(data)

    def isMapOpen(self):
        if not self.mapselectmodel.selectedIndexes(): # no map is open
            return False
        else:
            self.selectMapidx = self.mapselectmodel.selectedIndexes()[0].row()
            return True

    def getCurrentSpecid(self):
        # get selected spectrum idx
        specidx = None #default value
        if self.specSelectModel.selectedIndexes():
            selectedSpecRow = self.specSelectModel.selectedIndexes()[0].row()
            currentSpecItem = self.specItemModel.item(selectedSpecRow)
            specidx = currentSpecItem.idx
        return specidx

    def updateResultSpec(self, plotChoice=0):
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        if (not self.isMapOpen()) or (specidx is None):
            return
        # create larch Group object
        out = lchGroup()
        out.energy, out.mu = self.energyList[self.selectMapidx], self.dataSets[self.selectMapidx][specidx]
        # calculate pre/post edge
        pre_edge(out, group=out)
        # clean up plots
        self.rawSpectra.clearAll()
        self.resultSpectra.clearAll()
        if plotChoice == 0: # plot raw spectrum
            self.updateRawSpec()
        elif plotChoice == 1:# plot raw, edges, norm
            self.rawSpectra.plotEdge(out, plotType='edge')
            self.resultSpectra.plotEdge(out, plotType='norm')
        elif plotChoice == 2:# plot raw, edges, flattened
            self.rawSpectra.plotEdge(out, plotType='edge')
            self.resultSpectra.plotEdge(out, plotType='flat')

    def updateRawSpec(self):
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        if (not self.isMapOpen()) or (specidx is None):
            return
        # make plots
        plotChoice = self.normBox.currentIndex()
        if plotChoice == 0:
            self.rawSpectra._mu = None # disable getMu func
            self.rawSpectra.showSpectra(specidx)
        else:
            self.updateResultSpec(plotChoice)

    def loadData(self):
        # get current map idx
        if not self.isMapOpen():
            return
        # pass the selected map data to plotwidget
        self.rawSpectra.setHeader(self.headers[self.selectMapidx], 'spectra')
        currentMapItem = self.headermodel.item(self.selectMapidx)
        rc2ind = self.rc2indList[self.selectMapidx]
        # get current map name
        mapName = currentMapItem.data(0)
        # get current selected pixels
        pixelCoord = currentMapItem.selectedPixels
        # get selected specIds
        spectraIds = []
        if currentMapItem.selectedPixels is None:  # select all
            spectraIds = list(range(len(rc2ind)))
        else:
            for i in range(len(pixelCoord)):
                row_col = tuple(pixelCoord[i])
                spectraIds.append(rc2ind[row_col])
            spectraIds = sorted(spectraIds)
        # add specitem model
        self.specItemModel.clear()
        for idx in spectraIds:
            item = QStandardItem(mapName + '# ' + str(idx))
            item.idx = idx
            self.specItemModel.appendRow(item)

    def removeSpec(self):
        # get current selectedSpecRow
        if self.specSelectModel.selectedIndexes():
            selectedSpecRow = self.specSelectModel.selectedIndexes()[0].row()
            self.specItemModel.removeRow(selectedSpecRow)
            # clean up plots
            self.rawSpectra.clearAll()
            self.resultSpectra.clearAll()

            print(self.specItemModel.rowCount())


    