from xicam.plugins.DataHandlerPlugin import DataHandlerPlugin, start_doc, descriptor_doc, embedded_local_event_doc
import functools
from lbl_ir.io_tools.read_map import read_all_formats
import uuid


class MapFilePlugin(DataHandlerPlugin):
    name = 'BSISB Map File'

    DEFAULT_EXTENTIONS = ['.map']

    descriptor_keys = ['object_keys']

    def __call__(self, *args, E=None, i=None):
        if not E and not i:
            ...
            # return volume

        elif not E and i:
            ...
            # return spectra

        elif E and not i:
            return self.h5['data/image/imagecube'][:,:,E]
            # return image

        else:
            raise ValueError(f'Handler could not extract data given kwargs: { dict(E=E, i=i) }')

        # data, fmt = read_all_formats(self.path)
        # return data.imageCube

    def __init__(self, path):
        super(MapFilePlugin, self).__init__()
        self.path = path
        self.h5 = h5py.File(self.path, 'r')

    def parseDataFile(self, *args, **kwargs):
        return dict()

    # TODO: spectra <-> image slice mapping in both events and descriptors

    @classmethod
    def getVolumeDescriptor(cls, path, start_uid):
        uid = uuid.uuid4()
        yield descriptor_doc(start_uid, uid, {})

    @classmethod
    def getVolumeEvents(cls, path, descriptor_uid):
        yield embedded_local_event_doc(descriptor_uid, 'volume', cls, (path,))

    @classmethod
    def getImageDescriptor(cls, path, start_uid):
        uid = uuid.uuid4()
        yield descriptor_doc(start_uid, uid, {})

    @classmethod
    def getImageEvents(cls, path, descriptor_uid):
        # get a h5 object
        # find the imagecube
        # get imagecube shape
        # iterate over E dimension
        with h5py.File(path, 'r') as f:
            n = f['data/image/imagecube'].shape[2]
        for i in range(n):
            yield embedded_local_event_doc(descriptor_uid, 'image', cls, (path,), {'E': i}, {'spectra_index': 0})

    @classmethod
    def getSpectraDescriptor(cls, path, start_uid):
        uid = uuid.uuid4()
        yield descriptor_doc(start_uid, uid, {})

    @classmethod
    def getSpectraEvents(cls, path, descriptor_uid):
        for i in range(...):
            yield embedded_local_event_doc(descriptor_uid, 'spectra', cls, (path,), {'i': i}, {'image_index': (0, 0)})

    @classmethod
    def ingest(cls, paths):
        paths = cls.reduce_paths(paths)

        # TODO: handle multiple paths
        path = paths[0]

        start_uid = str(uuid.uuid4())

        volume_descriptor = cls.getVolumeDescriptor(path, start_uid)
        image_descriptor = cls.getImageDescriptor(path, start_uid)
        spectra_descriptor = cls.getSpectraDescriptor(path, start_uid)

        return {'start': cls._setTitle(cls.getStartDoc(paths, start_uid), paths),
                'descriptors': [volume_descriptor, image_descriptor, spectra_descriptor],
                'events': list(cls.getVolumeEvents(path, volume_descriptor['uid'])) +
                          list(cls.getImageEvents(path, image_descriptor['uid'])) +
                          list(cls.getSpectraEvents(path, spectra_descriptor['uid'])),
                'stop': cls.getStopDoc(paths, start_uid)}
