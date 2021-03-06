import logging
import os
import pickle
from collections import defaultdict
import nltk
from nltk.corpus import stopwords
from sklearn import mixture, decomposition

from python.layouteagle import config

from nltk.corpus import wordnet as wn
import numpy as np

import spacy

from allennlp.modules.elmo import Elmo, batch_to_ids

from python.layouteagle.StandardConverter.Dict2Graph import Dict2Graph
from python.nlp.Topics.TextRank4Keywords import TextRank4Keyword


class TopicMaker:
    options_file = "https://s3-us-west-2.amazonaws.com/allennlp/models/elmo/2x1024_128_2048cnn_1xhighway/elmo_2x1024_128_2048cnn_1xhighway_options.json"
    weight_file = "https://s3-us-west-2.amazonaws.com/allennlp/models/elmo/2x1024_128_2048cnn_1xhighway/elmo_2x1024_128_2048cnn_1xhighway_weights.hdf5"

    def __init__(self, nouns_file_path=None):
        if not nouns_file_path:
            nouns_file_path = config.cache + "nouns.txt"
        if not os.path.isfile(nouns_file_path):
            logging.warning("NLTK Download")

            nltk.download('stopwords')
            nltk.download('punkt')
            nltk.download('wordnet')
            self.nouns = {x.name().split('.', 1)[0] for x in wn.all_synsets('n')}
            with open(nouns_file_path, 'w') as f:
                f.write("\n".join(self.nouns))
        else:
            with open(nouns_file_path, 'r') as f:
                self.nouns = [w.strip() for w in f.readlines()]

    def test(self):
        self.nlp = spacy.load("en_core_web_md")

        logging.warning("Reading texts")

        # with open("/home/stefan/PycharmProjects/LayoutEagle/test/corpus/faust.txt") as f:
        #    text = " ".join([l for l in f.readlines() ])
        with open("/home/stefan/PycharmProjects/LayoutEagle/python/test/corpus/faust.txt") as f:
            text = " ".join([l for l in f.readlines()])[5000:15000]

        doc = self.nlp(text)

        logging.warning("Tokenizing texts")

        def paragraphs(document):
            length = 50
            start = 0
            try:
                for token in document:
                    if token.is_space and token.text.count("\n") > 1:
                        yield document[start:token.i][:length]
                        start = token.i
                yield document[start:][:length]
            except IndexError:
                logging.error("accessing doc after end")

        def nps(d):
            for t in d:
                try:
                    yield t.text
                except IndexError as e:
                    logging.error("token not found")
                continue

        texts = list(map(lambda d: list(nps(d)), paragraphs(doc)))

        print(texts[:3])
        return texts, [{"text": text} for text in texts]

    def __call__(self, texts, meta, *args, **kwargs):
        self.nlp = spacy.load("en_core_web_md")
        self.elmo = Elmo(self.options_file, self.weight_file, 1, dropout=0)

        texts = list(texts)

        embeddings = self.embed(texts=texts)
        topics = self.topicize_recursively(embeddings, meta, texts)

        with open( config.topics_dump, 'wb') as f:
            pickle.dump(topics, f)
        return topics, meta

    def topicize_recursively(self, embeddings, meta, texts, split_size=10, max_level=3, level=0):
        print(f"Making Topics {level+1} of maximally {max_level+1}")
        labels = self.cluster(embeddings=embeddings)
        topic_ids_2_doc_ids = self.labels2docs(texts=texts, labels=labels)
        keywords = self.make_keywords(topic_2_docids=topic_ids_2_doc_ids, texts=texts, lookup=meta)
        topics = self.make_titles(keywords)


        if max_level == level:
            return topics

        for i_group_label, i_group in topic_ids_2_doc_ids.items():
            try:
                group_embeddings = embeddings[i_group]
                group_meta = [meta[i] for i in i_group]
                group_texts = [texts[i] for i in i_group]
                if len(i_group) > split_size:
                    sub_topics = self.topicize_recursively(
                        group_embeddings,
                        group_meta,
                        group_texts,
                        split_size,
                        max_level=max_level,
                        level=level + 1)
                    topics[list(topics)[i_group_label]] = sub_topics
            except TypeError as e:
                logging.error(f"computing gaussian mixture {e}")
                raise (e)
                return topics
            except IndexError as e:
                logging.error(f"computing subtopics with {e}")
                return topics
        return topics

    def embed(self, texts):
        logging.info("Topic modelling")

        logging.warning("- getting embeddings")

        character_ids = batch_to_ids(texts)

        def chunks(lst, n):
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        Xs = []
        chunks_ = list(chunks(character_ids, 30))

        for n, chunk in enumerate(chunks_):
            print(f" · {n + 1} of {len(chunks_)}")
            embeddings = self.elmo(chunk)
            X = embeddings['elmo_representations'][0].detach().numpy()
            X = X.reshape(X.shape[0], -1)

            Xs.append(X)

            del embeddings
            del X

        X = np.vstack(Xs)
        # print(X.shape)
        logging.warning("sizing embeddings")

        pca = decomposition.PCA(n_components=min(X.shape[0], 1000))
        pca.fit(X)
        X = pca.transform(X)

        logging.warning("- cluster embeddings")
        return X

    def cluster(self, embeddings):
        X = embeddings

        g = mixture.GaussianMixture(
            n_components=min(X.shape[0] // 2, 10),
            covariance_type="full",
            reg_covar=1e-1,
            n_init=20
        )

        g.fit(X)

        labels = g.predict(X)

        return labels

    def labels2docs(self, texts, labels):
        topic_2_docids = defaultdict(list)
        for i in range(len(texts)):
            topic_2_docids[labels[i]].append(i)

        # print(topic_2_docids)
        return topic_2_docids

    def make_keywords(self, topic_2_docids, texts, lookup=None):
        if not lookup:
            lookup = texts

        stop_words = stopwords.words()

        def stop_word_removal(x):
            tokens = x.split()

            return ' '.join([w for w in tokens
                             if (not w in stop_words)
                             and (w in self.nouns)])

        titled_clustered_documents = dict()
        for topic_id, text_ids in topic_2_docids.items():
            constructed_doc = " ".join([w.title() for id in text_ids for w in texts[id]]
                                       )
            #constructed_doc = remove_stopwords(stop_word_removal(constructed_doc.lower()))

            tr4w = TextRank4Keyword()
            tr4w.analyze(constructed_doc, candidate_pos=['NOUN', 'PROPN'], window_size=4, lower=False)
            keywords = tr4w.get_keywords(10)

            try:
                titled_clustered_documents[tuple(keywords) if keywords else ("no keywords",)] = \
                        [lookup[id] for id in text_ids]
            except:
                logging.error("ERROR")
        return titled_clustered_documents

    def numpy_fillna(self, data, fill_value=0):
        lens = np.array([len(i) for i in data])
        max_len = max(lens)

        out = []
        for i, d in enumerate(data):
            out.append(d + (max_len - lens[i]) * [fill_value])
        return np.array(out)

    def make_titles(self, keywords_to_texts):
        keyword_to_headwords = {keys: [kw[0] for kw in keys]
                 for keys, values in keywords_to_texts.items()}

        titles_to_texts = {" ".join(headwords[:4]): keywords_to_texts[keywords]
                           for keywords, headwords in keyword_to_headwords.items()}

        return titles_to_texts


if __name__ == "__main__":
    tm = TopicMaker()
    topics = tm(*tm.test())
    d2g = Dict2Graph
    print(list(d2g([topics]))[0][0][0])

