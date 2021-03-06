import os
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from functools import partial
from qtpy.QtWidgets import *
from qtpy.QtCore import Qt, QItemSelectionModel, Signal
from qtpy.QtGui import QStandardItemModel, QStandardItem, QFont
from pyqtgraph.parametertree import ParameterTree, Parameter
from xicam.core import msg
from lbl_ir.data_objects.ir_map import ir_map, val2ind
from lbl_ir.tasks.preprocessing.EMSC import Kohler_zero
from xicam.BSISB.widgets.spectraplotwidget import baselinePlotWidget
from xicam.BSISB.widgets.uiwidget import MsgBox, YesNoDialog


class Preprocessor:
    def __init__(self, wavenumbers, spectrum):
        self.wavenumbers = wavenumbers
        self.spectrum = spectrum
        self.preprocess_method = None
        self.interp_method = None
        self.wav_anchor = None

    def parse_anchors(self, anchors):
        """
        parse anchor points str to real valued wavenumbers and confine energy range
        :return: None
        """
        anchor_idx = []
        for entry in anchors.split(','):
            try:
                anchor_idx.append(val2ind(int(entry.strip()), self.wavenumbers))
            except:
                continue
        anchor_idx = sorted(anchor_idx)

        self.energy = self.wavenumbers[anchor_idx[0]: anchor_idx[-1] + 1]
        self.specTrim = self.spectrum[anchor_idx[0]: anchor_idx[-1] + 1]

        self.wav_anchor = self.wavenumbers[anchor_idx]
        self.spec_anchor = self.spectrum[anchor_idx]
        return None

    def isBaseFitOK(self, anchors, kind, w_regions):
        """
        Check is there is enough anchor points to fit higher order baseline
        :param anchors: anchor points
        :param kind: fitting method
        :return: decide if there is enough anchor points for baseline fit
        """
        # parse anchor points
        self.parse_anchors(anchors)
        if self.preprocess_method == 'rubberband':
            # decide if num of anchor points is enough for 'quadratic' or 'cubic' fit
            if len(self.wav_anchor) < 2:
                MsgBox('Baseline fitting needs at least 2 anchor points.\n' +
                       'Please add more "anchor points" to correctly fit the baseline.', type='error')
                return False
            elif len(self.wav_anchor) < 3 and kind == 'quadratic':
                MsgBox('Quadratic baseline needs more than 2 anchor points.\n' +
                       'Please add more "anchor points" to correctly fit the baseline.', type='error')
                return False
            elif len(self.wav_anchor) < 4 and kind == 'cubic':
                MsgBox('Cubic baseline needs more than 3 anchor points.\n' +
                       'Please add more "anchor points" to correctly fit the baseline.', type='error')
                return False
            else:
                return True
        elif self.preprocess_method == 'kohler':
            try:  # read w_regions
                self.w_regions = eval(w_regions)
            except :
                MsgBox('Fitting regions format is not correct.\n' +
                       'Please consult default values.', type='error')
            if self.w_regions is not None:
                return True
            else:
                return False


    def rubber_band(self, anchors, kind='linear', w_regions=None):
        """
        Calculate rubberBaseline, debased spectrum and 2nd, 4th order derivative of the spectrum
        :param anchors: rubberband anchor points
        :param kind: spline fit curve order
        :return: baseline fit success (bool)
        """
        self.preprocess_method = 'rubberband'
        self.interp_method = kind
        # get rubberBaseline and debased spectrum
        if not self.isBaseFitOK(anchors, kind, w_regions):
            return False

        f = interp1d(self.wav_anchor, self.spec_anchor, kind=kind)
        self.rubberBaseline = f(self.energy)
        self.rubberDebased = self.specTrim - self.rubberBaseline

        # get 2nd order derivatives
        self.get_derivative()
        return True

    def kohler(self, anchors=None, kind=None, w_regions=None):
        self.preprocess_method = 'kohler'
        # get kohler baseline and debased spectrum
        if not self.isBaseFitOK(anchors, kind, w_regions):
            return False

        self.kohlerDebased, self.kohlerBaseline = Kohler_zero(self.energy, self.specTrim, self.w_regions)
        # get 2nd order derivatives
        self.get_derivative()
        return True

    def get_derivative(self):
        """
        Calculate 2nd and 4th order derivative of the spectrum
        :param n: the derivative order
        :return: None
        """
        dx = self.energy[1] - self.energy[0]
        if self.preprocess_method == 'rubberband':
            self.deriv2_rubber = self.nthOrderGradient(dx, self.specTrim, n=2)
        elif self.preprocess_method == 'kohler':
            self.deriv2_kohler = self.nthOrderGradient(dx, self.kohlerDebased, n=2)
        return None

    def nthOrderGradient(self, dx, y, n=1):
        """
        Calculate nth order derivative of array y
        :param dx: spacing of x
        :param y: array
        :param n: order of derivative
        :return: nth order derivative
        """
        for i in range(n):
            z = np.gradient(y, dx)
            y = z
        y = np.where(np.abs(y) == np.inf, 0, y)  # fix infinity values
        return y


