from qtpy.QtWidgets import QSplitter, QGridLayout, QWidget, QListView
from qtpy.QtCore import Qt, QItemSelectionModel
from qtpy.QtGui import QStandardItemModel
from pyqtgraph import PlotWidget, PlotDataItem, TextItem, mkPen, InfiniteLine, ImageItem, PolyLineROI
from pyqtgraph.parametertree import ParameterTree, Parameter
from xicam.BSISB.widgets.spectraplotwidget import SpectraPlotWidget

class NormalizationParameters(ParameterTree):

    def __init__(self):
        super(NormalizationParameters, self).__init__()

        self.parameter = Parameter(name='params', type='group',
                                   children=[{'name': "Load spectra",
                                              'type': 'action'},
                                             {'name': "Plot type",
                                              'values': ['Normalized', 'Flattened', \
                                                         'mback', 'mback + poly normalized', \
                                                         '1st derivative', 'Normalized + derivative'],
                                              'value': 'Normalized',
                                              'type': 'list'},
                                             {'name': "Normalization method",
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
    def __init__(self):
        super(NormalizationWidget, self).__init__()

        # split between spectrum parameters and viewwindow
        self.paramsplitter = QSplitter()
        self.paramsplitter.setOrientation(Qt.Vertical)
        # spectrum list view
        self.speclistview = QListView()
        # spectrum plot
        self.rawSpectra = SpectraPlotWidget()
        self.normSpectra = SpectraPlotWidget()
        # ParameterTree
        self.parametertree = NormalizationParameters()

        #assemble widgets
        self.paramsplitter.addWidget(self.parametertree)
        self.paramsplitter.addWidget(self.rawSpectra)
        self.paramsplitter.addWidget(self.normSpectra)
        self.paramsplitter.setSizes([1000, 450, 450])
        self.addWidget(self.paramsplitter)
        self.addWidget(self.speclistview)
        self.setSizes([1000, 200])


