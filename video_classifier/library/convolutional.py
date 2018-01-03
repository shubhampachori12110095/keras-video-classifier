import numpy as np
from keras import Sequential
from keras.callbacks import ModelCheckpoint
from keras.layers import Conv2D, Activation, MaxPooling2D, Dropout, Flatten, Dense
from keras.utils import np_utils
from sklearn.model_selection import train_test_split

from video_classifier.utility.ucf.UCF101_extractor import scan_and_extract_videos_for_conv2d

BATCH_SIZE = 64
NUM_EPOCHS = 20


def generate_batch(x_samples, y_samples):
    num_batches = len(x_samples) // BATCH_SIZE

    while True:
        for batchIdx in range(0, num_batches):
            start = batchIdx * BATCH_SIZE
            end = (batchIdx + 1) * BATCH_SIZE
            yield np.array(x_samples[start:end]), y_samples[start:end]


class CnnVideoClassifier(object):
    model_name = 'vgg16-bidirectional-lstm'

    def __init__(self):
        self.img_width = None
        self.img_height = None
        self.img_channels = None
        self.nb_classes = None
        self.labels = None
        self.labels_idx2word = None
        self.model = None
        self.expected_frames = None
        self.config = None

    def create_model(self, input_shape, nb_classes):
        model = Sequential()
        model.add(Conv2D(filters=32, input_shape=input_shape, padding='same', kernel_size=(3, 3)))
        model.add(Activation('relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))

        model.add(Conv2D(filters=32, padding='same', kernel_size=(3, 3)))
        model.add(Activation('relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))

        model.add(Dropout(rate=0.25))

        model.add(Conv2D(filters=64, kernel_size=(3, 3), padding='same', input_shape=input_shape))
        model.add(Activation('relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))

        model.add(Conv2D(filters=64, padding='same', kernel_size=(3, 3)))
        model.add(Activation('relu'))
        model.add(MaxPooling2D(pool_size=(2, 2)))

        model.add(Dropout(rate=0.25))

        model.add(Flatten())
        model.add(Dense(units=512))
        model.add(Activation('relu'))
        model.add(Dropout(rate=0.5))
        model.add(Dense(units=nb_classes))
        model.add(Activation('softmax'))

        return model

    @staticmethod
    def get_config_file_path(model_dir_path):
        return model_dir_path + '/' + CnnVideoClassifier.model_name + '-config.npy'

    @staticmethod
    def get_weight_file_path(model_dir_path):
        return model_dir_path + '/' + CnnVideoClassifier.model_name + '-weights.h5'

    @staticmethod
    def get_architecture_file_path(model_dir_path):
        return model_dir_path + '/' + CnnVideoClassifier.model_name + '-architecture.json'

    def load_model(self, config_file_path, weight_file_path):

        config = np.load(config_file_path).item()
        self.img_width = config['img_width']
        self.img_height = config['img_height']
        self.img_channels = config['img_channels']
        self.nb_classes = config['nb_classes']
        self.labels = config['labels']
        self.expected_frames = config['expected_frames']
        self.labels_idx2word = dict([(idx, word) for word, idx in self.labels.items()])
        self.config = config

        self.model = self.create_model(
            input_shape=(self.img_width, self.img_height, self.img_channels * self.expected_frames),
            nb_classes=self.nb_classes)
        self.model.load_weights(weight_file_path)

    def predict(self, video_file_path):
        x = extract_vgg16_features_live(self.vgg16_model, video_file_path)
        frames = x.shape[0]
        if frames > self.expected_frames:
            x = x[0:self.expected_frames, :]
        elif frames < self.expected_frames:
            temp = np.zeros(shape=(self.expected_frames, x.shape[1]))
            temp[0:frames, :] = x
            x = temp
        predicted_class = np.argmax(self.model.predict(np.array([x]))[0])
        predicted_label = self.labels_idx2word[predicted_class]
        return predicted_label

    def fit(self, data_dir_path, model_dir_path, epochs=None, dataset_name=None, max_frames=None):
        if epochs is None:
            epochs = NUM_EPOCHS
        if max_frames is None:
            max_frames = 10
        if dataset_name is None:
            dataset_name = 'UCF-101'

        config_file_path = CnnVideoClassifier.get_config_file_path(model_dir_path)
        weight_file_path = CnnVideoClassifier.get_weight_file_path(model_dir_path)
        architecture_file_path = CnnVideoClassifier.get_architecture_file_path(model_dir_path)

        max_frames = 0
        self.labels = dict()
        x_samples, y_samples = scan_and_extract_videos_for_conv2d(data_dir_path,
                                                                  max_frames=max_frames,
                                                                  dataset_name=dataset_name)
        self.img_width, self.img_height, self.img_channels = x_samples[0].shape
        frames_list = []
        for x in x_samples:
            frames = x.shape[0]
            frames_list.append(frames)
            max_frames = max(frames, max_frames)
        self.expected_frames = int(np.mean(frames_list))
        print('max frames: ', max_frames)
        print('expected frames: ', self.expected_frames)
        for i in range(len(x_samples)):
            x = x_samples[i]
            frames = x.shape[0]
            if frames > self.expected_frames:
                x = x[0:self.expected_frames, :]
                x_samples[i] = x
            elif frames < self.expected_frames:
                temp = np.zeros(shape=(self.expected_frames, x.shape[1]))
                temp[0:frames, :] = x
                x_samples[i] = temp
        for y in y_samples:
            if y not in self.labels:
                self.labels[y] = len(self.labels)
        print(self.labels)
        for i in range(len(y_samples)):
            y_samples[i] = self.labels[y_samples[i]]

        self.nb_classes = len(self.labels)

        y_samples = np_utils.to_categorical(y_samples, self.nb_classes)

        config = dict()
        config['labels'] = self.labels
        config['nb_classes'] = self.nb_classes
        config['img_width'] = self.img_width
        config['img_height'] = self.img_height
        config['img_channels'] = self.img_channels
        config['expected_frames'] = self.expected_frames

        self.config = config

        np.save(config_file_path, config)

        model = self.create_model()
        open(architecture_file_path, 'w').write(model.to_json())

        Xtrain, Xtest, Ytrain, Ytest = train_test_split(x_samples, y_samples, test_size=0.3, random_state=42)

        train_gen = generate_batch(Xtrain, Ytrain)
        test_gen = generate_batch(Xtest, Ytest)

        train_num_batches = len(Xtrain) // BATCH_SIZE
        test_num_batches = len(Xtest) // BATCH_SIZE

        checkpoint = ModelCheckpoint(filepath=weight_file_path, save_best_only=True)
        history = model.fit_generator(generator=train_gen, steps_per_epoch=train_num_batches,
                                      epochs=epochs,
                                      verbose=1, validation_data=test_gen, validation_steps=test_num_batches,
                                      callbacks=[checkpoint])
        model.save_weights(weight_file_path)

        return history