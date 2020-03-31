import os
import numpy as np
import pandas as pd
from functools import partial
from qtpy.QtWidgets import *
from qtpy.QtCore import Qt, QItemSelectionModel, Signal
from qtpy.QtGui import QStandardItemModel, QStandardItem, QFont
from pyqtgraph.parametertree import ParameterTree, Parameter
from xicam.core import msg
from lbl_ir.data_objects.ir_map import ir_map
from xicam.BSISB.widgets.xasimagewidget import xasSpectraWidget
from xicam.BSISB.widgets.uiwidget import MsgBox, YesNoDialog
from larch import Group as lchGroup
from larch.xafs import pre_edge, mback_norm


class NormalizationParameters(ParameterTree):
    sigParamChanged = Signal(object)

    def __init__(self):
        super(NormalizationParameters, self).__init__()

        self.parameter = Parameter(name='params', type='group',
                                   children=[{'name': "Normalization method",
                                              'values': ['polynomial', 'mback'],
                                              'value': 'polynomial',
                                              'type': 'list'},
                                             {'name': "Z number",
                                              'value': 0,
                                              'type': 'int'},
                                             {'name': "Edge",
                                              'value': 'K',
                                              'values': ['K', 'L2', 'L3'],
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
                                              'type': 'float'}
                                             ])
        self.setParameters(self.parameter, showTop=False)
        self.setIndentation(0)
        self.parameter.child('Z number').hide()
        self.parameter.child('Edge').hide()
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
                       "Z number": 'z',
                       "Edge": 'edge',
                       "Edge step": 'step',
                       "Pre-edge low E(E0=0)": 'pre1',
                       "Pre-edge high E(E0=0)": 'pre2',
                       "Normalization low E(E0=0)": 'norm1',
                       "Normalization high E(E0=0)": 'norm2',
                       "Polynomial order": 'nnorm',
                       "Victoreen order": 'nvict'
                       }
        # set self.normArgs default value to e0 = None, step = None, pre1 = None, pre2 = None,
        # norm1 = None, norm2 = None, nnorm = None, nvict = 0
        self.normArgs = {}
        for child in self.parameter.childs:
            if child.name() == "Victoreen order":
                self.normArgs['nvict'] = 0
            elif child.name() == "Edge":
                self.normArgs['edge'] = 'K'
            elif child.name() not in ["Normalization method"]:
                self.normArgs[self.argMap[child.name()]] = None

        # connect signals
        self.parameter.child('Normalization method').sigValueChanged.connect(self.updateMethod)
        for name in self.argMap.keys():
            self.parameter.child(name).sigValueChanged.connect(partial(self.updateParam, name))

    def updateMethod(self):
        """
        Toggle parameter menu based on fit method
        :return:
        """
        if self.parameter["Normalization method"] == 'mback':
            self.parameter.child('Z number').show()
            self.parameter.child('Edge').show()
            self.parameter.child('Edge step').hide()
        else:
            self.parameter.child('Z number').hide()
            self.parameter.child('Edge').hide()
            self.parameter.child('Edge step').show()

    def updateParam(self, name):
        """
        get latest parameter values
        :param name: parameter name
        :return: None
        """
        if self.parameter.child(name).valueIsDefault() and (name not in ["Victoreen order", "Edge"]):
            # set pre_edge args(except 'nvict') to default value
            self.normArgs[self.argMap[name]] = None
        else:
            # either value is not default or param name in ["Victoreen order","Edge"]
            self.normArgs[self.argMap[name]] = self.parameter[name]
        self.sigParamChanged.emit(self.normArgs)