class PreprocessParameters(ParameterTree):
    sigParamChanged = Signal(object)

    def __init__(self):
        super(PreprocessParameters, self).__init__()

        self.parameter = Parameter(name='params', type='group',
                                   children=[{'name': "Preprocess method",
                                              'values': ['Kohler_EMSC','Rubberband'],
                                              'value': 'Kohler_EMSC',
                                              'type': 'list'},
                                             {'name': "Anchor points",
                                              'value': '400, 4000',
                                              'type': 'str'},
                                             {'name': "Fitting regions",
                                              'value': '[(650, 750),(1780, 2680),(3680, 4000)]',
                                              'type': 'str'},
                                             {'name': "Interp method",
                                              'value': 'linear',
                                              'values': ['linear', 'quadratic', 'cubic'],
                                              'type': 'list'}
                                             ])
        self.setParameters(self.parameter, showTop=False)
        self.setIndentation(0)
        self.parameter.child('Interp method').hide()
        self.parameter.child('Anchor points').hide()

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
        self.argMap = {"Anchor points": 'anchors',
                       "Interp method": 'kind',
                       "Fitting regions": 'w_regions'
                       }
        # set self.processArgs to default value
        self.processArgs = {}
        for child in self.parameter.childs:
            if child.name() == "Anchor points":
                self.processArgs['anchors'] = '400, 4000'
            elif child.name() == "Interp method":
                self.processArgs['kind'] = 'linear'
            elif child.name() == "Fitting regions":
                self.processArgs['w_regions'] = '[(650, 750), (1780, 2680), (3680, 4000)]'

        # connect signals
        self.parameter.child('Preprocess method').sigValueChanged.connect(self.updateMethod)
        for name in self.argMap.keys():
            self.parameter.child(name).sigValueChanged.connect(partial(self.updateParam, name))

    def updateParam(self, name):
        """
        get latest parameter values
        :param name: parameter name
        :return: None
        """
        self.processArgs[self.argMap[name]] = self.parameter[name]
        self.sigParamChanged.emit(self.processArgs)

    def updateMethod(self):
        """
        Toggle parameter menu based on fit method
        :return:
        """
        if self.parameter["Preprocess method"] == 'Kohler_EMSC':
            self.parameter.child('Fitting regions').show()
            self.parameter.child('Interp method').hide()
            self.parameter.child('Anchor points').hide()
        else:
            self.parameter.child('Fitting regions').hide()
            self.parameter.child('Interp method').show()
            self.parameter.child('Anchor points').show()


