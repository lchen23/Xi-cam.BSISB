import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA, NMF
from sklearn.preprocessing import StandardScaler
from qtpy.QtWidgets import QSplitter, QGridLayout, QWidget, QListView
from qtpy.QtCore import Qt, QItemSelectionModel, Signal
from qtpy.QtGui import QStandardItemModel
from functools import partial
from pyqtgraph import TextItem, mkPen, ImageItem, PolyLineROI
from pyqtgraph.parametertree import ParameterTree, Parameter
from xicam.core import msg
from xicam.BSISB.widgets.imshowwidget import SlimImageView
from xicam.BSISB.widgets.mapviewwidget import toHtml
from xicam.BSISB.widgets.uiwidget import MsgBox


class Spectra2DQuadView(QWidget):
    def __init__(self, invertY=False):
        super(Spectra2DQuadView, self).__init__()
        self.gridlayout = QGridLayout()
        self.setLayout(self.gridlayout)
        self.quadViewDict = {0: 'NWview', 1: 'NEview', 2: 'SWview', 3: 'SEview'}
        for i in self.quadViewDict:
            setattr(self, self.quadViewDict[i], SlimImageView(invertY=invertY))
            # add into gridlayout
            self.gridlayout.addWidget(getattr(self, self.quadViewDict[i]), i // 2, i % 2, 1, 1)
            # add title
            getattr(self, self.quadViewDict[i]).imageTitle = TextItem()
            getattr(self, self.quadViewDict[i]).view.addItem(getattr(self, self.quadViewDict[i]).imageTitle)

    def drawImage(self, img, i, title=None):
        # i is imageview/window number
        getattr(self, self.quadViewDict[i]).setImage(img=img)
        # set imageTitle
        imageTitle = getattr(self, self.quadViewDict[i]).imageTitle
        imageTitle.setPos(0, img.shape[0] + 5)
        if title is not None:
            imageTitle.setHtml(toHtml(title, size=8))
        else:
            imageTitle.setText('')



class Spectra2DParameters(ParameterTree):
    sigPCA = Signal(object)

    def __init__(self, headermodel: QStandardItemModel, selectionmodel: QItemSelectionModel):
        super(Spectra2DParameters, self).__init__()

        self.headermodel = headermodel
        self.selectionmodel = selectionmodel

        self.parameter = Parameter(name='params', type='group',
                                   children=[{'name': "Method",
                                              'values': ['PCA', 'NMF'],
                                              'value': 'NMF',
                                              'type': 'list'},
                                             {'name': "# of Components",
                                              'value': 4,
                                              'type': 'int'},
                                             {'name': "Calculate",
                                              'type': 'action'},
                                             {'name': "Map 1 Component",
                                              'values': [1, 2, 3, 4],
                                              'value': 1,
                                              'type': 'list'},
                                             {'name': "Map 2 Component",
                                              'values': [1, 2, 3, 4],
                                              'value': 2,
                                              'type': 'list'},
                                             {'name': "Map 3 Component",
                                              'values': [1, 2, 3, 4],
                                              'value': 3,
                                              'type': 'list'},
                                             {'name': "Map 4 Component",
                                              'values': [1, 2, 3, 4],
                                              'value': 4,
                                              'type': 'list'},
                                             {'name': "Save results",
                                              'type': 'action'}
                                             ])

        self.setParameters(self.parameter, showTop=False)
        self.setIndentation(0)
        # constants
        self.method = 'NMF'
        self.field = 'spectra'

        self.parameter.child('Calculate').sigActivated.connect(self.calculate)
        self.parameter.child('Save results').sigActivated.connect(self.saveResults)
        self.parameter.child('# of Components').sigValueChanged.connect(self.setNumComponents)
        self.parameter.child('Method').sigValueChanged.connect(self.setMethod)

    def setMethod(self):
        if self.parameter['Method'] == 'PCA':
            self.method = 'PCA'
        elif self.parameter['Method'] == 'NMF':
            self.method = 'NMF'

    def setHeader(self, wavenumbers, imgShapes, rc2indList, ind2rcList):
        # get all headers selected
        self.headers = [self.headermodel.item(i).header for i in range(self.headermodel.rowCount())]

        self.wavenumbers = wavenumbers
        self.N_w = len(self.wavenumbers)
        self.imgShapes = imgShapes
        self.rc2indList = rc2indList
        self.ind2rcList = ind2rcList
        self._dataSets = []

        for header in self.headers:
            data = None
            try:  # spectra datasets
                data = header.meta_array(self.field)
            except IndexError:
                msg.showMessage(f'Header object contained no frames with field {self.field}.')
            if data is not None:
                self._dataSets.append(data)

    def setNumComponents(self):
        N = self.parameter['# of Components']
        for i in range(4):
            param = self.parameter.child(f'Map {i + 1} Component')
            param.setLimits(list(range(1, N + 1)))

    def calculate(self):

        N = self.parameter['# of Components']

        if hasattr(self, '_dataSets'):
            self.wavenumbers_select = self.wavenumbers
            # get map ROI selected region
            self.selectedPixelsList = [self.headermodel.item(i).selectedPixels for i in
                                       range(self.headermodel.rowCount())]
            self.df_row_idx = []  # row index for dataframe data_fac

            msg.showMessage('Start computing', self.method + '. Image shape:', str(self.imgShapes))
            self.dataRowSplit = [0]  # remember the starting/end row positions of each dataset
            # PCA workflow
            self.N_w = len(self.wavenumbers_select)
            self._allData = np.empty((0, self.N_w))

            for i, data in enumerate(self._dataSets):  # i: map idx
                if self.selectedPixelsList[i] is None: # full map
                    n_spectra = len(data)
                    tmp = np.zeros((n_spectra, self.N_w))
                    for j in range(n_spectra):
                        tmp[j, :] = data[j]
                        self.df_row_idx.append((self.ind2rcList[i][j], j))
                else:
                    n_spectra = len(self.selectedPixelsList[i])
                    tmp = np.zeros((n_spectra, self.N_w))
                    for j in range(n_spectra):  # j: jth selected pixel
                        row_col = tuple(self.selectedPixelsList[i][j])
                        tmp[j, :] = data[self.rc2indList[i][row_col]]
                        self.df_row_idx.append((row_col, self.rc2indList[i][row_col]))

                self.dataRowSplit.append(self.dataRowSplit[-1] + n_spectra)
                self._allData = np.append(self._allData, tmp, axis=0)

            if len(self._allData) > 0:
                if self.method == 'PCA':
                    self.data_fac_name = 'data_PCA' # define pop up plots labels
                    # mean center
                    data_centered = StandardScaler(with_std=False).fit_transform(self._allData)
                    # Do PCA
                    self.PCA = PCA(n_components=N)
                    self.PCA.fit(data_centered)
                    self.data_PCA = self.PCA.transform(data_centered)
                    # pop up plots
                    self.popup_plots()
                elif self.method == 'NMF':
                    self.data_fac_name = 'data_NMF'  # define pop up plots labels
                    # Do NMF
                    self.NMF = NMF(n_components=N)
                    self.NMF.fit(self._allData)
                    self.data_NMF = self.NMF.transform(self._allData)
                    # pop up plots
                    self.popup_plots()
            else:
                msg.showMessage('The data matrix is empty. No PCA is performed.')
                MsgBox('The data matrix is empty. No PCA is performed.', 'error')
                self.PCA, self.data_PCA = None, None
                self.NMF, self.data_NMF = None, None
            # emit PCA and transformed data
            if self.method == 'PCA':
                self.sigPCA.emit((self.wavenumbers_select, self.PCA, self.data_PCA, self.dataRowSplit))
            elif self.method == 'NMF':
                self.sigPCA.emit((self.wavenumbers_select, self.NMF, self.data_NMF, self.dataRowSplit))
            msg.showMessage('Finished computing', self.method + '.')

    def popup_plots(self):
        labels = []
        # loadings plot
        for i in range(getattr(self, self.method).components_.shape[0]):
            labels.append(self.method + str(i + 1))
            # component variance ratio plot
            if self.method == 'PCA':
                plt.plot(getattr(self, self.method).explained_variance_ratio_, 'o-b')
                ax = plt.gca()
                ax.set_ylabel('Explained variance ratio', fontsize=16)
                ax.set_xlabel('Component number',  fontsize=16)
                ax.set_xticks(np.arange(self.parameter['# of Components']))
        # pair plot
        groupLabel = np.zeros((self.dataRowSplit[-1], 1))
        for i in range(len(self.dataRowSplit) - 1):
            groupLabel[self.dataRowSplit[i]:self.dataRowSplit[i + 1]] = int(i)

        df_scores = pd.DataFrame(np.append(getattr(self, self.data_fac_name), groupLabel, axis=1),
                                 columns=labels + ['Group label'])
        grid = sns.pairplot(df_scores, vars=labels, hue="Group label")
        # change legend properties
        legend_labels = []
        for i in range(self.headermodel.rowCount()):
            if (self.selectedPixelsList[i] is None) or (self.selectedPixelsList[i].size > 0):
                legend_labels.append(self.headermodel.item(i).data(0))
        for t, l in zip(grid._legend.texts, legend_labels): t.set_text(l)
        plt.setp(grid._legend.get_texts(), fontsize=14)
        plt.setp(grid._legend.get_title(), fontsize=14)
        plt.setp(grid._legend, bbox_to_anchor=(0.2, 0.95), frame_on=True, draggable=True)
        plt.setp(grid._legend.get_frame(), edgecolor='k', linewidth=1, alpha=1)
        plt.show()

    def saveResults(self):
        if (hasattr(self, 'PCA') and self.PCA is not None) or (hasattr(self, 'NMF') and self.NMF is not None):
            name = self.method
            df_fac_components = pd.DataFrame(getattr(self, name).components_, columns=self.wavenumbers_select)
            df_data_fac = pd.DataFrame(getattr(self, self.data_fac_name), index=self.df_row_idx)
            df_fac_components.to_csv(name + '_components.csv')
            df_data_fac.to_csv(name + '_data.csv')
            np.savetxt(name + '_mapRowSplit.csv', np.array(self.dataRowSplit), fmt='%d', delimiter=',')
            MsgBox(name + ' components successfully saved!')
        else:
            MsgBox('No factorization components available.')


class Spectra2DQuadViewROI(Spectra2DQuadView):
    def __init__(self, headermodel, selectionmodel, invertY=False, sideLen=20):
        super(Spectra2DQuadViewROI, self).__init__(invertY=invertY)
        self.headermodel = headermodel
        self.selectionmodel = selectionmodel
        # constant
        self.selectMapIdx = 0
        self.sideLen = sideLen
        self._data_fac = None
        self.imgShapes = []
        self.roiList = []
        self.maskList = []
        self.selectMaskList = []
        # set up quadview window
        for i in self.quadViewDict:
            # set up roi item
            roi = PolyLineROI(positions=[[0, 0], [self.sideLen, 0], [self.sideLen, self.sideLen], [0, self.sideLen]], closed=True)
            roi.hide()
            self.roiInitState = roi.getState()
            self.roiList.append(roi)
            # set up auto mask item
            maskItem = ImageItem(np.ones((1, 1)), axisOrder="row-major", autoLevels=True, opacity=0.3)
            maskItem.hide()
            self.maskList.append(maskItem)
            # set up select mask item
            selectMaskItem = ImageItem(np.ones((1, 1)), axisOrder="row-major", autoLevels=True, opacity=0.3,
                                       lut=np.array([[0, 0, 0], [255, 0, 0]]))
            selectMaskItem.hide()
            self.selectMaskList.append(selectMaskItem)
            getattr(self, self.quadViewDict[i]).view.addItem(roi)
            getattr(self, self.quadViewDict[i]).view.addItem(maskItem)
            getattr(self, self.quadViewDict[i]).view.addItem(selectMaskItem)

    def updateRoiMask(self):
        if self.selectionmodel.hasSelection():
            self.selectMapIdx = self.selectionmodel.selectedIndexes()[0].row()
        elif self.headermodel.rowCount() > 0:
            self.selectMapIdx = 0
        else:
            return
        # update roi
        try:
            roiState = self.headermodel.item(self.selectMapIdx).roiState
            for i in range(4):
                if roiState[0]:  # roi on
                    self.roiList[i].show()
                else:
                    self.roiList[i].hide()
                # update roi state
                self.roiList[i].blockSignals(True)
                self.roiList[i].setState(roiState[1])
                self.roiList[i].blockSignals(False)
        except Exception:
            for i in range(4):
                self.roiList[i].hide()
        # update automask
        try:
            maskState = self.headermodel.item(self.selectMapIdx).maskState
            for i in range(4):
                self.maskList[i].setImage(maskState[1])
                if maskState[0]:  # automask on
                    self.maskList[i].show()
                else:
                    self.maskList[i].hide()
        except Exception:
            pass
        # update selectMask
        try:
            selectMaskState = self.headermodel.item(self.selectMapIdx).selectState
            for i in range(4):
                self.selectMaskList[i].setImage(selectMaskState[1])
                if selectMaskState[0]:  # selectmask on
                    self.selectMaskList[i].show()
                else:
                    self.selectMaskList[i].hide()
        except Exception:
            pass


class Spectra2DFAWidget(QSplitter):
    def __init__(self, headermodel, selectionmodel):
        super(Spectra2DFAWidget, self).__init__()
        self.headermodel = headermodel
        self.selectionmodel = selectionmodel
        # map quadview, spectra quadview splitter
        self.display = QSplitter()
        self.display.setOrientation(Qt.Vertical)
        # parameters widget, list view splitter
        self.rightsplitter = QSplitter()
        self.rightsplitter.setOrientation(Qt.Vertical)
        # parameters widget
        self.parametertree = Spectra2DParameters(headermodel, selectionmodel)
        self.parameter = self.parametertree.parameter
        # map quadview
        self.mapView = Spectra2DQuadViewROI(headermodel, selectionmodel)
        # spectra quadview
        self.componentSpectra = Spectra2DQuadView()
        # Headers listview
        self.headerlistview = QListView()
        self.headerlistview.setModel(headermodel)
        self.headerlistview.setSelectionModel(selectionmodel)
        self.headerlistview.setSelectionMode(QListView.SingleSelection)
        # assemble widget
        self.display.addWidget(self.mapView)
        self.display.addWidget(self.componentSpectra)
        self.rightsplitter.addWidget(self.parametertree)
        self.rightsplitter.addWidget(self.headerlistview)
        self.addWidget(self.display)
        self.addWidget(self.rightsplitter)
        self.setOrientation(Qt.Horizontal)
        # connect signals
        self.selectionmodel.selectionChanged.connect(self.updateMap)
        self.selectionmodel.selectionChanged.connect(self.mapView.updateRoiMask)
        self.parametertree.sigPCA.connect(self.showComponents)
        for i in range(4):
            self.parameter.child(f'Map {i + 1} Component').sigValueChanged.connect(partial(self.updateComponents, i))

    def showComponents(self, fac_obj):
        # get map ROI selected region
        self.selectedPixelsList = [self.headermodel.item(i).selectedPixels for i in range(self.headermodel.rowCount())]

        self.wavenumbers, self._fac, self._data_fac, self._dataRowSplit = fac_obj[0], fac_obj[1], fac_obj[2], fac_obj[3]

        if self._fac is not None:
            for i in range(4):
                # draw component loadings 2D image
                component_index = self.parameter[f'Map {i + 1} Component']
                title = self.parameter['Method'] + '_Component#' + str(component_index)
                # show loading plots
                spec = self._fac.components_[component_index - 1, :].reshape(self.specShape[0], self.specShape[1])
                self.componentSpectra.drawImage(spec, i, title)
                # show score plots
                self.drawMap(component_index, i)
            # update the last image and loading plots as a recalculation complete signal
            N = self.parameter['# of Components']
            self.parameter.child(f'Map 4 Component').setValue(N)
        # clear maps
        else:
            tab_idx = self.headermodel.rowCount() - 1
            if tab_idx >= 0:
                for i in range(4):
                    img = np.zeros((self.imgShapes[tab_idx][0], self.imgShapes[tab_idx][1]))
                    spec = np.zeros((self.specShape[0], self.specShape[1]))
                    self.mapView.drawImage(img, i)
                    self.componentSpectra.drawImage(spec, i)

    def updateMap(self):
        if self.selectionmodel.hasSelection():
            self.selectMapIdx = self.selectionmodel.selectedIndexes()[0].row()
        elif self.headermodel.rowCount() > 0:
            self.selectMapIdx = 0
        else:
            return

        if hasattr(self, '_data_fac') and (self._data_fac is not None):
            if len(self._dataRowSplit) < self.selectMapIdx + 2:  # some maps are not included in the factorization calculation
                msg.showMessage('One or more maps are not included in the factorization dataset. Please click "calculate" to re-compute factors.')
            else:
                for i in range(4):
                    component_index = self.parameter[f'Map {i + 1} Component']
                    # update map
                    self.drawMap(component_index, i)
        elif hasattr(self, 'imgShapes') and (self.selectMapIdx < len(self.imgShapes)):  # clear maps
            for i in range(4):
                img = np.zeros((self.imgShapes[self.selectMapIdx][0], self.imgShapes[self.selectMapIdx][1]))
                self.mapView.drawImage(img, i)

    def drawMap(self, component_index, i):
        # i is imageview/window number
        data_slice = self._data_fac[self._dataRowSplit[self.selectMapIdx]:self._dataRowSplit[self.selectMapIdx + 1],
                     component_index - 1]
        # draw map
        if self.selectedPixelsList[self.selectMapIdx] is None:  # full map
            img = data_slice.reshape(self.imgShapes[self.selectMapIdx][0], self.imgShapes[self.selectMapIdx][1])
        elif self.selectedPixelsList[self.selectMapIdx].size == 0:  # empty ROI
            img = np.zeros((self.imgShapes[self.selectMapIdx][0], self.imgShapes[self.selectMapIdx][1]))
        else:
            img = np.zeros((self.imgShapes[self.selectMapIdx][0], self.imgShapes[self.selectMapIdx][1]))
            img[self.selectedPixelsList[self.selectMapIdx][:, 0], self.selectedPixelsList[self.selectMapIdx][:, 1]] = data_slice
        img = np.flipud(img)
        title = self.parameter['Method'] + str(component_index)
        # draw map
        self.mapView.drawImage(img, i, title)

    def updateComponents(self, i):
        # i is imageview/window number
        # component_index is the PCA component index
        component_index = self.parameter[f'Map {i + 1} Component']
        # update scoreplots on view i
        if hasattr(self, '_data_fac') and (self._data_fac is not None):
            # update map
            self.drawMap(component_index, i)
        # update components
            title = self.parameter['Method'] + '_Component#' + str(component_index)
            # show loading plots
            spec = self._fac.components_[component_index - 1, :].reshape(self.specShape[0], self.specShape[1])
            self.componentSpectra.drawImage(spec, i, title)

    def setHeader(self, field: str):

        self.headers = [self.headermodel.item(i).header for i in range(self.headermodel.rowCount())]
        self.field = field
        wavenum_align = []
        self.imgShapes = []
        self.rc2indList = []
        self.ind2rcList = []

        # get wavenumbers, imgShapes
        for header in self.headers:
            dataEvent = next(header.events(fields=[field]))
            self.wavenumbers = dataEvent['wavenumbers']
            wavenum_align.append(
                (round(self.wavenumbers[0]), len(self.wavenumbers)))  # append (first wavenum value, wavenum length)
            self.imgShapes.append(dataEvent['imgShape'])
            self.specShape = dataEvent['specShape']
            self.rc2indList.append(dataEvent['rc_index'])
            self.ind2rcList.append(dataEvent['index_rc'])

        # init maps
        if len(self.imgShapes) > 0:
            self.showComponents((self.wavenumbers, None, None, None))

        if wavenum_align and (wavenum_align.count(wavenum_align[0]) != len(wavenum_align)):
            MsgBox('Length of wavenumber arrays of displayed maps are not equal. \n'
                   'Perform PCA or NMF on these maps will lead to error.','warn')

        self.parametertree.setHeader(self.wavenumbers, self.imgShapes, self.rc2indList, self.ind2rcList)


