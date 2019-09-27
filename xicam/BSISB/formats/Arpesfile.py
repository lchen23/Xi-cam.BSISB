from xicam.plugins.datahandlerplugin import DataHandlerPlugin, start_doc, descriptor_doc, embedded_local_event_doc
import uuid
import h5py
from functools import lru_cache
from lbl_ir.gui_tools.rc2ind_mapping import getRC2Ind
import numpy as np


class ArpesFilePlugin(DataHandlerPlugin):
    name = 'ARPES Map File'

    DEFAULT_EXTENTIONS = ['.xnpy']

    descriptor_keys = ['object_keys']

    def __call__(self, *args, E=None, i=None):
        if E is None and i is not None:
            # return ith linearized spectra
            # row, col = self.img_ind2rc[i][0], self.img_ind2rc[i][1]
            # return np.flipud(self.im4d[row, col, :, :]).reshape(-1)
            return self.spectra[i, :]
        elif E is not None and i is None:
            # return image at 2D energy spectrum index = E
            row, col = self.spec_ind2rc[E][0], self.spec_ind2rc[E][1]
            return np.flipud(self.im4d[:, :, row, col])

        else:
            raise ValueError(f'Handler could not extract data given kwargs: {dict(E=E, i=i)}')

        # data, fmt = read_all_formats(self.path)
        # return data.imageCube

    @lru_cache(maxsize=1)
    def __init__(self, path):
        super(ArpesFilePlugin, self).__init__()
        self.path = path
        self.im4d = np.load(self.path, mmap_mode='r')
        self.imgShape, self.specShape = self.im4d.shape[:2], self.im4d.shape[2:]
        self.spectra = self.im4d.reshape(self.imgShape[0] * self.imgShape[1], self.specShape[0] * self.specShape[1])
        # self.img_ind2rc, self.img_rc2ind = getRC2Ind(self.imgShape)
        # self.spec_ind2rc, self.spec_rc2ind = getRC2Ind(self.specShape)
        self._img_ind2rc = self._img_rc2ind = self._spec_ind2rc = self._spec_rc2ind = None

    @property
    def img_ind2rc(self):
        if not self._img_ind2rc:
            self._img_ind2rc, self._img_rc2ind = getRC2Ind(self.imgShape)
        return self._img_ind2rc

    @property
    def img_rc2ind(self):
        if not self._img_rc2ind:
            self._img_ind2rc, self._img_rc2ind = getRC2Ind(self.imgShape)
        return self._img_rc2ind

    @property
    def spec_ind2rc(self):
        if not self._spec_ind2rc:
            self._spec_ind2rc, self._spec_rc2ind = getRC2Ind(self.specShape)
        return self._spec_ind2rc

    @property
    def spec_rc2ind(self):
        if not self._spec_rc2ind:
            self._spec_ind2rc, self._spec_rc2ind = getRC2Ind(self.specShape)
        return self._spec_rc2ind

    def parseDataFile(self, *args, **kwargs):
        return dict()

    @classmethod
    def getImageDescriptor(cls, path, start_uid):
        uid = uuid.uuid4()
        return descriptor_doc(start_uid, uid, {})

    @classmethod
    def getImageEvents(cls, path, descriptor_uid):
        """
        Get 4D image and iterate over linear energy index E
        :param path: file path
        :param descriptor_uid: descriptor_uid
        :return: None
        """
        im4d = np.load(path, mmap_mode='r')
        imgShape, specShape = im4d.shape[:2], im4d.shape[2:]
        img_ind2rc, img_rc2ind = getRC2Ind(imgShape)
        # get number of energies
        n = specShape[0] * specShape[1]
        wavenumbers = np.arange(n)
        for i in range(n):
            yield embedded_local_event_doc(descriptor_uid, 'image', cls, (path,), resource_kwargs={'E': i},
                  metadata={'wavenumbers': wavenumbers, 'rc_index': img_rc2ind, 'index_rc': img_ind2rc,
                            'imgShape': imgShape})

    @classmethod
    def getSpectraDescriptor(cls, path, start_uid):
        uid = uuid.uuid4()
        return descriptor_doc(start_uid, uid, {})

    @classmethod
    def getSpectraEvents(cls, path, descriptor_uid):
        """
        Get 4D image and iterate over linear spectra index i
        :param path: file path
        :param descriptor_uid: descriptor_uid
        :return: None
        """
        im4d = np.load(path, mmap_mode='r')
        imgShape, specShape = im4d.shape[:2], im4d.shape[2:]
        img_ind2rc, img_rc2ind = getRC2Ind(imgShape)
        spec_ind2rc, spec_rc2ind = getRC2Ind(specShape)
        # get number of spectra
        n = imgShape[0] * imgShape[1]
        wavenumbers = np.arange(specShape[0] * specShape[1])

        for i in range(n):
            yield embedded_local_event_doc(descriptor_uid, 'spectra', cls, (path,), resource_kwargs={'i': i},
                  metadata={'wavenumbers': wavenumbers, 'rc_index': img_rc2ind, 'index_rc': img_ind2rc, 'imgShape': imgShape,
                            'spec_rc_index': spec_rc2ind, 'spec_index_rc': spec_ind2rc, 'specShape': specShape})

    @classmethod
    def ingest(cls, paths):
        paths = cls.reduce_paths(paths)

        # TODO: handle multiple paths
        path = paths[0]

        start_uid = str(uuid.uuid4())

        image_descriptor = cls.getImageDescriptor(path, start_uid)
        spectra_descriptor = cls.getSpectraDescriptor(path, start_uid)

        return {'start': cls._setTitle(cls.getStartDoc(paths, start_uid), paths),
                'descriptors': [image_descriptor, spectra_descriptor],
                'events': list(cls.getImageEvents(path, image_descriptor['uid'])) +
                          list(cls.getSpectraEvents(path, spectra_descriptor['uid'])),
                'stop': cls.getStopDoc(paths, start_uid)}