class NormalizationWidget(QSplitter):
    def __init__(self, headermodel, selectionmodel):
        super(NormalizationWidget, self).__init__()
        self.headermodel = headermodel
        self.mapselectmodel = selectionmodel
        self.selectMapidx = 0
        self.resultDict = {}
        self.isBatchProcessOn = False
        self.reportList = ['atsym', 'edge', 'e0', 'edge_step_poly', 'edge_step_mback', 'nnorm', 'norm1',
                           'norm2', 'nvict', 'pre1', 'pre2', 'pre_offset', 'pre_slope']
        self.arrayList = ['norm_poly', 'norm_mback', 'flat']

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
                               'Normalized',
                               'Flattened',
                               'Mback + poly normalized',
                               'Raw + 1st derivative',
                               'Normalized + 1st derivative',
                               ])
        self.normBox.setFont(font)
        self.batchBtn = QPushButton()
        self.batchBtn.setText('Batch Process')
        self.batchBtn.setFont(font)
        self.saveResultBox = QComboBox()
        self.saveResultBox.addItems(['Save poly normalized',
                                     'Save mback normalized',
                                     'Save flattened',
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
        self.normArgs = self.parametertree.normArgs
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
        self.specSelectModel.selectionChanged.connect(self.updateSpecPlot)
        self.normBox.currentIndexChanged.connect(self.updateSpecPlot)
        self.parametertree.sigParamChanged.connect(self.updateSpecPlot)

    def setHeader(self, field: str):
        self.headers = [self.headermodel.item(i).header for i in range(self.headermodel.rowCount())]
        self.field = field
        self.energyList = []
        self.rc2indList = []
        self.ind2rcList = []
        self.pathList = []
        self.dataSets = []

        # get wavenumbers, rc2ind
        for header in self.headers:
            dataEvent = next(header.events(fields=[field]))
            self.energyList.append(dataEvent['wavenumbers'])
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

    def getCurrentSpecid(self):
        # get selected spectrum idx
        specidx = None  # default value
        if self.specSelectModel.selectedIndexes():
            selectedSpecRow = self.specSelectModel.selectedIndexes()[0].row()
            currentSpecItem = self.specItemModel.item(selectedSpecRow)
            specidx = currentSpecItem.idx
        return specidx

    def updateSpecPlot(self):
        # get current map idx and selected spectrum idx
        specidx = self.getCurrentSpecid()
        if not self.isMapOpen():
            return
        elif self.specItemModel.rowCount() == 0:
            MsgBox('No spectrum is loaded.\nPlease click "Load spectra" to import data.')
            return
        elif (specidx is None) and (not self.isBatchProcessOn):
            MsgBox('No spectrum is selected.\nPlease select a spectrum in the "Spectrum List" to show.')
            return

        # get plot choice
        plotChoice = self.normBox.currentIndex()
        # kwargs for pre_edge func
        preEdgeArgs = self.normArgs.copy()
        preEdgeArgs.pop('z', None)
        preEdgeArgs.pop('edge', None)
        # create larch Group object
        # self.out = None
        self.out = lchGroup()
        self.out.energy, self.out.mu = self.energyList[self.selectMapidx], self.dataSets[self.selectMapidx][specidx]
        # calculate pre/post edge, polynomial fit
        pre_edge(self.out, group=self.out, **preEdgeArgs)
        self.out.dmude = np.where(np.abs(self.out.dmude) == np.inf, 0, self.out.dmude)  # fix infinity values
        self.out.dnormde = self.out.dmude / (self.out.edge_step if self.out.edge_step != 0 else 1)
        if plotChoice in [3]:  # mback fit
            # set parameter menu
            self.parametertree.parameter['Normalization method'] = 'mback'
            # get calculated pre2
            if self.normArgs['pre2'] is None:
                self.normArgs['pre2'] = self.out.pre_edge_details.pre2
            # get calculated norm1
            if self.normArgs['norm1'] is None:
                self.normArgs['norm1'] = self.out.pre_edge_details.norm1
            # kwargs for mback func
            mbackArgs = self.normArgs.copy()
            mbackArgs.pop('step', None)
            mback_norm(self.out, group=self.out, **mbackArgs)
        else:
            # set parameter menu
            self.parametertree.parameter['Normalization method'] = 'polynomial'

        # make results report
        if plotChoice != 0:
            self.getReport(self.out)

        # if not batch processing, show plots
        if not self.isBatchProcessOn:
            # clean up plots
            self.rawSpectra.clearAll()
            self.resultSpectra.clearAll()
            if plotChoice == 0:  # plot raw spectrum
                self.rawSpectra._mu = None  # disable getMu func
                self.infoBox.setText('')  # clear txt
                self.rawSpectra.showSpectra(specidx)
            elif plotChoice == 1:  # plot raw, edges, norm
                self.rawSpectra.plotEdge(self.out, plotType='edge')
                self.resultSpectra.plotEdge(self.out, plotType='norm')
            elif plotChoice == 2:  # plot raw, edges, flattened
                self.rawSpectra.plotEdge(self.out, plotType='edge')
                self.resultSpectra.plotEdge(self.out, plotType='flat')
            elif plotChoice == 3:  # plot raw, edges, Mback + poly normalized
                self.rawSpectra.plotEdge(self.out, plotType='edge')
                self.resultSpectra.plotEdge(self.out, plotType='norm+mback')
            elif plotChoice == 4:  # plot raw, edges, Raw + 1st derivative
                self.rawSpectra.plotEdge(self.out, plotType='edge')
                self.resultSpectra.plotEdge(self.out, plotType='raw+derivative')
            elif plotChoice == 5:  # plot raw, edges, normalized + 1st derivative
                self.rawSpectra.plotEdge(self.out, plotType='edge')
                self.resultSpectra.plotEdge(self.out, plotType='norm+derivative')

    def getReport(self, output):
        resultTxt = ''
        # get normalization results
        for item in dir(output):
            if item in self.reportList:
                if item in ['atsym', 'edge']:
                    resultTxt += item + ': ' + getattr(output, item) + '\n'
                else:
                    resultTxt += item + ': ' + f'{getattr(output, item): .4f}' + '\n'
            if (item in self.arrayList) or (item in self.reportList):
                self.resultDict[item] = getattr(output, item)
        # get pre_edge params
        for item in dir(output.pre_edge_details):
            if item in self.reportList:
                resultTxt += item + ': ' + f'{getattr(output.pre_edge_details, item): .4f}' + '\n'
                self.resultDict[item] = getattr(output.pre_edge_details, item)
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
            self.specItemModel.removeRow(selectedSpecRow)
            # clean up plots
            self.rawSpectra.clearAll()
            self.resultSpectra.clearAll()

    def batchProcess(self):
        # get current map idx
        if not self.isMapOpen():
            return
        elif self.specItemModel.rowCount() == 0:
            MsgBox('No spectrum is loaded.\nPlease click "Load spectra" to import data.')
            return
        # notice to user
        userMsg = YesNoDialog(f'Ready to batch process selected spectra.\nDo you want to continue?')
        userChoice = userMsg.choice()
        if userChoice == QMessageBox.No: # user choose to stop
            return

        self.isBatchProcessOn = True
        # set plot type to Mback + poly normalized
        self.normBox.setCurrentIndex(3)

        # init resultSetsDict, paramsDict
        self.resultSetsDict = {}
        self.paramsDict = {}
        self.paramsDict['specID'] = []
        self.paramsDict['row_column'] = []
        energy = self.energyList[self.selectMapidx]
        ind2rc = self.ind2rcList[self.selectMapidx]
        filePath = self.pathList[self.selectMapidx]
        n_energy = len(energy)
        # note that self.arrayList = ['norm_poly', 'norm_mback', 'flat']
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
                self.resultSetsDict[item] = np.append(self.resultSetsDict[item], self.resultDict[item].reshape(1, -1), axis=0)
            for item in self.reportList:
                self.paramsDict[item].append(self.resultDict[item])

        # result collection completed. convert paramsDict to df
        dfDict = {}
        dfDict['param'] = pd.DataFrame(self.paramsDict)
        for item in self.arrayList:
            # convert resultSetsDict to df and concatenate
            dfDict[item] = pd.DataFrame(self.resultSetsDict[item], columns=energy.tolist())
            dfDict[item] = pd.concat([dfDict['param'], dfDict[item]], axis=1)

        #  save df to files
        msg.showMessage(f'Batch processing is completed! Saving results to csv files.')
        saveDataChoice = self.saveResultBox.currentIndex()
        if saveDataChoice != 3: # save a single result
            saveDataType = self.arrayList[saveDataChoice]
            dirName, csvName, h5Name = self.saveToFiles(dfDict, filePath, saveDataType)
            if h5Name is None:
                MsgBox(f'Processed data was saved as csv file at: \n{dirName + csvName}')
            else:
                MsgBox(f'Processed data was saved as: \n\ncsv file at: {dirName + csvName} and \n\nHDF5 file at: {dirName + h5Name}')
        else: # save all results
            csvList = []
            h5List = []
            for saveDataType in self.arrayList:
                dirName, csvName, h5Name = self.saveToFiles(dfDict, filePath, saveDataType)
                csvList.append(csvName)
                h5List.append(h5Name)

            allcsvName = (' + ').join(csvList)
            if h5Name is None:
                MsgBox(f'Processed data was saved as csv file at: \n{dirName + allcsvName}')
            else:
                allh5Name = (' + ').join(h5List)
                MsgBox( f'Processed data was saved as: \n\ncsv file at: {dirName + allcsvName} and \n\nHDF5 file at: {dirName + allh5Name}')

        self.isBatchProcessOn = False # batch process completed

    def saveToFiles(self, dfDict, filePath, saveDataType):

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
            for i in self.paramsDict['specID']:
                fullMap.data[i, :] = self.resultSetsDict[saveDataType][i, :]
                row, col = ind2rc[i]
                fullMap.imageCube[row, col, :] = fullMap.data[i, :] = self.resultSetsDict[saveDataType][i, :]
            # save data as hdf5
            h5Name = oldFileName[:-3] + '_' + saveDataType + '.h5'
            fullMap.write_as_hdf5(dirName + h5Name)

        return dirName, csvName, h5Name