class PreprocessWidget(QSplitter):
    def __init__(self, headermodel, selectionmodel):
        super(PreprocessWidget, self).__init__()
        self.headermodel = headermodel
        self.mapselectmodel = selectionmodel
        self.selectMapidx = 0
        self.resultDict = {}
        self.isBatchProcessOn = False
        self.out = None
        self.dfDict = None
        self.reportList = ['preprocess_method', 'wav_anchor', 'interp_method', 'w_regions']
        self.arrayList = ['kohlerDebased', 'kohlerBaseline', 'rubberDebased', 'deriv2_kohler', 'deriv2_rubber']
        self.mousePosList = []

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
        self.normBox.addItems(['Raw spectrum',
                               'Kohler EMSC baseline',
                               'Rubberband baseline',
                               'Kohler EMSC + 2nd derivative',
                               'Rubberband + 2nd derivative',
                               ])
        self.normBox.setFont(font)
        self.batchBtn = QPushButton()
        self.batchBtn.setText('Batch process')
        self.batchBtn.setFont(font)
        self.saveResultBox = QComboBox()
        self.saveResultBox.addItems(['Save kohler',
                                     'Save kohler baseline',
                                     'Save rubberband',
                                     'Save kohler 2nd derivative',
                                     'Save rubberband 2nd derivative',
                                     'Save all',
                                     ])
        self.saveResultBox.setFont(font)
        # add all buttons
        self.buttonlayout.addWidget(self.loadBtn)
        self.buttonlayout.addWidget(self.removeBtn)
        self.buttonlayout.addWidget(self.normBox)
        self.buttonlayout.addWidget(self.batchBtn)
        self.buttonlayout.addWidget(self.saveResultBox)
        # define report
        self.reportWidget = QWidget()
        self.reportWidget.setLayout(QVBoxLayout())
        self.infoBox = QTextEdit()
        reportTitle = QLabel('Preprocess results')
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
        self.rawSpectra = baselinePlotWidget()
        self.resultSpectra = baselinePlotWidget()
        # ParameterTree
        self.parametertree = PreprocessParameters()
        self.parameter = self.parametertree.parameter
        self.processArgs = self.parametertree.processArgs
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
        self.speclist_and_report.setSizes([150, 100])
        self.addWidget(self.params_and_specview)
        self.addWidget(self.speclist_and_report)
        self.setSizes([1000, 200])

        # Connect signals
        self.loadBtn.clicked.connect(self.loadData)
        self.removeBtn.clicked.connect(self.removeSpec)
        self.batchBtn.clicked.connect(self.batchProcess)
        self.saveResultBox.currentIndexChanged.connect(self.saveResults)
        self.specSelectModel.selectionChanged.connect(self.updateSpecPlot)
        self.normBox.currentIndexChanged.connect(self.updateSpecPlot)
        self.parametertree.sigParamChanged.connect(self.updateSpecPlot)
        self.rawSpectra.scene().sigMouseClicked.connect(self.setAnchors)
        self.parameter.child('Preprocess method').sigValueChanged.connect(self.updateMethod)

    def setHeader(self, field: str):
        self.headers = [self.headermodel.item(i).header for i in range(self.headermodel.rowCount())]
        self.field = field
        self.wavenumberList = []
        self.rc2indList = []
        self.ind2rcList = []
        self.pathList = []
        self.dataSets = []

        # get wavenumbers, rc2ind
        for header in self.headers:
            dataEvent = next(header.events(fields=[field]))
            self.wavenumberList.append(dataEvent['wavenumbers'])
            self.rc2indList.append(dataEvent['rc_index'])
            self.ind2rcList.append(dataEvent['index_rc'])
            self.pathList.append(dataEvent['path'])
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

    def setAnchors(self, event):
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        plotChoice = self.normBox.currentIndex()
        if (not self.isMapOpen()) or (self.specItemModel.rowCount() == 0) or (specidx is None) or (plotChoice not in [2, 4]):
            return

        pos = event.pos()
        button = event.button()
        parser = Preprocessor(self.wavenumberList[self.selectMapidx], self.dataSets[self.selectMapidx][specidx])
        parser.parse_anchors(self.parameter['Anchor points'])
        anchor_low, anchor_high = parser.wav_anchor[0], parser.wav_anchor[-1]
        if self.rawSpectra.getViewBox().sceneBoundingRect().contains(pos):
            mousePoint = self.rawSpectra.getViewBox().mapToView(pos)
            x = mousePoint.x()
            if anchor_low < x < anchor_high:
                if button == Qt.LeftButton:# left click, add point to mousePosList
                    self.mousePosList.append(x)
                elif (button == Qt.MidButton) and self.mousePosList :# right click, remove last point from mousePosList
                    self.mousePosList.pop()
                # set anchors list
                anchors = [anchor_low] + sorted(self.mousePosList) + [anchor_high]
                txt = ', '.join([str(int(round(x))) for x in anchors])
                self.parameter.child('Anchor points').setValue(txt)

    def getCurrentSpecid(self):
        # get selected spectrum idx
        specidx = None  # default value
        if self.specSelectModel.selectedIndexes():
            selectedSpecRow = self.specSelectModel.selectedIndexes()[0].row()
            currentSpecItem = self.specItemModel.item(selectedSpecRow)
            specidx = currentSpecItem.idx
        return specidx

    def updateMethod(self):
        if self.parameter["Preprocess method"] == 'Kohler_EMSC':
            self.normBox.setCurrentIndex(1)
        else:
            self.normBox.setCurrentIndex(2)

    def updateSpecPlot(self):
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        if not self.isMapOpen():
            return
        elif self.specItemModel.rowCount() == 0:
            MsgBox('No spectrum is loaded.\nPlease click "Load spectra" to import data.')
            return
        elif specidx is None:
            return

        # get plotchoice
        plotChoice = self.normBox.currentIndex()

        # create Preprocessor object
        self.out = Preprocessor(self.wavenumberList[self.selectMapidx], self.dataSets[self.selectMapidx][specidx])
        baselineOK = self.out.rubber_band(**self.processArgs) and self.out.kohler(**self.processArgs)

        if not baselineOK:
            return

        # make results report
        if plotChoice != 0:
            self.getReport(self.out, plotChoice)

        # if not batch processing, show plots
        if not self.isBatchProcessOn:
            # clean up plots
            self.rawSpectra.clearAll()
            self.resultSpectra.clearAll()
            if plotChoice == 0:  # plot raw spectrum
                self.infoBox.setText('')  # clear txt
                self.rawSpectra.plotBase(self.out, plotType='raw')
            elif plotChoice == 1:  # plot raw, kohler
                self.rawSpectra.plotBase(self.out, plotType='kohler_base')
                self.resultSpectra.plotBase(self.out, plotType='kohler')
            elif plotChoice == 2:  # plot raw, rubberband
                self.rawSpectra.plotBase(self.out, plotType='rubber_base')
                self.resultSpectra.plotBase(self.out, plotType='rubberband')
            elif plotChoice == 3:  # plot raw, kohler 2nd derivative
                self.rawSpectra.plotBase(self.out, plotType='kohler_base')
                self.resultSpectra.plotBase(self.out, plotType='deriv2_kohler')
            elif plotChoice == 4:  # plot raw, rubberband 2nd derivative
                self.rawSpectra.plotBase(self.out, plotType='rubber_base')
                self.resultSpectra.plotBase(self.out, plotType='deriv2_rubberband')

            if plotChoice in [1, 3]:
                self.parameter.child('Preprocess method').setValue('Kohler_EMSC', blockSignal=self.updateMethod)
            elif plotChoice in [2, 4]:
                self.parameter.child('Preprocess method').setValue('Rubberband', blockSignal=self.updateMethod)

    def getReport(self, output, plotChoice):
        resultTxt = ''
        # get baseline results
        reportList = self.reportList.copy()
        if plotChoice in [2, 4]:
            reportList = self.reportList[:-1]
            output.preprocess_method = 'rubberband'
        elif plotChoice in [1, 3]:
            reportList = [self.reportList[0], self.reportList[-1]]
            output.preprocess_method = 'kohler'

        for item in dir(output):
            if item in reportList:
                if item == 'wav_anchor':
                    val = getattr(output, item)
                    printFormat = ('{:.2f}, ' * len(val))[:-1]
                    resultTxt += item + ': ' + printFormat.format(*val) + '\n'
                else:
                    resultTxt += item + ': ' + str(getattr(output, item)) + '\n'
            if (item in self.arrayList) or (item in self.reportList):
                self.resultDict[item] = getattr(output, item)

        # send text to report info box
        self.infoBox.setText(resultTxt)

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
            self.specSelectModel.blockSignals(True)
            self.specItemModel.removeRow(selectedSpecRow)
            self.specSelectModel.blockSignals(False)
            # clean up plots
            self.rawSpectra.clearAll()
            self.resultSpectra.clearAll()
            self.infoBox.setText('')

    def cleanUp(self):
        self.specItemModel.clear()
        self.rawSpectra.clearAll()
        self.resultSpectra.clearAll()
        self.infoBox.setText('')
        self.mousePosList = []
        self.normBox.setCurrentIndex(0)

    def batchProcess(self):
        # get current map idx
        if not self.isMapOpen():
            return
        elif self.specItemModel.rowCount() == 0:
            MsgBox('No spectrum is loaded.\nPlease click "Load spectra" to import data.')
            return
        # check if baseline fit OK
        if self.out is None:
            self.out = Preprocessor(self.wavenumberList[self.selectMapidx], self.dataSets[self.selectMapidx][0])

        # get plotchoice
        plotChoice = self.normBox.currentIndex()
        if plotChoice != 0:
            # calculate rubberband and kohler baseline
            baselineOK = self.out.rubber_band(**self.processArgs) and self.out.kohler(**self.processArgs)
        else:
            MsgBox('Plot type is "Raw spectrum".\nPlease change plot type to "Kohler" or "Rubberband".')
            return
        if not baselineOK:
            return

        # notice to user
        userMsg = YesNoDialog(f'Ready to batch process selected spectra.\nDo you want to continue?')
        userChoice = userMsg.choice()
        if userChoice == QMessageBox.No:  # user choose to stop
            return

        self.isBatchProcessOn = True

        # init resultSetsDict, paramsDict
        self.resultSetsDict = {}
        self.paramsDict = {}
        self.paramsDict['specID'] = []
        self.paramsDict['row_column'] = []
        ind2rc = self.ind2rcList[self.selectMapidx]
        energy = self.out.energy
        n_energy = len(energy)
        for item in self.arrayList:
            self.resultSetsDict[item] = np.empty((0, n_energy))
        for item in self.reportList:
            self.paramsDict[item] = []
        # batch process begins
        n_spectra = self.specItemModel.rowCount()
        for i in range(n_spectra):
            msg.showMessage(f'Processing {i + 1}/{n_spectra} spectra')
            # select each spec and collect results
            self.specSelectModel.select(self.specItemModel.index(i, 0), QItemSelectionModel.ClearAndSelect)
            # get spec idx
            currentSpecItem = self.specItemModel.item(i)
            self.paramsDict['specID'].append(currentSpecItem.idx)
            self.paramsDict['row_column'].append(ind2rc[currentSpecItem.idx])
            # append all results into a single array/list
            for item in self.arrayList:
                self.resultSetsDict[item] = np.append(self.resultSetsDict[item], self.resultDict[item].reshape(1, -1),
                                                      axis=0)
            for item in self.reportList:
                self.paramsDict[item].append(self.resultDict[item])

        # result collection completed. convert paramsDict to df
        self.dfDict = {}
        self.dfDict['param'] = pd.DataFrame(self.paramsDict).set_index('specID')
        for item in self.arrayList:
            # convert resultSetsDict to df
            self.dfDict[item] = pd.DataFrame(self.resultSetsDict[item], columns=energy.tolist(),
                                        index=self.paramsDict['specID']).rename_axis('specID', axis=0)

        # batch process completed
        self.isBatchProcessOn = False
        msg.showMessage(f'Batch processing is completed! Saving results to csv files.')
        #  save df to files
        self.saveResults()

    def saveResults(self):
        if self.dfDict is None:
            return
        filePath = self.pathList[self.selectMapidx]
        energy = self.out.energy
        saveDataChoice = self.saveResultBox.currentIndex()
        if saveDataChoice != 5:  # save a single result
            saveDataType = self.arrayList[saveDataChoice]
            dirName, csvName, h5Name = self.saveToFiles(energy, self.dfDict, filePath, saveDataType)
            if h5Name is None:
                MsgBox(f'Processed data was saved as csv file at: \n{dirName + csvName}')
            else:
                MsgBox(
                    f'Processed data was saved as: \n\ncsv file at: {dirName + csvName} and \n\nHDF5 file at: {dirName + h5Name}')
        else:  # save all results
            csvList = []
            h5List = []
            for saveDataType in self.arrayList:
                dirName, csvName, h5Name = self.saveToFiles(energy, self.dfDict, filePath, saveDataType)
                csvList.append(csvName)
                h5List.append(h5Name)

            allcsvName = (', ').join(csvList)
            if h5Name is None:
                MsgBox(f'Processed data was saved as csv files at: \n{dirName + allcsvName}')
            else:
                allh5Name = (', ').join(h5List)
                MsgBox(
                    f'Processed data was saved as: \n\ncsv files at: {dirName + allcsvName} and \n\nHDF5 files at: {dirName + allh5Name}')

        # save parameter
        xlsName = csvName[:-4] + '_param.xlsx'
        self.dfDict['param'].to_excel(dirName + xlsName)

    def saveToFiles(self, energy, dfDict, filePath, saveDataType):

        ind2rc = self.ind2rcList[self.selectMapidx]
        n_spectra = self.specItemModel.rowCount()

        # get dirname and old filename
        dirName = os.path.dirname(filePath)
        dirName += '/'
        oldFileName = os.path.basename(filePath)

        # save dataFrames to csv file
        csvName = oldFileName[:-3] + '_' + saveDataType + '.csv'
        dfDict[saveDataType].to_csv(dirName + csvName)

        # if a full map is processed, also save results to a h5 file
        h5Name = None
        if n_spectra == len(ind2rc):
            fullMap = ir_map(filename=filePath)
            fullMap.add_image_cube()
            fullMap.wavenumbers = energy
            fullMap.N_w = len(energy)
            fullMap.data = np.zeros((fullMap.data.shape[0], fullMap.N_w))
            fullMap.imageCube = np.zeros((fullMap.imageCube.shape[0], fullMap.imageCube.shape[1], fullMap.N_w))
            for i in self.paramsDict['specID']:
                fullMap.data[i, :] = self.resultSetsDict[saveDataType][i, :]
                row, col = ind2rc[i]
                fullMap.imageCube[row, col, :] = fullMap.data[i, :] = self.resultSetsDict[saveDataType][i, :]
            # save data as hdf5
            h5Name = oldFileName[:-3] + '_' + saveDataType + '.h5'
            fullMap.write_as_hdf5(dirName + h5Name)

        return dirName, csvName, h5Name
