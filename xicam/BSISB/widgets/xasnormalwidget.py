import numpy as np
from functools import partial
from qtpy.QtWidgets import *
from qtpy.QtCore import Qt, QItemSelectionModel, Signal
from qtpy.QtGui import QStandardItemModel, QStandardItem, QFont
from pyqtgraph.parametertree import ParameterTree, Parameter
from xicam.core import msg
from xicam.BSISB.widgets.xasimagewidget import xasSpectraWidget
from larch import Group as lchGroup
from larch.xafs import pre_edge


class NormalizationParameters(ParameterTree):
    sigParamChanged = Signal(object)

    def __init__(self):
        super(NormalizationParameters, self).__init__()

        self.parameter = Parameter(name='params', type='group',
                                   children=[{'name': "Normalization method",
                                              'values': ['polynomial', 'mback'],
                                              'value': 'polynomial',
                                              'type': 'list'},
                                             {'name': "E0",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Edge step",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Pre-edge low E(E0=0)",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Pre-edge high E(E0=0)",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Polynomial order",
                                              'values': list(range(6)),
                                              'value': 0,
                                              'type': 'list'},
                                             {'name': "Victoreen order",
                                              'values': list(range(10)),
                                              'value': 0,
                                              'type': 'list'},
                                             {'name': "Normalization low E(E0=0)",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Normalization high E(E0=0)",
                                              'value': 0,
                                              'type': 'float'},
                                             {'name': "Y offset",
                                              'value': 0,
                                              'type': 'float'},
                                             ])
        self.setParameters(self.parameter, showTop=False)
        self.setIndentation(0)
        # change Fonts
        self.fontSize = 12
        font = QFont("Helvetica [Cronyx]", self.fontSize)
        boldFont = QFont("Helvetica [Cronyx]", self.fontSize, QFont.Bold)
        self.header().setFont(font)
        for item in self.listAllItems():
            if hasattr(item, 'widget'):
                item.setFont(0, boldFont)
                item.widget.setFont(font)
                item.displayLabel.setFont(font)
                item.widget.setMaximumHeight(40)
        # init params dict
        self.argMap = {"E0": 'e0',
                       "Edge step": 'step',
                       "Pre-edge low E(E0=0)": 'pre1',
                       "Pre-edge high E(E0=0)": 'pre2',
                       "Normalization low E(E0=0)": 'norm1',
                       "Normalization high E(E0=0)": 'norm2',
                       "Polynomial order": 'nnorm',
                       "Victoreen order": 'nvict'
                       }
        # set self.preEdgeArgs default value to e0 = None, step = None, pre1 = None, pre2 = None,
        # norm1 = None, norm2 = None, nnorm = None, nvict = 0
        self.preEdgeArgs = {}
        for child in self.parameter.childs:
            if child.name() == "Victoreen order":
                self.preEdgeArgs['nvict'] = 0
            elif child.name() not in ["Normalization method", "Y offset"]:
                self.preEdgeArgs[self.argMap[child.name()]] = None

        # connect signals
        for name in self.argMap.keys():
            self.parameter.child(name).sigValueChanged.connect(partial(self.updateParam, name))

    def updateParam(self, name):
        # get latest parameter values
        if self.parameter.child(name).valueIsDefault() and (name != "Victoreen order"):
            # set pre_edge args(except 'nvict') to default value
            self.preEdgeArgs[self.argMap[name]] = None
        else:
            # either value is not default or param name = "Victoreen order"
            self.preEdgeArgs[self.argMap[name]] = self.parameter[name]
        self.sigParamChanged.emit(self.preEdgeArgs)


