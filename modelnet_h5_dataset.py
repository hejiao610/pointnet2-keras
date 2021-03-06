'''
    ModelNet dataset. Support ModelNet40, XYZ channels. Up to 2048 points.
    Faster IO than ModelNetDataset in the first epoch.
'''

import os
import sys
import numpy as np
import h5py

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
ROOT_DIR = BASE_DIR
from util.provider import shuffle_points, shift_point_cloud, rotate_perturbation_point_cloud, jitter_point_cloud, \
    rotate_point_cloud, random_scale_point_cloud

# Download dataset for point cloud classification
DATA_DIR = os.path.join(ROOT_DIR, 'data')
if not os.path.exists(DATA_DIR):
    os.mkdir(DATA_DIR)
if not os.path.exists(os.path.join(DATA_DIR, 'modelnet40_ply_hdf5_2048')):
    www = 'https://shapenet.cs.stanford.edu/media/modelnet40_ply_hdf5_2048.zip'
    zipfile = os.path.basename(www)
    os.system('wget %s; unzip %s' % (www, zipfile))
    os.system('mv %s %s' % (zipfile[:-4], DATA_DIR))
    os.system('rm %s' % (zipfile))


def shuffle_data(data, labels):
    """ Shuffle data and labels.
        Input:
          data: B,N,... numpy array
          label: B,... numpy array
        Return:
          shuffled data, label and shuffle indices
    """
    idx = np.arange(len(labels))
    np.random.shuffle(idx)
    return data[idx, ...], labels[idx], idx


def getDataFiles(list_filename):
    return [line.rstrip() for line in open(list_filename)]


def load_h5(h5_filename):
    f = h5py.File(h5_filename)
    data = f['data'][:]
    label = f['label'][:]
    return (data, label)


def loadDataFile(filename):
    return load_h5(filename)


class ModelNetH5Dataset(object):
    def __init__(self, list_filename, batch_size=32, npoints=1024, shuffle=True):
        self.list_filename = list_filename
        self.batch_size = batch_size
        self.npoints = npoints
        self.shuffle = shuffle
        self.h5_files = getDataFiles(self.list_filename)
        self.reset()
        self.total_batch_nb = self.calc_total_batch()

    def reset(self):
        ''' reset order of h5 files '''
        self.file_idxs = np.arange(0, len(self.h5_files))
        if self.shuffle: np.random.shuffle(self.file_idxs)
        self.current_data = None
        self.current_label = None
        self.current_file_idx = 0
        self.batch_idx = 0

    def _augment_batch_data(self, batch_data):
        rotated_data = rotate_point_cloud(batch_data)
        rotated_data = rotate_perturbation_point_cloud(rotated_data)
        jittered_data = random_scale_point_cloud(rotated_data[:, :, 0:3])
        jittered_data = shift_point_cloud(jittered_data)
        jittered_data = jitter_point_cloud(jittered_data)
        rotated_data[:, :, 0:3] = jittered_data
        return shuffle_points(rotated_data)

    def _get_data_filename(self):
        return self.h5_files[self.file_idxs[self.current_file_idx]]

    def _load_data_file(self, filename):
        self.current_data, self.current_label = load_h5(filename)
        self.current_label = np.squeeze(self.current_label)
        self.batch_idx = 0
        if self.shuffle:
            self.current_data, self.current_label, _ = shuffle_data(self.current_data, self.current_label)

    def _has_next_batch_in_file(self):
        return self.batch_idx * self.batch_size < self.current_data.shape[0]

    def num_channel(self):
        return 3

    def has_next_batch(self):
        # TODO: add backend thread to load data
        if (self.current_data is None) or (not self._has_next_batch_in_file()):
            if self.current_file_idx >= len(self.h5_files):
                return False
            self._load_data_file(self._get_data_filename())
            self.batch_idx = 0
            self.current_file_idx += 1
        return self._has_next_batch_in_file()

    def next_batch(self, augment=False):
        ''' returned dimension may be smaller than self.batch_size '''
        start_idx = self.batch_idx * self.batch_size
        end_idx = min((self.batch_idx + 1) * self.batch_size, self.current_data.shape[0])
        bsize = end_idx - start_idx
        batch_label = np.zeros((bsize), dtype=np.int32)
        data_batch = self.current_data[start_idx:end_idx, 0:self.npoints, :].copy()
        label_batch = self.current_label[start_idx:end_idx].copy()
        self.batch_idx += 1
        if augment: data_batch = self._augment_batch_data(data_batch)
        return data_batch, label_batch

    def calc_total_batch(self):
        counter = 0
        while self.has_next_batch():
            self.next_batch()
            counter += 1
        self.reset()
        return counter

    def total_batch(self):
        return self.total_batch_nb


if __name__ == '__main__':
    # the classes list
    classes = []

    with open('data/modelnet40_ply_hdf5_2048/shape_names.txt', 'r') as shapeName:
        for line in shapeName.readlines():
            classes.append(line.strip())

    d = ModelNetH5Dataset('data/modelnet40_ply_hdf5_2048/train_files.txt', batch_size=16, npoints=1024)
    print(d.total_batch())
    if d.has_next_batch():
        data, label = d.next_batch()
        print(data.shape)

