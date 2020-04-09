import logging
import os

import numpy
import pandas
import tensorflow as tf
import tensorflow_addons as tf_ad

from layouteagle.bi_lstm_crf_layout.model import LayoutModel
from layouteagle.helpers.list_tools import Lookup


class Bi_LSTM_CRF:
    def __init__(self, batch_size=84, hidden_num=150, lr=1e-3, embedding_size=8, epoch=160, output_dir="models/"):
        self.batch_size = batch_size
        self.hidden_num = hidden_num
        self.lr = lr
        self.embedding_size = embedding_size
        self.epoch = epoch
        self.output_dir = output_dir
        self.optimizer = tf.keras.optimizers.Adam(self.lr)

    def __call__(self, feature_path):
        os.system(f"rm -r {self.output_dir} & mkdir {self.output_dir}")
        self.prepare_from_pickle(feature_path)
        self.train()
        logging.info("finished")
        model_file_path = self.output_dir + 'model.ckpt'
        return model_file_path

    def prepare_from_pickle(self, feature_path):
        feature_df = pandas.read_pickle(feature_path)
        self.prepare(feature_df)

    def prepare(self, feature_df):

        # append padding features
        ml_data = pandas.DataFrame([[0] * len (feature_df.columns)], columns=feature_df.columns)
        self.PAD_FEATURE_INDEX = 0
        self.PAD_LABEL = "PAD"
        ml_data['column_labels'] = self.PAD_LABEL
        ml_data['page_number'] = -1
        ml_data['doc_id'] = 0
        feature_df = pandas.concat([ml_data, feature_df])

        feature_df.reset_index(drop=True, inplace=True)
        feature_df['index'] = feature_df.index

        in_page = feature_df[1:].groupby(["doc_id", "page_number"]).groups

        cols_to_use = ["x", "y", "len", "height",  "page_number", "font-size", "coarse_grained_pdf", "line-height"]

        # normalise
        for col in cols_to_use:
            feature_df[col] = feature_df[col] / max(feature_df[col])

        # zip token ids and labels
        content_ids, labels = list(zip(*[(
            pp,
            feature_df.iloc[list(pp)]['column_labels'].tolist()) for pp in in_page.values()]))

        # PAD Tokens
        content_ids = tf.keras.preprocessing.sequence.pad_sequences(content_ids, padding='post', value=self.PAD_FEATURE_INDEX)

        self.label_lookup = Lookup([ml_data['column_labels'].tolist()] + list(labels))
        labels = self.label_lookup(token_s=labels)
        labels = tf.keras.preprocessing.sequence.pad_sequences(
            labels,
            padding='post',
            value=self.label_lookup.token_to_id[self.PAD_LABEL])

        self.train_dataset = tf.data.Dataset.from_tensor_slices((content_ids, labels))
        self.train_dataset = self.train_dataset.shuffle(
            len(feature_df['index']) - len(ml_data), reshuffle_each_iteration=True).batch(self.batch_size, drop_remainder=True,
                                                           )
        logging.info("hidden_num:{}, vocab_size:{}, label_size:{}".format(self.hidden_num,
                                                                          len(feature_df['index']),
                                                                          len(feature_df['column_labels'].unique())))



        self.embedding_matrix = [feature_df.iloc[[sample for sample in samples]][cols_to_use] for samples in content_ids]

        int_to_one_hot  = ["reading_sequence", "page_number"]
        for col in cols_to_use:
            feature_df[col] = feature_df[col] / feature_df[col].max()


        self.model = LayoutModel(hidden_num=self.hidden_num,
                              data=feature_df,
                              cols_to_use=cols_to_use,
                              embedding_size=self.embedding_size,
                              pad_label=self.PAD_FEATURE_INDEX)

        ckpt = tf.train.Checkpoint(optimizer=self.optimizer, model=self.model)
        ckpt.restore(tf.train.latest_checkpoint(self.output_dir))
        self.ckpt_manager = tf.train.CheckpointManager(ckpt,
                                                       self.output_dir,
                                                       checkpoint_name='model.ckpt',
                                                       max_to_keep=3)

    # @tf.function
    def train_one_step(self, text_batch, labels_batch):
        with tf.GradientTape() as tape:
            logits, text_lens, log_likelihood = self.model(text_batch, labels_batch, training=True)
            loss = - tf.reduce_mean(log_likelihood)
        gradients = tape.gradient(loss, self.model.trainable_variables)
        self.optimizer.apply_gradients(zip(gradients, self.model.trainable_variables))
        return loss, logits, text_lens

    def get_acc_one_step(self, logits, text_lens, labels_batch):
        paths = []
        accuracy = 0
        accuracies = []
        for logit, text_len, labels in zip(logits, text_lens, labels_batch):
            viterbi_path, _ = tf_ad.text.viterbi_decode(logit, self.model.transition_params)
            paths.append(viterbi_path)

            # wee don't need to adapt correct padding values here, because they are equal anyway
            correct_prediction = tf.equal(
                tf.convert_to_tensor(tf.keras.preprocessing.sequence.pad_sequences([viterbi_path],
                                                                                   padding='post',
                                                                                   value=self.label_lookup.token_to_id[self.PAD_LABEL]),
                                     dtype=tf.int32),
                tf.convert_to_tensor(tf.keras.preprocessing.sequence.pad_sequences([labels],
                                                                                   padding='post',
                                                                                   value=self.label_lookup.token_to_id[self.PAD_LABEL]),
                                     dtype=tf.int32)
            )
            accuracies.append(tf.reduce_mean(tf.cast(correct_prediction, tf.float32)))
            # print(tf.reduce            # print(tf.reduce_mean(tf.cast(correct_prediction, tf.float32)))
        accuracy = sum(numpy.array(accuracies) / len(paths))
        return accuracy

    best_name = "bestmodel"
    def train(self):
        best_acc = 0
        step = 0
        best_loss = 10000


        for epoch in range(self.epoch):
            dataset = list(enumerate(self.train_dataset))
            for _, (text_batch, labels_batch) in dataset:

                step = step + 1
                loss, logits, text_lens = self.train_one_step(text_batch, labels_batch)

                accuracy = self.get_acc_one_step(logits, text_lens, labels_batch)
                logging.warning(f'epoch {epoch}, step {step}/{len(dataset)}, '
                                f'loss {loss} , accuracy {accuracy}')


                if accuracy > best_acc and accuracy > 0.5:
                    best_loss = loss
                    best_acc = accuracy

                    viterbi_path, _ = tf_ad.text.viterbi_decode(logits[0], self.model.transition_params)
                    prediction = viterbi_path

                    logging.warning(
                        f"\n{self.label_lookup.ids_to_tokens(prediction)} | \n{self.label_lookup.ids_to_tokens(labels_batch[0].numpy())}")

                    #self.ckpt_manager.save()

                    # save model
                    # for this, we have to do a dummy prediction, to set the real input shapes

                    #self.model.predict(text_batch[1:3])
                    tf.saved_model.save(self.model, self.output_dir + self.best_name)
                    logging.warning("Saved best model up to now")

    def predict(self, features):
        self.prepare(features)
        dataset = list(enumerate(self.train_dataset))
        for _, (text_batch, labels_batch) in dataset:
            logits, text_lens = self.model.predict(dataset)
            paths = []
            for logit, text_len in zip(logits, text_lens):
                viterbi_path, _ = tf_ad.text.viterbi_decode(logit[:text_len], model.transition_params)
                paths.append(viterbi_path)
            print(paths[0])
            print([self.label_lookup[id] for id in paths[0]])

    def load(self):
        self.model = tf.saved_model.load(
            self.output_dir + self.best_name, tags=None
        )