class NormalizationWidget(QSplitter):
    def __init__(self, headermodel, selectionmodel):
        super(NormalizationWidget, self).__init__()
        self.headermodel = headermodel
        self.mapselectmodel = selectionmodel
        self.selectMapidx = 0
        self.reportList = ['e0', 'edge_step', 'nnorm', 'norm1', 'norm2', 'nvict',
                           'pre1', 'pre2', 'pre_offset', 'pre_slope']

        # split between spectrum parameters and viewwindow, vertical split
        self.params_and_specview = QSplitter()
        self.params_and_specview.setOrientation(Qt.Vertical)
        # split between buttons and parameters
        self.buttons_and_params = QSplitter()
        self.buttons_and_params.setOrientation(Qt.Horizontal)
        # split between speclist and report
        self.speclist_and_report = QSplitter()
        self.speclist_and_report.setOrientation(Qt.Vertical)

        # buttons layout
        self.buttons = QWidget()
        self.buttonlayout = QGridLayout()
        self.buttons.setLayout(self.buttonlayout)
        # set up buttons
        self.fontSize = 12
        font = QFont("Helvetica [Cronyx]", self.fontSize)
        self.loadBtn = QPushButton()
        self.loadBtn.setText('Load spectra')
        self.loadBtn.setFont(font)
        self.removeBtn = QPushButton()
        self.removeBtn.setText('Remove spectrum')
        self.removeBtn.setFont(font)
        self.normBox = QComboBox()
        self.normBox.addItems(
            ['Plot type', 'Raw', 'Normalized', 'Flattened', '1st derivative', 'mback', 'mback + poly normalized',
             'Normalized + derivative'])
        self.normBox.setFont(font)
        self.batchBtn = QPushButton()
        self.batchBtn.setText('Batch Process')
        self.batchBtn.setFont(font)
        # add all buttons
        self.buttonlayout.addWidget(self.loadBtn)
        self.buttonlayout.addWidget(self.removeBtn)
        self.buttonlayout.addWidget(self.normBox)
        self.buttonlayout.addWidget(self.batchBtn)

        # define report
        self.reportWidget = QWidget()
        self.reportWidget.setLayout(QVBoxLayout())
        self.infoBox = QTextEdit()
        reportTitle = QLabel('Normalization results')
        reportTitle.setFont(font)
        self.reportWidget.layout().addWidget(reportTitle)
        self.reportWidget.layout().addWidget(self.infoBox)
        # spectrum list view
        self.specItemModel = QStandardItemModel()
        self.specSelectModel = QItemSelectionModel(self.specItemModel)
        self.speclistview = QListView()
        self.speclistview.setModel(self.specItemModel)
        self.speclistview.setSelectionModel(self.specSelectModel)
        # add title to list view
        self.specListWidget = QWidget()
        self.listLayout = QVBoxLayout()
        self.specListWidget.setLayout(self.listLayout)
        specListTitle = QLabel('Spectrum List')
        specListTitle.setFont(font)
        self.listLayout.addWidget(specListTitle)
        self.listLayout.addWidget(self.speclistview)

        # spectrum plot
        self.rawSpectra = xasSpectraWidget()
        self.resultSpectra = xasSpectraWidget()
        # ParameterTree
        self.parametertree = NormalizationParameters()
        self.preEdgeArgs = self.parametertree.preEdgeArgs
        self.argMap = self.parametertree.argMap

        # assemble widgets
        self.buttons_and_params.addWidget(self.parametertree)
        self.buttons_and_params.addWidget(self.buttons)
        self.buttons_and_params.setSizes([1000, 100])
        self.params_and_specview.addWidget(self.buttons_and_params)
        self.params_and_specview.addWidget(self.rawSpectra)
        self.params_and_specview.addWidget(self.resultSpectra)
        self.params_and_specview.setSizes([150, 50, 50])
        self.speclist_and_report.addWidget(self.specListWidget)
        self.speclist_and_report.addWidget(self.reportWidget)
        self.speclist_and_report.setSizes([250, 100])
        self.addWidget(self.params_and_specview)
        self.addWidget(self.speclist_and_report)
        self.setSizes([1000, 200])

        # Connect signals
        self.specSelectModel.selectionChanged.connect(self.updateRawSpec)
        self.loadBtn.clicked.connect(self.loadData)
        self.normBox.currentIndexChanged.connect(self.updateResultSpec)
        self.removeBtn.clicked.connect(self.removeSpec)
        self.parametertree.sigParamChanged.connect(self.updateResultSpec)

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
        if not self.mapselectmodel.selectedIndexes():  # no map is open
            return False
        else:
            self.selectMapidx = self.mapselectmodel.selectedIndexes()[0].row()
            return True

    def getCurrentSpecid(self):
        # get selected spectrum idx
        specidx = None  # default value
        if self.specSelectModel.selectedIndexes():
            selectedSpecRow = self.specSelectModel.selectedIndexes()[0].row()
            currentSpecItem = self.specItemModel.item(selectedSpecRow)
            specidx = currentSpecItem.idx
        return specidx

    def updateResultSpec(self):
        # get plot choice
        plotChoice = self.normBox.currentIndex()
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        if (not self.isMapOpen()) or (specidx is None) or (plotChoice == 0):
            return
        # create larch Group object
        out = None
        out = lchGroup()
        out.energy, out.mu = self.energyList[self.selectMapidx], self.dataSets[self.selectMapidx][specidx]
        # calculate pre/post edge
        pre_edge(out, group=out, **self.preEdgeArgs)
        # clean up plots
        self.rawSpectra.clearAll()
        self.resultSpectra.clearAll()
        if plotChoice == 1:  # plot raw spectrum
            self.updateRawSpec()
        elif plotChoice == 2:  # plot raw, edges, norm
            self.rawSpectra.plotEdge(out, plotType='edge')
            self.resultSpectra.plotEdge(out, plotType='norm')
        elif plotChoice == 3:  # plot raw, edges, flattened
            self.rawSpectra.plotEdge(out, plotType='edge')
            self.resultSpectra.plotEdge(out, plotType='flat')
        elif plotChoice == 4:  # plot raw, edges, 1st derivative
            out.dmude = np.where(np.abs(out.dmude) == np.inf, 0, out.dmude)  # fix infinity
            self.rawSpectra.plotEdge(out, plotType='edge')
            self.resultSpectra.plotEdge(out, plotType='derivative')
        # make results report
        if plotChoice != 1:
            result = ''
            for item in dir(out):
                if item in self.reportList:
                    result += item + ': ' + f'{getattr(out, item): .4f}' + '\n'
            for item in dir(out.pre_edge_details):
                if item in self.reportList:
                    result += item + ': ' + f'{getattr(out.pre_edge_details, item): .4f}' + '\n'
            self.infoBox.setText(result)

    def updateRawSpec(self):
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        if (not self.isMapOpen()) or (specidx is None):
            return
        # make plots
        plotChoice = self.normBox.currentIndex()
        if plotChoice == 0:
            return
        elif plotChoice == 1:
            self.rawSpectra._mu = None  # disable getMu func
            self.infoBox.setText('') # clear txt
            self.rawSpectra.showSpectra(specidx)
        else:
            self.updateResultSpec()

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
